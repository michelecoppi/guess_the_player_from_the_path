from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from services import manual_event_service
from services.manual_event_service import (
    ManualEventError,
    build_father_son_event,
    create_manual_event,
    get_template,
    parse_answers,
    parse_start_date,
)

ITALY_TZ = ZoneInfo("Europe/Rome")
START = datetime(2026, 12, 1, tzinfo=ITALY_TZ)


def _pairs(n):
    return [
        {"id": f"pair{i}", "file_id": f"file{i}", "answers": [f"coppia{i}", f"coppia {i}"]}
        for i in range(n)
    ]


def test_parse_answers_splits_and_normalizes():
    assert parse_answers("Maldini,  Paolo e Cesare | maldini") == ["maldini", "paolo e cesare"]
    assert parse_answers("") == []
    assert parse_answers("   ") == []


def test_parse_start_date_accepts_bot_format():
    assert parse_start_date("01/12/26").strftime("%d/%m/%y") == "01/12/26"
    with pytest.raises(ManualEventError):
        parse_start_date("2026-12-01")


def test_get_template_unknown_id_explains_options():
    with pytest.raises(ManualEventError) as excinfo:
        get_template("non_esiste")
    assert "coppie_leggendarie" in str(excinfo.value)


def test_father_son_event_uses_one_pair_per_day():
    template = get_template("coppie_leggendarie")
    code, doc, used = build_father_son_event(_pairs(6), START, template)

    assert code == "coppie_leggendarie_20261201"
    assert len(doc["dates"]) == template["duration_days"]
    assert len(used) == len(doc["dates"])
    assert len(set(used)) == len(used)  # nessuna coppia ripetuta nello stesso evento
    assert doc["source"] == "manual"
    assert doc["trophy_day"] == doc["dates"][-1]


def test_father_son_event_shortens_when_pairs_are_few():
    template = get_template("coppie_leggendarie")
    _, doc, used = build_father_son_event(_pairs(2), START, template)

    assert len(doc["dates"]) == 2
    assert len(used) == 2


def test_father_son_daily_data_carries_photo_and_answers():
    template = get_template("coppie_leggendarie")
    _, doc, _ = build_father_son_event(_pairs(4), START, template)

    first_day = doc["dates"][0]
    day = doc["daily_data"][first_day]
    assert day["image_url"] == "file0"
    assert day["correct_answers"] == ["coppia0", "coppia 0"]
    assert day["first_correct_user"] is False
    assert "career_path" not in day  # l'evento padre/figlio non ha percorsi di carriera


def test_father_son_event_without_pairs_explains_how_to_add_them():
    template = get_template("coppie_leggendarie")
    with pytest.raises(ManualEventError) as excinfo:
        build_father_son_event([], START, template)
    assert "/admin_fs_add" in str(excinfo.value)


def test_create_manual_event_saves_and_marks_pairs_used(monkeypatch):
    saved = {}
    marked = {}
    monkeypatch.setattr(manual_event_service.firebase_service, "get_active_events", lambda day=None: [])
    monkeypatch.setattr(manual_event_service.firebase_service, "list_father_son_pairs", lambda only_unused=False: _pairs(4))
    monkeypatch.setattr(manual_event_service.firebase_service, "event_exists", lambda code: False)
    monkeypatch.setattr(manual_event_service.firebase_service, "save_event", lambda code, doc: saved.update({code: doc}))
    monkeypatch.setattr(
        manual_event_service.firebase_service,
        "mark_father_son_pairs_used",
        lambda ids, code: marked.update({code: list(ids)}),
    )

    summary = create_manual_event("coppie_leggendarie", start_date=START)

    assert summary["code"] in saved
    assert saved[summary["code"]]["type"] == "father_son"
    assert marked[summary["code"]] == ["pair0", "pair1", "pair2", "pair3"]


def test_create_manual_event_refuses_when_the_dates_overlap(monkeypatch):
    monkeypatch.setattr(manual_event_service.firebase_service, "get_active_events",
                        lambda day=None: [{"code": "attivo", "name": "Evento in corso"}])
    monkeypatch.setattr(manual_event_service.firebase_service, "list_father_son_pairs", lambda only_unused=False: _pairs(4))
    monkeypatch.setattr(manual_event_service.firebase_service, "event_exists", lambda code: False)
    monkeypatch.setattr(manual_event_service.firebase_service, "save_event",
                        lambda code, doc: pytest.fail("non deve salvare un evento sovrapposto"))

    with pytest.raises(ManualEventError) as excinfo:
        create_manual_event("coppie_leggendarie", start_date=START)
    assert "si sovrappone" in str(excinfo.value)


def test_create_manual_event_allows_a_future_event_while_one_is_running(monkeypatch):
    # Un evento in corso oggi non deve impedire di programmarne uno per il mese prossimo.
    running_days = {"2026-11-30"}
    saved = {}
    monkeypatch.setattr(manual_event_service.firebase_service, "get_active_events",
                        lambda day=None: [{"code": "attivo"}] if day in running_days else [])
    monkeypatch.setattr(manual_event_service.firebase_service, "list_father_son_pairs", lambda only_unused=False: _pairs(4))
    monkeypatch.setattr(manual_event_service.firebase_service, "event_exists", lambda code: False)
    monkeypatch.setattr(manual_event_service.firebase_service, "save_event", lambda code, doc: saved.update({code: doc}))
    monkeypatch.setattr(manual_event_service.firebase_service, "mark_father_son_pairs_used", lambda ids, code: None)

    summary = create_manual_event("coppie_leggendarie", start_date=START)

    assert summary["code"] in saved


def test_create_manual_event_refuses_duplicate_code(monkeypatch):
    monkeypatch.setattr(manual_event_service.firebase_service, "get_active_events", lambda day=None: [])
    monkeypatch.setattr(manual_event_service.firebase_service, "list_father_son_pairs", lambda only_unused=False: _pairs(4))
    monkeypatch.setattr(manual_event_service.firebase_service, "event_exists", lambda code: True)
    monkeypatch.setattr(manual_event_service.firebase_service, "save_event", lambda code, doc: pytest.fail("non deve salvare"))

    with pytest.raises(ManualEventError):
        create_manual_event("coppie_leggendarie", start_date=START)


def test_create_manual_event_can_force_an_automatic_template(monkeypatch):
    saved = {}
    monkeypatch.setattr(manual_event_service.firebase_service, "get_active_events", lambda day=None: [])
    monkeypatch.setattr(manual_event_service.firebase_service, "event_exists", lambda code: False)
    monkeypatch.setattr(manual_event_service.firebase_service, "save_event", lambda code, doc: saved.update({code: doc}))

    summary = create_manual_event("giramondo", start_date=START)

    assert summary["code"].startswith("giramondo_")
    assert saved[summary["code"]]["source"] == "manual"
    assert saved[summary["code"]]["daily_data"]
