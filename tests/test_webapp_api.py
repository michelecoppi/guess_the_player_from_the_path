"""Il profilo che la mini app riceve: gli stessi numeri dei comandi, in una risposta sola."""
import pytest

from services import webapp_api

DAY = "2026-09-08"

USER = {
    "telegram_id": 42,
    "first_name": "Anna",
    "points_totali": 120,
    "monthly_points": 18,
    "players_guessed": 40,
    "bonus_first_guessed": 3,
    "current_streak": 5,
    "best_streak": 9,
    "archive_solved": 2,
    "trophies": ["1_giramondo_36_2026", "MON_July_3_2026_2"],
    "leagues": ["ABC23X"],
    "last_played_day": DAY,
    "has_guessed_today": True,
    "daily_attempts": 2,
}


@pytest.fixture
def firebase(monkeypatch):
    state = {"user": dict(USER), "challenge": {"day": DAY, "difficulty": "hard", "first_correct_user": True}}

    monkeypatch.setattr(webapp_api.firebase_service, "get_user_data", lambda uid: state["user"])
    monkeypatch.setattr(webapp_api.firebase_service, "get_daily_path", lambda day: state["challenge"])
    monkeypatch.setattr(webapp_api.firebase_service, "get_top_users", lambda limit=10: [
        {"telegram_id": 7, "username": "Bea", "points": 300},
        {"telegram_id": 42, "username": "Anna", "points": 120},
    ])
    monkeypatch.setattr(webapp_api.firebase_service, "get_league", lambda code: {"code": code, "name": "Amici del bar", "members_count": 4})
    monkeypatch.setattr(webapp_api.firebase_service, "get_league_leaderboard", lambda code, limit=20: [
        {"telegram_id": 7, "name": "Bea", "points": 60},
        {"telegram_id": 42, "name": "Anna", "points": 25},
    ])
    return state


def test_the_profile_carries_the_numbers_shown_by_the_commands(firebase):
    profile = webapp_api.build_profile(42, day_iso=DAY)

    assert profile["user"]["points"] == 120
    assert profile["user"]["streak"] == 5
    assert profile["user"]["trophies"] == 2


def test_today_is_marked_solved_only_for_the_current_day(firebase):
    solved = webapp_api.build_profile(42, day_iso=DAY)["today"]
    assert solved["solved"] is True
    assert solved["attempts_left"] == 1

    firebase["user"]["last_played_day"] = "2026-09-01"
    stale = webapp_api.build_profile(42, day_iso=DAY)["today"]
    assert stale["solved"] is False
    assert stale["attempts_used"] == 0  # i contatori di ieri valgono zero oggi


def test_the_reader_is_marked_in_the_leaderboard(firebase):
    rows = webapp_api.build_profile(42, day_iso=DAY)["leaderboard"]
    assert [row["me"] for row in rows] == [False, True]
    assert rows[0]["position"] == 1


def test_leagues_carry_the_personal_position(firebase):
    leagues = webapp_api.build_profile(42, day_iso=DAY)["leagues"]
    assert leagues[0]["name"] == "Amici del bar"
    assert leagues[0]["position"] == 2
    assert leagues[0]["points"] == 25


def test_an_unknown_user_has_no_profile(firebase, monkeypatch):
    monkeypatch.setattr(webapp_api.firebase_service, "get_user_data", lambda uid: None)
    assert webapp_api.build_profile(42) is None


def test_a_day_without_challenge_does_not_break_the_page(firebase):
    firebase["challenge"] = None
    today = webapp_api.build_profile(42, day_iso=DAY)["today"]
    assert today["available"] is False
    assert today["points"] == 0
