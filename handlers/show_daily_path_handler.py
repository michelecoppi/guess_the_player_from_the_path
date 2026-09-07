from cache import get_cache, set_cache
from services.firebase_service import load_daily_challenge
from services.daily_generator import ensure_daily_buffer
from services.path_image import render_career_path_image
from datetime import datetime
import pytz
from telegram import Update
from telegram.ext import ContextTypes

async def show(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cache = get_cache()

    if cache.get("current_day") is None:
        italy_tz = pytz.timezone('Europe/Rome')
        now_italy = datetime.now(italy_tz)
        today_str = now_italy.strftime('%d/%m/%y')
        load_daily_challenge(today_str)
        if get_cache().get("current_day") is None:
            # Fallback: nessuna sfida generata in anticipo (es. GitHub Action non eseguita).
            # La generiamo ora, cosi' il gioco non si blocca ("esecuzione alla prima richiesta del giorno").
            ensure_daily_buffer(days_ahead=1)
            load_daily_challenge(today_str)

    career_path = cache.get("career_path")
    image_url = cache.get("image_url")

    if not career_path and not image_url:
        await update.message.reply_text("❗ Non c'è ancora una sfida giornaliera disponibile.")
        return

    difficulty = cache.get("difficulty", "unknown").capitalize()
    points = points_for_difficulty(cache.get("difficulty"))

    bonus_info = "💎 Bonus: +1 punto se sei il primo a rispondere!" if cache.get("first_correct_user") is False else ""

    caption = (
        f"🎯 Difficoltà: {difficulty}\n"
        f"🏆 Punti: {points}\n"
        f"{bonus_info}"
        f"\n\n🔍 Indovina la carriera con il comando /guess <risposta> in privato al bot!\n"
    )

    if career_path:
        photo = render_career_path_image(career_path)
    else:
        photo = image_url

    await update.message.reply_photo(
        photo=photo,
        caption=caption
    )

def points_for_difficulty(difficulty):
    if difficulty == "easy":
        return 1
    elif difficulty == "medium":
        return 2
    elif difficulty == "hard":
        return 3
    elif difficulty == "impossible":
        return 4
    else:
        return 0
