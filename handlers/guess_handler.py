"""Tentativi sulla sfida del giorno.

Due porte d'ingresso, un solo percorso: `/guess <nome>` e il **messaggio libero** in chat
privata (scrivere il nome e basta). La seconda esiste perche' digitare il comando ad ogni
tentativo era l'attrito piu' inutile del gioco; un messaggio che non somiglia a un nome
(link, frasi lunghe) non consuma un tentativo, viene solo spiegato come si gioca.

Il confronto con la risposta passa da services/matching.py: un refuso non brucia piu' un
tentativo. Non si dice mai qual era la risposta giusta, nemmeno per suggerire la
correzione: sarebbe rivelare la soluzione.
"""
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from handlers.archive_handler import process_archive_answer
from handlers.group_handler import process_group_answer
from handlers.training_handler import process_training_answer
from services import firebase_service
from services.daily_challenge import MAX_ATTEMPTS, challenge_number, get_today_challenge
from services.dates import today_iso
from services.difficulty import points_for_difficulty
from services.guess_feedback import build_comparison, comparison_text
from services.i18n import resolve_language, t
from services.matching import find_match, looks_like_an_answer
from services.share import share_text, share_url


def _language_for(update: Update, user_data=None):
    client_lang = resolve_language(getattr(update.effective_user, "language_code", None))
    return (user_data or {}).get("language") or client_lang


def _answer_from_command(text):
    """Il testo dopo il comando, gestendo anche la forma `/guess@nome_bot Messi`."""
    if not text:
        return ""
    _, _, remainder = text.partition(" ")
    return remainder.strip()


async def guess(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user_answer = _answer_from_command(message.text or "")

    # In un gruppo /guess non e' un tentativo sulla sfida di oggi (che rovinerebbe la
    # giornata a chi legge) ma la risposta al round del gruppo, su una sfida gia' passata.
    if message.chat.type != "private":
        await process_group_answer(update, context, user_answer)
        return

    if not user_answer:
        await message.reply_text(t(_language_for(update), "guess.missing_answer"))
        return

    await process_answer(update, context, user_answer)


async def free_text_guess(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qualsiasi messaggio di testo in chat privata e' un tentativo, se ne ha la forma."""
    message = update.effective_message
    text = (message.text or "").strip()

    if not looks_like_an_answer(text):
        await message.reply_text(t(_language_for(update), "guess.free_text_hint"))
        return

    await process_answer(update, context, text)


async def process_answer(update: Update, context: ContextTypes.DEFAULT_TYPE, user_answer):
    message = update.effective_message
    lang = _language_for(update)

    if message.chat.type != "private":
        await message.reply_text(t(lang, "common.private_only"))
        return

    user_id = update.effective_user.id
    user_data = firebase_service.get_user_data(user_id)
    lang = _language_for(update, user_data)

    # Con una sfida d'archivio (o di allenamento) aperta la risposta vale per quella: e'
    # l'unico modo di rispondere a una sfida passata senza inventare un secondo comando.
    if user_data and user_data.get("archive_day"):
        await process_archive_answer(update, context, user_answer, user_data)
        return

    if user_data and user_data.get("training_key"):
        await process_training_answer(update, context, user_answer, user_data)
        return

    challenge = get_today_challenge()
    if not challenge:
        await message.reply_text(t(lang, "common.no_challenge"))
        return

    day_iso = today_iso()

    # Il tentativo viene consumato in transazione: contatori corretti anche con due risposte
    # inviate nello stesso istante, e nessun bisogno di azzerarli con un job notturno.
    attempt = firebase_service.begin_guess_attempt(user_id, day_iso, MAX_ATTEMPTS)
    if not attempt["ok"]:
        await message.reply_text(_attempt_error_message(lang, attempt["reason"]))
        return

    logging.info(f"[GUESS] Risposta dell'utente: {user_answer}")

    match = find_match(user_answer, challenge.get("correct_answers", []))
    if not match:
        attempts_left = attempt["attempts_left"]
        # Il confronto con il calciatore scritto (nazionalita', ruolo, eta') e' l'unica cosa
        # che l'utente si porta via da un tentativo sbagliato: senza, tre tentativi su una
        # sfida difficile sono tre nomi sparati a caso.
        comparison = comparison_text(lang, build_comparison(user_answer, challenge.get("player_id")))
        if attempts_left == 0:
            # A tentativi finiti la card si condivide comunque: "X/3" e' meta' del gioco in
            # un gruppo, e non rivela niente della soluzione.
            await message.reply_text(
                t(lang, "guess.wrong_last") + comparison,
                reply_markup=_share_keyboard(lang, attempt["attempts_used"], streak=0, solved=False),
            )
        else:
            await message.reply_text(t(lang, "guess.wrong_remaining", attempts_left=attempts_left) + comparison)
        return

    points = points_for_difficulty(challenge.get("difficulty"))
    # Il bonus del primo va assegnato una volta sola: chi vince la transazione lo prende.
    bonus = 1 if firebase_service.claim_daily_first_correct(day_iso) else 0

    # I punti della striscia li calcola la transazione che la aggiorna: qui non sappiamo (e
    # non possiamo sapere senza leggere) a che giorno consecutivo siamo arrivati.
    result = firebase_service.register_correct_guess(user_id, points + bonus, bonus, day_iso) or {}
    awarded = result.get("points_awarded", points + bonus)
    streak = result.get("current_streak", 0)

    # Le leghe private tengono il loro punteggio: i codici sono gia' sul documento utente,
    # quindi non serve nessuna query per sapere dove sommarli.
    firebase_service.add_points_to_leagues(
        user_id, (user_data or {}).get("leagues", []), awarded, name=update.effective_user.first_name
    )

    bonus_message = t(lang, "guess.bonus", bonus=bonus) if bonus else ""
    text = t(lang, "guess.correct", points=awarded, bonus_message=bonus_message)
    if result.get("streak_bonus"):
        text += t(lang, "guess.streak_bonus", streak=streak, bonus=result["streak_bonus"])
    elif streak > 1:
        text += t(lang, "guess.streak", streak=streak)
    if match["typo"]:
        text += t(lang, "guess.typo_note", written=user_answer)

    await message.reply_text(text, reply_markup=_share_keyboard(lang, attempt["attempts_used"], streak))


def _share_keyboard(lang, attempts_used, streak, solved=True):
    """Il risultato in quadratini, da incollare in un gruppo senza rivelare la risposta.

    Vale anche per chi non ci e' arrivato (`solved=False`, cioe' "X/3"): la sconfitta e'
    meta' di quello che si condivide in un gruppo, ed e' l'unica riga che non puo'
    spoilerare niente."""
    text = share_text(lang, challenge_number(), attempts_used, MAX_ATTEMPTS, solved=solved, streak=streak)
    url = share_url(text)
    if not url:
        return None
    return InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "share.button"), url=url)]])


def _attempt_error_message(lang, reason):
    key = {
        "not_registered": "guess.error.not_registered",
        "already_guessed": "guess.error.already_guessed",
        "no_attempts": "guess.error.no_attempts",
    }.get(reason, "guess.error.default")
    return t(lang, key)
