"""La legenda dell'immagine del percorso.

L'immagine e' disegnata senza una parola (services/path_image.py), perche' la stessa PNG
va a chi gioca in italiano, spagnolo e inglese: ogni informazione ha quindi un segno e non
un'etichetta. Il rovescio della medaglia e' che i segni finora non erano scritti da nessuna
parte, ne' in `/help` ne' altrove: chi apriva la sfida stava indovinando anche la notazione
(la barretta tratteggiata, la freccia, i numeri fra parentesi).

Il bottone sta sotto l'immagine, cioe' nel momento in cui la domanda viene: /legenda esiste
per chi la cerca dopo.
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from handlers.keyboards import language_for
from services.i18n import t

CALLBACK_DATA = "legend"


def legend_keyboard(lang, extra_rows=None):
    """La riga con "Come si legge", eventualmente sotto altre righe di bottoni."""
    rows = list(extra_rows or [])
    rows.append([InlineKeyboardButton(t(lang, "legend.button"), callback_data=CALLBACK_DATA)])
    return InlineKeyboardMarkup(rows)


async def legend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = language_for(update)
    await update.effective_message.reply_text(t(lang, "legend.text"), parse_mode="HTML")


async def legend_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = language_for(update)
    # Messaggio nuovo invece di modificare quello della sfida: l'immagine deve restare
    # visibile mentre si legge come si interpreta.
    await query.message.reply_text(t(lang, "legend.text"), parse_mode="HTML")
