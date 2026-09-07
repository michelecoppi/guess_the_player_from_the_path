from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from services.firebase_service import get_user_data, set_user_notifications


def notifications_enabled(user_data):
    """`notifications_enabled` e' il flag esplicito; `chat_id != -1` e' il vecchio modo di
    dire la stessa cosa e resta letto per gli utenti non ancora migrati."""
    if "notifications_enabled" in user_data:
        return bool(user_data["notifications_enabled"])
    return user_data.get("chat_id", -1) != -1


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

    if notifications_enabled(user_data):
        text = "🔔 Le notifiche sono attive. Vuoi disattivarle?"
        keyboard = [[InlineKeyboardButton("❌ Disattiva notifiche", callback_data="disable_notify")]]
    else:
        text = "🔕 Le notifiche non sono attive. Vuoi attivarle?"
        keyboard = [[InlineKeyboardButton("✅ Attiva notifiche", callback_data="enable_notify")]]

    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def notify_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    chat_id = query.message.chat.id

    if query.data == "enable_notify":
        set_user_notifications(user_id, chat_id, True)
        await query.edit_message_text("✅ Notifiche attivate! Riceverai un messaggio ogni giorno.")
    elif query.data == "disable_notify":
        set_user_notifications(user_id, chat_id, False)
        await query.edit_message_text("🔕 Notifiche disattivate. Potrai riattivarle con /notify.")
