from cache import get_cache, set_cache
from telegram import Update
from telegram.ext import ContextTypes
from services.firebase_service import update_user_points, load_daily_challenge, update_daily_challenge_first_correct, get_user_daily_status, update_user_daily_attempts, get_user_data
from datetime import datetime
import pytz
import logging

MAX_ATTEMPTS = 3

async def guess(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        await update.message.reply_text("❗ Questo comando può essere usato solo in chat privata.")
        return
    
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    if not user_data:
        await update.message.reply_text("❗ Devi registrarti prima di giocare! Usa /start.")
        return
    
    if get_cache().get("current_day") is None:
        italy_tz = pytz.timezone('Europe/Rome')
        now_italy = datetime.now(italy_tz)
        today_str = now_italy.strftime('%d/%m/%y')
        load_daily_challenge(today_str) 

    daily_attempts, has_guessed_today = get_user_daily_status(user_id)

    if has_guessed_today:
        await update.message.reply_text("✅ Hai già indovinato oggi! Torna domani per una nuova sfida.")
        return

    if daily_attempts >= MAX_ATTEMPTS:
        await update.message.reply_text("❌ Hai esaurito i tentativi per oggi! Riprova domani.")
        return

    message_text = update.message.text or ""
    message_text_lower = message_text.lower()

    if message_text_lower.startswith("/guess"):
        user_answer = message_text[6:].strip().lower() 
    else:
        user_answer = ""

    if not user_answer:
        await update.message.reply_text("❗ Devi scrivere anche il nome del calciatore dopo /guess!")
        return

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
        update_user_points(user_id, total_points, bonus, True)
        bonus_message = f"💎 Bonus: +{bonus} punto perchè sei il primo ad indovinare!" if bonus > 0 else ""
        await update.message.reply_text(f"✅ Corretto! Hai guadagnato {total_points} punti.\n{bonus_message}")
    else:
        attempts_left = MAX_ATTEMPTS - (daily_attempts + 1)
        if attempts_left == 0:
            await update.message.reply_text("❌ Risposta sbagliata, hai esaurito i tentativi per oggi! Riprova domani.")
        else:
            await update.message.reply_text(f"❌ Risposta sbagliata, riprova! Hai {attempts_left} tentativi rimasti.")

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
