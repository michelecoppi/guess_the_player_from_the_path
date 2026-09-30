"""Sfida inline (#240): `@<bot>` in qualsiasi chat. Le regole stanno in
services/inline_challenge.py; qui c'e' solo il dialogo con Telegram.

1. `inline_query`: chi scrive `@<bot>` riceve qualche card (foto del percorso + bottone).
2. `chosen_inline_result`: la card scelta e' partita. Si segna nel registro del mittente e
   si crea il suo contatore; il bottone viene riscritto con l'id della card, cosi' chi la
   gioca fa salire il conto di *quel* messaggio. Telegram manda questo update solo se
   l'inline feedback e' attivo su BotFather (`/setinlinefeedback`): senza, le card
   funzionano lo stesso, ma senza tetto, registro e contatore.
3. `report_card_result`: a fine partita (services -> training_handler) aggiorna la
   didascalia della card con il conto.
"""
import asyncio
import logging

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultPhoto,
    InlineQueryResultsButton,
    Update,
)
from telegram.error import TelegramError
from telegram.ext import ContextTypes

import config
from services import firebase_service, inline_challenge
from services.dates import today_iso
from services.i18n import DEFAULT_LANGUAGE, resolve_language, t
from services.repos import inline_cards

# Le card sono personali (registro e tetto dipendono da chi scrive) e cambiano a ogni
# richiesta: niente cache lato Telegram oltre pochi secondi.
CACHE_SECONDS = 5


def _lang(user, user_data):
    return (user_data or {}).get("language") or resolve_language(getattr(user, "language_code", None))


def play_link(code, card=None):
    return f"https://t.me/{config.BOT_USERNAME}?start={inline_challenge.start_parameter(code, card)}"


def card_url(code, lang):
    return f"{config.PUBLIC_BASE_URL}/inline/card/{code}.jpg?lang={lang}"


def _markup(lang, code, card=None):
    return InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "inline.play_button"), url=play_link(code, card))]])


def _result(lang, challenge):
    code = inline_challenge.code_for(challenge["key"])
    return InlineQueryResultPhoto(
        id=code,
        photo_url=card_url(code, lang),
        thumbnail_url=card_url(code, lang),
        caption=inline_challenge.caption(lang, challenge),
        parse_mode="HTML",
        reply_markup=_markup(lang, code),
    )


async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query
    user = query.from_user
    user_data = await asyncio.to_thread(firebase_service.get_user_data, user.id)
    lang = _lang(user, user_data)

    if not config.BOT_USERNAME or not config.PUBLIC_BASE_URL:
        await query.answer([], cache_time=CACHE_SECONDS, is_personal=True)
        return
    # Chi non ha mai aperto il bot non ha un registro dove segnare le card: prima si entra.
    if not user_data:
        await query.answer([], cache_time=CACHE_SECONDS, is_personal=True,
                           button=InlineQueryResultsButton(t(lang, "inline.start_button"), start_parameter="inline"))
        return
    if inline_challenge.remaining_today(user_data, today_iso()) <= 0:
        await query.answer([], cache_time=CACHE_SECONDS, is_personal=True,
                           button=InlineQueryResultsButton(t(lang, "inline.limit_button"), start_parameter="inline"))
        return

    cards = await asyncio.to_thread(inline_challenge.pick_cards, user_data.get("inline_sent") or [])
    await query.answer([_result(lang, challenge) for challenge in cards],
                       cache_time=CACHE_SECONDS, is_personal=True)


async def chosen_inline_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chosen = update.chosen_inline_result
    code = chosen.result_id
    key = await asyncio.to_thread(inline_challenge.key_for, code)
    if not key:
        return
    user_id = chosen.from_user.id
    await asyncio.to_thread(inline_cards.record_sent, user_id, key, today_iso(),
                            inline_challenge.daily_limit(), inline_challenge.SENT_MEMORY)
    if not chosen.inline_message_id:
        return

    user_data = await asyncio.to_thread(firebase_service.get_user_data, user_id)
    lang = _lang(chosen.from_user, user_data)
    card = await asyncio.to_thread(inline_cards.create_card, code, lang, chosen.inline_message_id)
    try:
        await context.bot.edit_message_reply_markup(inline_message_id=chosen.inline_message_id,
                                                    reply_markup=_markup(lang, code, card))
    except TelegramError as exc:
        logging.warning(f"[INLINE] bottone della card {card} non aggiornato: {exc}")


async def report_card_result(bot, user_id, card_id, solved):
    """Conta il risultato di una partita partita da una card e riscrive la didascalia."""
    if not card_id or not inline_challenge.CARD.fullmatch(card_id):
        return
    card = await asyncio.to_thread(inline_cards.record_result, user_id, card_id, solved)
    if not card or not card.get("inline_message_id"):
        return
    challenge = await asyncio.to_thread(inline_challenge.challenge_for, card.get("code"))
    if not challenge:
        return
    lang = card.get("lang") or DEFAULT_LANGUAGE
    try:
        await bot.edit_message_caption(
            inline_message_id=card["inline_message_id"],
            caption=inline_challenge.caption(lang, challenge, card.get("solved", 0), card.get("failed", 0)),
            parse_mode="HTML",
            reply_markup=_markup(lang, card["code"], card_id),
        )
    except TelegramError as exc:
        # Messaggio cancellato, troppo vecchio o identico: il conto resta comunque salvato.
        logging.info(f"[INLINE] didascalia della card {card_id} non aggiornata: {exc}")
