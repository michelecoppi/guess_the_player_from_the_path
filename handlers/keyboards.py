"""Tastiera del menu e menu comandi di Telegram.

Prima l'unico modo di sapere cosa sapeva fare il bot era leggere il muro di testo di
`/help` e ricopiare i comandi a mano. Qui ci sono le due cose che lo evitano:

- `menu_keyboard()`: la tastiera inline che accompagna /start, /menu e /help. I bottoni
  richiamano gli stessi handler dei comandi, quindi non esiste una seconda versione della
  logica da tenere allineata;
- `bot_commands()`: la lista per `set_my_commands`, cioe' il menu "/" che Telegram mostra
  accanto alla casella di scrittura, tradotto per lingua.
"""
from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo

from config import WEBAPP_URL
from services.firebase_service import get_user_data
from services.i18n import resolve_language, t

CALLBACK_PREFIX = "menu_"

# Comando -> chiave della descrizione mostrata nel menu "/" di Telegram.
#
# I nomi sono in **inglese**, anche nel menu italiano: la descrizione accanto e' tradotta,
# il comando no. Un bot che parla tre lingue con tre serie di comandi diversi obbligherebbe
# a scriverne una versione per lingua in ogni messaggio ("torna a oggi con /oggi" per un
# italiano, "con /today" per un inglese), e chi cambia lingua si ritroverebbe i comandi che
# ha imparato a non funzionare piu'.
#
# Gli alias italiani restano registrati in bot.py (/archivio, /oggi, /lega...): chi li ha
# imparati continua a usarli, semplicemente non sono piu' quelli che il bot suggerisce.
COMMAND_KEYS = (
    ("start", "cmd.start"),
    ("show", "cmd.show"),
    ("stats", "cmd.stats"),
    ("top", "cmd.top"),
    ("events", "cmd.events"),
    ("archive", "cmd.archive"),
    ("training", "cmd.training"),
    ("league", "cmd.league"),
    ("notify", "cmd.notify"),
    ("language", "cmd.language"),
    ("help", "cmd.help"),
)


def language_for(update: Update):
    user = update.effective_user
    user_data = get_user_data(user.id)
    if user_data and user_data.get("language"):
        return user_data["language"]
    return resolve_language(getattr(user, "language_code", None))


def _button(lang, key, action):
    return InlineKeyboardButton(t(lang, key), callback_data=f"{CALLBACK_PREFIX}{action}")


def menu_keyboard(lang):
    rows = [
        [_button(lang, "menu.play", "play"), _button(lang, "menu.events", "events")],
        [_button(lang, "menu.stats", "stats"), _button(lang, "menu.top", "top")],
        [_button(lang, "menu.archive", "archive"), _button(lang, "menu.training", "training")],
        [_button(lang, "menu.leagues", "leagues"), _button(lang, "menu.notify", "notify")],
        [_button(lang, "menu.language", "language"), _button(lang, "menu.help", "help")],
    ]
    if WEBAPP_URL:
        # La mini app e' un di piu': se non e' configurata il menu resta identico a prima.
        rows.insert(0, [InlineKeyboardButton(t(lang, "menu.app"), web_app=WebAppInfo(url=WEBAPP_URL))])
    return InlineKeyboardMarkup(rows)


def bot_commands(lang):
    return [BotCommand(command, t(lang, key)) for command, key in COMMAND_KEYS]


