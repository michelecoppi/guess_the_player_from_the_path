from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from services.firebase_service import get_user_data

TROPHIES_PER_PAGE = 5

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    
    if not user_data:
        await update.message.reply_text("❗ Non sei registrato! Usa /start per registrarti.")
        return
    
    trophies = user_data.get("trophies", [])
    context.user_data["trophies"] = trophies 

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

    keyboard = InlineKeyboardMarkup([
    [InlineKeyboardButton("🎖️ I miei trofei", callback_data="show_trophies_0")]
    ])

    await update.message.reply_text(stats_message, reply_markup=keyboard)

async def show_trophies_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    trophies = context.user_data.get("trophies", [])

    _, _, page_str = query.data.split("_")
    page = int(page_str)

    if not trophies:
        await query.edit_message_text("😕 Nessun trofeo guadagnato ancora.")
        return

    start = page * TROPHIES_PER_PAGE
    end = start + TROPHIES_PER_PAGE
    displayed = trophies[start:end]

    message = "🎖️ *I tuoi trofei:*\n\n"
    for t in displayed:
        parts = t.split("_")
        if len(parts) == 4:
            pos, event, week, year = parts
            message += f"🏅 *{event}* (Settimana {week}, {year}) - 🥇 Posizione: {pos}\n"
        else:
            message += f"🏅 {t}\n"

    buttons = []
    if start > 0:
        buttons.append(InlineKeyboardButton("⬅️ Indietro", callback_data=f"show_trophies_{page - 1}"))
    if end < len(trophies):
        buttons.append(InlineKeyboardButton("➡️ Avanti", callback_data=f"show_trophies_{page + 1}"))

    keyboard = InlineKeyboardMarkup([buttons]) if buttons else None
    await query.edit_message_text(message, reply_markup=keyboard, parse_mode="Markdown")
