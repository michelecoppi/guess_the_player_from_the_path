import asyncio
from types import SimpleNamespace

import pytest

from handlers import admin_handler


class FakeMessage:
    def __init__(self):
        self.replies = []
        self.text = "/admin_test"

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)


def make_update(user_id):
    message = FakeMessage()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id),
        message=message,
    )
    return update, message


def test_non_admin_is_rejected(monkeypatch):
    monkeypatch.setattr(admin_handler, "ADMIN_TELEGRAM_IDS", [111])
    update, message = make_update(999)

    asyncio.run(admin_handler.admin_status(update, None))

    assert len(message.replies) == 1
    assert "riservato" in message.replies[0].lower()


def test_admin_is_allowed(monkeypatch):
    monkeypatch.setattr(admin_handler, "ADMIN_TELEGRAM_IDS", [111])
    monkeypatch.setattr(admin_handler, "get_current_event", lambda: None)
    monkeypatch.setattr(admin_handler, "get_incomplete_or_unverified_players", lambda: [])

    update, message = make_update(111)
    asyncio.run(admin_handler.admin_status(update, None))

    assert len(message.replies) == 1
    assert "riservato" not in message.replies[0].lower()


def test_unauthenticated_user_none_id_is_rejected(monkeypatch):
    monkeypatch.setattr(admin_handler, "ADMIN_TELEGRAM_IDS", [111])
    update, message = make_update(None)

    asyncio.run(admin_handler.admin_regen(update, None))

    assert "riservato" in message.replies[0].lower()
