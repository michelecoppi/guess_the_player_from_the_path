"""Classifiche.

La top 10 la ordina Firestore (`order_by(...).limit(10)`): prima si scaricava l'intera
collection `users` ad ogni /top, cioe' una lettura per utente registrato per mostrarne dieci.
La posizione di chi resta fuori dalla top 10 si ottiene con un conteggio lato server
(`count()`), non scorrendo la classifica.
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from services import firebase_service

FIELD_BY_VIEW = {"global": "points_totali", "monthly": "monthly_points"}
MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}


def format_leaderboard(top_users, telegram_id, view, user_position=None, user_score=None):
    title = "🏆 <b>Top 10 generale</b> 🏆" if view == "global" else "📆 <b>Top 10 mensile</b> 📆"
    score_key = "points" if view == "global" else "monthly_points"

    message = f"{title}\n\n"
    for index, user in enumerate(top_users, start=1):
        medal = "🔟" if index == 10 else MEDALS.get(index, f"{index}️⃣")
        highlight = " <b>[TU]</b>" if user["telegram_id"] == telegram_id else ""
        message += f"{medal} {user['username']}{highlight} - {user.get(score_key, 0)} punti\n"

    if user_position and user_position > len(top_users):
        message += f"\n📍 <b>La tua posizione:</b> {user_position}° - {user_score} punti"

    return message


def _leaderboard_for(view, telegram_id):
    field = FIELD_BY_VIEW[view]
    top_users = firebase_service.get_top_users(field=field, limit=10)

    if any(u["telegram_id"] == telegram_id for u in top_users):
        return format_leaderboard(top_users, telegram_id, view)

    user_data = firebase_service.get_user_data(telegram_id)
    if not user_data:
        return format_leaderboard(top_users, telegram_id, view)

    user_score = user_data.get(field, 0)
    position = firebase_service.count_users_ahead(field, user_score) + 1
    return format_leaderboard(top_users, telegram_id, view, user_position=position, user_score=user_score)


def _keyboard(view):
    if view == "global":
        return InlineKeyboardMarkup([[InlineKeyboardButton("📆 Classifica Mensile", callback_data="show_monthly")]])
    return InlineKeyboardMarkup([[InlineKeyboardButton("🌐 Classifica Generale", callback_data="show_global")]])


async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    message = _leaderboard_for("global", telegram_id)
    await update.message.reply_text(message, parse_mode=ParseMode.HTML, reply_markup=_keyboard("global"))


async def leaderboard_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    telegram_id = query.from_user.id
    await query.answer()

    view = "monthly" if query.data == "show_monthly" else "global"
    message = _leaderboard_for(view, telegram_id)

    await query.edit_message_text(message, parse_mode=ParseMode.HTML, reply_markup=_keyboard(view))
