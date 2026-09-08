"""Partita di gruppo: un round alla volta, vince chi risponde per primo.

Non e' la sfida di oggi ripubblicata nel gruppo, ed e' la scelta che regge tutto il resto:
la risposta comparirebbe in chiaro davanti a chi non ha ancora giocato, e brucerebbe la
giornata anche a chi non stava guardando. Il round pesca invece dallo stesso materiale
dell'allenamento (services/practice_content.py): calciatori riservati, che come sfida del
giorno non escono mai, e sfide gia' passate, che sono pubbliche per costruzione.

Le altre tre conseguenze della stessa scelta:

- **i punti restano nel gruppo** (`group_rounds/{chat}/players/{utente}`) e non toccano ne'
  la classifica generale ne' quella del mese: un gruppo creato con un account secondario non
  sposta niente di quello che conta;
- **si risponde con `/guess`**, non a messaggio libero. Leggere i messaggi liberi di un
  gruppo vorrebbe dire spegnere la privacy mode in BotFather, cioe' ricevere *tutti* i
  messaggi di *tutti* i gruppi in cui il bot e' dentro. I comandi arrivano lo stesso;
- **non serve essersi registrati**: in gruppo non c'e' niente da salvare sull'utente, e
  chiedere /start prima di poter giocare toglierebbe alla modalita' l'unica cosa che la
  rende utile, cioe' che chi passa di li' possa rispondere e basta.
"""
import html
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from handlers.legend_handler import legend_keyboard
from services import firebase_service, practice_content
from services.difficulty import points_for_difficulty
from services.guess_feedback import build_comparison, comparison_text
from services.i18n import difficulty_label, resolve_language, t
from services.matching import find_match
from services.path_image import render_career_path_image
from services.share import bot_link

MAX_GROUP_ATTEMPTS = 3
STANDINGS_SIZE = 10
NEW_ROUND = "grp_new"


def _lang_for(update: Update):
    """In un gruppo non c'e' "la lingua della chat": si usa quella del client di chi ha
    scritto, che e' l'unica informazione vera che abbiamo."""
    return resolve_language(getattr(update.effective_user, "language_code", None))


def _display_name(user):
    return user.first_name or user.username or str(user.id)


def _safe(name):
    """I messaggi del gruppo sono in HTML e il nome lo sceglie l'utente: senza questa
    conversione basterebbe chiamarsi "<b" per far fallire ogni messaggio del round (o per
    scrivere in grassetto dentro un messaggio del bot). Sul database il nome si salva
    invece com'e': quello che va reso innocuo e' il rendering, non il dato."""
    return html.escape(name or "?")


def _challenge_keyboard(lang):
    """Sotto la sfida: la legenda e, se sappiamo qual e' il link del bot, l'invito a
    giocare anche in privato. E' da qui che il gruppo porta gente al gioco quotidiano."""
    rows = []
    link = bot_link()
    if link:
        rows.append([InlineKeyboardButton(t(lang, "group.button_private"), url=link)])
    return legend_keyboard(lang, extra_rows=rows)


async def group_challenge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/sfida: apre un round nuovo (e chiude quello in corso)."""
    message = update.effective_message
    lang = _lang_for(update)

    if message.chat.type == "private":
        await message.reply_text(t(lang, "group.private_hint"))
        return

    chat_id = message.chat.id
    previous = firebase_service.get_group_round(chat_id) or {}
    challenge = practice_content.pick(exclude_keys=previous.get("recent_keys", []))
    if not challenge or not challenge.get("career_path"):
        await message.reply_text(t(lang, "group.empty"))
        return

    round_doc = firebase_service.start_group_round(chat_id, challenge)

    difficulty = difficulty_label(lang, challenge.get("difficulty"))
    career_path = challenge["career_path"]
    photo = render_career_path_image(
        career_path,
        title=t(lang, "image.path_title"),
        subtitle=t(lang, "image.path_subtitle", stops=len(career_path)),
        badge=difficulty.upper(),
        footer=f"{difficulty} ({points_for_difficulty(challenge.get('difficulty'))})",
        lang=lang,
    )
    await message.reply_photo(
        photo=photo,
        caption=t(
            lang, "group.round_opened",
            number=round_doc["number"],
            difficulty=difficulty,
            points=points_for_difficulty(challenge.get("difficulty")),
            attempts=MAX_GROUP_ATTEMPTS,
        ),
        reply_markup=_challenge_keyboard(lang),
        parse_mode="HTML",
    )


async def process_group_answer(update: Update, context: ContextTypes.DEFAULT_TYPE, user_answer):
    """Un `/guess` arrivato da un gruppo. La chiama guess_handler."""
    message = update.effective_message
    lang = _lang_for(update)
    chat_id = message.chat.id

    round_doc = firebase_service.get_group_round(chat_id)
    if not round_doc or not round_doc.get("correct_answers"):
        await message.reply_text(t(lang, "group.no_round"))
        return

    if not user_answer:
        await message.reply_text(t(lang, "group.usage"), parse_mode="HTML")
        return

    if round_doc.get("solved_by"):
        await message.reply_text(
            t(lang, "group.already_solved", winner=_safe(round_doc.get("solved_name"))),
            parse_mode="HTML",
        )
        return

    user = update.effective_user
    name = _display_name(user)
    number = round_doc.get("number", 0)

    attempt = firebase_service.begin_group_attempt(chat_id, user.id, number, name, MAX_GROUP_ATTEMPTS)
    if not attempt["ok"]:
        await message.reply_text(t(lang, "group.no_attempts", name=_safe(name)), parse_mode="HTML")
        return

    logging.info(f"[GROUP] {chat_id} round {number}: {user.id} tenta '{user_answer}'")

    if not find_match(user_answer, round_doc.get("correct_answers", [])):
        comparison = comparison_text(lang, build_comparison(user_answer, round_doc.get("player_id")))
        await message.reply_text(
            t(lang, "group.wrong", name=_safe(name), attempts_left=attempt["attempts_left"]) + comparison,
            parse_mode="HTML",
        )
        return

    # Due risposte giuste nello stesso istante, in un gruppo, sono la norma: il round lo
    # prende chi vince la transazione, esattamente come il bonus del primo sulla sfida di
    # oggi.
    if not firebase_service.claim_group_round(chat_id, number, user.id, name):
        await message.reply_text(t(lang, "group.already_solved", winner="?"), parse_mode="HTML")
        return

    points = points_for_difficulty(round_doc.get("difficulty"))
    firebase_service.add_group_points(chat_id, user.id, name, points)
    await message.reply_text(
        t(lang, "group.correct", name=_safe(name), points=points, number=number),
        reply_markup=_challenge_keyboard(lang),
        parse_mode="HTML",
    )


async def group_standings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/classifica: la classifica di questo gruppo, che non c'entra con quella generale."""
    message = update.effective_message
    lang = _lang_for(update)

    if message.chat.type == "private":
        await message.reply_text(t(lang, "group.private_hint"))
        return

    players = firebase_service.get_group_leaderboard(message.chat.id, limit=STANDINGS_SIZE)
    if not players:
        await message.reply_text(t(lang, "group.standings_empty"))
        return

    text = t(lang, "group.standings_title")
    for position, player in enumerate(players, start=1):
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(position, f"{position}.")
        text += t(
            lang, "group.standings_line",
            medal=medal, name=_safe(player.get("name")),
            points=player.get("points", 0), rounds=player.get("rounds_won", 0),
        )

    await message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton(t(lang, "group.button_new_round"), callback_data=NEW_ROUND)]]
        ),
        parse_mode="HTML",
    )


async def group_new_round_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Il bottone "un altro round" sotto la classifica: `effective_message` di una callback
    e' il messaggio del bottone, che sta nello stesso gruppo, quindi non serve altro."""
    await update.callback_query.answer()
    await group_challenge(update, context)
