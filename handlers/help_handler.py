from telegram import Update
from telegram.ext import ContextTypes

from handlers.keyboards import app_invitation, language_for, menu_keyboard
from services.i18n import t


async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # `language_for` e non `resolve_language`: chi ha scelto una lingua con /language deve
    # trovarla anche qui, non quella del suo client Telegram.
    lang = language_for(update)
    private = getattr(getattr(update, "effective_chat", None), "type", None) == "private"
    text = "\n\n".join(filter(None, [app_invitation(lang) if private else "", t(lang, "help.message")]))
    await update.effective_message.reply_text(text, reply_markup=menu_keyboard(lang, include_app=private))
