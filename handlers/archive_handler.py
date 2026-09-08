"""Archivio: rigiocare le sfide dei giorni passati.

Serve a chi salta un giorno — che in un gioco quotidiano e' la ragione principale per cui
si smette. Le sfide d'archivio **non danno punti**: rigiocare il passato non deve permettere
di scalare la classifica. Si tiene solo il conto di quante se ne sono recuperate.

Come si risponde: aprire un giorno mette l'utente "in modalita' archivio" (`archive_day` sul
documento utente, non in memoria: su Cloud Run l'istanza puo' sparire fra un messaggio e
l'altro). Da quel momento i messaggi liberi valgono per quella sfida, finche' non la si
risolve o non si torna a oggi con /oggi.

Qui, a differenza della sfida del giorno, la risposta si puo' rivelare: e' gia' passata.
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from handlers.legend_handler import legend_keyboard
from services import firebase_service
from services.daily_challenge import challenge_number
from services.dates import to_display
from services.difficulty import points_for_difficulty
from services.guess_feedback import build_comparison, comparison_text
from services.i18n import difficulty_label, resolve_language, t
from services.matching import find_match
from services.path_image import render_career_path_image
from services.share import share_text, share_url

MAX_ARCHIVE_ATTEMPTS = 3
ARCHIVE_DAYS = 10
CALLBACK_PREFIX = "arch_"
BACK_TO_TODAY = "arch_today"


def _lang_for(update: Update, user_data=None):
    if user_data and user_data.get("language"):
        return user_data["language"]
    return resolve_language(getattr(update.effective_user, "language_code", None))


def _keyboard(days, solved_days, lang):
    buttons = []
    row = []
    for day in days:
        mark = " ✅" if day in solved_days else ""
        row.append(InlineKeyboardButton(f"{to_display(day)}{mark}", callback_data=f"{CALLBACK_PREFIX}{day}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(t(lang, "archive.button_today"), callback_data=BACK_TO_TODAY)])
    return InlineKeyboardMarkup(buttons)


async def archive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = firebase_service.get_user_data(user_id)
    lang = _lang_for(update, user_data)

    if not user_data:
        await update.effective_message.reply_text(t(lang, "archive.not_registered"))
        return

    past = firebase_service.get_past_daily_paths(limit=ARCHIVE_DAYS)
    days = [doc.get("day") for doc in past if doc.get("day")]
    if not days:
        await update.effective_message.reply_text(t(lang, "archive.empty"))
        return

    solved_days = firebase_service.get_solved_archive_days(user_id)
    await update.effective_message.reply_text(
        t(lang, "archive.title"),
        reply_markup=_keyboard(days, solved_days, lang),
        parse_mode="HTML",
    )


async def archive_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    user_data = firebase_service.get_user_data(user_id)
    lang = _lang_for(update, user_data)

    if query.data == BACK_TO_TODAY:
        firebase_service.set_archive_day(user_id, None)
        await query.message.reply_text(t(lang, "archive.exited"))
        return

    day_iso = query.data[len(CALLBACK_PREFIX):]
    challenge = firebase_service.get_daily_path(day_iso)
    if not challenge:
        await query.message.reply_text(t(lang, "archive.missing_day"))
        return

    result = firebase_service.get_archive_result(user_id, day_iso)
    if result and result.get("solved"):
        await query.message.reply_text(t(lang, "archive.already_solved"))
        return

    firebase_service.set_archive_day(user_id, day_iso)
    await _send_challenge(query.message, challenge, day_iso, lang)


async def _send_challenge(message, challenge, day_iso, lang):
    career_path = challenge.get("career_path")
    caption = t(lang, "archive.opened", date=to_display(day_iso))

    if not career_path:
        await message.reply_text(caption)
        return

    photo = render_career_path_image(
        career_path,
        title=t(lang, "image.path_title"),
        subtitle=t(lang, "image.path_subtitle", stops=len(career_path)),
        badge=difficulty_label(lang, challenge.get("difficulty")).upper(),
        footer=f"{to_display(day_iso)}  ({points_for_difficulty(challenge.get('difficulty'))})",
        lang=lang,
    )
    await message.reply_photo(photo=photo, caption=caption, reply_markup=legend_keyboard(lang))


async def back_to_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/oggi: esce da qualunque partita che non sia quella di oggi - archivio, allenamento o
    evento. E' un comando solo perche' all'utente la differenza non interessa: vuole tornare
    alla sfida del giorno."""
    user_id = update.effective_user.id
    user_data = firebase_service.get_user_data(user_id)
    lang = _lang_for(update, user_data)

    if not user_data:
        await update.effective_message.reply_text(t(lang, "archive.not_registered"))
        return

    # Le tre sessioni si escludono a vicenda (services/firebase_service.py), quindi al
    # massimo una di queste e' vera e il messaggio di uscita non e' mai ambiguo.
    if user_data.get("archive_day"):
        firebase_service.set_archive_day(user_id, None)
        message_key = "archive.exited"
    elif user_data.get("training_key"):
        firebase_service.clear_training_key(user_id)
        message_key = "training.exited"
    elif user_data.get("event_key"):
        firebase_service.clear_event_key(user_id)
        message_key = "events.exited"
    else:
        await update.effective_message.reply_text(t(lang, "archive.not_in_archive"))
        return

    await update.effective_message.reply_text(t(lang, message_key))


async def process_archive_answer(update: Update, context: ContextTypes.DEFAULT_TYPE, user_answer, user_data):
    """Tentativo su una sfida d'archivio. Chiamata dal flusso normale delle risposte quando
    l'utente ha una partita d'archivio aperta."""
    message = update.effective_message
    user_id = update.effective_user.id
    lang = _lang_for(update, user_data)
    day_iso = user_data.get("archive_day")

    challenge = firebase_service.get_daily_path(day_iso)
    if not challenge:
        firebase_service.set_archive_day(user_id, None)
        await message.reply_text(t(lang, "archive.missing_day"))
        return

    attempt = firebase_service.begin_archive_attempt(user_id, day_iso, MAX_ARCHIVE_ATTEMPTS)
    if not attempt["ok"]:
        key = "archive.already_solved" if attempt["reason"] == "already_solved" else "archive.no_attempts"
        await message.reply_text(t(lang, key))
        return

    if find_match(user_answer, challenge.get("correct_answers", [])):
        firebase_service.register_archive_solved(user_id, day_iso, attempt["attempts_used"])
        firebase_service.set_archive_day(user_id, None)
        await message.reply_text(
            t(lang, "archive.correct", date=to_display(day_iso), attempts=attempt["attempts_used"]),
            reply_markup=_share_keyboard(lang, day_iso, attempt["attempts_used"], solved=True),
        )
        return

    # Stesso confronto della sfida di oggi: un tentativo sbagliato deve lasciare qualcosa
    # anche qui, altrimenti l'archivio e' piu' difficile del gioco vero.
    comparison = comparison_text(lang, build_comparison(user_answer, challenge.get("player_id")))

    if attempt["attempts_left"] > 0:
        await message.reply_text(
            t(lang, "archive.wrong", attempts_left=attempt["attempts_left"]) + comparison
        )
        return

    # Tentativi finiti: la sfida e' passata, la risposta si puo' dire.
    answer = firebase_service.get_display_name_for_day(day_iso) or "?"
    firebase_service.set_archive_day(user_id, None)
    await message.reply_text(
        t(lang, "archive.wrong_last", answer=answer),
        reply_markup=_share_keyboard(lang, day_iso, attempt["attempts_used"], solved=False),
    )


def _share_keyboard(lang, day_iso, attempts_used, solved):
    """Come per la sfida di oggi, ma marcata come recuperata dall'archivio: chi la incolla
    in un gruppo non deve sembrare che abbia risolto quella di oggi. La striscia non
    c'entra (l'archivio non la muove) e non compare."""
    text = share_text(
        lang, challenge_number(day_iso), attempts_used, MAX_ARCHIVE_ATTEMPTS,
        solved=solved, archive=True,
    )
    url = share_url(text)
    if not url:
        return None
    return InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "share.button"), url=url)]])
