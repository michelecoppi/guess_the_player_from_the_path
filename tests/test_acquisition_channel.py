"""`/start` campaign links: which channel brought a user (#137) and which campaign (#218)."""
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
    ("src_telegram_channel", "telegram_channel"),
    ("src_someone_s_private_name", "other"),
    ("src_", "other"),
    ("hello", "other"),
    ("src_tiktok-2026w40-whois", "tiktok"),
    ("src_telegram_channel-promo1", "telegram_channel"),
    ("src_tiktok-", "tiktok"),
    ("src_tiktok-" + "a" * 25, "tiktok"),
    ("src_tiktok-free text!", "tiktok"),
    ("src_unknown-2026w40", "other"),
])
def test_start_argument_maps_to_a_known_channel(argument, channel):
    assert start_handler.acquisition_channel(argument) == channel
    assert channel in analytics.ACQUISITION_CHANNELS


@pytest.mark.parametrize("argument, campaign", [
    ("src_tiktok-2026w40-whois", "2026w40-whois"),
    ("src_TikTok-2026W40", "2026w40"),
    ("src_qr-" + "a" * 24, "a" * 24),
    ("src_tiktok", None),
    ("src_tiktok-", None),
    ("src_tiktok-" + "a" * 25, None),
    ("src_tiktok-free text!", None),
    ("src_tiktok-café", None),
    ("src_unknown-2026w40", None),
    ("ref_abc-123", None),
    ("", None),
])
def test_campaign_id_is_a_bounded_slug_of_a_known_source(argument, campaign):
    assert start_handler.campaign_id(argument) == campaign


def test_campaign_id_validation_on_bot_started():
    clean = analytics._clean_properties
    assert clean(analytics.Event.BOT_STARTED, {"campaign_id": "2026w40-whois"}) == {"campaign_id": "2026w40-whois"}
    assert clean(analytics.Event.BOT_STARTED, {"campaign_id": "Free Text"}) == {}
    assert clean(analytics.Event.BOT_STARTED, {"campaign_id": "a" * 25}) == {}
    assert clean(analytics.Event.MINIAPP_OPENED, {"campaign_id": "2026w40"}) == {}


def test_every_channel_passes_bot_started_validation():
    for channel in analytics.ACQUISITION_CHANNELS:
        cleaned = analytics._clean_properties(analytics.Event.BOT_STARTED, {"acquisition_channel": channel})
        assert cleaned == {"acquisition_channel": channel}
    assert analytics._clean_properties(analytics.Event.BOT_STARTED, {"acquisition_channel": "free text"}) == {}
    assert analytics._clean_properties(analytics.Event.MINIAPP_OPENED, {"acquisition_channel": "tiktok"}) == {}


def _start(monkeypatch, argument):
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

    asyncio.run(start_handler.start(update, SimpleNamespace(args=[argument])))

    reply.assert_awaited_once()
    join.assert_not_awaited()
    return captured


def test_campaign_link_shows_the_normal_welcome_and_reports_the_channel(monkeypatch):
    assert _start(monkeypatch, "src_tiktok") == [
        (analytics.Event.BOT_STARTED, {"language": "it", "is_new_user": True, "acquisition_channel": "tiktok"})]


def test_campaign_link_with_a_campaign_reports_it(monkeypatch):
    assert _start(monkeypatch, "src_tiktok-2026w40-whois") == [
        (analytics.Event.BOT_STARTED, {"language": "it", "is_new_user": True, "acquisition_channel": "tiktok",
                                       "campaign_id": "2026w40-whois"})]
