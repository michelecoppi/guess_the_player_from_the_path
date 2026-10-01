"""Native share of the Daily result card with shareMessage (#185)."""
import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from telegram.error import BadRequest, NetworkError, RetryAfter, TimedOut

import config
from apps.api import miniapp, share_message
from services import product_analytics as analytics
from services import webapp_api

TODAY = "2026-09-27"
RESULT = {"day": TODAY, "solved": True, "attempts": 2, "hints": 1}


class FakeBot:
    def __init__(self):
        self.uploads = []
        self.prepared = []
        self.fail_with = None

    async def send_photo(self, **kwargs):
        if self.fail_with:
            raise self.fail_with
        self.uploads.append(kwargs)
        return SimpleNamespace(photo=[SimpleNamespace(file_id="small"), SimpleNamespace(file_id=f"file-{len(self.uploads)}")])

    async def save_prepared_inline_message(self, **kwargs):
        self.prepared.append(kwargs)
        return SimpleNamespace(id=f"prep-{len(self.prepared)}",
                               expiration_date=datetime(2026, 9, 28, tzinfo=timezone.utc))


@pytest.fixture(autouse=True)
def fresh_cache():
    share_message.reset_cache()
    yield
    share_message.reset_cache()


@pytest.fixture
def api(monkeypatch):
    app = FastAPI()
    app.include_router(miniapp.router)
    bot = FakeBot()
    app.state.telegram = SimpleNamespace(application=SimpleNamespace(bot=bot))
    monkeypatch.setattr(config, "SHARE_STORAGE_CHAT_ID", -100123)
    monkeypatch.setattr(miniapp, "_webapp_user", lambda payload, cost=1: (42, {"first_name": "Anna", "current_streak": 4}))
    monkeypatch.setattr(miniapp, "today_iso", lambda: TODAY)
    monkeypatch.setattr(webapp_api.firebase_service, "get_daily_history", lambda uid, limit: [dict(RESULT)])
    monkeypatch.setattr(webapp_api, "result_card_png", lambda user, lang, result: b"png-" + str(result["attempts"]).encode())
    monkeypatch.setattr(webapp_api.referrals, "invite_link", lambda uid: "https://t.me/gtp_bot?start=ref_abc")
    monkeypatch.setattr(webapp_api.shop, "squares_symbols", lambda user: None)
    return TestClient(app), bot


def test_prepare_uploads_the_saved_result_once_and_prepares_a_photo_message(api):
    client, bot = api
    response = client.post("/app/api/share/prepare", json={"day": TODAY, "attempts": 1, "solved": False})
    assert response.status_code == 200
    assert response.json() == {"id": "prep-1", "expires_at": int(datetime(2026, 9, 28, tzinfo=timezone.utc).timestamp())}

    [upload] = bot.uploads
    assert upload["chat_id"] == -100123 and upload["photo"] == b"png-2"  # the saved result, not the claim
    assert upload["disable_notification"] is True
    [prepared] = bot.prepared
    assert prepared["user_id"] == 42
    assert prepared["allow_user_chats"] and prepared["allow_group_chats"] and not prepared["allow_bot_chats"]
    photo = prepared["result"]
    assert photo.photo_file_id == "file-1"
    assert "2/3" in photo.caption and "https://t.me/gtp_bot?start=ref_abc" in photo.caption
    [[button]] = photo.reply_markup.inline_keyboard
    assert button.url == "https://t.me/gtp_bot?start=ref_abc"

    # The same card is not uploaded again; a new message is still prepared.
    assert client.post("/app/api/share/prepare", json={}).status_code == 200
    assert len(bot.uploads) == 1 and len(bot.prepared) == 2
    assert bot.prepared[1]["result"].photo_file_id == "file-1"


def test_prepare_is_unavailable_without_a_storage_chat(api, monkeypatch):
    client, bot = api
    monkeypatch.setattr(config, "SHARE_STORAGE_CHAT_ID", None)
    response = client.post("/app/api/share/prepare", json={})
    assert response.status_code == 503 and response.json()["detail"] == "share_unavailable"
    assert bot.uploads == []


def test_prepare_refuses_an_unfinished_or_stale_day(api, monkeypatch):
    client, bot = api
    assert client.post("/app/api/share/prepare", json={"day": "2026-09-26"}).status_code == 409
    monkeypatch.setattr(webapp_api.firebase_service, "get_daily_history", lambda uid, limit: [])
    response = client.post("/app/api/share/prepare", json={})
    assert response.status_code == 409 and response.json()["detail"] == "partita non conclusa"
    assert bot.uploads == []


@pytest.mark.parametrize("error, retry_after", [
    (RetryAfter(timedelta(seconds=17)), "17"),
    (BadRequest("chat not found"), None),
    (TimedOut(), None),
])
def test_telegram_failures_fall_back_to_the_classic_share(api, error, retry_after):
    client, bot = api
    bot.fail_with = error
    response = client.post("/app/api/share/prepare", json={})
    assert response.status_code == 503 and response.json()["detail"] == "share_unavailable"
    assert response.headers.get("retry-after") == retry_after


def test_share_result_without_a_link_has_no_button():
    photo = share_message.share_result("file", "text", "", "it")
    assert photo.reply_markup is None and photo.caption == "text"


def test_file_id_cache_is_bounded(monkeypatch):
    monkeypatch.setattr(share_message, "MAX_CACHED_FILES", 2)
    for name in ("a", "b", "c"):
        share_message._remember_file_id(name, f"id-{name}")
    assert share_message._cached_file_id("a") is None
    assert share_message._cached_file_id("c") == "id-c"


def test_sent_records_one_analytics_event_and_requires_a_signature(api, monkeypatch):
    client, _ = api
    assert client.post("/app/api/share/sent", json={}).status_code == 401
    captured = []
    monkeypatch.setattr(miniapp, "user_id_from_init_data", lambda *args: 42)
    monkeypatch.setattr(miniapp.analytics, "capture", lambda event, **kwargs: captured.append((event, kwargs)))
    assert client.post("/app/api/share/sent", json={"initData": "signed"}).status_code == 200
    assert captured == [(analytics.Event.RESULT_SHARED,
                         {"user_id": 42, "properties": {"surface": "miniapp", "method": "share_message"}})]


def test_result_shared_properties_are_validated():
    assert analytics._clean_properties(
        analytics.Event.RESULT_SHARED, {"surface": "miniapp", "method": "share_message", "user_id": 1},
    ) == {"surface": "miniapp", "method": "share_message"}


@pytest.mark.parametrize("error, event, level", [
    (TimedOut(), "share.prepare.unavailable", logging.WARNING),
    (NetworkError("connection reset"), "share.prepare.unavailable", logging.WARNING),
    (BadRequest("chat not found"), "share.prepare.failed", logging.ERROR),
])
def test_only_actionable_telegram_failures_are_reported_as_errors(api, monkeypatch, error, event, level):
    client, bot = api
    bot.fail_with = error
    events = []
    monkeypatch.setattr(miniapp.observability, "log_event",
                        lambda name, lvl=logging.INFO, **fields: events.append((name, lvl)))
    response = client.post("/app/api/share/prepare", json={})
    assert response.status_code == 503 and response.json()["detail"] == "share_unavailable"
    assert (event, level) in events
