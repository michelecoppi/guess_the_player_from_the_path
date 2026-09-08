import pytest

from services import content_admin
from services.content_admin import ContentAdminError
from services.player_pool import get_all_players

TODAY = "2026-03-10"


@pytest.fixture
def fake_db(monkeypatch):
    """Un finto Firestore in memoria: le funzioni di content_admin vanno provate sulle
    regole che applicano, non sul client di Firebase."""
    state = {"daily": {}, "events": {}, "blocked": [], "recent": []}

    def get_daily_path(day_iso):
        return state["daily"].get(day_iso)

    def save_daily_path(day_iso, doc):
        doc = dict(doc)
        doc["day"] = day_iso
        state["daily"][day_iso] = doc

    def delete_daily_path(day_iso):
        return state["daily"].pop(day_iso, None) is not None

    def update_daily_path(day_iso, fields):
        state["daily"][day_iso].update(fields)

    def get_daily_paths_range(start, end, limit=180):
        return [doc for day, doc in sorted(state["daily"].items()) if start <= day <= end]

    def get_event(code):
        event = state["events"].get(code)
        return dict(event) if event else None

    def update_event(code, fields):
        event = state["events"][code]
        for key, value in fields.items():
            if "." in key:  # daily_data.<giorno>.<campo>, come Firestore
                _, day, field = key.split(".", 2)
                event.setdefault("daily_data", {}).setdefault(day, {})[field] = value
            else:
                event[key] = value

    def delete_event(code):
        return state["events"].pop(code, None) is not None

    def get_active_events(day_iso=None):
        return [e for e in state["events"].values() if day_iso in (e.get("dates") or [])]

    monkeypatch.setattr(content_admin.firebase_service, "get_daily_path", get_daily_path)
    monkeypatch.setattr(content_admin.firebase_service, "save_daily_path", save_daily_path)
    monkeypatch.setattr(content_admin.firebase_service, "delete_daily_path", delete_daily_path)
    monkeypatch.setattr(content_admin.firebase_service, "update_daily_path", update_daily_path)
    monkeypatch.setattr(content_admin.firebase_service, "get_daily_paths_range", get_daily_paths_range)
    monkeypatch.setattr(content_admin.firebase_service, "get_event", get_event)
    monkeypatch.setattr(content_admin.firebase_service, "update_event", update_event)
    monkeypatch.setattr(content_admin.firebase_service, "delete_event", delete_event)
    monkeypatch.setattr(content_admin.firebase_service, "get_active_events", get_active_events)
    monkeypatch.setattr(content_admin.firebase_service, "get_blocked_player_ids", lambda: state["blocked"])
    monkeypatch.setattr(content_admin.firebase_service, "get_recent_player_ids", lambda days: state["recent"])
    return state


def _event(code="ev", dates=("2026-03-09", "2026-03-10", "2026-03-11"), with_content=True):
    dates = list(dates)
    daily_data = {day: {"correct_answers": ["x"], "points": 1} for day in dates} if with_content else {}
    return {
        "code": code,
        "name": "Evento di prova",
        "dates": dates,
        "daily_data": daily_data,
        "trophy_day": dates[-1],
        "active": True,
        "type": "path",
    }


# ---------------------------------------------------------------------------
# Sfide giornaliere
# ---------------------------------------------------------------------------

def test_day_status_distinguishes_past_today_and_planned():
    assert content_admin.day_status("2026-03-09", TODAY) == content_admin.STATUS_PAST
    assert content_admin.day_status(TODAY, TODAY) == content_admin.STATUS_TODAY
    assert content_admin.day_status("2026-03-11", TODAY) == content_admin.STATUS_PLANNED


def test_describe_daily_without_document_is_marked_missing():
    info = content_admin.describe_daily(TODAY, None, today=TODAY)
    assert info["status"] == content_admin.STATUS_MISSING
    assert info["exists"] is False
    assert info["day_display"] == "10/03/26"


def test_describe_daily_completes_the_document_with_dataset_info():
    doc = {"player_id": "messi", "correct_answers": ["messi"], "difficulty": "easy", "career_path": [{"team": "Barcelona"}]}
    info = content_admin.describe_daily(TODAY, doc, today=TODAY)

    assert info["player_name"] == "Lionel Messi"  # non e' nel documento: viene dal dataset
    assert info["player_in_dataset"] is True
    assert info["difficulty_score"] is not None
    assert info["points"] == 1  # easy
    assert info["teams_count"] == 1
    assert info["status"] == content_admin.STATUS_TODAY


def test_describe_daily_survives_a_player_removed_from_the_dataset():
    doc = {"player_id": "non_esiste", "correct_answers": ["x"], "difficulty": "hard", "career_path": []}
    info = content_admin.describe_daily(TODAY, doc, today=TODAY)

    assert info["player_in_dataset"] is False
    assert info["player_name"] is None
    assert info["answers"] == ["x"]


def test_list_daily_window_includes_days_without_challenge(fake_db):
    fake_db["daily"]["2026-03-10"] = {"day": "2026-03-10", "player_id": "messi", "difficulty": "easy"}

    rows = content_admin.list_daily_window(days_back=1, days_ahead=1, today=TODAY)

    assert [r["day"] for r in rows] == ["2026-03-09", "2026-03-10", "2026-03-11"]
    assert [r["exists"] for r in rows] == [False, True, False]
    assert rows[2]["status"] == content_admin.STATUS_MISSING


def test_buffer_health_counts_only_consecutive_days_from_today(fake_db):
    for day in ("2026-03-10", "2026-03-11", "2026-03-13"):  # il 12 manca: il buffer si ferma li'
        fake_db["daily"][day] = {"day": day, "player_id": "messi"}

    health = content_admin.buffer_health(today=TODAY)

    assert health["covered_days"] == 2
    assert health["last_covered_day"] == "2026-03-11"
    assert "2026-03-12" in health["missing_days"]


def test_set_daily_player_rejects_an_unknown_id(fake_db):
    with pytest.raises(ContentAdminError):
        content_admin.set_daily_player(TODAY, "non_esiste")


def test_set_daily_player_writes_answers_and_difficulty_from_the_dataset(fake_db):
    info = content_admin.set_daily_player(TODAY, "Messi")  # id normalizzato in minuscolo

    saved = fake_db["daily"][TODAY]
    assert saved["player_id"] == "messi"
    assert "lionel messi" in saved["correct_answers"]
    assert saved["career_path"]
    assert saved["source"] == "manual"
    assert info["player_name"] == "Lionel Messi"


def test_set_daily_player_does_not_reopen_an_assigned_bonus(fake_db):
    """Sostituire il giocatore di una giornata gia' vinta non deve rimettere in palio il
    bonus del primo: sarebbe un secondo bonus per lo stesso giorno."""
    fake_db["daily"][TODAY] = {"day": TODAY, "player_id": "messi", "first_correct_user": True}
    other_id = next(p["id"] for p in get_all_players() if p["id"] != "messi")

    content_admin.set_daily_player(TODAY, other_id)

    assert fake_db["daily"][TODAY]["player_id"] == other_id
    assert fake_db["daily"][TODAY]["first_correct_user"] is True


def test_regenerate_daily_picks_a_different_player_than_the_current_one(fake_db):
    first = content_admin.regenerate_daily("2026-03-15", avoid_current=False)
    fake_db["daily"]["2026-03-15"]["player_id"] = first["player_id"]

    second = content_admin.regenerate_daily("2026-03-15", avoid_current=True)

    assert second["player_id"] != first["player_id"]


def test_regenerate_daily_is_stable_without_avoid(fake_db):
    first = content_admin.regenerate_daily("2026-03-15", avoid_current=False)
    fake_db["daily"].clear()
    second = content_admin.regenerate_daily("2026-03-15", avoid_current=False)

    assert first["player_id"] == second["player_id"]


def test_parse_answers_list_normalizes_and_deduplicates():
    assert content_admin.parse_answers_list("Messi,  LEO   Messi | messi") == ["messi", "leo messi"]
    assert content_admin.parse_answers_list("") == []


def test_update_daily_answers_requires_an_existing_challenge(fake_db):
    with pytest.raises(ContentAdminError):
        content_admin.update_daily_answers(TODAY, ["messi"])


def test_update_daily_answers_refuses_an_empty_list(fake_db):
    fake_db["daily"][TODAY] = {"day": TODAY, "player_id": "messi"}
    with pytest.raises(ContentAdminError):
        content_admin.update_daily_answers(TODAY, [])


def test_update_daily_difficulty_rejects_an_unknown_level(fake_db):
    fake_db["daily"][TODAY] = {"day": TODAY, "player_id": "messi"}
    with pytest.raises(ContentAdminError):
        content_admin.update_daily_difficulty(TODAY, "difficilissima")

    content_admin.update_daily_difficulty(TODAY, "hard")
    assert fake_db["daily"][TODAY]["difficulty"] == "hard"


def test_set_daily_first_correct_reopens_the_bonus(fake_db):
    fake_db["daily"][TODAY] = {"day": TODAY, "player_id": "messi", "first_correct_user": True}

    content_admin.set_daily_first_correct(TODAY, False)

    assert fake_db["daily"][TODAY]["first_correct_user"] is False


def test_delete_daily_refuses_the_challenge_in_play(fake_db):
    fake_db["daily"][TODAY] = {"day": TODAY, "player_id": "messi"}

    with pytest.raises(ContentAdminError):
        content_admin.delete_daily(TODAY, today=TODAY)

    assert TODAY in fake_db["daily"]


def test_delete_daily_removes_a_planned_challenge(fake_db):
    fake_db["daily"]["2026-03-12"] = {"day": "2026-03-12", "player_id": "messi"}

    assert content_admin.delete_daily("2026-03-12", today=TODAY) is True
    assert "2026-03-12" not in fake_db["daily"]


# ---------------------------------------------------------------------------
# Eventi
# ---------------------------------------------------------------------------

def test_event_status_follows_the_calendar():
    assert content_admin.event_status(_event(dates=["2026-03-01", "2026-03-02"]), TODAY) == content_admin.EVENT_STATUS_ENDED
    assert content_admin.event_status(_event(dates=["2026-03-20"]), TODAY) == content_admin.EVENT_STATUS_PLANNED
    assert content_admin.event_status(_event(), TODAY) == content_admin.EVENT_STATUS_RUNNING


def test_describe_event_numbers_the_days_and_finds_the_current_one():
    detail = content_admin.describe_event(_event(), today=TODAY)

    assert detail["days_total"] == 3
    assert detail["current_index"] == 2
    assert detail["days"][1]["status"] == content_admin.STATUS_TODAY
    assert detail["trophy_day"] == "2026-03-11"
    assert detail["days_without_content"] == []


def test_describe_event_reports_days_without_content():
    event = _event()
    del event["daily_data"]["2026-03-11"]

    detail = content_admin.describe_event(event, today=TODAY)

    assert detail["days_without_content"] == ["11/03/26"]
    assert detail["days"][2]["has_content"] is False


def test_update_event_day_answers_refuses_a_day_outside_the_event(fake_db):
    fake_db["events"]["ev"] = _event()

    with pytest.raises(ContentAdminError):
        content_admin.update_event_day_answers("ev", "2026-04-01", ["risposta"])

    content_admin.update_event_day_answers("ev", "2026-03-11", ["risposta"])
    assert fake_db["events"]["ev"]["daily_data"]["2026-03-11"]["correct_answers"] == ["risposta"]


def test_set_event_day_first_correct_touches_only_that_day(fake_db):
    fake_db["events"]["ev"] = _event()

    content_admin.set_event_day_first_correct("ev", "2026-03-10", True)

    daily = fake_db["events"]["ev"]["daily_data"]
    assert daily["2026-03-10"]["first_correct_user"] is True
    assert "first_correct_user" not in daily["2026-03-11"]


def test_shift_event_remaps_dates_content_and_trophy_day(fake_db):
    event = _event()
    event["daily_data"]["2026-03-09"]["correct_answers"] = ["primo giorno"]
    fake_db["events"]["ev"] = event

    result = content_admin.shift_event("ev", "2026-03-20", today=TODAY)

    saved = fake_db["events"]["ev"]
    assert result["dates"] == ["2026-03-20", "2026-03-21", "2026-03-22"]
    assert saved["trophy_day"] == "2026-03-22"
    assert set(saved["daily_data"]) == set(result["dates"])
    # il contenuto segue il suo giorno, non resta appeso alla vecchia data
    assert saved["daily_data"]["2026-03-20"]["correct_answers"] == ["primo giorno"]


def test_shift_event_refuses_an_ended_event(fake_db):
    fake_db["events"]["ev"] = _event(dates=["2026-03-01", "2026-03-02"])

    with pytest.raises(ContentAdminError):
        content_admin.shift_event("ev", "2026-03-20", today=TODAY)


def test_shift_event_refuses_to_overlap_another_event(fake_db):
    fake_db["events"]["ev"] = _event()
    fake_db["events"]["altro"] = _event(code="altro", dates=["2026-03-21", "2026-03-22"])

    with pytest.raises(ContentAdminError) as excinfo:
        content_admin.shift_event("ev", "2026-03-20", today=TODAY)

    assert "sovrappon" in str(excinfo.value)


def test_delete_event_refuses_the_running_one_and_deletes_the_others(fake_db):
    fake_db["events"]["ev"] = _event()
    fake_db["events"]["vecchio"] = _event(code="vecchio", dates=["2026-03-01", "2026-03-02"])

    with pytest.raises(ContentAdminError):
        content_admin.delete_event("ev", today=TODAY)

    assert content_admin.delete_event("vecchio", today=TODAY) is True
    assert "vecchio" not in fake_db["events"]


def test_set_event_active_toggles_the_flag(fake_db):
    fake_db["events"]["ev"] = _event()

    content_admin.set_event_active("ev", False)

    assert fake_db["events"]["ev"]["active"] is False


def test_unknown_event_code_is_a_readable_error(fake_db):
    with pytest.raises(ContentAdminError) as excinfo:
        content_admin.set_event_active("non_esiste", False)
    assert "non_esiste" in str(excinfo.value)
