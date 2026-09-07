"""Dashboard locale per gestire il bot da PC, senza Telegram e senza hosting aggiuntivo.

Riusa esattamente gli stessi servizi (Firestore, dataset, generatori) usati da
handlers/admin_handler.py: nessuna logica duplicata, solo un'interfaccia diversa.
Va lanciata in locale con le stesse credenziali del bot (.env, firebase-key.json).

Uso: streamlit run admin_ui.py
"""
import asyncio
import os
from datetime import datetime
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

# Sotto lo script runner di Streamlit, la ricerca automatica di python-dotenv (che risale
# dal frame del chiamante) parte dalla cartella sbagliata e non trova l'.env: lo carichiamo
# esplicitamente da qui prima di importare config, cosi' FIREBASE_CREDENTIALS_PATH & co.
# risultano gia' in os.environ quando config.py fa il suo load_dotenv().
_PROJECT_ROOT = Path(__file__).resolve().parent
_ENV_PATH = _PROJECT_ROOT / ".env"
load_dotenv(_ENV_PATH)

st.set_page_config(page_title="Guess the Player — Admin", layout="wide")

if not os.getenv("FIREBASE_CREDENTIALS_PATH") or not os.getenv("BOT_TOKEN"):
    st.error(
        "Configurazione mancante: FIREBASE_CREDENTIALS_PATH e/o BOT_TOKEN non sono impostati.\n\n"
        f"File .env cercato in: `{_ENV_PATH}`\n"
        f"Esiste: **{_ENV_PATH.exists()}**\n\n"
        "Verifica che il file `.env` sia proprio in questa cartella (non in una sottocartella "
        "o nella cartella da cui lanci il comando) e che contenga le righe "
        "`FIREBASE_CREDENTIALS_PATH=...` e `BOT_TOKEN=...` senza virgolette."
    )
    st.stop()

credentials_path = Path(os.environ["FIREBASE_CREDENTIALS_PATH"])
if not credentials_path.is_absolute():
    credentials_path = _PROJECT_ROOT / credentials_path
if not credentials_path.exists():
    st.error(
        f"Il file delle credenziali Firebase non esiste: `{credentials_path}`\n\n"
        "Controlla il valore di FIREBASE_CREDENTIALS_PATH nel .env: se è un percorso "
        "relativo (es. `firebase-key.json`) deve essere relativo alla cartella del progetto."
    )
    st.stop()
# firebase_service legge FIREBASE_CREDENTIALS_PATH da config.py al momento dell'uso:
# qui lo normalizziamo ad assoluto cosi' funziona indipendentemente dalla cwd da cui parte streamlit.
os.environ["FIREBASE_CREDENTIALS_PATH"] = str(credentials_path)

from config import BOT_TOKEN, ADMIN_TELEGRAM_IDS
from services import firebase_service
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
from services.dates import ITALY_TZ, to_display

st.title("🛠️ Guess the Player — Pannello admin locale")

PAGES = [
    "Stato generale",
    "Statistiche utenti",
    "Dataset",
    "Sfide",
    "Eventi",
    "Giocatori bloccati",
    "Coppie padre/figlio",
]
page = st.sidebar.radio("Sezione", PAGES)


def error_box(exc):
    st.error(f"Errore: {exc}")


# ---------------------------------------------------------------------------
# Stato generale
# ---------------------------------------------------------------------------
if page == "Stato generale":
    if st.button("🔄 Aggiorna"):
        st.rerun()

    now_italy = datetime.now(ITALY_TZ)
    st.caption(f"{now_italy.strftime('%d/%m/%y %H:%M')} (Europe/Rome)")

    current_event = firebase_service.get_current_event()
    if current_event:
        st.success(f"🎊 Evento attivo: {current_event.get('name')}")
    else:
        st.info("🎊 Nessun evento attivo")

    incomplete = get_incomplete_or_unverified_players()
    col1, col2, col3 = st.columns(3)
    col1.metric("Giocatori esclusi dal pool", len(incomplete))

    try:
        report = build_report()
        col2.metric("Selezionabili / Totale", f"{report['selectable']}/{report['total']}")
        col3.metric("Autonomia senza ripetizioni", f"{report['autonomy_days']} giorni")
        if report["warnings"]:
            st.warning(f"🚨 {len(report['warnings'])} avvisi sul dataset — vedi sezione Dataset")
        else:
            st.success("✅ Dataset senza avvisi")
    except Exception as e:
        error_box(e)

    try:
        upcoming = firebase_service.get_upcoming_daily_paths(limit=5)
        st.write(f"📅 Sfide già in buffer su Firestore: **{len(upcoming)}**")
    except Exception as e:
        error_box(e)

# ---------------------------------------------------------------------------
# Statistiche utenti
# ---------------------------------------------------------------------------
elif page == "Statistiche utenti":
    try:
        overview = firebase_service.get_admin_overview()
        total = overview["users_total"] or 1
        guessed = overview["users_guessed_today"]
        col1, col2, col3 = st.columns(3)
        col1.metric("Utenti registrati", overview["users_total"])
        col2.metric("Con notifiche attive", overview["users_with_notifications"])
        col3.metric("Hanno indovinato oggi", f"{guessed} ({guessed * 100 // total}%)")
    except Exception as e:
        error_box(e)

# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------
elif page == "Dataset":
    try:
        blocked = firebase_service.get_blocked_player_ids()
    except Exception as e:
        blocked = []
        error_box(e)

    report = build_report(exclude_ids=blocked)

    col1, col2, col3 = st.columns(3)
    col1.metric("Totale", report["total"])
    col2.metric("Verificati", report["verified"])
    col3.metric("Selezionabili", report["selectable"])

    st.subheader("Per difficoltà")
    st.bar_chart(report["by_difficulty"])

    st.subheader("Eventi tematici")
    st.dataframe(
        [
            {
                "template": t["id"],
                "candidati": t["candidates"],
                "durata (giorni)": t["duration_days"],
                "stato": "manuale" if t["manual_only"] else ("ok" if t["ok"] else "POCHI CANDIDATI"),
            }
            for t in report["templates"]
        ],
        use_container_width=True,
        hide_index=True,
    )

    if report["warnings"]:
        st.subheader("⚠️ Avvisi")
        for w in report["warnings"]:
            st.warning(w)

    st.subheader("Giocatori esclusi dalla selezione automatica")
    incomplete = get_incomplete_or_unverified_players()
    if not incomplete:
        st.success("✅ Nessun giocatore da rivedere: dataset pulito.")
    else:
        st.dataframe(
            [
                {"id": item["id"], "nome": item["full_name"], "problemi": "; ".join(item["problems"])}
                for item in incomplete
            ],
            use_container_width=True,
            hide_index=True,
        )

# ---------------------------------------------------------------------------
# Sfide
# ---------------------------------------------------------------------------
elif page == "Sfide":
    limit = st.slider("Quante sfide mostrare", 1, 30, 7)
    try:
        upcoming = firebase_service.get_upcoming_daily_paths(limit=limit)
    except Exception as e:
        upcoming = []
        error_box(e)

    if not upcoming:
        st.info("📭 Nessuna sfida in buffer.")
    else:
        st.dataframe(
            [
                {
                    "giorno": to_display(doc.get("day")),
                    "soluzione": (doc.get("correct_answers") or ["?"])[-1],
                    "difficoltà": doc.get("difficulty"),
                }
                for doc in upcoming
            ],
            use_container_width=True,
            hide_index=True,
        )

    st.divider()
    if st.button("⏳ Genera subito sfide/eventi mancanti", type="primary"):
        with st.spinner("Generazione in corso..."):
            try:
                generated_days = ensure_daily_buffer()
                event_code = maybe_generate_event()
            except Exception as e:
                error_box(e)
            else:
                if generated_days:
                    st.success("✅ Sfide generate:")
                    for d in generated_days:
                        st.write(f"- {to_display(d['day'])}: {d['player_id']} ({d['difficulty']})")
                else:
                    st.info("Nessuna sfida mancante.")
                st.info(f"Eventi: {'nuovo evento creato: ' + event_code if event_code else 'nessun nuovo evento'}")

# ---------------------------------------------------------------------------
# Eventi
# ---------------------------------------------------------------------------
elif page == "Eventi":
    st.subheader("Ultimi eventi")
    limit = st.slider("Quanti mostrare", 1, 20, 5)
    try:
        events = firebase_service.get_recent_events(limit=limit)
    except Exception as e:
        events = []
        error_box(e)

    if not events:
        st.info("📭 Nessun evento presente.")
    else:
        for event in events:
            dates = event.get("dates", [])
            period = f"{to_display(dates[0])} → {to_display(dates[-1])}" if dates else "date non disponibili"
            st.write(
                f"**{event.get('name')}** [{event.get('code')}] — {period} — "
                f"tipo {event.get('type')} — origine {event.get('source', 'auto')} — "
                f"{event.get('participants_count', 0)} partecipanti"
            )

    st.divider()
    st.subheader("Crea evento manuale")
    templates = load_templates()
    template_id = st.selectbox("Template", [t["id"] for t in templates])
    col1, col2 = st.columns(2)
    start_text = col1.text_input("Data inizio (gg/mm/aa, vuoto = oggi)")
    duration = col2.number_input("Durata (giorni, 0 = default template)", min_value=0, value=0)

    if st.button("✅ Crea evento", type="primary"):
        try:
            start_date = parse_start_date(start_text or None)
            summary = create_manual_event(
                template_id, start_date=start_date, duration_days=duration or None
            )
        except ManualEventError as e:
            st.error(str(e))
        except Exception as e:
            error_box(e)
        else:
            st.success(
                f"Evento creato: **{summary['name']}** [{summary['code']}] — "
                f"{summary['days']} giorni ({summary['dates'][0]} → {summary['dates'][-1]}) — "
                f"trofei il {summary['trophy_day']}"
            )

# ---------------------------------------------------------------------------
# Giocatori bloccati
# ---------------------------------------------------------------------------
elif page == "Giocatori bloccati":
    try:
        blocked = firebase_service.get_blocked_player_ids()
    except Exception as e:
        blocked = []
        error_box(e)

    st.subheader("Sospesi dalla selezione automatica")
    if not blocked:
        st.success("✅ Nessun giocatore sospeso.")
    else:
        for player_id in blocked:
            col1, col2 = st.columns([4, 1])
            col1.write(f"`{player_id}`")
            if col2.button("Riammetti", key=f"unblock_{player_id}"):
                firebase_service.unblock_player_id(player_id)
                st.rerun()

    st.divider()
    st.subheader("Sospendi un giocatore")
    new_id = st.text_input("Player id (come in data/players.json)")
    if st.button("🚫 Sospendi"):
        pid = new_id.strip().lower()
        if not pid:
            st.warning("Inserisci un id.")
        elif not get_player_by_id(pid):
            st.error(f"Nessun giocatore con id '{pid}' nel dataset.")
        else:
            try:
                firebase_service.block_player_id(pid)
            except Exception as e:
                error_box(e)
            else:
                st.success(f"'{pid}' sospeso.")
                st.rerun()

# ---------------------------------------------------------------------------
# Coppie padre/figlio
# ---------------------------------------------------------------------------
elif page == "Coppie padre/figlio":
    try:
        pairs = firebase_service.list_father_son_pairs()
    except Exception as e:
        pairs = []
        error_box(e)

    st.subheader("Coppie salvate")
    if not pairs:
        st.info("📭 Nessuna coppia padre/figlio salvata.")
    else:
        for pair in pairs:
            used = ", ".join(pair.get("used_in_events", [])) or "mai usata"
            col1, col2 = st.columns([5, 1])
            col1.write(f"`{pair['id']}` — {', '.join(pair.get('answers', []))} ({used})")
            if col2.button("Elimina", key=f"del_{pair['id']}"):
                firebase_service.delete_father_son_pair(pair["id"])
                st.rerun()

    st.divider()
    st.subheader("Aggiungi coppia")
    st.caption(
        "La foto viene inviata al bot (serve un ADMIN_TELEGRAM_IDS già avviato in chat con il bot) "
        "per ottenere il file_id da Telegram: nessuna copia dell'immagine viene salvata altrove."
    )
    photo = st.file_uploader("Foto della coppia", type=["jpg", "jpeg", "png"])
    answers_text = st.text_input("Risposte accettate (separate da virgola)", placeholder="Maldini, Paolo e Cesare Maldini")
    admin_chat_id = st.number_input(
        "Chat id admin a cui inviare la foto",
        value=ADMIN_TELEGRAM_IDS[0] if ADMIN_TELEGRAM_IDS else 0,
        step=1,
    )

    if st.button("➕ Salva coppia", type="primary"):
        answers = parse_answers(answers_text)
        if not photo:
            st.error("Serve una foto.")
        elif not answers:
            st.error("Servono le risposte accettate.")
        elif not admin_chat_id:
            st.error("Serve una chat id admin valida.")
        else:
            try:
                from telegram import Bot

                async def _send():
                    bot = Bot(token=BOT_TOKEN)
                    return await bot.send_photo(chat_id=int(admin_chat_id), photo=photo.getvalue())

                message = asyncio.run(_send())
                file_id = message.photo[-1].file_id
                pair_id = firebase_service.add_father_son_pair(
                    {"file_id": file_id, "answers": answers, "added_by": "admin_ui"}
                )
            except Exception as e:
                error_box(e)
            else:
                st.success(f"Coppia salvata (id `{pair_id}`). Risposte: {', '.join(answers)}")
                st.rerun()
