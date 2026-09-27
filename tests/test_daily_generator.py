import pytest

from services import daily_generator, daily_planner, dates
from services.difficulty import DIFFICULTY_ORDER, model_fingerprint, predict_difficulty
from services.player_pool import get_player_by_id
from tests import planner_fakes

TODAY = "2026-05-01"


@pytest.fixture
def store(monkeypatch):
    monkeypatch.setattr(dates, "today_iso", lambda: TODAY)
    monkeypatch.setattr(daily_planner, "today_iso", lambda: TODAY)
    return planner_fakes.install(monkeypatch)


def test_ensure_daily_buffer_skips_existing_days(store):
    for offset in range(3):
        day = dates.shift_iso(TODAY, offset)
        store.save_daily_path(day, {"player_id": "messi", "difficulty": "easy", "career_path": []})
    store.saved.clear()

    assert daily_generator.ensure_daily_buffer(days_ahead=3) == []
    assert store.saved == []


def test_ensure_daily_buffer_generates_missing_days(store):
    result = daily_generator.ensure_daily_buffer(days_ahead=2)

    assert [row["day"] for row in result] == [TODAY, "2026-05-02"]
    for day in store.saved:
        doc = store.daily[day]
        assert doc["correct_answers"]
        assert doc["career_path"]
        assert doc["difficulty"] in DIFFICULTY_ORDER
        assert doc["first_correct_user"] is False
        assert doc["source"] == "auto"
        assert doc["planner_audit"]["target_band"] in DIFFICULTY_ORDER


def test_ensure_daily_buffer_does_not_repeat_a_player_already_programmed_later(store):
    """Il buffer rispetta anche i giorni futuri fissati (es. una sfida scelta a mano fra 5 giorni)."""
    first = daily_generator.ensure_daily_buffer(days_ahead=1)[0]
    store.daily.clear()
    store.save_daily_path("2026-05-06", {"player_id": first["player_id"], "difficulty": first["difficulty"],
                                         "career_path": [], "source": "manual"})
    assert daily_generator.ensure_daily_buffer(days_ahead=1)[0]["player_id"] != first["player_id"]


def test_the_generated_doc_photographs_the_difficulty_prediction(store):
    """#21: la previsione si salva alla generazione, con la taratura di quel momento."""
    daily_generator.ensure_daily_buffer(days_ahead=1)
    doc = store.daily[TODAY]
    prediction = doc["difficulty_prediction"]
    assert prediction == predict_difficulty(get_player_by_id(doc["player_id"]))
    assert prediction["band"] == doc["difficulty"]
    assert prediction["model"] == model_fingerprint()
