from telegram import Update
from telegram.ext import ContextTypes
from services.firebase_service import get_user_data

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)

    if not user_data:
        await update.message.reply_text("❗ Non sei registrato! Usa /start per registrarti.")
        return

    first_name = user_data.get("first_name", "N/A")
    points_totali = user_data.get("points_totali", 0)
    players_guessed = user_data.get("players_guessed", 0)
    bonus_first_guessed = user_data.get("bonus_first_guessed", 0)

    stats_message = (
        f"📊 Le tue statistiche:\n\n"
        f"👤 Nome: {first_name}\n"
        f"🏆 Punti totali: {points_totali}\n"
        f"🧠 Indovinati: {players_guessed}\n"
        f"⚡ Bonus primo indovino ottenuti: {bonus_first_guessed}"
    )

    await update.message.reply_text(stats_message)
