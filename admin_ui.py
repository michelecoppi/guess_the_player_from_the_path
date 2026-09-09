"""Dashboard locale per gestire il bot da PC, senza Telegram e senza hosting aggiuntivo.

Riusa esattamente gli stessi servizi (Firestore, dataset, generatori) usati da
handlers/admin_handler.py: nessuna logica duplicata, solo un'interfaccia diversa. Le
modifiche ai documenti passano da services/content_admin.py, che applica le regole del
gioco (anti-ripetizione, coerenza fra date e contenuti, bonus gia' assegnati) invece di
scrivere campi a caso.

Va lanciata in locale con le stesse credenziali del bot (.env, firebase-key.json).

Uso: streamlit run admin_ui.py
"""
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

from admin_pages import blocked, challenges, dataset, events, father_son, leagues, overview, users
from admin_pages.shared import CACHE_TTL_SECONDS, ITALY_TZ, firebase_service, render_flash, today_iso

# ---------------------------------------------------------------------------
# Intestazione e navigazione
# ---------------------------------------------------------------------------

st.title("🛠️ Guess the Player — Pannello admin locale")

today = today_iso()
now_italy = datetime.now(ITALY_TZ)

PAGES = [
    "📊 Stato generale",
    "📅 Sfide giornaliere",
    "🎊 Eventi",
    "👤 Utenti",
    "🏆 Leghe",
    "📚 Dataset",
    "🚫 Giocatori sospesi",
    "👨‍👦 Coppie padre/figlio",
]
page = st.sidebar.radio("Sezione", PAGES)

st.sidebar.divider()
if st.sidebar.button("🔄 Ricarica dati", width="stretch"):
    st.cache_data.clear()
    st.rerun()
try:
    project_id = firebase_service.db.project
except Exception:  # noqa: BLE001 - il nome del progetto è solo informativo
    project_id = "?"
st.sidebar.caption(
    f"Progetto Firestore: `{project_id}`\n\n"
    f"{now_italy.strftime('%d/%m/%y %H:%M')} (Europe/Rome)\n\n"
    f"Le letture sono in cache per {CACHE_TTL_SECONDS}s."
)
st.sidebar.caption("⚠️ Le modifiche scrivono sul database **di produzione**.")

render_flash()


# ---------------------------------------------------------------------------
# Stato generale
# ---------------------------------------------------------------------------
RENDERERS = {
    '📊 Stato generale': overview.render,
    '📅 Sfide giornaliere': challenges.render,
    '🎊 Eventi': events.render,
    '👤 Utenti': users.render,
    '🏆 Leghe': leagues.render,
    '📚 Dataset': dataset.render,
    '🚫 Giocatori sospesi': blocked.render,
    '👨\u200d👦 Coppie padre/figlio': father_son.render,
}
RENDERERS[page](today, now_italy)
