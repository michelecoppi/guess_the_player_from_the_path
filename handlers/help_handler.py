from telegram import Update
from telegram.ext import ContextTypes

from handlers.keyboards import language_for, menu_keyboard
from services.i18n import t


async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # `language_for` e non `resolve_language`: chi ha scelto una lingua con /language deve
    # trovarla anche qui, non quella del suo client Telegram.
    lang = language_for(update)
    await update.effective_message.reply_text(t(lang, "help.message"), reply_markup=menu_keyboard(lang))
