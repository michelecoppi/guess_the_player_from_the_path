"""Assistenza sugli acquisti richiesta dalla piattaforma Telegram Stars."""
import asyncio
import logging

from telegram import Update
from telegram.ext import ContextTypes

from config import ADMIN_TELEGRAM_IDS
from services import firebase_service
from services.i18n import resolve_language, t


async def paysupport(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_data = (await asyncio.to_thread(firebase_service.get_user_data, user.id))
    lang = (user_data or {}).get("language") or resolve_language(
        getattr(user, "language_code", None)
    )
    if update.effective_chat.id != user.id:
        await update.effective_message.reply_text(t(lang, "paysupport.private_only"))
        return

    body = " ".join(getattr(context, "args", None) or []).strip()
    if not body:
        await update.effective_message.reply_text(t(lang, "paysupport.usage"))
        return
    if not ADMIN_TELEGRAM_IDS:
        logging.error("/paysupport non disponibile: ADMIN_TELEGRAM_IDS vuoto")
        await update.effective_message.reply_text(t(lang, "paysupport.error"))
        return

    name = getattr(user, "first_name", None) or "—"
    request = (
        "💳 Richiesta assistenza acquisto\n"
        f"Utente: {name}\nTelegram ID: {user.id}\n\n{body[:3500]}\n\n"
        f"Rispondi: /admin_support_reply {user.id} <messaggio>"
    )
    try:
        for admin_id in ADMIN_TELEGRAM_IDS:
            await context.bot.send_message(chat_id=admin_id, text=request)
    except Exception:
        logging.exception("Invio richiesta /paysupport fallito per %s", user.id)
        await update.effective_message.reply_text(t(lang, "paysupport.error"))
        return
    await update.effective_message.reply_text(t(lang, "paysupport.sent"))
