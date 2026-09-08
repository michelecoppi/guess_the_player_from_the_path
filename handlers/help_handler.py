from telegram import Update
from telegram.ext import ContextTypes

from handlers.keyboards import menu_keyboard
from services.i18n import resolve_language, t


async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = resolve_language(getattr(update.effective_user, "language_code", None))
    await update.effective_message.reply_text(t(lang, "help.message"), reply_markup=menu_keyboard(lang))
