"""Il bottone "Indizio" sotto una risposta sbagliata.

Le regole del gioco (quando si sbloccano, quanto costano, quanti sono) stanno in
services/hints.py e services/game.py, cioe' nello stesso posto da cui le prende la mini app:
qui c'e' solo il pezzo che parla con Telegram.

Un dettaglio che sembra un dettaglio e non lo e': l'indizio arriva come **messaggio nuovo**,
non modificando quello del tentativo. Cosi' resta in chat la traccia di cosa si e' chiesto e
quando - e soprattutto il messaggio con il confronto sul nome sbagliato non sparisce proprio
mentre serve.
"""
import asyncio

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from handlers.keyboards import language_for
from services import game
from services.daily_challenge import get_today_challenge
from services.i18n import t

CALLBACK_DATA = "hint_daily"

_ERRORS = {
    "not_registered": "hint.not_registered",
    "needs_attempt": "hint.needs_attempt",
    "already_guessed": "hint.already_guessed",
    "no_attempts": "hint.no_attempts",
    "no_more": "hint.no_more",
}


def hint_keyboard(lang, challenge, hints_used):
    """Il bottone dell'indizio, o None se non c'e' piu' niente da offrire.

    Quanti indizi ci sono davvero dipende dalla **scheda**, non dal massimo teorico: una
    scheda senza ruolo ne ha uno solo, e un bottone che poi non da' niente e' peggio di
    nessun bottone."""
    if hints_used >= game.max_hints_for(challenge, lang):
        return None
    return InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "hint.button"), callback_data=CALLBACK_DATA)]])


async def hint_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    lang = (await asyncio.to_thread(language_for, update))
    message = query.message

    challenge = (await asyncio.to_thread(get_today_challenge))
    if not challenge:
        await message.reply_text(t(lang, "common.no_challenge"))
        return

    result = (await asyncio.to_thread(game.take_hint, update.effective_user.id, lang, challenge=challenge))

    if result["status"] == "unavailable":
        await message.reply_text(t(lang, "hint.unavailable"))
        return

    if result["status"] == "refused":
        await message.reply_text(
            t(lang, _ERRORS.get(result["reason"], "hint.unavailable"), max_hints=result["total"])
        )
        return

    text = (
        t(lang, "hint.header", index=result["index"], total=result["total"])
        + "\n"
        + result["text"]
        + t(lang, "hint.cost", points=result["points"], full_points=result["full_points"])
    )

    await message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=hint_keyboard(lang, challenge, result["hints_used"]),
    )
