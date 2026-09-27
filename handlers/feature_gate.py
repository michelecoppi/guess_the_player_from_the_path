"""Feature flags (#51) at the Telegram boundary.

`feature_gate(Flag.X)` wraps a command or callback handler: if the flag is off for the user
(or the group chat) the handler is not run and the user gets a short localized notice. The
wrapped function is the same object the menu buttons call (handlers/menu_handler.py), so a
button and its command can never disagree.

A refusal is expected behaviour, not an error: nothing is logged per update and nothing
reaches Sentry. Evaluation goes through the cached service in services/feature_flags.py and
never raises.
"""
import asyncio
import functools

from telegram import Update
from telegram.ext import ContextTypes

from services import feature_flags
from services.feature_flags import Flag
from services.i18n import resolve_language, t

GROUP_CHAT_TYPES = ("group", "supergroup")


def context_ids(update):
    """(user_id, group_id) for flag evaluation; group only in group chats."""
    user = getattr(update, "effective_user", None)
    chat = getattr(update, "effective_chat", None)
    group_id = getattr(chat, "id", None) if getattr(chat, "type", None) in GROUP_CHAT_TYPES else None
    return getattr(user, "id", None), group_id


async def flag_enabled(flag: Flag, update) -> bool:
    user_id, group_id = context_ids(update)
    return await asyncio.to_thread(feature_flags.is_enabled, flag, user_id=user_id, group_id=group_id)


def _language(update):
    try:
        from handlers.keyboards import language_for
        return language_for(update)
    except Exception:  # noqa: BLE001 - the notice must still go out
        return resolve_language(getattr(getattr(update, "effective_user", None), "language_code", None))


async def notify_disabled(update):
    lang = await asyncio.to_thread(_language, update)
    text = t(lang, "feature.disabled")
    query = getattr(update, "callback_query", None)
    if query is not None:
        try:
            await query.answer(text, show_alert=True)
            return
        except Exception:  # noqa: BLE001 - already answered (menu buttons answer first)
            pass
    message = getattr(update, "effective_message", None) or getattr(query, "message", None)
    if message is not None:
        await message.reply_text(text)


def feature_gate(flag: Flag):
    def decorate(handler):
        @functools.wraps(handler)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            if not await flag_enabled(flag, update):
                await notify_disabled(update)
                return None
            return await handler(update, context, *args, **kwargs)
        wrapper.feature_flag = flag  # type: ignore[attr-defined]
        return wrapper
    return decorate
