from cache import get_cache, set_cache
from services.firebase_service import reload_daily_challenge
from datetime import datetime, timezone
from telegram import Update
from telegram.ext import ContextTypes

async def show(update: Update, context: ContextTypes.DEFAULT_TYPE):

    cache = get_cache()

    if not cache.get("image_url"):
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

    await update.message.reply_photo(
        photo=cache["image_url"],
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
