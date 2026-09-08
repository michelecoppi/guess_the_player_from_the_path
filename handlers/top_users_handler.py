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
from services.i18n import resolve_language, t

FIELD_BY_VIEW = {"global": "points_totali", "monthly": "monthly_points"}
MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}


def format_leaderboard(top_users, telegram_id, view, user_position=None, user_score=None, lang="it"):
    title = t(lang, "top.title_global") if view == "global" else t(lang, "top.title_monthly")
    score_key = "points" if view == "global" else "monthly_points"
    points_suffix = t(lang, "top.points_suffix")

    message = f"{title}\n\n"
    for index, user in enumerate(top_users, start=1):
        medal = "🔟" if index == 10 else MEDALS.get(index, f"{index}️⃣")
        highlight = t(lang, "top.you_tag") if user["telegram_id"] == telegram_id else ""
        message += f"{medal} {user['username']}{highlight} - {user.get(score_key, 0)} {points_suffix}\n"

    if user_position and user_position > len(top_users):
        message += t(lang, "top.your_position", position=user_position, score=user_score)

    return message


def _leaderboard_for(view, telegram_id, fallback_lang="it"):
    field = FIELD_BY_VIEW[view]
    top_users = firebase_service.get_top_users(field=field, limit=10)

    matched = next((u for u in top_users if u["telegram_id"] == telegram_id), None)
    if matched:
        # L'utente e' gia' nei documenti appena letti: niente lettura in piu' solo per la lingua.
        return format_leaderboard(top_users, telegram_id, view, lang=matched.get("language", fallback_lang))

    user_data = firebase_service.get_user_data(telegram_id)
    if not user_data:
        return format_leaderboard(top_users, telegram_id, view, lang=fallback_lang)

    lang = user_data.get("language", fallback_lang)
    user_score = user_data.get(field, 0)
    position = firebase_service.count_users_ahead(field, user_score) + 1
    return format_leaderboard(top_users, telegram_id, view, user_position=position, user_score=user_score, lang=lang)


def _keyboard(view, lang="it"):
    if view == "global":
        return InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "top.button_monthly"), callback_data="show_monthly")]])
    return InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "top.button_global"), callback_data="show_global")]])


async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    fallback_lang = resolve_language(getattr(update.effective_user, "language_code", None))
    message = _leaderboard_for("global", telegram_id, fallback_lang=fallback_lang)
    await update.effective_message.reply_text(message, parse_mode=ParseMode.HTML, reply_markup=_keyboard("global", fallback_lang))


async def leaderboard_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    telegram_id = query.from_user.id
    fallback_lang = resolve_language(getattr(query.from_user, "language_code", None))
    await query.answer()

    view = "monthly" if query.data == "show_monthly" else "global"
    message = _leaderboard_for(view, telegram_id, fallback_lang=fallback_lang)

    await query.edit_message_text(message, parse_mode=ParseMode.HTML, reply_markup=_keyboard(view, fallback_lang))
