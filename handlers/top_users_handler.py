from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from services.firebase_service import get_all_users

async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_telegram_id = update.effective_user.id

    users = get_all_users()

    sorted_users = sorted(users, key=lambda x: x["points"], reverse=True)

    top_users = sorted_users[:10]

    user_rank = next((index for index, user in enumerate(sorted_users, start=1) if user["telegram_id"] == user_telegram_id), None)

    message = "🏆 <b>Top 10 Classifica</b> 🏆\n\n"

    medals = {1: "🥇", 2: "🥈", 3: "🥉"}

    for index, user in enumerate(top_users, start=1):
        name = user["username"]
        points = user["points"]

        if index == 10:
            medal = "🔟"
        else:
            medal = medals.get(index, f"{index}️⃣")

        if user["telegram_id"] == user_telegram_id:
            message += f"{medal} <b>{name} [TU] </b> - {points} punti\n"
        else:
            message += f"{medal} {name} - {points} punti\n"

    if user_rank and user_rank > 10:
        user_data = next((user for user in sorted_users if user["telegram_id"] == user_telegram_id), None)
        if user_data:
            message += f"\n📍 <b>La tua posizione:</b> {user_rank}° - {user_data['points']} punti"

    await update.message.reply_text(message, parse_mode=ParseMode.HTML)
