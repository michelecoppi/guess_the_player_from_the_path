"""Native share of the Daily result card with Telegram's `shareMessage` (#185).

The Mini App cannot hand Telegram an image: `WebApp.shareMessage(id)` only takes the id of a
message the **bot** prepared with `savePreparedInlineMessage`. Its photo must be a public URL
or a `file_id`; a public URL of the card would expose the name printed on it (see
`/app/api/card`), so the bot uploads the card once to a private storage chat
(`config.SHARE_STORAGE_CHAT_ID`) and reuses the resulting `file_id`.

- The content comes from the server (`services.webapp_api.result_share`): a page cannot share
  a result it did not get.
- Identical cards (same player, day, result and look) are uploaded once per process: the
  `file_id` is cached by the image hash. Telegram limits how many messages a bot posts in one
  chat per minute; the cache keeps repeated shares out of that budget.
- Prepared messages expire (Telegram sets `expiration_date`); the page prepares a new one
  when it needs it.
"""
from __future__ import annotations

import hashlib
import uuid
from collections import OrderedDict
from typing import Any, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultCachedPhoto

from services.i18n import t

MAX_CACHED_FILES = 512
_file_ids: "OrderedDict[str, str]" = OrderedDict()


def _cached_file_id(digest: str) -> Optional[str]:
    file_id = _file_ids.get(digest)
    if file_id is not None:
        _file_ids.move_to_end(digest)
    return file_id


def _remember_file_id(digest: str, file_id: str) -> None:
    _file_ids[digest] = file_id
    _file_ids.move_to_end(digest)
    while len(_file_ids) > MAX_CACHED_FILES:
        _file_ids.popitem(last=False)


def reset_cache() -> None:
    """Tests only."""
    _file_ids.clear()


async def upload_card(bot: Any, storage_chat_id: int, png: bytes) -> tuple[str, bool]:
    """The `file_id` of `png` in the storage chat, uploading it only the first time.

    Returns (file_id, cached)."""
    digest = hashlib.sha256(png).hexdigest()
    cached = _cached_file_id(digest)
    if cached is not None:
        return cached, True
    message = await bot.send_photo(chat_id=storage_chat_id, photo=png, disable_notification=True)
    file_id = message.photo[-1].file_id
    _remember_file_id(digest, file_id)
    return file_id, False


def share_result(file_id: str, text: str, link: str, lang: str) -> InlineQueryResultCachedPhoto:
    """The message people receive: the figurina, the same text as the chat card and, when the
    bot's link is known, a button that opens it (inline messages cannot carry web_app buttons)."""
    markup = None
    if link:
        markup = InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "share.play_button"), url=link)]])
    return InlineQueryResultCachedPhoto(
        id=uuid.uuid4().hex,
        photo_file_id=file_id,
        caption=text,
        reply_markup=markup,
    )


async def prepare(bot: Any, user_id: int, storage_chat_id: int, share: dict, lang: str) -> dict:
    """Uploads (or reuses) the card and prepares the message; returns what the page needs."""
    file_id, cached = await upload_card(bot, storage_chat_id, share["image"])
    prepared = await bot.save_prepared_inline_message(
        user_id=user_id,
        result=share_result(file_id, share["text"], share["link"], lang),
        allow_user_chats=True,
        allow_bot_chats=False,
        allow_group_chats=True,
        allow_channel_chats=True,
    )
    expires = getattr(prepared, "expiration_date", None)
    return {
        "id": prepared.id,
        "expires_at": int(expires.timestamp()) if expires is not None else None,
        "cached": cached,
    }
