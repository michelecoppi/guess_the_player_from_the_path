"""Exercise extracted renderers without connecting to production or clicking writes."""
import importlib

import pytest
from streamlit.testing.v1 import AppTest


@pytest.mark.parametrize("page", ["overview", "challenges", "events", "users", "leagues", "dataset", "player_review", "blocked", "father_son"])
def test_admin_page_renders_with_unavailable_database(page):
    module = importlib.import_module(f"admin_pages.{page}")
    assert callable(module.render)
    script = f'''
from datetime import datetime
from zoneinfo import ZoneInfo
from admin_pages.{page} import render
render("2026-09-09", datetime(2026, 9, 9, tzinfo=ZoneInfo("Europe/Rome")))
'''
    result = AppTest.from_string(script).run(timeout=20)
    assert not result.exception


def test_dataset_calibration_tab_renders_a_real_report_without_firestore():
    """#21: la scheda "Prevista vs osservata" su giornate finte, senza toccare Firestore."""
    script = '''
from datetime import datetime
from zoneinfo import ZoneInfo
from services import firebase_service
from admin_pages.dataset import render

def fake_range(start, end, limit=180):
    ids = ["totti", "forlan", "jankto", "kevin_constant", "delpiero"]
    return [
        {"day": f"2026-08-{10 + i:02d}", "player_id": pid, "difficulty": "easy",
         "players_count": 40, "solved_count": 35 - 7 * i, "solved_attempts_total": 50,
         "difficulty_prediction": {"score": 10.0 * i, "band": "easy", "model": "vecchia"} if i % 2 else None}
        for i, pid in enumerate(ids)
    ]

firebase_service.get_daily_paths_range = fake_range
firebase_service.get_blocked_player_ids = lambda: []
render("2026-09-09", datetime(2026, 9, 9, tzinfo=ZoneInfo("Europe/Rome")))
'''
    result = AppTest.from_string(script).run(timeout=30)
    assert not result.exception
    assert not result.error
    labels = [metric.label for metric in result.metric]
    assert "Correlazione di rango" in labels
    assert any("taratura diversa" in warning.value for warning in result.warning)
