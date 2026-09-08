"""I bottoni del menu, collegati agli handler dei comandi.

Un bottone non ha una logica sua: richiama esattamente la funzione del comando
corrispondente, cosi' non esistono due versioni della stessa schermata da tenere allineate.
La tastiera vive in handlers/keyboards.py, che non importa nessun handler: serve anche a
/start e /help, e cosi' non si crea un import circolare.
"""
from telegram import Update
from telegram.ext import ContextTypes

from handlers.archive_handler import archive
from handlers.events_handler import events
from handlers.help_handler import help
from handlers.keyboards import CALLBACK_PREFIX, language_for, menu_keyboard
from handlers.language_handler import language
from handlers.league_handler import leagues
from handlers.notify_handler import notify
from handlers.show_daily_path_handler import show
from handlers.show_stats_handler import stats
from handlers.solution_handler import solution
from handlers.top_users_handler import top
from handlers.training_handler import training
from services.i18n import t


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = language_for(update)
    await update.effective_message.reply_text(
        t(lang, "menu.title"), reply_markup=menu_keyboard(lang), parse_mode="HTML"
    )


ACTIONS = {
    "play": show,
    "solution": solution,
    "events": events,
    "archive": archive,
    "training": training,
    "leagues": leagues,
    "stats": stats,
    "top": top,
    "notify": notify,
    "language": language,
    "help": help,
}


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """I bottoni del menu richiamano gli handler dei comandi: la risposta arriva come nuovo
    messaggio, cosi' il menu resta in chat e si puo' premere un altro bottone."""
    query = update.callback_query
    await query.answer()

    action = query.data[len(CALLBACK_PREFIX):]
    handler = ACTIONS.get(action)
    if handler is None:
        return
    await handler(update, context)
