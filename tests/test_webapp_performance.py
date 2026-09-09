"""Exercise actual HTTP routes without Telegram startup or a live database."""
import asyncio
import importlib.util
import threading
from pathlib import Path

import httpx
import pytest

import config


@pytest.fixture
def server(monkeypatch):
    monkeypatch.setattr(config, "BOT_TOKEN", "123456:test-token")
    spec = importlib.util.spec_from_file_location("performance_bot", Path(__file__).parents[1] / "bot.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_slow_firestore_read_does_not_block_other_requests(server, monkeypatch):
    entered = threading.Event()
    release = threading.Event()

    def slow_user(payload):
        entered.set()
        assert release.wait(3), "Database read blocked the event loop"
        return 42, {"first_name": "Anna"}

    monkeypatch.setattr(server, "_webapp_user", slow_user)
    monkeypatch.setattr(server.shop, "catalogue_for", lambda *args: {"sections": []})

    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test") as client:
            pending = asyncio.create_task(client.post("/app/api/shop", json={}))
            try:
                assert await asyncio.to_thread(entered.wait, 2)
                response = await asyncio.wait_for(client.head("/ping"), timeout=1)
                assert response.status_code == 200
                assert not pending.done()
            finally:
                release.set()
                response = await pending
            assert response.status_code == 200
            assert response.headers["server-timing"].startswith("app;dur=")

    asyncio.run(exercise())


def test_profile_route_reads_user_only_once(server, monkeypatch):
    reads = []

    def read_user(uid):
        reads.append(uid)
        return {"first_name": "Anna"}

    monkeypatch.setattr(server, "user_id_from_init_data", lambda *args: 42)
    monkeypatch.setattr(server.firebase_service, "get_user_data", read_user)
    monkeypatch.setattr(server.firebase_service, "get_daily_path", lambda *args: None)

    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test") as client:
            response = await client.post("/app/api/me", json={"lightweight": True})
            assert response.status_code == 200
            assert response.json()["user"]["name"] == "Anna"
            assert "leaderboard" not in response.json()

    asyncio.run(exercise())
    assert reads == [42]


def test_arena_routes_require_authentication_and_serve_assets(server):
    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test") as client:
            for mode in ("training", "duel", "events"):
                response = await client.post("/app/api/arena", json={"mode": mode, "user_id": 42})
                assert response.status_code == 401
            for asset in ("arena.js", "arena.css"):
                response = await client.get(f"/app/{asset}")
                assert response.status_code == 200
                cached = await client.get(f"/app/{asset}", headers={"If-None-Match": response.headers["etag"]})
                assert cached.status_code == 304
    asyncio.run(exercise())


def test_arena_route_uses_signed_identity_language_and_structured_errors(server, monkeypatch):
    from services import arena
    monkeypatch.setattr(server, "_webapp_user", lambda payload, cost: (42, {"language": "es"}))
    calls = []

    def train(uid, action, answer, revision, lang):
        calls.append((uid, lang))
        raise arena.ArenaError("stale")

    monkeypatch.setattr(arena, "training", train)

    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test") as client:
            response = await client.post("/app/api/arena", json={"mode": "training", "user_id": 7, "language": "en"})
            assert response.status_code == 409
            assert response.json() == {"detail": "stale"}
    asyncio.run(exercise())
    assert calls == [(42, "es")]
