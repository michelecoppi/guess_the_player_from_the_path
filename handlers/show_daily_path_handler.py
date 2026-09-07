from telegram import Update
from telegram.ext import ContextTypes

from services.daily_challenge import bonus_available, get_today_challenge
from services.difficulty import points_for_difficulty
from services.path_image import render_career_path_image


async def show(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # get_today_challenge genera la sfida al volo se manca (es. GitHub Action non eseguita).
    challenge = get_today_challenge()

    if not challenge:
        await update.message.reply_text("❗ Non c'è ancora una sfida giornaliera disponibile.")
        return

    career_path = challenge.get("career_path")
    image_url = challenge.get("image_url")
    if not career_path and not image_url:
        await update.message.reply_text("❗ Non c'è ancora una sfida giornaliera disponibile.")
        return

    difficulty = (challenge.get("difficulty") or "unknown").capitalize()
    points = points_for_difficulty(challenge.get("difficulty"))
    bonus_info = "💎 Bonus: +1 punto se sei il primo a rispondere!" if bonus_available() else ""

    caption = (
        f"🎯 Difficoltà: {difficulty}\n"
        f"🏆 Punti: {points}\n"
        f"{bonus_info}"
        f"\n\n🔍 Indovina la carriera con il comando /guess <risposta> in privato al bot!\n"
    )

    photo = render_career_path_image(career_path) if career_path else image_url

    await update.message.reply_photo(photo=photo, caption=caption)
