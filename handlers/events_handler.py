from telegram import Update
from telegram.ext import ContextTypes
from services.firebase_service import create_event


async def events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    create_event()
    await update.message.reply_text("❗ Questo comando non è ancora implementato.")