"""Calendario degli eventi dai template (#31): data fissa, finestre, regole e premi copiati."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from services import event_config, event_generator

ITALY_TZ = ZoneInfo("Europe/Rome")


def _template(template_id, schedule, **overrides):
    template = {
        "id": template_id, "name": template_id, "description": "d",
        "name_i18n": {"es": "x", "en": "x"}, "description_i18n": {"es": "x", "en": "x"},
        "type": "path", "category": "c", "difficulty": "medium", "duration_days": 3,
        "filters": {"min_teams": 3}, "schedule": schedule,
    }
    template.update(overrides)
    return event_config.resolved(template)


@pytest.fixture
def backend(monkeypatch):
    state = {"active": [], "saved": {}, "recent": [], "last_end": None, "templates": []}
    fs = event_generator.firebase_service
    monkeypatch.setattr(event_generator, "load_templates", lambda: state["templates"])
    monkeypatch.setattr(fs, "get_active_events", lambda day_iso=None: [
        e for e in state["active"] if day_iso is None or day_iso in e["dates"]
    ])
    monkeypatch.setattr(fs, "save_event", lambda code, doc: state["saved"].__setitem__(code, doc))
    monkeypatch.setattr(fs, "event_exists", lambda code: code in state["saved"])
    monkeypatch.setattr(fs, "get_recent_event_template_ids", lambda limit: state["recent"])
    monkeypatch.setattr(fs, "get_last_event_end_date", lambda: state["last_end"])
    return state


def test_a_fixed_event_is_created_ahead_and_only_once(backend):
    backend["templates"] = [_template("mondiali", {"mode": "fixed", "start": "2026-06-05"})]
    now = datetime(2026, 6, 1, 3, 0, tzinfo=ITALY_TZ)
    assert event_generator.maybe_generate_event(now) == "mondiali_20260605"
    doc = backend["saved"]["mondiali_20260605"]
    assert doc["dates"] == ["2026-06-05", "2026-06-06", "2026-06-07"]
    assert event_generator.maybe_generate_event(now) is None  # gia' creato, la rotazione non parte (min gap)


def test_a_fixed_event_too_far_ahead_waits(backend):
    backend["templates"] = [_template("mondiali", {"mode": "fixed", "start": "2026-07-01"})]
    assert event_generator.maybe_generate_event(datetime(2026, 6, 1, tzinfo=ITALY_TZ)) is None
    assert backend["saved"] == {}


def test_a_fixed_event_does_not_overlap_an_existing_event(backend):
    backend["templates"] = [_template("mondiali", {"mode": "fixed", "start": "2026-06-05"})]
    backend["active"] = [{"code": "altro", "name": "Altro", "dates": ["2026-06-06"]}]
    assert event_generator.maybe_generate_event(datetime(2026, 6, 1, tzinfo=ITALY_TZ)) is None
    assert backend["saved"] == {}


def test_rotation_never_takes_the_days_of_an_upcoming_fixed_event(backend):
    fixed = _template("mondiali", {"mode": "fixed", "start": "2026-06-20"})
    rotating = _template("giro", {"mode": "rotation"}, duration_days=5)
    backend["templates"] = [fixed, rotating]
    assert event_generator.pick_event_template(datetime(2026, 6, 17, tzinfo=ITALY_TZ)) is None
    assert event_generator.pick_event_template(datetime(2026, 6, 10, tzinfo=ITALY_TZ))["id"] == "giro"


def test_rotation_respects_windows_and_start_weekdays(backend):
    backend["templates"] = [
        _template("natale", {"mode": "rotation", "window": {"from": "12-01", "to": "01-06"}}),
        _template("weekend", {"mode": "rotation", "start_weekdays": ["sat", "sun"]}),
        _template("a_mano", {"mode": "manual", "reason": "x"}),
    ]
    tuesday_in_june = datetime(2026, 6, 16, tzinfo=ITALY_TZ)
    assert event_generator.pick_event_template(tuesday_in_june) is None
    saturday_in_december = datetime(2026, 12, 5, tzinfo=ITALY_TZ)
    ids = {event_generator.pick_event_template(saturday_in_december)["id"] for _ in range(5)}
    assert ids <= {"natale", "weekend"}
    assert event_generator.pick_event_template(datetime(2026, 12, 8, tzinfo=ITALY_TZ))["id"] == "natale"


def test_rules_and_rewards_are_copied_on_the_event_document(backend):
    template = _template(
        "carriera", {"mode": "rotation"}, type="career", filters={"min_teams": 4},
        rules={"attempts": 5, "min_correct_ratio": 1.0}, rewards={"points_per_day": 3, "podium_trophies": 1},
    )
    code, doc = event_generator.build_event_doc(template, datetime(2026, 6, 15, tzinfo=ITALY_TZ))
    assert doc["rules"] == {"attempts": 5, "min_correct_ratio": 1.0}
    assert doc["rewards"] == {"points_per_day": 3, "first_correct_bonus": 1, "podium_trophies": 1}
    for day in doc["daily_data"].values():
        assert day["points"] == 3
        assert day["min_correct"] == len(day["correct_answers"])  # ratio 1.0: tutte


def test_transfer_guess_shows_only_the_last_stop(backend):
    template = _template("trasferimento", {"mode": "rotation"}, type="transfer_guess")
    _, doc = event_generator.build_event_doc(template, datetime(2026, 6, 15, tzinfo=ITALY_TZ))
    assert all(len(day["career_path"]) == 1 for day in doc["daily_data"].values())


def test_an_invalid_template_in_the_file_is_skipped_not_fatal(monkeypatch, caplog):
    good = {k: v for k, v in _template("buono", {"mode": "rotation"}).items()}
    monkeypatch.setattr(event_generator, "load_payload", lambda: {
        "schema_version": 2, "templates": [good, {"id": "rotto", "type": "path"}],
    })
    event_generator.reload_templates()
    try:
        assert [t["id"] for t in event_generator.load_templates()] == ["buono"]
        assert "rotto" in caplog.text
    finally:
        event_generator.reload_templates()


def test_the_podium_size_comes_from_the_event(monkeypatch):
    from services import firebase_service
    from services.repos import events

    calls = []
    monkeypatch.setattr(firebase_service, "get_event_leaderboard",
                        lambda code, limit: calls.append(limit) or [{"telegram_id": i} for i in range(1, limit + 1)])
    monkeypatch.setattr(firebase_service, "add_user_trophy", lambda uid, code: None)
    assert len(events.update_users_trophies({"code": "e_20260101", "rewards": {"podium_trophies": 1}})) == 1
    assert events.update_users_trophies({"code": "e_20260101", "rewards": {"podium_trophies": 0}}) == []
    assert len(events.update_users_trophies({"code": "e_20260101"})) == 3  # evento pre-#31
    assert calls == [1, 3]
