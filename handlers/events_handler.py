"""Eventi tematici: la home a schede, la sfida del giorno dell'evento e i tentativi.

Fino a ieri gli eventi erano l'unica modalita' in cui bisognava ancora scrivere un comando
per rispondere (`/events Messi`), mentre dappertutto altrove bastava scrivere il nome. Ora
aprire la scheda "Giocatore" apre una **sessione** sul documento utente (`event_key`,
come `archive_day` e `training_key`): da quel momento i messaggi liberi valgono per
l'evento, e si torna alla sfida di oggi con /today. Il comando resta, per chi lo ha
imparato.

La chiave porta con se' anche il **giorno** (`codice:2026-09-08`): a mezzanotte l'immagine
dell'evento cambia, quindi una sessione di ieri non deve rispondere per la sfida di oggi.
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Update
from telegram.ext import ContextTypes

from handlers.legend_handler import legend_keyboard
from services import firebase_service
from services.dates import to_display, today_iso
from services.guess_feedback import build_comparison, comparison_text
from services.i18n import content_text, resolve_language, t
from services.matching import find_match, normalize
from services.path_image import render_career_path_image, render_event_banner

MAX_EVENT_ATTEMPTS = 3
MAX_CAREER_ANSWERS_PER_ATTEMPT = 5

# I tipi di evento in cui la risposta e' un **calciatore del dataset**: solo per questi ha
# senso il confronto per nazionalita'/ruolo/eta' dopo un tentativo sbagliato. Negli eventi
# "career" si risponde con delle squadre, e nei "father_son" con una coppia che nel dataset
# non c'e': li' il confronto non avrebbe niente su cui lavorare.
PLAYER_ANSWER_TYPES = ("path", "transfer_guess")


async def events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = _lang_for(update.effective_user)

    event = firebase_service.get_current_event()
    if not event:
        await update.effective_message.reply_text(t(lang, "events.no_active"))
        return
    if context.args:
        await process_event_guess(update, context, event, lang)
        return

    message = get_event_home_message(event, lang)
    image_url = event.get("event_img") or _event_banner(event, lang)

    keyboard = [
        [
            InlineKeyboardButton(t(lang, "events.button_home") + " ✅", callback_data="event_home"),
            InlineKeyboardButton(t(lang, "events.button_player"), callback_data="event_player"),
            InlineKeyboardButton(t(lang, "events.button_leaderboard"), callback_data="event_leaderboard"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.effective_message.reply_photo(
        photo=image_url,
        caption=message,
        reply_markup=reply_markup,
        parse_mode="HTML"
    )

    context.user_data['current_event'] = event
    context.user_data['lang'] = lang


async def handle_event_navigation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get('lang') or _lang_for(query.from_user)

    event = context.user_data.get('current_event')
    if not event:
        await query.delete_message()
        await query.message.reply_text(t(lang, "events.no_active_nav"))
        return

    data = query.data
    image_url = None

    if data == "event_home":
        message = get_event_home_message(event, lang)
        image_url = event.get("event_img") or _event_banner(event, lang)
        active = "home"
    elif data == "event_player":
        message, image_url = get_today_player_message(event, lang)
        active = "player"
        # Aprire la scheda del giocatore apre la sessione: da qui in poi un messaggio
        # libero e' un tentativo su questo evento, non sulla sfida del giorno.
        if (event.get("daily_data") or {}).get(today_iso()):
            firebase_service.set_event_key(update.effective_user.id, session_key(event["code"]))
    elif data == "event_leaderboard":
        # La classifica si legge sempre fresca: e' l'unica parte dell'evento che cambia
        # mentre l'utente naviga.
        podium = firebase_service.get_event_leaderboard(event["code"], limit=3)
        message = get_event_leaderboard_message(podium, lang)
        image_url = event.get("leaderboard_img") or _event_banner(event, lang, "image.badge_leaderboard")
        active = "leaderboard"
    else:
        return

    tabs = [
        InlineKeyboardButton(t(lang, "events.button_home") + (" ✅" if active == "home" else ""), callback_data="event_home"),
        InlineKeyboardButton(t(lang, "events.button_player") + (" ✅" if active == "player" else ""), callback_data="event_player"),
        InlineKeyboardButton(t(lang, "events.button_leaderboard") + (" ✅" if active == "leaderboard" else ""), callback_data="event_leaderboard"),
    ]

    # La legenda solo sulla scheda del giocatore, e solo quando l'immagine e' davvero un
    # percorso di carriera: sotto un banner o una foto di coppia non spiegherebbe niente.
    shows_career_path = active == "player" and bool(
        ((event.get("daily_data") or {}).get(today_iso()) or {}).get("career_path")
    )
    reply_markup = (
        legend_keyboard(lang, extra_rows=[tabs]) if shows_career_path else InlineKeyboardMarkup([tabs])
    )

    await query.edit_message_media(
        media=InputMediaPhoto(media=image_url, caption=message, parse_mode="HTML"),
        reply_markup=reply_markup,
    )


def session_key(event_code, day_iso=None):
    """La chiave della sessione: quale evento e **quale giornata** dell'evento.

    Il giorno c'e' perche' a mezzanotte la sfida dell'evento cambia: senza, la sessione
    aperta ieri risponderebbe per l'immagine di oggi, che l'utente non ha nemmeno visto."""
    return f"{event_code}:{day_iso or today_iso()}"


def _event_name(event, lang):
    """Il nome dell'evento nella lingua di chi guarda: sta nel documento dell'evento
    (`name_i18n`), non fra le traduzioni, ed e' l'italiano se manca."""
    return content_text(event, "name", lang, default=t(lang, "events.unnamed"))


def _event_banner(event, lang, badge_key="image.badge_event"):
    return render_event_banner(
        _event_name(event, lang),
        content_text(event, "description", lang) if badge_key == "image.badge_event" else "",
        badge_text=t(lang, badge_key),
    )


def _lang_for(telegram_user):
    user_data = firebase_service.get_user_data(telegram_user.id)
    if user_data and user_data.get("language"):
        return user_data["language"]
    return resolve_language(getattr(telegram_user, "language_code", None))


def get_event_home_message(event, lang="it"):
    name = _event_name(event, lang)
    description = content_text(event, "description", lang)
    dates = event.get("dates", [])
    end_date = to_display(dates[-1]) if dates else t(lang, "events.no_end_date")

    event_type = event.get("type", "path")
    gameplay_line = t(lang, {
        "career": "events.gameplay.career",
        "path": "events.gameplay.path",
        "father_son": "events.gameplay.father_son",
        "transfer_guess": "events.gameplay.transfer_guess",
    }.get(event_type, "events.gameplay.default"))

    return t(lang, "events.home_message", name=name, description=description, end_date=end_date, gameplay_line=gameplay_line)


def get_today_player_message(event, lang="it"):
    today_data = (event.get("daily_data") or {}).get(today_iso())

    if not today_data:
        return t(lang, "events.no_player_today"), None

    career_path = today_data.get("career_path")
    if career_path:
        image_url = render_career_path_image(
            career_path,
            title=t(lang, "image.path_title"),
            subtitle=t(lang, "image.path_subtitle", stops=len(career_path)),
            badge=_event_name(event, lang).upper()[:22] or None,
            footer=_event_name(event, lang),
            lang=lang,
        )
    elif today_data.get("image_url"):
        image_url = today_data["image_url"]
    else:
        image_url = _event_banner(event, lang, "image.badge_player")

    points = today_data.get("points", 1)
    first_correct_user = today_data.get("first_correct_user", False)
    bonus_msg = t(lang, "events.bonus_available") if not first_correct_user else t(lang, "events.bonus_taken")

    event_type = event.get("type", "path")

    key = {
        "career": "events.player_message.career",
        "father_son": "events.player_message.father_son",
        "transfer_guess": "events.player_message.transfer_guess",
        "path": "events.player_message.path",
    }.get(event_type, "events.player_message.default")

    message = t(
        lang, key,
        points=points,
        bonus_msg=bonus_msg,
        attempts=MAX_EVENT_ATTEMPTS,
        max_answers=MAX_CAREER_ANSWERS_PER_ATTEMPT,
        min_correct=today_data.get("min_correct", 1),
        player_name=today_data.get("player_name"),
    )
    return message, image_url


def get_event_leaderboard_message(podium, lang="it"):
    if not podium:
        return t(lang, "events.no_participants")

    message = t(lang, "events.leaderboard_title")
    medals = ["🥇", "🥈", "🥉"]

    for i, user in enumerate(podium):
        name = user.get("name", t(lang, "events.unknown_user"))
        points = user.get("points", 0)
        medal = medals[i] if i < len(medals) else "🏅"
        message += f"{medal} <b>{name}</b> - {points} {t(lang, 'top.points_suffix')}\n"

    message += t(lang, "events.leaderboard_footer")

    return message


def evaluate_event_guess(event_type, guess, today_data):
    """Separata dal resto per poterla testare senza Telegram e senza Firestore.
    Ritorna (corretto, quante risposte azzeccate, totale risposte).

    Il confronto e' lo stesso della sfida giornaliera (services/matching.py): tollera
    accenti e refusi. Per gli eventi "career" si contano le **risposte azzeccate**, non le
    parole scritte: elencare due volte la stessa squadra non fa punteggio."""
    correct_answers = today_data.get("correct_answers", [])

    if event_type != "career":
        return find_match(guess, correct_answers) is not None, None, len(correct_answers)

    matched_answers = set()
    for part in guess.split(","):
        match = find_match(part, correct_answers)
        if match:
            matched_answers.add(normalize(match["answer"]))

    matched = len(matched_answers)
    min_correct = today_data.get("min_correct", len(correct_answers))
    return matched >= min_correct, matched, len(correct_answers)


async def process_event_guess(update: Update, context: ContextTypes.DEFAULT_TYPE, event: dict, lang=None):
    """`/events <risposta>`: il modo classico di rispondere, tenuto per chi lo ha imparato."""
    await _process_guess(update, event, " ".join(context.args), lang)


async def process_event_answer(update: Update, context: ContextTypes.DEFAULT_TYPE, user_answer, user_data):
    """Tentativo dal messaggio libero, quando l'utente ha una sessione evento aperta.

    La chiama il flusso normale delle risposte (handlers/guess_handler.py), come per
    l'archivio e l'allenamento."""
    lang = user_data.get("language") or _lang_for(update.effective_user)
    key = user_data.get("event_key") or ""
    event_code, _, day_iso = key.partition(":")

    event = firebase_service.get_current_event()
    # La sessione vale per **quella** giornata di **quell'** evento: se l'evento e' finito o
    # se e' passata la mezzanotte, la sfida che l'utente ha davanti non c'e' piu'.
    if not event or event.get("code") != event_code or day_iso != today_iso():
        firebase_service.clear_event_key(update.effective_user.id)
        await update.effective_message.reply_text(t(lang, "events.not_open"))
        return

    await _process_guess(update, event, user_answer, lang, close_session=True)


async def _process_guess(update: Update, event: dict, raw_answer, lang=None, close_session=False):
    """`close_session` chiude la sessione evento quando la risposta e' giusta. Vale solo
    per il testo libero: chi risponde con `/events <nome>` una sessione non l'ha mai
    aperta, e chiuderla sarebbe una scrittura per niente."""
    if lang is None:
        lang = _lang_for(update.effective_user)

    if update.effective_chat.type != "private":
        await update.effective_message.reply_text(t(lang, "common.private_only"))
        return

    user = update.effective_user
    guess = (raw_answer or "").strip().lower()

    event_code = event["code"]
    day_iso = today_iso()
    today_data = (event.get("daily_data") or {}).get(day_iso)
    if not today_data:
        await update.effective_message.reply_text(t(lang, "events.no_daily_challenge"))
        return

    event_type = event.get("type", "path")

    if event_type == "career" and len([p for p in guess.split(",") if p.strip()]) > MAX_CAREER_ANSWERS_PER_ATTEMPT:
        await update.effective_message.reply_text(t(lang, "events.max_answers", max_answers=MAX_CAREER_ANSWERS_PER_ATTEMPT))
        return

    attempt = firebase_service.begin_event_attempt(
        event_code, user.id, user.first_name, day_iso, MAX_EVENT_ATTEMPTS
    )
    if not attempt["ok"]:
        await update.effective_message.reply_text(_event_attempt_error(lang, attempt["reason"]))
        return

    is_correct, matched, total_answers = evaluate_event_guess(event_type, guess, today_data)

    if not is_correct:
        feedback = t(lang, "events.wrong", used=attempt["attempts_used"], max_attempts=MAX_EVENT_ATTEMPTS)
        if event_type == "career":
            feedback += t(lang, "events.wrong_career_extra", matched=matched, total=total_answers)
        # Lo stesso confronto della sfida del giorno, dove la risposta e' un calciatore:
        # senza, un tentativo sbagliato dentro un evento lascia meno di uno fuori.
        if event_type in PLAYER_ANSWER_TYPES:
            feedback += comparison_text(lang, build_comparison(guess, today_data.get("player_id")))
        await update.effective_message.reply_text(feedback)
        return

    bonus = 1 if firebase_service.claim_event_first_correct(event_code, day_iso) else 0
    earned_points = today_data.get("points", 1) + bonus
    firebase_service.register_event_correct_guess(event_code, user.id, earned_points, day_iso)

    # Indovinata: la sessione si chiude da sola, cosi' i messaggi successivi tornano a
    # valere per la sfida del giorno senza dover ricordarsi di /today.
    if close_session:
        firebase_service.clear_event_key(user.id)

    bonus_tag = t(lang, "events.bonus_tag") if bonus else ""
    await update.effective_message.reply_text(t(lang, "events.correct", points=earned_points, bonus_tag=bonus_tag))


def _event_attempt_error(lang, reason):
    key = {
        "already_guessed": "events.error.already_guessed",
        "no_attempts": "events.error.no_attempts",
    }.get(reason, "events.error.default")
    if reason == "no_attempts":
        return t(lang, key, max_attempts=MAX_EVENT_ATTEMPTS)
    return t(lang, key)
