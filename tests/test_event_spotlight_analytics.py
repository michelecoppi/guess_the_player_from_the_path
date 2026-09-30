"""Mini App Events visits are counted by where they came from (#248).

The Daily banner and the Arena dot load the events in the background: that load carries no
`entry` and must never count as a view. Opening the Events page does, with its entry point.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api import miniapp
from services import app_events
from services import product_analytics as analytics

CARD = {"code": "carriera_al_buio", "type": "blind_path", "available": True}


@pytest.fixture
def api(monkeypatch):
    app = FastAPI()
    app.include_router(miniapp.router)
    monkeypatch.setattr(miniapp, "_webapp_user", lambda payload, cost=1: (42, {"first_name": "Anna"}))
    monkeypatch.setattr(miniapp, "_require_feature", lambda *args: None)
    return TestClient(app)


@pytest.fixture
def captured(monkeypatch):
    events = []
    monkeypatch.setattr(miniapp.analytics, "capture", lambda event, **kwargs: events.append((event, kwargs)))
    return events


def _events(monkeypatch, cards):
    monkeypatch.setattr(app_events, "list_events", lambda user_id, lang: {"events": cards})


@pytest.mark.parametrize("entry", ["daily_banner", "arena_card", "arena_list"])
def test_a_visit_is_an_event_view_with_its_entry(api, monkeypatch, captured, entry):
    _events(monkeypatch, [dict(CARD, available=False, code="spento"), CARD])
    response = api.post("/app/api/arena", json={"mode": "events", "action": "get", "entry": entry})
    assert response.status_code == 200
    assert response.json()["events"][1]["code"] == "carriera_al_buio"
    assert captured == [(analytics.Event.EVENT_VIEWED, {"user_id": 42, "properties": {
        "surface": "miniapp", "entry": entry, "event_code": "carriera_al_buio", "event_type": "blind_path",
    }})]


@pytest.mark.parametrize("entry", [None, "other", "x" * 20])
def test_background_or_unknown_loads_are_not_views(api, monkeypatch, captured, entry):
    _events(monkeypatch, [CARD])
    body = {"mode": "events", "action": "get"}
    if entry:
        body["entry"] = entry
    assert api.post("/app/api/arena", json=body).status_code == 200
    assert captured == []


def test_entry_must_be_short_text(api, monkeypatch, captured):
    _events(monkeypatch, [CARD])
    for bad in (["daily_banner"], 1, "x" * 21):
        assert api.post("/app/api/arena", json={"mode": "events", "entry": bad}).status_code == 422
    assert captured == []


def test_a_visit_without_a_running_event_still_counts(api, monkeypatch, captured):
    _events(monkeypatch, [])
    api.post("/app/api/arena", json={"mode": "events", "entry": "arena_list"})
    assert captured == [(analytics.Event.EVENT_VIEWED, {"user_id": 42, "properties": {
        "surface": "miniapp", "entry": "arena_list"}})]


def test_the_entry_property_passes_the_analytics_schema():
    cleaned = analytics._clean_properties(analytics.Event.EVENT_VIEWED, {
        "surface": "miniapp", "entry": "daily_banner", "event_code": "carriera_al_buio", "event_type": "blind_path",
    })
    assert cleaned == {"surface": "miniapp", "entry": "daily_banner",
                       "event_code": "carriera_al_buio", "event_type": "blind_path"}
    assert "entry" not in analytics._clean_properties(analytics.Event.EVENT_VIEWED, {"entry": "elsewhere"})
