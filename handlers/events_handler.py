from telegram import Update
from telegram.ext import ContextTypes
from services.firebase_service import get_current_event


async def events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    event = get_current_event()
    if not event:
        await update.message.reply_text("❗ Non ci sono eventi attivi al momento.")
        return
    await update.message.reply_text("❗ Questo comando non è ancora implementato.")