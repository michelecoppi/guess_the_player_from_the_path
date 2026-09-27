"""Adattatore Telegram della partita di gruppo: `/round`, `/guess` in un gruppo e
`/standings`. Le regole (materiale che non spoilera, tentativi, chi vince, punti che restano
nel gruppo) stanno in `domains/groups/service.py`; qui si legge l'update e si scrive la
risposta localizzata.
"""
import asyncio
import html

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from domains.groups import service as groups
from handlers.legend_handler import legend_keyboard
from services import product_analytics as analytics
from services.guess_feedback import comparison_text
from services.i18n import difficulty_label, resolve_language, t
from services.path_image import render_career_path_image
from services.share import bot_link

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

    opened = await asyncio.to_thread(groups.open_round, message.chat.id)
    if not opened:
        await message.reply_text(t(lang, "group.empty"))
        return

    # Who opened it, never which group: a group id would identify the chat (#139).
    if update.effective_user:
        analytics.capture(analytics.Event.GROUP_ROUND_STARTED, user_id=update.effective_user.id)

    difficulty = difficulty_label(lang, opened.difficulty)
    career_path = opened.career_path
    photo = (await asyncio.to_thread(render_career_path_image, career_path, title=t(lang, "image.path_title"), subtitle=t(lang, "image.path_subtitle", stops=len(career_path)), badge=difficulty.upper(), footer=f"{difficulty} ({opened.points})", lang=lang))
    await message.reply_photo(
        photo=photo,
        caption=t(
            lang, "group.round_opened",
            number=opened.number,
            difficulty=difficulty,
            points=opened.points,
            attempts=groups.MAX_GROUP_ATTEMPTS,
        ),
        reply_markup=_challenge_keyboard(lang),
        parse_mode="HTML",
    )


async def process_group_answer(update: Update, context: ContextTypes.DEFAULT_TYPE, user_answer):
    """Un `/guess` arrivato da un gruppo. La chiama guess_handler."""
    message = update.effective_message
    lang = _lang_for(update)
    user = update.effective_user
    name = _display_name(user)

    outcome = await asyncio.to_thread(groups.submit_answer, message.chat.id, user.id, name, user_answer)

    if outcome.status == "no_round":
        await message.reply_text(t(lang, "group.no_round"))
    elif outcome.status == "usage":
        await message.reply_text(t(lang, "group.usage"), parse_mode="HTML")
    elif outcome.status == "already_solved":
        # Senza nome: il round l'ha appena preso qualcun altro, vincendo la transazione.
        winner = _safe(outcome.winner) if outcome.winner is not None else "?"
        await message.reply_text(t(lang, "group.already_solved", winner=winner), parse_mode="HTML")
    elif outcome.status == "no_attempts":
        await message.reply_text(t(lang, "group.no_attempts", name=_safe(name)), parse_mode="HTML")
    elif outcome.status == "wrong":
        await message.reply_text(
            t(lang, "group.wrong", name=_safe(name), attempts_left=outcome.attempts_left)
            + comparison_text(lang, outcome.comparison),
            parse_mode="HTML",
        )
    else:
        await message.reply_text(
            t(lang, "group.correct", name=_safe(name), points=outcome.points, number=outcome.number),
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

    rows = await asyncio.to_thread(groups.standings, message.chat.id)
    if not rows:
        await message.reply_text(t(lang, "group.standings_empty"))
        return

    text = t(lang, "group.standings_title")
    for row in rows:
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(row["position"], f"{row['position']}.")
        text += t(
            lang, "group.standings_line",
            medal=medal, name=_safe(row["name"]),
            points=row["points"], rounds=row["rounds_won"],
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
