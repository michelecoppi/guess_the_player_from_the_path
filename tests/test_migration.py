"""Le trasformazioni della migrazione (scripts/migrate_firestore.py) sono funzioni pure
proprio per poterle provare qui: girano una volta sola su dati veri, quindi devono essere
giuste al primo colpo.
"""
from scripts.migrate_firestore import (
    merge_duplicate_users,
    migrate_daily_path_payload,
    migrate_event_payload,
    migrate_user_payload,
    participants_from_ranking,
)


def test_user_gets_notifications_flag_from_the_old_chat_id_sentinel():
    assert migrate_user_payload({"telegram_id": 1, "chat_id": 12345})["notifications_enabled"] is True
    assert migrate_user_payload({"telegram_id": 1, "chat_id": -1})["notifications_enabled"] is False


def test_user_who_already_guessed_keeps_the_flag_anchored_to_today():
    payload = migrate_user_payload(
        {"telegram_id": 1, "has_guessed_today": True, "daily_attempts": 2}, today="2026-09-07"
    )
    assert payload["last_played_day"] == "2026-09-07"
    assert payload["has_guessed_today"] is True
    assert payload["daily_attempts"] == 2


def test_user_who_did_not_play_starts_clean():
    payload = migrate_user_payload(
        {"telegram_id": 1, "has_guessed_today": False, "daily_attempts": 0}, today="2026-09-07"
    )
    assert payload["last_played_day"] is None
    assert payload["daily_attempts"] == 0
    assert payload["has_guessed_today"] is False


def test_duplicate_users_are_merged_without_losing_points_or_trophies():
    first = {
        "telegram_id": 7, "first_name": "Anna", "points_totali": 10, "monthly_points": 3,
        "players_guessed": 4, "bonus_first_guessed": 1, "trophies": ["1_evento"], "chat_id": -1,
        "notifications_enabled": False, "last_played_day": "2026-09-01",
    }
    second = {
        "telegram_id": 7, "first_name": "Anna", "points_totali": 5, "monthly_points": 2,
        "players_guessed": 2, "bonus_first_guessed": 0, "trophies": ["2_altro", "1_evento"],
        "chat_id": 999, "notifications_enabled": True, "last_played_day": "2026-09-05",
        "has_guessed_today": True,
    }

    merged = merge_duplicate_users(first, second)

    assert merged["points_totali"] == 15
    assert merged["monthly_points"] == 5
    assert merged["players_guessed"] == 6
    assert sorted(merged["trophies"]) == ["1_evento", "2_altro"]
    assert merged["chat_id"] == 999
    assert merged["notifications_enabled"] is True
    assert merged["last_played_day"] == "2026-09-05"


def test_daily_path_document_id_becomes_iso():
    day, payload = migrate_daily_path_payload({"current_day": "01/12/26", "player_id": "messi"})
    assert day == "2026-12-01"
    assert payload["day"] == "2026-12-01"
    assert "current_day" not in payload


def test_daily_path_falls_back_on_the_old_document_id():
    day, payload = migrate_daily_path_payload({"player_id": "messi"}, old_doc_id="01-12-26")
    assert day == "2026-12-01"
    assert payload["day"] == "2026-12-01"


def test_event_dates_and_daily_data_keys_become_iso():
    payload = migrate_event_payload({
        "dates": ["01/12/26", "02/12/26"],
        "daily_data": {"01/12/26": {"points": 2}, "02/12/26": {"points": 2}},
        "trophy_day": "02/12/26",
        "ranking": {"1": {"points": 3}},
    })

    assert payload["dates"] == ["2026-12-01", "2026-12-02"]
    assert sorted(payload["daily_data"]) == ["2026-12-01", "2026-12-02"]
    assert payload["trophy_day"] == "2026-12-02"
    assert "ranking" not in payload  # esce dal documento: diventa una sotto-collection


def test_ranking_becomes_one_document_per_participant():
    participants = participants_from_ranking({
        "42": {
            "telegram_id": 42, "name": "Anna", "points": 7,
            "daily_attempts": {"01/12/26": 3, "02/12/26": 1},
            "has_guessed_today": True,
        },
        "99": {"telegram_id": 99, "name": "Bruno", "points": 2},
    })

    assert set(participants) == {"42", "99"}
    anna = participants["42"]
    assert anna["points"] == 7
    assert anna["last_played_day"] == "2026-12-02"
    assert anna["daily_attempts"] == 1  # solo i tentativi dell'ultimo giorno giocato
    assert participants["99"]["last_played_day"] is None


def test_ranking_entries_that_are_not_dicts_are_ignored():
    assert participants_from_ranking({"42": "rotto", "7": None}) == {}
    assert participants_from_ranking(None) == {}
