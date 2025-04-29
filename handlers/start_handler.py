from telegram import Update
from telegram.ext import ContextTypes
from services.firebase_service import save_user

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        await update.message.reply_text("❗ Questo comando può essere usato solo in chat privata.")
        return
    
    user = update.effective_user
    response_message = save_user(user.id, user.first_name)
    
    await update.message.reply_text(response_message)
