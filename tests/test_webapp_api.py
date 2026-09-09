"""Quello che la mini app riceve - e soprattutto quello che non deve ricevere.

Il test che vale piu' di tutti e' `test_the_answer_never_reaches_the_page`: adesso che
la mini app gioca davvero, una risposta che si porta dietro `correct_answers` sarebbe
il gioco finito, e non se ne accorgerebbe nessuno guardando lo schermo.
"""
import json

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
    state = {
        "user": dict(USER),
        "challenge": {
            "day": DAY,
            "difficulty": "hard",
            "first_correct_user": True,
            "player_id": "messi",
            # Non devono uscire mai: sono qui apposta, per poterlo verificare.
            "correct_answers": ["messi", "lionel messi"],
            "career_path": [
                {"team": "Barcelona", "country": "Spagna", "league": "La Liga",
                 "start_year": 2004, "end_year": 2021},
            ],
        },
        "history": [],
        "past": [],
        "recovered": set(),
        "archive_result": {},
    }

    monkeypatch.setattr(webapp_api.firebase_service, "get_daily_history", lambda uid, limit=60: state["history"])
    monkeypatch.setattr(
        webapp_api.firebase_service, "get_past_daily_paths",
        lambda limit=10, before_day_iso=None: state["past"],
    )
    monkeypatch.setattr(webapp_api.firebase_service, "get_solved_archive_days", lambda uid: state["recovered"])
    monkeypatch.setattr(webapp_api.firebase_service, "get_archive_result", lambda uid, day: state["archive_result"])

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


def test_profile_reuses_authenticated_user(firebase, monkeypatch):
    def unexpected_read(*args, **kwargs):
        pytest.fail("The authenticated user must not be read twice")

    monkeypatch.setattr(webapp_api.firebase_service, "get_user_data", unexpected_read)
    profile = webapp_api.build_profile(42, day_iso=DAY, user=firebase["user"])
    assert profile["user"]["points"] == 120
    assert profile["leaderboard"]
    assert profile["leagues"]


def test_lightweight_profile_skips_social_queries_but_refreshes_game(firebase, monkeypatch):
    full = webapp_api.build_profile(42, day_iso=DAY)

    def unexpected_read(*args, **kwargs):
        pytest.fail("Game refresh must not query standings or leagues")

    for name in ("get_top_users", "get_league", "get_league_leaderboard"):
        monkeypatch.setattr(webapp_api.firebase_service, name, unexpected_read)
    firebase["user"]["daily_attempts"] = 3
    fresh = webapp_api.build_profile(42, day_iso=DAY, include_social=False)
    assert "leaderboard" not in fresh
    assert "leagues" not in fresh
    assert fresh["today"]["attempts_left"] == 0
    assert full["today"]["attempts_left"] == 1
    assert {**full, **fresh}["leagues"] == full["leagues"]
    assert "correct_answers" not in json.dumps(fresh)


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


# ---------------------------------------------------------------------------
# Quello che la pagina NON deve ricevere
# ---------------------------------------------------------------------------

def test_the_answer_never_reaches_the_page(firebase):
    """Il client e' il telefono di chi gioca: qualunque cosa gli mandiamo la puo' leggere."""
    payload = json.dumps(webapp_api.build_profile(42, day_iso=DAY), default=str).lower()
    assert "correct_answers" not in payload
    assert "player_id" not in payload
    assert "messi" not in payload


def test_only_the_hints_already_paid_for_are_sent(firebase, monkeypatch):
    monkeypatch.setattr(
        webapp_api, "build_hints", lambda player, lang: ["🌍 Nazionalità: Argentina", "🧭 Ruolo: Attaccante"]
    )
    firebase["user"]["daily_hints"] = 1
    hints = webapp_api.build_profile(42, day_iso=DAY)["today"]["hints"]

    assert hints["used"] == 1
    assert hints["total"] == 2
    assert hints["taken"] == ["🌍 Nazionalità: Argentina"]   # il secondo non si manda


def test_yesterdays_hints_do_not_count_today(firebase, monkeypatch):
    monkeypatch.setattr(webapp_api, "build_hints", lambda player, lang: ["a", "b"])
    firebase["user"]["daily_hints"] = 2
    firebase["user"]["last_played_day"] = "2026-09-01"

    hints = webapp_api.build_profile(42, day_iso=DAY)["today"]["hints"]
    assert hints["used"] == 0
    assert hints["taken"] == []


# ---------------------------------------------------------------------------
# Percorso tradotto, istogramma, calendario, suggerimenti
# ---------------------------------------------------------------------------

def test_the_career_path_arrives_translated(firebase):
    stops = webapp_api.build_profile(42, day_iso=DAY, lang="en")["today"]["career_path"]
    assert stops[0]["country"] == "Spain"
    assert stops[0]["league"] == "La Liga"      # nome proprio, non si traduce


def test_the_distribution_has_a_slot_per_attempt(firebase):
    firebase["user"]["solved_in"] = {"1": 3, "3": 7}
    distribution = webapp_api.build_profile(42, day_iso=DAY)["distribution"]

    assert distribution == [
        {"attempts": 1, "count": 3}, {"attempts": 2, "count": 0}, {"attempts": 3, "count": 7},
    ]


def test_a_user_who_never_solved_anything_has_an_empty_distribution(firebase):
    assert [d["count"] for d in webapp_api.build_profile(42, day_iso=DAY)["distribution"]] == [0, 0, 0]


def test_the_calendar_distinguishes_the_four_outcomes(firebase):
    firebase["past"] = [
        {"day": "2026-09-07", "difficulty": "easy"},
        {"day": "2026-09-06", "difficulty": "hard"},
        {"day": "2026-09-05", "difficulty": "medium"},
        {"day": "2026-09-04", "difficulty": "medium"},
    ]
    firebase["history"] = [
        {"day": "2026-09-07", "solved": True, "attempts": 2},
        {"day": "2026-09-06", "solved": False, "attempts": 3},
    ]
    firebase["recovered"] = {"2026-09-05"}

    calendar = webapp_api.build_calendar(42, today=DAY)
    assert [day["status"] for day in calendar] == ["solved", "lost", "recovered", "missed"]
    assert [day["playable"] for day in calendar] == [False, True, False, True]
    assert calendar[0]["attempts"] == 2


def test_a_day_lost_and_then_recovered_counts_as_recovered(firebase):
    """Recuperata in archivio non e' un buco: e' diverso da una giornata persa e basta."""
    firebase["past"] = [{"day": "2026-09-06", "difficulty": "hard"}]
    firebase["history"] = [{"day": "2026-09-06", "solved": False, "attempts": 3}]
    firebase["recovered"] = {"2026-09-06"}

    assert webapp_api.build_calendar(42, today=DAY)[0]["status"] == "recovered"


def test_an_archive_challenge_carries_the_path_but_not_the_answer(firebase):
    firebase["archive_result"] = {"attempts": 1, "solved": False}
    day = webapp_api.build_archive_challenge(42, "2026-09-06")

    assert day["attempts_left"] == 2
    assert day["career_path"][0]["team"] == "Barcelona"
    assert "correct_answers" not in day and "player_id" not in day


def test_a_missing_archive_day_gives_nothing(firebase):
    firebase["challenge"] = None
    assert webapp_api.build_archive_challenge(42, "2026-09-06") is None


# ---------------------------------------------------------------------------
# Il tentativo dalla mini app: stesse regole della chat, stessa card
# ---------------------------------------------------------------------------

def test_a_guess_without_a_day_plays_today(firebase, monkeypatch):
    played = []
    monkeypatch.setattr(
        webapp_api.game, "play_daily",
        lambda uid, data, answer, first_name=None, **kw: played.append(answer) or {"status": "wrong", "attempts_left": 2},
    )
    webapp_api.play(42, USER, "messi", today=DAY)
    assert played == ["messi"]


def test_a_guess_with_a_past_day_plays_the_archive(firebase, monkeypatch):
    played = []
    monkeypatch.setattr(
        webapp_api.game, "play_archive",
        lambda uid, day, answer, mx: played.append((day, mx)) or {"status": "wrong", "attempts_left": 1},
    )
    webapp_api.play(42, USER, "messi", day="2026-09-01", today=DAY)
    assert played == [("2026-09-01", webapp_api.MAX_ARCHIVE_ATTEMPTS)]


def test_a_guess_with_todays_date_is_still_todays_challenge(firebase, monkeypatch):
    """La pagina puo' mandare `day` anche per oggi: non deve finire nell'archivio, che non
    darebbe punti."""
    played = []
    monkeypatch.setattr(
        webapp_api.game, "play_daily",
        lambda uid, data, answer, first_name=None, **kw: played.append(answer) or {"status": "wrong", "attempts_left": 2},
    )
    monkeypatch.setattr(webapp_api.game, "play_archive", lambda *a: pytest.fail("non deve passare di qui"))
    webapp_api.play(42, USER, "messi", day=DAY, today=DAY)
    assert played == ["messi"]


def test_the_share_card_appears_only_when_the_game_is_over(share_link):
    still_open = webapp_api.with_share_card({"status": "wrong", "attempts_left": 1, "attempts_used": 2}, "it", 3)
    assert "share" not in still_open

    lost = webapp_api.with_share_card({"status": "wrong", "attempts_left": 0, "attempts_used": 3}, "it", 3)
    assert "X/3" in lost["share"]["text"]

    won = webapp_api.with_share_card(
        {"status": "correct", "attempts_used": 2, "streak": 4, "hints_used": 1}, "it", 3
    )
    assert "2/3" in won["share"]["text"]
    assert "💡" in won["share"]["text"]


def test_the_shared_card_never_carries_the_answer(share_link):
    card = webapp_api.with_share_card({"status": "correct", "attempts_used": 1}, "it", 3)
    assert "messi" not in card["share"]["text"].lower()


@pytest.fixture
def share_link(monkeypatch):
    """Senza BOT_USERNAME non c'e' nessun link da condividere: nei test lo diamo per
    configurato, altrimenti si proverebbe il caso sbagliato."""
    from services import share

    monkeypatch.setattr(share, "BOT_USERNAME", "guess_the_player_bot")
