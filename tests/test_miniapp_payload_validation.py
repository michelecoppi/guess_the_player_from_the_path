"""Malformed Mini App input is rejected before game state or Telegram changes."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api import miniapp


@pytest.fixture
def api(monkeypatch):
    app = FastAPI()
    app.include_router(miniapp.router)
    monkeypatch.setattr(miniapp, "_webapp_user", lambda payload, cost=1: (42, {"first_name": "Anna"}))
    monkeypatch.setattr(miniapp, "_require_feature", lambda *args: None)
    return TestClient(app)


@pytest.mark.parametrize("answer", [["Messi"], 123, {"name": "Messi"}, " ", "x" * 221])
@pytest.mark.parametrize("day", [None, "2020-01-01"], ids=["daily", "archive"])
def test_bad_guess_never_reaches_game(api, monkeypatch, answer, day):
    monkeypatch.setattr(miniapp, "play", lambda *args, **kwargs: pytest.fail("attempt consumed"))
    body = {"answer": answer}
    if day:
        body["day"] = day
    response = api.post("/app/api/guess", json=body)
    assert response.status_code == 422


@pytest.mark.parametrize("day", [["2020-01-01"], 123, {}, "x" * 100])
def test_bad_archive_day_never_reaches_game(api, monkeypatch, day):
    monkeypatch.setattr(miniapp, "play", lambda *args, **kwargs: pytest.fail("attempt consumed"))
    response = api.post("/app/api/guess", json={"answer": "Messi", "day": day})
    assert response.status_code == 422


@pytest.mark.parametrize("message", [["bad"], 123, {"text": "bad"}, "x" * 3501])
def test_bad_report_never_sends(api, message):
    response = api.post("/app/api/support/report", json={"message": message})
    assert response.status_code == 422


@pytest.mark.parametrize("path,body", [
    ("/app/api/arena", {"mode": []}),
    ("/app/api/arena", {"mode": "training", "answer": {}}),
    ("/app/api/arena", {"mode": "events", "revision": True}),
    ("/app/api/calendar", {"day": {}}),
    ("/app/api/league", {"action": "create", "name": []}),
    ("/app/api/shop/look", {"action": "save", "name": 12}),
])
def test_service_inputs_reject_wrong_types(api, path, body):
    assert api.post(path, json=body).status_code == 422


@pytest.mark.parametrize("init_data", [["signed"], 123, {}, "x" * 4097])
def test_bad_init_data_is_rejected_before_parser(monkeypatch, init_data):
    app = FastAPI()
    app.include_router(miniapp.router)
    monkeypatch.setattr(
        miniapp, "user_id_from_init_data", lambda *args: pytest.fail("invalid initData reached parser"),
    )
    response = TestClient(app).post("/app/api/me", json={"initData": init_data})
    assert response.status_code == 422
