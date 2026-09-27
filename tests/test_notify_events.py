"""#139: turning daily notifications on or off is a product event, only on a real change."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from handlers import notify_handler


def callback(data):
    message = SimpleNamespace(chat=SimpleNamespace(id=42), reply_text=AsyncMock())
    query = SimpleNamespace(data=data, from_user=SimpleNamespace(id=42, language_code="it"),
                            message=message, edit_message_text=AsyncMock())
    return SimpleNamespace(callback_query=query)


@pytest.mark.parametrize("data, was_on, expected", [
    ("enable_notify", False, [True]),
    ("enable_notify", True, []),
    (notify_handler.ENABLE_INLINE, False, [True]),
    (notify_handler.ENABLE_INLINE, True, []),
    ("disable_notify", True, [False]),
    ("disable_notify", False, []),
])
def test_notifications_changed_fires_only_on_a_change(monkeypatch, data, was_on, expected):
    monkeypatch.setattr(notify_handler, "get_user_data",
                        lambda uid: {"language": "it", "notifications_enabled": was_on})
    monkeypatch.setattr(notify_handler, "set_user_notifications", lambda *a: None)
    captured = []
    monkeypatch.setattr(notify_handler.analytics, "capture",
                        lambda event, **kw: captured.append((event.value, kw["properties"]["enabled"])))

    asyncio.run(notify_handler.notify_callback(callback(data), None))

    assert captured == [("notifications_changed", value) for value in expected]
