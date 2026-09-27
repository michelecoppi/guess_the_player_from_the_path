import asyncio

from telegram import Update
from telegram.ext import ContextTypes

from handlers.keyboards import app_keyboard, language_for
from services.i18n import t


async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Spiega il gioco e porta alla mini app. Nient'altro: niente menu con tutti i bottoni
    (quello resta su /start) e niente elenco dei comandi, che Telegram mostra gia' nel menu "/".
    Assorbe il vecchio /info, che diceva le stesse cose in versione piu' corta."""
    # `language_for` e non `resolve_language`: chi ha scelto una lingua con /language deve
    # trovarla anche qui, non quella del suo client Telegram.
    lang = (await asyncio.to_thread(language_for, update))
    # I bottoni web_app funzionano solo in chat privata: in un gruppo la spiegazione arriva
    # da sola.
    private = getattr(getattr(update, "effective_chat", None), "type", None) == "private"
    keyboard = app_keyboard(lang) if private else None
    text = t(lang, "help.message")
    if keyboard:
        text = f"{text}\n\n{t(lang, 'help.open_app')}"
    await update.effective_message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")
