import functools
import logging
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from config import ADMIN_TELEGRAM_IDS
from services.player_pool import get_incomplete_or_unverified_players
from services.daily_generator import ensure_daily_buffer
from services.event_generator import maybe_generate_event
from services.firebase_service import get_current_event, ITALY_TZ


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


@admin_only
async def admin_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now_italy = datetime.now(ITALY_TZ)
    current_event = get_current_event()
    event_line = f"🎊 Evento attivo: {current_event.get('name')}" if current_event else "🎊 Nessun evento attivo"

    incomplete = get_incomplete_or_unverified_players()
    incomplete_line = f"⚠️ Giocatori esclusi dal pool automatico: {len(incomplete)}"

    text = (
        f"🛠️ <b>Stato bot</b> — {now_italy.strftime('%d/%m/%y %H:%M')} (Europe/Rome)\n\n"
        f"{event_line}\n"
        f"{incomplete_line}\n\n"
        "Comandi disponibili:\n"
        "/admin_status - questo riepilogo\n"
        "/admin_regen - forza la generazione del buffer di sfide/eventi mancanti\n"
        "/admin_review - elenco giocatori esclusi dalla selezione automatica"
    )
    await update.message.reply_text(text, parse_mode="HTML")


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

    days_text = "\n".join(f"- {d['date']}: {d['player_id']} ({d['difficulty']})" for d in generated_days) or "nessuna sfida mancante"
    event_text = f"nuovo evento creato: {event_code}" if event_code else "nessun nuovo evento (attivo o rotazione non pronta)"

    await update.message.reply_text(
        f"✅ Generazione completata.\n\n📅 Sfide generate:\n{days_text}\n\n🎊 Eventi: {event_text}"
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
    await update.message.reply_text(
        "⚠️ Giocatori esclusi dalla selezione automatica:\n\n" + "\n".join(lines) + extra
    )
