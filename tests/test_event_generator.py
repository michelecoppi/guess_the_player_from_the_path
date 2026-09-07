from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from services import event_generator

ITALY_TZ = ZoneInfo("Europe/Rome")


def test_manual_only_template_never_selected(monkeypatch):
    monkeypatch.setattr(event_generator.firebase_service, "get_recent_event_template_ids", lambda limit: [])
    monkeypatch.setattr(event_generator.firebase_service, "get_last_event_end_date", lambda: None)

    for _ in range(50):
        template = event_generator.pick_event_template(datetime(2026, 6, 15, tzinfo=ITALY_TZ))
        if template:
            assert template["id"] != "coppie_leggendarie"


def test_recently_used_template_excluded(monkeypatch):
    monkeypatch.setattr(event_generator.firebase_service, "get_recent_event_template_ids", lambda limit: ["giramondo"])
    monkeypatch.setattr(event_generator.firebase_service, "get_last_event_end_date", lambda: None)

    for _ in range(50):
        template = event_generator.pick_event_template(datetime(2026, 6, 15, tzinfo=ITALY_TZ))
        if template:
            assert template["id"] != "giramondo"


def test_event_min_gap_blocks_generation_too_soon(monkeypatch):
    now = datetime(2026, 6, 15, tzinfo=ITALY_TZ)
    monkeypatch.setattr(event_generator.firebase_service, "get_recent_event_template_ids", lambda limit: [])
    monkeypatch.setattr(event_generator.firebase_service, "get_last_event_end_date", lambda: now.replace(tzinfo=None) - timedelta(days=2))

    template = event_generator.pick_event_template(now)
    assert template is None


def test_event_min_gap_allows_generation_after_gap(monkeypatch):
    now = datetime(2026, 6, 15, tzinfo=ITALY_TZ)
    monkeypatch.setattr(event_generator.firebase_service, "get_recent_event_template_ids", lambda limit: [])
    monkeypatch.setattr(event_generator.firebase_service, "get_last_event_end_date", lambda: now.replace(tzinfo=None) - timedelta(days=30))

    template = event_generator.pick_event_template(now)
    assert template is not None


def test_weekend_only_template_not_picked_on_weekday(monkeypatch):
    monkeypatch.setattr(event_generator.firebase_service, "get_recent_event_template_ids", lambda limit: [])
    monkeypatch.setattr(event_generator.firebase_service, "get_last_event_end_date", lambda: None)

    tuesday = datetime(2026, 6, 16, tzinfo=ITALY_TZ)
    assert tuesday.weekday() == 1
    for _ in range(50):
        template = event_generator.pick_event_template(tuesday)
        if template:
            assert template["id"] != "weekend_transfer"


def test_build_event_doc_career_type_has_min_correct_and_no_leak_image():
    template = next(t for t in event_generator.load_templates() if t["id"] == "carriera_a_squadre")
    code, doc = event_generator.build_event_doc(template, datetime(2026, 6, 15, tzinfo=ITALY_TZ))

    assert code.startswith("carriera_a_squadre_")
    first_day = doc["dates"][0]
    day_data = doc["daily_data"][first_day]
    assert "min_correct" in day_data
    assert "career_path" not in day_data  # non deve rivelare le squadre come immagine


def test_build_event_doc_path_type_has_career_path_and_answers():
    template = next(t for t in event_generator.load_templates() if t["id"] == "giramondo")
    code, doc = event_generator.build_event_doc(template, datetime(2026, 6, 15, tzinfo=ITALY_TZ))

    first_day = doc["dates"][0]
    day_data = doc["daily_data"][first_day]
    assert day_data["correct_answers"]
    assert day_data["career_path"]


def test_maybe_generate_event_skips_when_event_active(monkeypatch):
    monkeypatch.setattr(event_generator.firebase_service, "get_active_events", lambda: [{"code": "x"}])
    saved = []
    monkeypatch.setattr(event_generator.firebase_service, "save_event", lambda code, doc: saved.append(code))

    result = event_generator.maybe_generate_event(datetime(2026, 6, 15, tzinfo=ITALY_TZ))

    assert result is None
    assert saved == []
