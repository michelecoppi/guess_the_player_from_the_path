import asyncio

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from services.firebase_service import get_user_data, set_user_language
from services.i18n import LANGUAGE_NAMES, SUPPORTED_LANGUAGES, resolve_language, t


def _keyboard():
    buttons = [InlineKeyboardButton(LANGUAGE_NAMES[lang], callback_data=f"set_lang_{lang}") for lang in SUPPORTED_LANGUAGES]
    return InlineKeyboardMarkup([buttons])


def _current_lang(update: Update):
    user_data = get_user_data(update.effective_user.id)
    if user_data and user_data.get("language") in SUPPORTED_LANGUAGES:
        return user_data["language"]
    return resolve_language(getattr(update.effective_user, "language_code", None))


async def language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = (await asyncio.to_thread(_current_lang, update))
    await update.effective_message.reply_text(t(lang, "language.prompt"), reply_markup=_keyboard())


async def language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    lang = query.data.replace("set_lang_", "")
    if lang not in SUPPORTED_LANGUAGES:
        return

    (await asyncio.to_thread(set_user_language, query.from_user.id, lang))
    await query.edit_message_text(t(lang, "language.confirm"))
