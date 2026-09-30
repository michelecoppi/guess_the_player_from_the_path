"""Il bottone "Indizio" rimasto sotto i vecchi tentativi in chat.

La sfida di oggi si gioca solo nella mini app (#243), e con lei i suoi indizi: le regole
stanno in services/hints.py e services/game.py, che la mini app usa da /app/api/hint. I
bottoni gia' finiti in chat pero' restano premibili per sempre: qui rispondono portando alla
mini app, senza prendere nessun indizio.
"""
import asyncio

from telegram import Update
from telegram.ext import ContextTypes

from handlers.keyboards import app_keyboard, language_for
from services.i18n import t

CALLBACK_DATA = "hint_daily"


async def hint_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = (await asyncio.to_thread(language_for, update))
    await query.message.reply_text(t(lang, "guess.daily_in_app"), reply_markup=app_keyboard(lang))
