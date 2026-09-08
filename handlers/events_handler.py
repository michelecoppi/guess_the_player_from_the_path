from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Update
from telegram.ext import ContextTypes

from services import firebase_service
from services.dates import to_display, today_iso
from services.i18n import content_text, resolve_language, t
from services.matching import find_match, normalize
from services.path_image import render_career_path_image, render_event_banner

MAX_EVENT_ATTEMPTS = 3
MAX_CAREER_ANSWERS_PER_ATTEMPT = 5


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
    elif data == "event_leaderboard":
        # La classifica si legge sempre fresca: e' l'unica parte dell'evento che cambia
        # mentre l'utente naviga.
        podium = firebase_service.get_event_leaderboard(event["code"], limit=3)
        message = get_event_leaderboard_message(podium, lang)
        image_url = event.get("leaderboard_img") or _event_banner(event, lang, "image.badge_leaderboard")
        active = "leaderboard"
    else:
        return

    keyboard = [
        [
            InlineKeyboardButton(t(lang, "events.button_home") + (" ✅" if active == "home" else ""), callback_data="event_home"),
            InlineKeyboardButton(t(lang, "events.button_player") + (" ✅" if active == "player" else ""), callback_data="event_player"),
            InlineKeyboardButton(t(lang, "events.button_leaderboard") + (" ✅" if active == "leaderboard" else ""), callback_data="event_leaderboard"),
        ]
    ]

    await query.edit_message_media(
        media=InputMediaPhoto(media=image_url, caption=message, parse_mode="HTML"),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


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
        )
    elif today_data.get("image_url"):
        image_url = today_data["image_url"]
    else:
        image_url = _event_banner(event, lang, "image.badge_player")

    points = today_data.get("points", 1)
    first_correct_user = today_data.get("first_correct_user", False)
    bonus_msg = t(lang, "events.bonus_available") if not first_correct_user else t(lang, "events.bonus_taken")

    event_type = event.get("type", "path")

    if event_type == "career":
        message = t(
            lang, "events.player_message.career",
            min_correct=today_data.get("min_correct", 1),
            player_name=today_data.get("player_name"),
            points=points,
            bonus_msg=bonus_msg,
        )
    elif event_type == "father_son":
        message = t(lang, "events.player_message.father_son", points=points, bonus_msg=bonus_msg)
    elif event_type == "transfer_guess":
        message = t(lang, "events.player_message.transfer_guess", points=points, bonus_msg=bonus_msg)
    elif event_type == "path":
        message = t(lang, "events.player_message.path", points=points, bonus_msg=bonus_msg)
    else:
        message = t(lang, "events.player_message.default", points=points, bonus_msg=bonus_msg)

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
    if lang is None:
        lang = _lang_for(update.effective_user)

    if update.effective_chat.type != "private":
        await update.effective_message.reply_text(t(lang, "common.private_only"))
        return

    user = update.effective_user
    guess = " ".join(context.args).strip().lower()

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
        await update.effective_message.reply_text(feedback)
        return

    bonus = 1 if firebase_service.claim_event_first_correct(event_code, day_iso) else 0
    earned_points = today_data.get("points", 1) + bonus
    firebase_service.register_event_correct_guess(event_code, user.id, earned_points, day_iso)

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
