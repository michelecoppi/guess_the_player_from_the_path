"""Foto profilo Telegram negli avatar della Mini App (#296): firma, endpoint, cache, ripieghi."""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from telegram.error import Forbidden, NetworkError

import config
from apps.api import avatars as avatar_api
from services import avatars, webapp_api

JPEG = b"\xff\xd8\xff\xe0fake-jpeg"


@pytest.fixture(autouse=True)
def secrets(monkeypatch):
    monkeypatch.setattr(config, "BOT_TOKEN", "123:test-token")
    avatar_api.reset_cache()


class FakeBot:
    """Risponde come Telegram: una foto in tre formati, o nessuna, o un errore."""

    def __init__(self, sizes=((160, "small"), (320, "mid"), (640, "big")), error=None):
        self.sizes, self.error, self.calls, self.downloaded = sizes, error, 0, []

    async def get_user_profile_photos(self, user_id, limit=None):
        self.calls += 1
        if self.error:
            raise self.error
        photo = [SimpleNamespace(width=w, file_id=f) for w, f in self.sizes]
        return SimpleNamespace(total_count=1 if photo else 0, photos=[photo] if photo else [])

    async def get_file(self, file_id):
        self.downloaded.append(file_id)

        async def download_as_bytearray():
            return bytearray(JPEG)
        return SimpleNamespace(download_as_bytearray=download_as_bytearray)


def _client(bot):
    app = FastAPI()
    app.include_router(avatar_api.router)
    app.state.telegram = SimpleNamespace(application=SimpleNamespace(bot=bot))
    return TestClient(app)


# --- firma --------------------------------------------------------------------------------

def test_the_signed_url_verifies_only_for_its_own_id():
    url = avatars.avatar_url(42)
    assert url.startswith("/app/api/avatar/42?s=")
    sig = url.split("?s=")[1]
    assert avatars.verify(42, sig)
    assert not avatars.verify(43, sig)
    assert not avatars.verify(42, "0" * len(sig))
    assert not avatars.verify(42, None)


def test_the_signature_changes_with_the_bot_token(monkeypatch):
    before = avatars.signature(42)
    monkeypatch.setattr(config, "BOT_TOKEN", "999:other")
    assert avatars.signature(42) != before


@pytest.mark.parametrize("bad", [None, 0, -1, 2**53, "42", 4.2, True])
def test_no_url_for_an_invalid_id(bad):
    assert avatars.avatar_url(bad) is None


# --- endpoint -----------------------------------------------------------------------------

def test_a_signed_request_gets_the_smallest_sharp_photo_cached_by_the_browser():
    bot = FakeBot()
    response = _client(bot).get(avatars.avatar_url(42))
    assert response.status_code == 200
    assert response.content == JPEG
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["cache-control"] == "public, max-age=86400"
    assert bot.downloaded == ["small"]  # 160 px: il primo formato >= 150


def test_without_a_valid_signature_telegram_is_never_asked():
    bot = FakeBot()
    client = _client(bot)
    for path in ["/app/api/avatar/42", "/app/api/avatar/42?s=nope", "/app/api/avatar/43?s=" + avatars.signature(42)]:
        assert client.get(path).status_code == 404
    assert bot.calls == 0


def test_a_user_without_a_visible_photo_gets_404_and_keeps_the_initials():
    bot = FakeBot(sizes=())
    response = _client(bot).get(avatars.avatar_url(42))
    assert response.status_code == 404
    assert response.headers["cache-control"] == "public, max-age=3600"


def test_photos_and_missing_photos_are_cached_per_process():
    bot = FakeBot()
    client = _client(bot)
    for _ in range(3):
        assert client.get(avatars.avatar_url(42)).status_code == 200
    assert bot.calls == 1

    nobody = FakeBot(sizes=())
    other = _client(nobody)
    for _ in range(3):
        other.get(avatars.avatar_url(7))
    assert nobody.calls == 1


@pytest.mark.parametrize("error", [Forbidden("bot was blocked by the user"), NetworkError("timeout")])
def test_a_telegram_error_is_a_404_retried_soon(error):
    bot = FakeBot(error=error)
    assert _client(bot).get(avatars.avatar_url(42)).status_code == 404
    hit, photo = avatar_api._cached(42, now=0)
    assert hit and photo is None
    expires = avatar_api._cache[42][0]
    assert expires - avatar_api.time.monotonic() <= avatar_api.ERROR_TTL


def test_the_cache_is_bounded():
    for user_id in range(1, avatar_api.MAX_CACHED + 50):
        avatar_api._remember(user_id, JPEG, 60, now=0)
    assert len(avatar_api._cache) == avatar_api.MAX_CACHED
    assert 1 not in avatar_api._cache


# --- dove compaiono --------------------------------------------------------------------------

def test_leaderboard_rows_and_profiles_carry_the_signed_avatar(monkeypatch):
    monkeypatch.setattr(webapp_api.firebase_service, "get_top_users", lambda field="points_totali", limit=10: [
        {"telegram_id": 42, "username": "Anna", "points": 3, "cosmetics": {}},
    ])
    assert webapp_api._leaderboard(1)[0]["avatar"] == avatars.avatar_url(42)

    monkeypatch.setattr(webapp_api.firebase_service, "get_user_data", lambda uid: {"first_name": "Anna"})
    assert webapp_api.build_public_profile(42)["user"]["avatar"] == avatars.avatar_url(42)
