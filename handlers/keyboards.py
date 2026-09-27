"""Tastiera del menu e menu comandi di Telegram.

Prima l'unico modo di sapere cosa sapeva fare il bot era leggere il muro di testo di
`/help` e ricopiare i comandi a mano. Qui ci sono le due cose che lo evitano:

- `menu_keyboard()`: la tastiera inline che accompagna /start. I bottoni richiamano gli
  stessi handler che un tempo erano comandi, quindi non esiste una seconda versione della
  logica da tenere allineata. Non e' piu' un comando Telegram: /menu e' stato rimosso, e
  /help non la manda piu' (spiega il gioco e apre la mini app, niente sotto-menu);
- `bot_commands()`: la lista per `set_my_commands`, cioe' il menu "/" che Telegram mostra
  accanto alla casella di scrittura, tradotto per lingua. Elenca solo i punti di ingresso
  rimasti come comandi veri (start/help/notify/language/forgetme/paysupport); tutto il
  resto (gioca, soluzione, statistiche, eventi, archivio, allenamento, leghe, negozio,
  leggenda) si raggiunge solo dai bottoni della tastiera inline.
"""
from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo

from config import PUBLIC_BASE_URL, WEBAPP_URL
from services.firebase_service import get_user_data
from services.i18n import resolve_language, t

CALLBACK_PREFIX = "menu_"

# Comando -> chiave della descrizione mostrata nel menu "/" di Telegram.
#
# I nomi sono in **inglese**, anche nel menu italiano: la descrizione accanto e' tradotta,
# il comando no.
#
# Questo e' l'elenco completo dei comandi rimasti: tutto il resto del gioco (gioca,
# soluzione, statistiche, top, eventi, archivio, allenamento, leghe, negozio, leggenda) non
# e' piu' un comando Telegram, si raggiunge solo dai bottoni di `menu_keyboard()`.
COMMAND_KEYS = (
    ("start", "cmd.start"),
    ("help", "cmd.help"),
    ("notify", "cmd.notify"),
    ("language", "cmd.language"),
    ("forgetme", "cmd.forgetme"),
    ("paysupport", "cmd.paysupport"),
)


def language_for(update: Update):
    user = update.effective_user
    user_data = get_user_data(user.id)
    if user_data and user_data.get("language"):
        return user_data["language"]
    return resolve_language(getattr(user, "language_code", None))


def _button(lang, key, action):
    return InlineKeyboardButton(t(lang, key), callback_data=f"{CALLBACK_PREFIX}{action}")


def legal_buttons(lang):
    if not PUBLIC_BASE_URL:
        return []
    base = PUBLIC_BASE_URL.rstrip("/")
    return [
        InlineKeyboardButton(t(lang, "shop.privacy_button"), url=f"{base}/privacy?lang={lang}"),
        InlineKeyboardButton(t(lang, "shop.refunds_button"), url=f"{base}/terms?lang={lang}#refunds"),
    ]


def app_keyboard(lang):
    if not WEBAPP_URL:
        return None
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "menu.app"), web_app=WebAppInfo(url=WEBAPP_URL))]
    ])


def app_invitation(lang):
    return t(lang, "app.intro") if WEBAPP_URL else ""


def menu_keyboard(lang, *, include_app=True):
    # La soluzione sta accanto a "Gioca": sono le due facce della stessa sfida, quella di
    # oggi da giocare e quella di ieri da scoprire.
    rows = [
        [_button(lang, "menu.play", "play"), _button(lang, "menu.solution", "solution")],
        [_button(lang, "menu.events", "events"), _button(lang, "menu.training", "training")],
        [_button(lang, "menu.archive", "archive"), _button(lang, "menu.leagues", "leagues")],
        [_button(lang, "menu.stats", "stats"), _button(lang, "menu.top", "top")],
        [_button(lang, "menu.notify", "notify"), _button(lang, "menu.language", "language")],
        [_button(lang, "menu.shop", "shop"), _button(lang, "menu.help", "help")],
    ]
    if legal_buttons(lang):
        rows.append(legal_buttons(lang))
    if WEBAPP_URL and include_app:
        rows.insert(0, list(app_keyboard(lang).inline_keyboard[0]))
    return InlineKeyboardMarkup(rows)


def bot_commands(lang):
    return [BotCommand(command, t(lang, key)) for command, key in COMMAND_KEYS]


