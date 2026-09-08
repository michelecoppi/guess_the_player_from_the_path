"""Allenamento: sfide a raffica, senza punti e senza calendario.

Chi installa il bot oggi gioca **una** partita e poi aspetta ventiquattro ore: e' il minuto
in cui si decide se restare, ed era vuoto. L'archivio copre solo gli ultimi dieci giorni ed
e' una lista da sfogliare; qui invece si preme un bottone e arriva un'altra sfida, per
sempre.

Il materiale arriva da services/practice_content.py, che non puo' spoilerare la sfida del
giorno: o e' un calciatore del **pool riservato** (che come sfida del giorno non esce mai),
o e' una sfida **gia' passata**.

I tentativi sono cinque e non infiniti. Non per avarizia: un campo di testo che accetta nomi
all'infinito e risponde "stessa nazionalita', ruolo diverso" e' un modo comodo per sondare
il dataset, e cinque tentativi con la risposta svelata alla fine fanno anche una partita
piu' bella di una senza fine.
"""
import logging

from telegram import InlineKeyboardButton, Update
from telegram.ext import ContextTypes

from handlers.legend_handler import legend_keyboard
from services import firebase_service, practice_content
from services.difficulty import points_for_difficulty
from services.guess_feedback import build_comparison, comparison_text
from services.i18n import difficulty_label, resolve_language, t
from services.matching import find_match
from services.path_image import render_career_path_image

MAX_TRAINING_ATTEMPTS = 5

NEXT = "trn_next"
REVEAL = "trn_reveal"


def _lang_for(update: Update, user_data=None):
    if user_data and user_data.get("language"):
        return user_data["language"]
    return resolve_language(getattr(update.effective_user, "language_code", None))


def _keyboard(lang, with_reveal=True):
    rows = [[InlineKeyboardButton(t(lang, "training.button_next"), callback_data=NEXT)]]
    if with_reveal:
        rows[0].append(InlineKeyboardButton(t(lang, "training.button_reveal"), callback_data=REVEAL))
    return legend_keyboard(lang, extra_rows=rows)


async def training(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/allenamento: apre (o cambia) una sfida di allenamento."""
    message = update.effective_message
    user_id = update.effective_user.id
    user_data = firebase_service.get_user_data(user_id)
    lang = _lang_for(update, user_data)

    if message.chat.type != "private":
        await message.reply_text(t(lang, "training.private_only"))
        return

    if not user_data:
        await message.reply_text(t(lang, "training.not_registered"))
        return

    await _serve_new_challenge(message, user_id, user_data.get("training_key"), lang)


async def _serve_new_challenge(message, user_id, exclude_key, lang):
    challenge = practice_content.pick(exclude_keys=[exclude_key] if exclude_key else ())
    if not challenge or not challenge.get("career_path"):
        await message.reply_text(t(lang, "training.empty"))
        return

    firebase_service.set_training_key(user_id, challenge["key"])

    difficulty = difficulty_label(lang, challenge.get("difficulty"))
    career_path = challenge["career_path"]
    photo = render_career_path_image(
        career_path,
        title=t(lang, "image.path_title"),
        subtitle=t(lang, "image.path_subtitle", stops=len(career_path)),
        badge=difficulty.upper(),
        footer=f"{difficulty} ({points_for_difficulty(challenge.get('difficulty'))})",
    )
    await message.reply_photo(
        photo=photo,
        caption=t(lang, "training.opened", attempts=MAX_TRAINING_ATTEMPTS),
        reply_markup=_keyboard(lang),
        parse_mode="HTML",
    )


async def training_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    user_data = firebase_service.get_user_data(user_id) or {}
    lang = _lang_for(update, user_data)

    if query.data == NEXT:
        await _serve_new_challenge(query.message, user_id, user_data.get("training_key"), lang)
        return

    # Rivela: qui la risposta si puo' dire sempre, perche' quella sfida non e' in gioco per
    # nessuno - o e' di un calciatore riservato all'allenamento, o e' una giornata passata.
    challenge = practice_content.load(user_data.get("training_key"))
    if not challenge:
        await query.message.reply_text(t(lang, "training.not_open"))
        return

    firebase_service.clear_training_key(user_id)
    await query.message.reply_text(
        t(lang, "training.revealed", answer=challenge["answer"]),
        reply_markup=_keyboard(lang, with_reveal=False),
    )


async def process_training_answer(update: Update, context: ContextTypes.DEFAULT_TYPE, user_answer, user_data):
    """Tentativo su una sfida di allenamento. La chiama il flusso normale delle risposte
    quando l'utente ha una sessione aperta."""
    message = update.effective_message
    user_id = update.effective_user.id
    lang = _lang_for(update, user_data)

    challenge = practice_content.load(user_data.get("training_key"))
    if not challenge:
        firebase_service.clear_training_key(user_id)
        await message.reply_text(t(lang, "training.gone"))
        return

    logging.info(f"[TRAINING] {user_id} su {challenge['key']}: {user_answer}")
    attempts = user_data.get("training_attempts", 0) + 1

    if find_match(user_answer, challenge.get("correct_answers", [])):
        firebase_service.register_training_solved(user_id)
        await message.reply_text(
            t(lang, "training.correct", attempts=attempts),
            reply_markup=_keyboard(lang, with_reveal=False),
        )
        return

    firebase_service.register_training_attempt(user_id)
    comparison = comparison_text(lang, build_comparison(user_answer, challenge.get("player_id")))
    attempts_left = MAX_TRAINING_ATTEMPTS - attempts

    if attempts_left > 0:
        await message.reply_text(t(lang, "training.wrong", attempts_left=attempts_left) + comparison)
        return

    firebase_service.clear_training_key(user_id)
    await message.reply_text(
        t(lang, "training.wrong_last", answer=challenge["answer"]) + comparison,
        reply_markup=_keyboard(lang, with_reveal=False),
    )
