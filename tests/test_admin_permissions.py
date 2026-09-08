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
    monkeypatch.setattr(admin_handler.firebase_service, "get_upcoming_daily_paths", lambda limit: [])

    update, message = make_update(111)
    asyncio.run(admin_handler.admin_status(update, None))

    assert len(message.replies) == 1
    assert "riservato" not in message.replies[0].lower()


def test_unauthenticated_user_none_id_is_rejected(monkeypatch):
    monkeypatch.setattr(admin_handler, "ADMIN_TELEGRAM_IDS", [111])
    update, message = make_update(None)

    asyncio.run(admin_handler.admin_regen(update, None))

    assert "riservato" in message.replies[0].lower()


ADMIN_COMMAND_HANDLERS = [
    "admin_help",
    "admin_status",
    "admin_stats",
    "admin_pool",
    "admin_regen",
    "admin_review",
    "admin_next",
    "admin_events",
    "admin_block",
    "admin_unblock",
    "admin_blocked",
    "admin_fs_add",
    "admin_fs_list",
    "admin_fs_del",
    "admin_event_create",
]


@pytest.mark.parametrize("handler_name", ADMIN_COMMAND_HANDLERS)
def test_every_admin_command_rejects_non_admins(monkeypatch, handler_name):
    monkeypatch.setattr(admin_handler, "ADMIN_TELEGRAM_IDS", [111])
    update, message = make_update(999)

    handler = getattr(admin_handler, handler_name)
    asyncio.run(handler(update, SimpleNamespace(args=[])))

    assert len(message.replies) == 1
    assert "riservato" in message.replies[0].lower()


def test_admin_help_lists_every_registered_command(monkeypatch):
    monkeypatch.setattr(admin_handler, "ADMIN_TELEGRAM_IDS", [111])
    update, message = make_update(111)

    asyncio.run(admin_handler.admin_help(update, SimpleNamespace(args=[])))

    text = "\n".join(message.replies)
    for command, _ in admin_handler.ADMIN_COMMANDS:
        assert command.split()[0] in text


def test_block_requires_an_existing_player_id(monkeypatch):
    monkeypatch.setattr(admin_handler, "ADMIN_TELEGRAM_IDS", [111])
    blocked = []
    monkeypatch.setattr(admin_handler.firebase_service, "block_player_id", lambda pid: blocked.append(pid))

    update, message = make_update(111)
    asyncio.run(admin_handler.admin_block(update, SimpleNamespace(args=["non_esiste"])))
    assert blocked == []
    assert "nessun giocatore" in message.replies[-1].lower()

    update, message = make_update(111)
    asyncio.run(admin_handler.admin_block(update, SimpleNamespace(args=["messi"])))
    assert blocked == ["messi"]
