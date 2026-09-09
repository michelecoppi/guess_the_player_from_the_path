"""Esercizio self-service del diritto alla cancellazione."""
import logging

from telegram import Update
from telegram.ext import ContextTypes

from services import firebase_service
from services.i18n import resolve_language, t


async def forgetme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_data = firebase_service.get_user_data(user.id)
    lang = (user_data or {}).get("language") or resolve_language(
        getattr(user, "language_code", None)
    )
    if update.effective_chat.id != user.id:
        await update.effective_message.reply_text(t(lang, "forgetme.private_only"))
        return
    if not user_data:
        await update.effective_message.reply_text(t(lang, "forgetme.not_registered"))
        return
    if (getattr(context, "args", None) or []) != ["DELETE"]:
        await update.effective_message.reply_text(t(lang, "forgetme.confirm"))
        return
    try:
        firebase_service.delete_user_data(user.id)
    except Exception:
        logging.exception("Errore durante /forgetme per %s", user.id)
        await update.effective_message.reply_text(t(lang, "forgetme.error"))
        return
    await update.effective_message.reply_text(t(lang, "forgetme.done"))
