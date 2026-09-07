import logging

from telegram import Update
from telegram.ext import ContextTypes

from services import firebase_service
from services.daily_challenge import get_today_challenge
from services.dates import today_iso
from services.difficulty import points_for_difficulty

MAX_ATTEMPTS = 3


async def guess(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        await update.message.reply_text("❗ Questo comando può essere usato solo in chat privata.")
        return

    user_id = update.effective_user.id
    day_iso = today_iso()

    message_text = update.message.text or ""
    user_answer = message_text[6:].strip().lower() if message_text.lower().startswith("/guess") else ""
    if not user_answer:
        await update.message.reply_text("❗ Devi scrivere anche il nome del calciatore dopo /guess!")
        return

    challenge = get_today_challenge()
    if not challenge:
        await update.message.reply_text("❗ Non c'è ancora una sfida giornaliera disponibile.")
        return

    # Il tentativo viene consumato in transazione: contatori corretti anche con due /guess
    # inviati nello stesso istante, e nessun bisogno di azzerarli con un job notturno.
    attempt = firebase_service.begin_guess_attempt(user_id, day_iso, MAX_ATTEMPTS)
    if not attempt["ok"]:
        await update.message.reply_text(_attempt_error_message(attempt["reason"]))
        return

    logging.info(f"[GUESS] Risposta dell'utente: {user_answer}")

    if user_answer not in challenge.get("correct_answers", []):
        attempts_left = attempt["attempts_left"]
        if attempts_left == 0:
            await update.message.reply_text(
                "❌ Risposta sbagliata, hai esaurito i tentativi per oggi! Riprova domani."
            )
        else:
            await update.message.reply_text(
                f"❌ Risposta sbagliata, riprova! Hai {attempts_left} tentativi rimasti."
            )
        return

    points = points_for_difficulty(challenge.get("difficulty"))
    # Il bonus del primo va assegnato una volta sola: chi vince la transazione lo prende.
    bonus = 1 if firebase_service.claim_daily_first_correct(day_iso) else 0
    total_points = points + bonus

    firebase_service.register_correct_guess(user_id, total_points, bonus, day_iso)

    bonus_message = f"💎 Bonus: +{bonus} punto perchè sei il primo ad indovinare!" if bonus else ""
    await update.message.reply_text(
        f"✅ Corretto! Hai guadagnato {total_points} punti.\n{bonus_message}"
    )


def _attempt_error_message(reason):
    return {
        "not_registered": "❗ Devi registrarti prima di giocare! Usa /start.",
        "already_guessed": "✅ Hai già indovinato oggi! Torna domani per una nuova sfida.",
        "no_attempts": "❌ Hai esaurito i tentativi per oggi! Riprova domani.",
    }.get(reason, "❗ Non è stato possibile registrare il tentativo, riprova.")
