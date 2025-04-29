from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from services.firebase_service import get_user_data, update_user_chat_id

async def notify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    user_data = get_user_data(user_id)

    if not user_data:
        await update.message.reply_text("❗ Devi registrarti prima con /start.")
        return

    if chat_id != user_id:
        await update.message.reply_text("❗ Usa questo comando in chat privata.")
        return

    keyboard = []
    if user_data.get("chat_id", -1) == -1:
        text = "🔕 Le notifiche non sono attive. Vuoi attivarle?"
        keyboard.append([InlineKeyboardButton("✅ Attiva notifiche", callback_data="enable_notify")])
    else:
        text = "🔔 Le notifiche sono attive. Vuoi disattivarle?"
        keyboard.append([InlineKeyboardButton("❌ Disattiva notifiche", callback_data="disable_notify")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(text, reply_markup=reply_markup)
    
async def notify_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    chat_id = query.message.chat.id

    if query.data == "enable_notify":
        update_user_chat_id(user_id, chat_id)
        await query.edit_message_text("✅ Notifiche attivate! Riceverai un messaggio ogni giorno.")
    elif query.data == "disable_notify":
        update_user_chat_id(user_id, -1)
        await query.edit_message_text("🔕 Notifiche disattivate. Potrai riattivarle con /notify.")