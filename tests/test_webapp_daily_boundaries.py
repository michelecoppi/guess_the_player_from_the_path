"""A stale page cannot spend a new day's attempts; cards reflect saved results."""
from io import BytesIO

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api import miniapp


def client(monkeypatch):
    app = FastAPI()
    app.include_router(miniapp.router)
    monkeypatch.setattr(miniapp, "_webapp_user", lambda payload, cost=1: (
        42, {"first_name": "Anna", "current_streak": 4},
    ))
    monkeypatch.setattr(miniapp, "_require_feature", lambda *args: None)
    monkeypatch.setattr(miniapp, "today_iso", lambda: "2026-09-27")
    return TestClient(app)


def test_stale_daily_guess_and_hint_do_not_mutate(monkeypatch):
    api = client(monkeypatch)
    monkeypatch.setattr(miniapp, "play", lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("stale guess reached game rules")
    ))
    monkeypatch.setattr(miniapp.game, "take_hint", lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("stale hint reached game rules")
    ))
    for route, fields in (
        ("/app/api/guess", {"answer": "Messi"}),
        ("/app/api/hint", {}),
    ):
        response = api.post(route, json={**fields, "expected_day": "2026-09-26"})
        assert response.status_code == 409
        assert response.json()["detail"] == "daily_changed"
        assert api.post(route, json={**fields, "expected_day": "yesterday"}).status_code == 422


def test_card_uses_saved_result_and_rejects_client_claims(monkeypatch):
    api = client(monkeypatch)
    result = {"day": "2026-09-27", "solved": True, "attempts": 2, "hints": 1}
    monkeypatch.setattr(miniapp.firebase_service, "get_daily_history", lambda uid, limit: [result])
    monkeypatch.setattr(miniapp.trophies, "showcase", lambda *args: [])
    captured = {}

    def render(*args, **kwargs):
        captured.update(kwargs)
        captured["attempts"] = args[3]
        return BytesIO(b"image")

    monkeypatch.setattr(miniapp, "card_image", render)
    assert api.post("/app/api/card", json={"solved": False, "attempts": 5}).status_code == 200
    assert api.post("/app/api/card", json={"attempts": "oops"}).status_code == 422
    response = api.post("/app/api/card", json={})
    assert response.status_code == 200
    assert response.json()["image"].startswith("data:image/png;base64,")
    assert captured["attempts"] == 2
    assert captured["solved"] is True
    assert captured["hints"] == 1
    assert captured["streak"] == 4

    result.update({"attempts": 1, "hints": 2})
    assert api.post("/app/api/card", json={}).status_code == 200
    assert captured["hints"] == 2

    result["day"] = "2026-09-26"
    assert api.post("/app/api/card", json={}).status_code == 409
