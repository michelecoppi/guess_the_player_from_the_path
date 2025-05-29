from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from services.firebase_service import get_all_users

def generate_leaderboard(users, telegram_id, field="points"):
    sorted_users = sorted(users, key=lambda x: x.get(field, 0), reverse=True)
    top_users = sorted_users[:10]
    user_position = next((i for i, u in enumerate(sorted_users, start=1) if u["telegram_id"] == telegram_id), None)

    title = "🏆 <b>Top 10 generale</b> 🏆" if field == "points" else "📆 <b>Top 10 mensile</b> 📆"
    message = f"{title}\n\n"
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}

    for index, user in enumerate(top_users, start=1):
        name = user["username"]
        score = user.get(field, 0)
        medal = "🔟" if index == 10 else medals.get(index, f"{index}️⃣")
        highlight = " <b>[TU]</b>" if user["telegram_id"] == telegram_id else ""
        message += f"{medal} {name}{highlight} - {score} punti\n"

    if user_position and user_position > 10:
        user_data = next((u for u in sorted_users if u["telegram_id"] == telegram_id), None)
        score = user_data.get(field, 0)
        message += f"\n📍 <b>La tua posizione:</b> {user_position}° - {score} punti"

    return message, user_position

async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    users = get_all_users()

    message, _ = generate_leaderboard(users, telegram_id, field="points")

    keyboard = [[InlineKeyboardButton("📆 Classifica Mensile", callback_data="show_monthly")]]
    await update.message.reply_text(message, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

async def leaderboard_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    telegram_id = query.from_user.id
    await query.answer()

    users = get_all_users()

    if query.data == "show_monthly":
        message, _ = generate_leaderboard(users, telegram_id, field="monthly_points")
        keyboard = [[InlineKeyboardButton("🌐 Classifica Generale", callback_data="show_global")]]
    else:
        message, _ = generate_leaderboard(users, telegram_id, field="points")
        keyboard = [[InlineKeyboardButton("📆 Classifica Mensile", callback_data="show_monthly")]]

    await query.edit_message_text(message, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
