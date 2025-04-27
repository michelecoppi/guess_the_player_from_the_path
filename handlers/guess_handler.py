from cache import get_cache, set_cache
from telegram import Update
from telegram.ext import ContextTypes
from services.firebase_service import update_user_points, reload_daily_challenge, update_daily_challenge_first_correct, get_user_daily_status, update_user_daily_attempts, get_user_data
from datetime import datetime, timezone
import logging

MAX_ATTEMPTS = 3

async def guess(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    if not user_data:
        await update.message.reply_text("❗ Devi registrarti prima di giocare! Usa /start.")
        return
    
    if update.message.chat.type != "private":
        await update.message.reply_text("❗ Questo comando può essere usato solo in chat privata.")
        return

    daily_attempts, has_guessed_today = get_user_daily_status(user_id)

    if has_guessed_today:
        await update.message.reply_text("✅ Hai già indovinato oggi! Torna domani per una nuova sfida.")
        return

    if daily_attempts >= MAX_ATTEMPTS:
        await update.message.reply_text("❌ Hai esaurito i tentativi per oggi! Riprova domani.")
        return

    message_text = update.message.text or ""
    user_answer = message_text.replace("/guess", "", 1).strip().lower()

    logging.info(f"[GUESS] Risposta dell'utente: {user_answer}")
    logging.info(f"[GUESS] Risposta corretta: {get_cache()['correct_answers']}")

    if user_answer in get_cache()["correct_answers"]:
        points = points_for_difficulty(get_cache()["difficulty"])
        bonus = 0

        if get_cache()["first_correct_user"] is False:
            bonus = 1
            set_cache({"first_correct_user": True})
            update_daily_challenge_first_correct()

        total_points = points + bonus
        update_user_points(user_id, total_points, bonus)
        bonus_message = f"💎 Bonus: +{bonus} punto perchè sei il primo ad indovinare!" if bonus > 0 else ""
        await update.message.reply_text(f"✅ Corretto! Hai guadagnato {total_points} punti.\n{bonus_message}")
    else:
        await update.message.reply_text("❌ Risposta sbagliata, riprova!")

    update_user_daily_attempts(user_id, daily_attempts + 1)
    

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