"""`/start` campaign links: which channel brought a user (#137)."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from handlers import keyboards, start_handler
from services import product_analytics as analytics


@pytest.mark.parametrize("argument, channel", [
    ("", "direct"),
    ("ref_abc123", "referral"),
    ("duel_" + "a" * 24, "duel"),
    (start_handler.DEEP_LINK_PREFIX + "ABC23X", "league"),
    ("src_tiktok", "tiktok"),
    ("src_TikTok", "tiktok"),
    ("src_telegram_group", "telegram_group"),
    ("src_someone_s_private_name", "other"),
    ("src_", "other"),
    ("hello", "other"),
])
def test_start_argument_maps_to_a_known_channel(argument, channel):
    assert start_handler.acquisition_channel(argument) == channel
    assert channel in analytics.ACQUISITION_CHANNELS


def test_every_channel_passes_bot_started_validation():
    for channel in analytics.ACQUISITION_CHANNELS:
        cleaned = analytics._clean_properties(analytics.Event.BOT_STARTED, {"acquisition_channel": channel})
        assert cleaned == {"acquisition_channel": channel}
    assert analytics._clean_properties(analytics.Event.BOT_STARTED, {"acquisition_channel": "free text"}) == {}
    assert analytics._clean_properties(analytics.Event.MINIAPP_OPENED, {"acquisition_channel": "tiktok"}) == {}


def test_campaign_link_shows_the_normal_welcome_and_reports_the_channel(monkeypatch):
    monkeypatch.setattr(keyboards, "WEBAPP_URL", "https://example.com/app")
    monkeypatch.setattr(start_handler, "save_user", lambda *a, **kw: {"language": "it", "created": True})
    captured = []
    monkeypatch.setattr(start_handler.analytics, "capture",
                        lambda event, **kw: captured.append((event, kw.get("properties"))))
    join = AsyncMock()
    monkeypatch.setattr(start_handler, "league_join", join)
    reply = AsyncMock()
    update = SimpleNamespace(effective_user=SimpleNamespace(id=42, first_name="Gio", language_code="it"),
                             effective_chat=SimpleNamespace(type="private"),
                             effective_message=SimpleNamespace(reply_text=reply))

    asyncio.run(start_handler.start(update, SimpleNamespace(args=["src_tiktok"])))

    assert captured == [(analytics.Event.BOT_STARTED,
                         {"language": "it", "is_new_user": True, "acquisition_channel": "tiktok"})]
    reply.assert_awaited_once()
    join.assert_not_awaited()
