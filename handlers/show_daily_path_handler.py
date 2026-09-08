from telegram import Update
from telegram.ext import ContextTypes

from handlers.keyboards import language_for
from handlers.legend_handler import legend_keyboard
from services.daily_challenge import MAX_ATTEMPTS, bonus_available, challenge_number, get_today_challenge
from services.difficulty import points_for_difficulty
from services.i18n import difficulty_label, t
from services.path_image import render_career_path_image


async def show(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = language_for(update)

    # get_today_challenge genera la sfida al volo se manca (es. GitHub Action non eseguita).
    challenge = get_today_challenge()

    if not challenge:
        await update.effective_message.reply_text(t(lang, "common.no_challenge"))
        return

    career_path = challenge.get("career_path")
    image_url = challenge.get("image_url")
    if not career_path and not image_url:
        await update.effective_message.reply_text(t(lang, "common.no_challenge"))
        return

    difficulty = difficulty_label(lang, challenge.get("difficulty"))
    points = points_for_difficulty(challenge.get("difficulty"))
    bonus_info = t(lang, "show.bonus_info") if bonus_available() else ""

    caption = t(
        lang, "show.caption",
        difficulty=difficulty, points=points, bonus_info=bonus_info, attempts=MAX_ATTEMPTS,
    )

    photo = image_url
    if career_path:
        photo = render_career_path_image(
            career_path,
            title=t(lang, "image.path_title"),
            subtitle=t(lang, "image.path_subtitle", stops=len(career_path)),
            badge=difficulty.upper(),
            footer=f"Guess the Player #{challenge_number()}",
            lang=lang,
        )

    # La legenda sta sotto l'immagine perche' e' li' che nasce la domanda: cosa vuol dire
    # la barretta tratteggiata, cosa sono i numeri fra parentesi.
    await update.effective_message.reply_photo(
        photo=photo, caption=caption, reply_markup=legend_keyboard(lang)
    )
