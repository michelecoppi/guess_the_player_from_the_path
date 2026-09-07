from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from services import daily_generator
from services.player_pool import get_all_players

ITALY_TZ = ZoneInfo("Europe/Rome")


def test_pick_player_avoids_recent_repeats():
    date_dt = datetime(2026, 3, 10, tzinfo=ITALY_TZ)
    all_ids = {p["id"] for p in get_all_players()}
    recent_ids = all_ids - {"messi"}  # tutti tranne uno esclusi

    player, difficulty = daily_generator.pick_player_for_date(date_dt, recent_ids, rotation_index=0)
    assert player["id"] == "messi"
    assert difficulty in ("easy", "medium", "hard", "impossible")


def test_pick_player_deterministic_for_same_date():
    date_dt = datetime(2026, 3, 10, tzinfo=ITALY_TZ)
    player1, diff1 = daily_generator.pick_player_for_date(date_dt, set(), rotation_index=2)
    player2, diff2 = daily_generator.pick_player_for_date(date_dt, set(), rotation_index=2)
    assert player1["id"] == player2["id"]
    assert diff1 == diff2


def test_pick_player_raises_when_dataset_empty(monkeypatch):
    monkeypatch.setattr(daily_generator, "get_all_players", lambda: [])
    with pytest.raises(ValueError):
        daily_generator.pick_player_for_date(datetime(2026, 1, 1, tzinfo=ITALY_TZ), set(), 0)


def test_ensure_daily_buffer_skips_existing_days(monkeypatch):
    saved = []
    monkeypatch.setattr(daily_generator.firebase_service, "daily_path_exists", lambda day_iso: True)
    monkeypatch.setattr(daily_generator.firebase_service, "get_recent_player_ids", lambda days: [])
    monkeypatch.setattr(daily_generator.firebase_service, "save_daily_path", lambda day_iso, doc: saved.append((day_iso, doc)))
    monkeypatch.setattr(daily_generator.firebase_service, "get_blocked_player_ids", lambda: [])

    result = daily_generator.ensure_daily_buffer(days_ahead=3)

    assert result == []
    assert saved == []


def test_ensure_daily_buffer_generates_missing_days(monkeypatch):
    saved = []
    monkeypatch.setattr(daily_generator.firebase_service, "daily_path_exists", lambda day_iso: False)
    monkeypatch.setattr(daily_generator.firebase_service, "get_recent_player_ids", lambda days: [])
    monkeypatch.setattr(daily_generator.firebase_service, "save_daily_path", lambda day_iso, doc: saved.append((day_iso, doc)))
    monkeypatch.setattr(daily_generator.firebase_service, "get_blocked_player_ids", lambda: [])

    result = daily_generator.ensure_daily_buffer(days_ahead=2)

    assert len(result) == 2
    assert len(saved) == 2
    for day_iso, doc in saved:
        assert doc["correct_answers"]
        assert doc["career_path"]
        assert doc["difficulty"] in ("easy", "medium", "hard", "impossible")
        assert doc["first_correct_user"] is False


def test_build_daily_path_doc_has_solvable_answers():
    date_dt = datetime(2026, 5, 1, tzinfo=ITALY_TZ)
    doc = daily_generator.build_daily_path_doc(date_dt, set(), rotation_index=0)
    assert len(doc["correct_answers"]) > 0
    assert len(doc["career_path"]) >= 2
