"""Recap mensile (#245): soglia, numeri del mese, perla, squadra, stile e percentuale."""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api import miniapp
from services import monthly_recap

MONTH = "2026-09"


def day(n, solved=True, attempts=1, hints=0, **extra):
    return {"day": f"{MONTH}-{n:02d}", "solved": solved, "attempts": attempts, "hints": hints, **extra}


def challenge(teams, players=20, solved=10, player_id=None, answers=("mario rossi",)):
    return {
        "player_id": player_id, "correct_answers": list(answers), "players_count": players,
        "solved_count": solved,
        "career_path": [{"team": team, "start_year": 2000 + i, "end_year": 2001 + i} for i, team in enumerate(teams)],
    }


def test_too_few_days_hide_the_recap():
    recap = monthly_recap.summarize(MONTH, [day(n) for n in range(1, 8)], {})
    assert recap == {"month": MONTH, "available": False, "played": 7, "min_played": 8}


def test_the_numbers_of_the_month():
    history = [day(n, attempts=1 + n % 3) for n in range(1, 11)] + [day(12, solved=False, attempts=3)]
    history.append({"day": "2026-08-31", "solved": True, "attempts": 1})  # un altro mese: fuori
    recap = monthly_recap.summarize(MONTH, history, {})

    assert recap["available"] is True
    assert (recap["played"], recap["solved"], recap["days"]) == (11, 10, 30)
    assert recap["calendar"][:12] == ["won"] * 10 + ["skip", "lost"]
    assert recap["attempts"] == [3, 4, 3]
    assert recap["best_streak"] == 10


def test_the_gem_is_the_rarest_solve_and_ignores_tiny_samples():
    history = [day(n) for n in range(1, 10)]
    challenges = {row["day"]: challenge(["A", "B"], players=20, solved=15) for row in history}
    challenges[f"{MONTH}-03"] = challenge(["Ajax", "Barcellona"], players=50, solved=3, answers=("jari litmanen",))
    challenges[f"{MONTH}-04"] = challenge(["X", "Y"], players=2, solved=0)  # troppo pochi giocatori

    gem = monthly_recap.summarize(MONTH, history, challenges)["gem"]

    assert gem["day"] == f"{MONTH}-03" and gem["rate"] == 6
    assert gem["name"] == "Jari Litmanen"
    assert [stop["team"] for stop in gem["path"]] == ["Ajax", "Barcellona"]


def test_the_lucky_club_needs_at_least_two_players():
    history = [day(n) for n in range(1, 10)]
    challenges = {row["day"]: challenge([f"Club {row['day']}"]) for row in history}
    assert "lucky_club" not in monthly_recap.summarize(MONTH, history, challenges)

    challenges[f"{MONTH}-01"] = challenge(["Juventus", "Milan"], answers=("alessandro del piero",))
    challenges[f"{MONTH}-02"] = challenge(["Juventus"], answers=("david trezeguet",))
    club = monthly_recap.summarize(MONTH, history, challenges)["lucky_club"]
    assert club == {"team": "Juventus", "count": 2, "players": ["Alessandro Del Piero", "David Trezeguet"]}


@pytest.mark.parametrize("rows, key", [
    ([day(n, first=n <= 3) for n in range(1, 11)], "professor"),
    ([day(n, attempts=1) for n in range(1, 11)], "sniper"),
    ([day(n, attempts=2) for n in range(1, 11)], "purist"),
    ([day(n, attempts=3, hints=1) for n in range(1, 11)], "last_minute"),
    ([day(n, attempts=2, hints=1) for n in range(1, 28)], "marathon"),
    ([day(n, attempts=2, hints=1) for n in range(1, 11)], "playmaker"),
])
def test_the_play_style(rows, key):
    assert monthly_recap.summarize(MONTH, rows, {})["style"]["key"] == key


def test_better_than_comes_from_the_saved_distribution():
    history = [day(n) for n in range(1, 10)]
    closure = {"points_distribution": [1, 2, 3, 4, 10, 20, 30, 40, 50, 60]}
    assert monthly_recap.summarize(MONTH, history, {}, monthly_points=35, closure=closure)["better_than"] == 70
    assert "better_than" not in monthly_recap.summarize(MONTH, history, {}, monthly_points=35)
    assert "better_than" not in monthly_recap.summarize(MONTH, history, {}, closure=closure)


def test_firsts_are_only_counted_once_the_history_records_them():
    old = monthly_recap.summarize(MONTH, [day(n) for n in range(1, 10)], {})
    new = monthly_recap.summarize(MONTH, [day(n, first=n == 2) for n in range(1, 10)], {})
    assert "firsts" not in old and new["firsts"] == 1


def test_recent_months_are_the_closed_ones():
    assert monthly_recap.previous_month("2026-01-05") == "2025-12"
    assert monthly_recap.recent_months("2026-10-01") == ["2026-09", "2026-08", "2026-07"]


# --- lettura, cache e API -----------------------------------------------------------------

@pytest.fixture
def store(monkeypatch):
    state = {"history": [day(n) for n in range(1, 10)], "closure": {"points_distribution": [1, 5, 9]}, "writes": []}
    fs = monthly_recap.fs
    monkeypatch.setattr(fs, "get_daily_history", lambda uid, limit: state["history"])
    monkeypatch.setattr(fs, "get_daily_path", lambda d: challenge(["Inter", "Milan"]))
    closure = SimpleNamespace(get=lambda: SimpleNamespace(
        exists=state["closure"] is not None, to_dict=lambda: state["closure"]))
    monkeypatch.setattr(fs, "db", SimpleNamespace(collection=lambda name: SimpleNamespace(document=lambda doc: closure)))
    monkeypatch.setattr(fs, "user_ref", lambda uid: SimpleNamespace(update=lambda data: state["writes"].append(data)))
    return state


def test_a_recap_is_saved_once_the_month_is_closed(store):
    recap = monthly_recap.recap_for(42, {"monthly_totals": {MONTH: 6}}, MONTH, today="2026-10-02")
    assert recap["better_than"] == 67
    assert store["writes"] == [{f"recaps.{MONTH}": recap}]

    store["writes"].clear()
    assert monthly_recap.recap_for(42, {"recaps": {MONTH: recap}}, MONTH, today="2026-10-02") is recap
    assert store["writes"] == []


def test_without_the_closure_the_recap_is_not_cached(store):
    store["closure"] = None
    recap = monthly_recap.recap_for(42, {}, MONTH, today="2026-10-02")
    assert recap["available"] and "better_than" not in recap
    assert store["writes"] == []


def test_too_few_days_are_cached_too_once_the_month_is_closed(store):
    store["history"] = [day(n) for n in range(1, 4)]
    recap = monthly_recap.recap_for(42, {}, MONTH, today="2026-10-02")
    assert recap["available"] is False
    assert store["writes"] == [{f"recaps.{MONTH}": recap}]


def test_only_recent_closed_months_are_served(store):
    assert monthly_recap.recap_for(42, {}, "2026-10", today="2026-10-02") is None
    assert monthly_recap.recap_for(42, {}, "2025-01", today="2026-10-02") is None


@pytest.fixture
def api(monkeypatch):
    app = FastAPI()
    app.include_router(miniapp.router)
    monkeypatch.setattr(miniapp, "_webapp_user", lambda payload, cost=1: (42, {"first_name": "Anna"}))
    monkeypatch.setattr(monthly_recap, "today_iso", lambda: "2026-10-02")
    monkeypatch.setattr(monthly_recap, "recap_for", lambda uid, user, month: {"month": month, "available": False})
    return TestClient(app)


@pytest.mark.parametrize("month", ["2026-13", "2026-9", "2026-10", "2020-01", 202609, "x" * 20])
def test_the_api_refuses_months_it_cannot_serve(api, month):
    assert api.post("/app/api/recap", json={"month": month}).status_code == 422


def test_the_api_defaults_to_the_last_closed_month(api):
    body = api.post("/app/api/recap", json={}).json()
    assert body["recap"]["month"] == "2026-09"
    assert body["months"] == ["2026-09", "2026-08", "2026-07"]
    assert body["name"] == "Anna"


def test_the_share_card_renders():
    recap = monthly_recap.summarize(MONTH, [day(n) for n in range(1, 12)], {}, monthly_points=9,
                                    closure={"points_distribution": [1, 2, 9, 20]})
    png = monthly_recap.recap_card_png(recap, "Anna", "it")
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
