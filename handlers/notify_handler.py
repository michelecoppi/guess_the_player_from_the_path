from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from services.firebase_service import get_user_data, set_user_notifications
from services.i18n import resolve_language, t

# Il bottone che compare sotto la sconfitta della sfida del giorno. E' una callback a parte
# e non `enable_notify` perche' quella **riscrive** il messaggio su cui sta: li' cancellerebbe
# il confronto sul tentativo sbagliato e il bottone di condivisione. Qui invece si risponde
# con un messaggio nuovo e si lascia stare quello di prima.
ENABLE_INLINE = "notify_on"


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
    lang = (user_data or {}).get("language") or resolve_language(getattr(update.effective_user, "language_code", None))

    if not user_data:
        await update.effective_message.reply_text(t(lang, "notify.not_registered"))
        return

    if chat_id != user_id:
        await update.effective_message.reply_text(t(lang, "notify.private_only"))
        return

    if notifications_enabled(user_data):
        text = t(lang, "notify.active_prompt")
        keyboard = [[InlineKeyboardButton(t(lang, "notify.button_disable"), callback_data="disable_notify")]]
    else:
        text = t(lang, "notify.inactive_prompt")
        keyboard = [[InlineKeyboardButton(t(lang, "notify.button_enable"), callback_data="enable_notify")]]

    await update.effective_message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def notify_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    chat_id = query.message.chat.id
    user_data = get_user_data(user_id)
    lang = (user_data or {}).get("language") or resolve_language(getattr(query.from_user, "language_code", None))

    if query.data == ENABLE_INLINE:
        already_on = notifications_enabled(user_data or {})
        if not already_on:
            set_user_notifications(user_id, chat_id, True)
        await query.message.reply_text(
            t(lang, "notify.already_enabled" if already_on else "notify.enabled_inline")
        )
    elif query.data == "enable_notify":
        set_user_notifications(user_id, chat_id, True)
        await query.edit_message_text(t(lang, "notify.enabled_confirm"))
    elif query.data == "disable_notify":
        set_user_notifications(user_id, chat_id, False)
        await query.edit_message_text(t(lang, "notify.disabled_confirm"))
