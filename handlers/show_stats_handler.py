from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ContextTypes
from services.firebase_service import get_user_data
import re

TROPHIES_PER_PAGE = 5
PALMARES_IMAGE = "https://i.postimg.cc/cHn605NN/Chat-GPT-Image-8-giu-2025-15-13-48.png"
FALLBACK_AVATAR = "https://static.thenounproject.com/png/4154905-200.png"

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE, user_data=None, edit_mode=False):
    user_id = update.effective_user.id
    if user_data is None:
        user_data = get_user_data(user_id)
    
    if not user_data:
        await update.message.reply_text("❗ Non sei registrato! Usa /start per registrarti.")
        return
    
    trophies = user_data.get("trophies", [])
    context.user_data["user_data"] = user_data
    context.user_data["trophies"] = trophies 

    first_name = user_data.get("first_name", "N/A")
    points_totali = user_data.get("points_totali", 0)
    monthly_points = user_data.get("monthly_points", 0)
    players_guessed = user_data.get("players_guessed", 0)
    bonus_first_guessed = user_data.get("bonus_first_guessed", 0)
    telegram_id = user_data.get("telegram_id")

    stats_message = (
        f"📊 Le tue statistiche:\n\n"
        f"👤 Nome: {first_name}\n"
        f"🏆 Punti totali: {points_totali}\n"
        f"📅 Punti mensili: {monthly_points}\n"
        f"🧠 Indovinati: {players_guessed}\n"
        f"⚡ Bonus primo indovino ottenuti: {bonus_first_guessed}"
    )

    keyboard = InlineKeyboardMarkup([
    [InlineKeyboardButton("🎖️ I miei trofei", callback_data="show_trophies_0")]
    ])

    photos = await context.bot.get_user_profile_photos(telegram_id)
    if photos.total_count > 0:
        profile_pic = photos.photos[0][-1].file_id
    else:
        profile_pic = FALLBACK_AVATAR

    if edit_mode:
        await update.callback_query.edit_message_media(
            media=InputMediaPhoto(
                media=profile_pic,
                caption=stats_message,
                parse_mode="Markdown"
            ),
            reply_markup=keyboard
        )
    else:
        await update.message.reply_photo(
            photo=profile_pic,
            caption=stats_message,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )

def format_event_name(event_name):
    return re.sub(r'([a-z])([A-Z])', r'\1 \2', event_name)

async def show_trophies_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    trophies = context.user_data.get("trophies", [])

    _, _, page_str = query.data.split("_")
    page = int(page_str)

    if not trophies:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Indietro", callback_data="back_to_stats")]
        ])
        await query.edit_message_media(
            media=InputMediaPhoto(
                media=PALMARES_IMAGE,
                caption="😕 Nessun trofeo guadagnato ancora.",
                parse_mode="Markdown"
            ),
            reply_markup=keyboard
        )
        return

    start = page * TROPHIES_PER_PAGE
    end = start + TROPHIES_PER_PAGE
    displayed = trophies[start:end]

    message = "🎖️ *I tuoi trofei:*\n\n"
    for trophy in displayed:
        if trophy.startswith("MON_"):
            # Trofeo classifica mensile
            try:
                _, month, season_num, year, pos = trophy.split("_")
                medal = {
                    "1": "🥇",
                    "2": "🥈",
                    "3": "🥉"
                }.get(pos, "🏅")
                message += f"{medal} *Classifica Mensile* ({month} {year}, Stagione {season_num}) - Posizione: {pos}\n"
            except:
                message += f"🏅 {trophy}\n"
        else:
            # Trofeo evento settimanale
            parts = trophy.split("_")
            if len(parts) == 4:
                pos, event, week, year = parts
                medal = {
                    "1": "🥇",
                    "2": "🥈",
                    "3": "🥉"
                }.get(pos, "🏅")
                formatted_event = format_event_name(event)
                message += f"{medal} *{formatted_event}* (Settimana {week}, {year}) - Posizione: {pos}\n"
            else:
                message += f"🏅 {trophy}\n"

    buttons = []
    if start > 0:
        buttons.append(InlineKeyboardButton("⬅️ Indietro", callback_data=f"show_trophies_{page - 1}"))
    if end < len(trophies):
        buttons.append(InlineKeyboardButton("➡️ Avanti", callback_data=f"show_trophies_{page + 1}"))

    navigation_row = buttons if buttons else []
    navigation_row.append(InlineKeyboardButton("🔙 Indietro", callback_data="back_to_stats"))

    keyboard = InlineKeyboardMarkup([navigation_row])

    await query.edit_message_media(
        media=InputMediaPhoto(
            media=PALMARES_IMAGE,
            caption=message,
            parse_mode="Markdown"
        ),
        reply_markup=keyboard
    )

async def back_to_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data.get("user_data")
    await stats(update, context, user_data=user_data, edit_mode=True)    