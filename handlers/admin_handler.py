"""Comandi di amministrazione via Telegram.

Il bot non ha (e non vuole avere) una dashboard web: tutto quello che serve a gestirlo -
stato del dataset, contenuti gia' generati, statistiche utenti, creazione manuale degli
eventi che non si possono generare in automatico - passa da qui, riservato agli ID elencati
in ADMIN_TELEGRAM_IDS.
"""
import functools
import logging
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from config import ADMIN_TELEGRAM_IDS
from services.player_pool import get_incomplete_or_unverified_players, get_player_by_id
from services.daily_generator import ensure_daily_buffer
from services.event_generator import maybe_generate_event, load_templates
from services.dataset_health import build_report
from services.manual_event_service import (
    ManualEventError,
    create_manual_event,
    parse_answers,
    parse_start_date,
)
from services import firebase_service
from services.dates import ITALY_TZ, to_display
from services.firebase_service import get_current_event

TELEGRAM_MAX_MESSAGE = 3900

ADMIN_COMMANDS = [
    ("/admin_help", "questo elenco"),
    ("/admin_status", "riepilogo: evento attivo, dataset, contenuti generati"),
    ("/admin_stats", "numeri sugli utenti (iscritti, notifiche, chi ha giocato oggi)"),
    ("/admin_pool", "salute del dataset: autonomia, difficolta', eventi senza candidati"),
    ("/admin_review", "giocatori esclusi dalla selezione automatica e perche'"),
    ("/admin_next [n]", "le prossime sfide gia' generate (mostra le soluzioni)"),
    ("/admin_events [n]", "ultimi eventi generati"),
    ("/admin_regen", "genera subito le sfide/eventi mancanti"),
    ("/admin_block <id>", "sospende un giocatore dalla selezione automatica"),
    ("/admin_unblock <id>", "riammette un giocatore sospeso"),
    ("/admin_blocked", "elenco dei giocatori sospesi"),
    ("/admin_fs_add <risposte>", "salva una coppia padre/figlio (in didascalia a una foto)"),
    ("/admin_fs_list", "coppie padre/figlio salvate"),
    ("/admin_fs_del <id>", "elimina una coppia padre/figlio"),
    ("/admin_event_create <template> [gg/mm/aa] [giorni]", "crea a mano un evento"),
]


def admin_only(handler):
    @functools.wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id if update.effective_user else None
        if user_id not in ADMIN_TELEGRAM_IDS:
            await update.message.reply_text("⛔ Comando riservato agli amministratori.")
            logging.warning(f"[ADMIN] Tentativo di accesso non autorizzato da {user_id} a /{update.message.text}")
            return
        await handler(update, context)
    return wrapper


async def _reply(update, text, parse_mode=None):
    """Telegram rifiuta i messaggi oltre ~4096 caratteri: gli elenchi lunghi vanno spezzati."""
    while text:
        chunk = text[:TELEGRAM_MAX_MESSAGE]
        if len(text) > TELEGRAM_MAX_MESSAGE:
            cut = chunk.rfind("\n")
            if cut > 0:
                chunk = chunk[:cut]
        await update.message.reply_text(chunk, parse_mode=parse_mode)
        text = text[len(chunk):].lstrip("\n")


def _int_arg(context, index=0, default=None):
    args = getattr(context, "args", None) or []
    if len(args) > index and args[index].isdigit():
        return int(args[index])
    return default


@admin_only
async def admin_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lines = ["🛠️ <b>Comandi amministrativi</b>\n"]
    lines += [f"<code>{command}</code> — {description}" for command, description in ADMIN_COMMANDS]
    await _reply(update, "\n".join(lines), parse_mode="HTML")


@admin_only
async def admin_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now_italy = datetime.now(ITALY_TZ)
    current_event = get_current_event()
    event_line = f"🎊 Evento attivo: {current_event.get('name')}" if current_event else "🎊 Nessun evento attivo"

    incomplete = get_incomplete_or_unverified_players()
    incomplete_line = f"⚠️ Giocatori esclusi dal pool automatico: {len(incomplete)}"

    try:
        report = build_report()
        pool_line = (
            f"📚 Dataset: {report['selectable']}/{report['total']} selezionabili "
            f"({report['autonomy_days']} giorni senza ripetizioni)"
        )
        warnings_line = f"🚨 Avvisi sul dataset: {len(report['warnings'])} (/admin_pool)" if report["warnings"] else "✅ Dataset senza avvisi"
    except Exception as e:
        logging.exception("Errore nel report dataset")
        pool_line = f"📚 Dataset: errore nel calcolo ({e})"
        warnings_line = ""

    try:
        upcoming = firebase_service.get_upcoming_daily_paths(limit=5)
        buffer_line = f"📅 Sfide gia' in buffer su Firestore: {len(upcoming)}"
    except Exception as e:
        logging.exception("Errore nella lettura del buffer sfide")
        buffer_line = f"📅 Buffer sfide: errore di lettura ({e})"

    text = (
        f"🛠️ <b>Stato bot</b> — {now_italy.strftime('%d/%m/%y %H:%M')} (Europe/Rome)\n\n"
        f"{event_line}\n"
        f"{pool_line}\n"
        f"{incomplete_line}\n"
        f"{buffer_line}\n"
        f"{warnings_line}\n\n"
        "Elenco completo dei comandi: /admin_help"
    )
    await _reply(update, text, parse_mode="HTML")


@admin_only
async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        overview = firebase_service.get_admin_overview()
    except Exception as e:
        logging.exception("Errore in /admin_stats")
        await update.message.reply_text(f"❌ Errore nella lettura delle statistiche: {e}")
        return

    total = overview["users_total"] or 1
    guessed = overview["users_guessed_today"]
    text = (
        "📊 <b>Utenti</b>\n\n"
        f"👥 Registrati: <b>{overview['users_total']}</b>\n"
        f"🔔 Con notifiche attive: <b>{overview['users_with_notifications']}</b>\n"
        f"🎯 Hanno indovinato oggi: <b>{guessed}</b> ({guessed * 100 // total}%)"
    )
    await _reply(update, text, parse_mode="HTML")


@admin_only
async def admin_pool(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        blocked = firebase_service.get_blocked_player_ids()
    except Exception:
        logging.exception("Errore nella lettura dei giocatori sospesi")
        blocked = []

    report = build_report(exclude_ids=blocked)

    lines = [
        "📚 <b>Salute del dataset</b>\n",
        f"Totale: <b>{report['total']}</b> — verificati: <b>{report['verified']}</b> — "
        f"selezionabili: <b>{report['selectable']}</b>",
        f"Autonomia senza ripetizioni: <b>{report['autonomy_days']} giorni</b> "
        f"(anti-ripetizione: {report['history_days_no_repeat']} giorni)",
        f"Sospesi a mano: <b>{len(blocked)}</b>",
        "",
        "<b>Per difficolta'</b>",
    ]
    for level, count in report["by_difficulty"].items():
        lines.append(f"• {level}: {count}")

    problem_templates = [t for t in report["templates"] if not t["ok"]]
    lines.append("")
    if problem_templates:
        lines.append("<b>Eventi con pochi candidati</b>")
        for template in problem_templates:
            lines.append(f"• {template['id']}: {template['candidates']} per {template['duration_days']} giorni")
    else:
        lines.append("✅ Tutti gli eventi automatici hanno abbastanza candidati")

    if report["warnings"]:
        lines.append("")
        lines.append("<b>Avvisi</b>")
        lines += [f"• {warning}" for warning in report["warnings"]]

    await _reply(update, "\n".join(lines), parse_mode="HTML")


@admin_only
async def admin_regen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Rigenerazione in corso...")
    try:
        generated_days = ensure_daily_buffer()
        event_code = maybe_generate_event()
    except Exception as e:
        logging.exception("Errore durante /admin_regen")
        await update.message.reply_text(f"❌ Errore durante la generazione: {e}")
        return

    days_text = "\n".join(f"- {to_display(d['day'])}: {d['player_id']} ({d['difficulty']})" for d in generated_days) or "nessuna sfida mancante"
    event_text = f"nuovo evento creato: {event_code}" if event_code else "nessun nuovo evento (attivo o rotazione non pronta)"

    await _reply(
        update,
        f"✅ Generazione completata.\n\n📅 Sfide generate:\n{days_text}\n\n🎊 Eventi: {event_text}",
    )


@admin_only
async def admin_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    incomplete = get_incomplete_or_unverified_players()
    if not incomplete:
        await update.message.reply_text("✅ Nessun giocatore da rivedere: dataset pulito.")
        return

    lines = []
    for item in incomplete[:20]:
        problems = "; ".join(item["problems"])
        lines.append(f"• {item['full_name']} ({item['id']}): {problems}")

    extra = f"\n… e altri {len(incomplete) - 20}" if len(incomplete) > 20 else ""
    await _reply(
        update,
        "⚠️ Giocatori esclusi dalla selezione automatica:\n\n" + "\n".join(lines) + extra,
    )


@admin_only
async def admin_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    limit = _int_arg(context, 0, default=7)
    try:
        upcoming = firebase_service.get_upcoming_daily_paths(limit=limit)
    except Exception as e:
        logging.exception("Errore in /admin_next")
        await update.message.reply_text(f"❌ Errore nella lettura delle sfide: {e}")
        return

    if not upcoming:
        await update.message.reply_text("📭 Nessuna sfida in buffer. Usa /admin_regen per generarle.")
        return

    lines = ["📅 <b>Sfide generate</b> (contengono le soluzioni!)\n"]
    for doc in upcoming:
        answers = doc.get("correct_answers", [])
        solution = answers[-1] if answers else "?"
        lines.append(f"• {to_display(doc.get('day'))} — {solution} ({doc.get('difficulty')})")

    await _reply(update, "\n".join(lines), parse_mode="HTML")


@admin_only
async def admin_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    limit = _int_arg(context, 0, default=5)
    try:
        events = firebase_service.get_recent_events(limit=limit)
    except Exception as e:
        logging.exception("Errore in /admin_events")
        await update.message.reply_text(f"❌ Errore nella lettura degli eventi: {e}")
        return

    if not events:
        await update.message.reply_text("📭 Nessun evento presente.")
        return

    lines = ["🎊 <b>Ultimi eventi</b>\n"]
    for event in events:
        dates = event.get("dates", [])
        period = f"{to_display(dates[0])} → {to_display(dates[-1])}" if dates else "date non disponibili"
        participants = event.get("participants_count", 0)
        lines.append(
            f"• <b>{event.get('name')}</b> [{event.get('code')}]\n"
            f"  {period} — tipo {event.get('type')} — origine {event.get('source', 'auto')} — "
            f"{participants} partecipanti"
        )

    await _reply(update, "\n".join(lines), parse_mode="HTML")


@admin_only
async def admin_block(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = getattr(context, "args", None) or []
    if not args:
        await update.message.reply_text("Uso: /admin_block <player_id> (l'id come in data/players.json)")
        return

    player_id = args[0].strip().lower()
    if not get_player_by_id(player_id):
        await update.message.reply_text(f"❗ Nessun giocatore con id '{player_id}' nel dataset.")
        return

    try:
        firebase_service.block_player_id(player_id)
    except Exception as e:
        logging.exception("Errore in /admin_block")
        await update.message.reply_text(f"❌ Errore: {e}")
        return

    await update.message.reply_text(
        f"🚫 '{player_id}' sospeso: non verra' piu' scelto per le sfide generate d'ora in poi.\n"
        "Le sfide gia' in buffer non cambiano (usa /admin_next per controllarle)."
    )


@admin_only
async def admin_unblock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = getattr(context, "args", None) or []
    if not args:
        await update.message.reply_text("Uso: /admin_unblock <player_id>")
        return

    player_id = args[0].strip().lower()
    try:
        firebase_service.unblock_player_id(player_id)
    except Exception as e:
        logging.exception("Errore in /admin_unblock")
        await update.message.reply_text(f"❌ Errore: {e}")
        return

    await update.message.reply_text(f"✅ '{player_id}' di nuovo selezionabile.")


@admin_only
async def admin_blocked(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        blocked = firebase_service.get_blocked_player_ids()
    except Exception as e:
        logging.exception("Errore in /admin_blocked")
        await update.message.reply_text(f"❌ Errore: {e}")
        return

    if not blocked:
        await update.message.reply_text("✅ Nessun giocatore sospeso.")
        return

    await _reply(update, "🚫 Giocatori sospesi:\n" + "\n".join(f"• {player_id}" for player_id in blocked))


# ---------------------------------------------------------------------------
# Eventi manuali: coppie padre/figlio
# ---------------------------------------------------------------------------

FS_ADD_USAGE = (
    "Uso: manda la <b>foto</b> della coppia con didascalia\n"
    "<code>/admin_fs_add Maldini, Paolo e Cesare Maldini</code>\n"
    "(le risposte accettate vanno separate da virgola)\n\n"
    "In alternativa rispondi a una foto gia' inviata con lo stesso comando."
)


def _extract_photo_and_answers(update: Update):
    """Il comando puo' arrivare come didascalia della foto oppure come risposta a una foto:
    in entrambi i casi servono il file_id della foto piu' grande e le risposte accettate."""
    message = update.message
    source_message = message if message.photo else (message.reply_to_message if message.reply_to_message else None)
    photo = source_message.photo if source_message and source_message.photo else None

    raw_text = message.caption if message.caption else (message.text or "")
    # toglie il comando iniziale, con o senza @nomebot
    _, _, remainder = raw_text.partition(" ")

    file_id = photo[-1].file_id if photo else None
    return file_id, parse_answers(remainder)


@admin_only
async def admin_fs_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file_id, answers = _extract_photo_and_answers(update)

    if not file_id:
        await update.message.reply_text("❗ Serve una foto.\n\n" + FS_ADD_USAGE, parse_mode="HTML")
        return
    if not answers:
        await update.message.reply_text("❗ Servono le risposte accettate.\n\n" + FS_ADD_USAGE, parse_mode="HTML")
        return

    try:
        pair_id = firebase_service.add_father_son_pair({
            "file_id": file_id,
            "answers": answers,
            "added_by": update.effective_user.id,
        })
    except Exception as e:
        logging.exception("Errore in /admin_fs_add")
        await update.message.reply_text(f"❌ Errore nel salvataggio: {e}")
        return

    await update.message.reply_text(
        f"✅ Coppia salvata (id <code>{pair_id}</code>).\n"
        f"Risposte accettate: {', '.join(answers)}\n\n"
        "Quando hai abbastanza coppie: /admin_event_create coppie_leggendarie",
        parse_mode="HTML",
    )


@admin_only
async def admin_fs_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        pairs = firebase_service.list_father_son_pairs()
    except Exception as e:
        logging.exception("Errore in /admin_fs_list")
        await update.message.reply_text(f"❌ Errore: {e}")
        return

    if not pairs:
        await update.message.reply_text("📭 Nessuna coppia padre/figlio salvata.\n\n" + FS_ADD_USAGE, parse_mode="HTML")
        return

    lines = ["👨‍👦 <b>Coppie padre/figlio</b>\n"]
    for pair in pairs:
        used = ", ".join(pair.get("used_in_events", [])) or "mai usata"
        lines.append(f"• <code>{pair['id']}</code> — {', '.join(pair.get('answers', []))} ({used})")

    await _reply(update, "\n".join(lines), parse_mode="HTML")


@admin_only
async def admin_fs_del(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = getattr(context, "args", None) or []
    if not args:
        await update.message.reply_text("Uso: /admin_fs_del <id> (l'id lo trovi con /admin_fs_list)")
        return

    try:
        deleted = firebase_service.delete_father_son_pair(args[0].strip())
    except Exception as e:
        logging.exception("Errore in /admin_fs_del")
        await update.message.reply_text(f"❌ Errore: {e}")
        return

    if not deleted:
        await update.message.reply_text(f"❗ Nessuna coppia con id '{args[0].strip()}'.")
        return
    await update.message.reply_text("🗑️ Coppia eliminata.")


@admin_only
async def admin_event_create(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = getattr(context, "args", None) or []
    if not args:
        template_ids = ", ".join(t["id"] for t in load_templates())
        await update.message.reply_text(
            "Uso: /admin_event_create &lt;template&gt; [gg/mm/aa] [giorni]\n\n"
            f"Template disponibili: {template_ids}",
            parse_mode="HTML",
        )
        return

    template_id = args[0].strip()
    start_text = args[1] if len(args) > 1 else None
    duration = int(args[2]) if len(args) > 2 and args[2].isdigit() else None

    try:
        start_date = parse_start_date(start_text)
        summary = create_manual_event(template_id, start_date=start_date, duration_days=duration)
    except ManualEventError as e:
        await update.message.reply_text(f"❗ {e}")
        return
    except Exception as e:
        logging.exception("Errore in /admin_event_create")
        await update.message.reply_text(f"❌ Errore nella creazione dell'evento: {e}")
        return

    await update.message.reply_text(
        f"✅ Evento creato: <b>{summary['name']}</b>\n"
        f"Codice: <code>{summary['code']}</code>\n"
        f"Tipo: {summary['type']}\n"
        f"Durata: {summary['days']} giorni ({summary['dates'][0]} → {summary['dates'][-1]})\n"
        f"Trofei assegnati il {summary['trophy_day']}",
        parse_mode="HTML",
    )
