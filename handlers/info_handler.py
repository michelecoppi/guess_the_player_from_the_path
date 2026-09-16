import asyncio

from telegram import Update
from telegram.ext import ContextTypes

from handlers.keyboards import app_keyboard, language_for
from services.i18n import t


async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = (await asyncio.to_thread(language_for, update))
    await update.effective_message.reply_text(t(lang, "info.message"), reply_markup=app_keyboard(lang))
