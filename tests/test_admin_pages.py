"""Exercise extracted renderers without connecting to production or clicking writes."""
import importlib

import pytest
from streamlit.testing.v1 import AppTest


@pytest.mark.parametrize("page", ["overview", "challenges", "planner", "events", "users", "leagues", "dataset", "player_review", "blocked", "father_son"])
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


RENDER = '''
from datetime import datetime
from zoneinfo import ZoneInfo
from admin_pages.{page} import render
render("2026-09-09", datetime(2026, 9, 9, tzinfo=ZoneInfo("Europe/Rome")))
'''


def test_dataset_calibration_tab_renders_a_real_report_without_firestore(monkeypatch):
    """#21: la scheda "Prevista vs osservata" su giornate finte, senza toccare Firestore.

    I finti si installano con monkeypatch e non dentro lo script: AppTest gira nello stesso
    processo, e un'assegnazione nello script resterebbe attiva per i test successivi."""
    from services import firebase_service

    def fake_range(start, end, limit=180):
        ids = ["totti", "forlan", "jankto", "kevin_constant", "delpiero"]
        return [
            {"day": f"2026-08-{10 + i:02d}", "player_id": pid, "difficulty": "easy",
             "players_count": 40, "solved_count": 35 - 7 * i, "solved_attempts_total": 50,
             "difficulty_prediction": {"score": 10.0 * i, "band": "easy", "model": "vecchia"} if i % 2 else None}
            for i, pid in enumerate(ids)
        ]

    monkeypatch.setattr(firebase_service, "get_daily_paths_range", fake_range)
    monkeypatch.setattr(firebase_service, "get_blocked_player_ids", lambda: [])
    result = AppTest.from_string(RENDER.format(page="dataset")).run(timeout=30)
    assert not result.exception
    assert not result.error
    labels = [metric.label for metric in result.metric]
    assert "Correlazione di rango" in labels
    assert any("taratura diversa" in warning.value for warning in result.warning)


def test_planner_page_renders_a_plan_without_firestore(monkeypatch):
    """#30: la pagina del planner su un Firestore finto, senza scrivere niente."""
    from services import firebase_service

    monkeypatch.setattr(firebase_service, "get_daily_paths_range", lambda start, end, limit=180: [
        {"day": "2026-09-12", "player_id": "messi", "difficulty": "easy", "career_path": [], "locked": True},
    ])
    monkeypatch.setattr(firebase_service, "get_blocked_player_ids", lambda: [])
    monkeypatch.setattr(firebase_service, "get_planner_exclusions",
                        lambda: {"totti": {"reason": "in tendenza", "until": None}})
    result = AppTest.from_string(RENDER.format(page="planner")).run(timeout=30)
    assert not result.exception
    assert not result.error
    labels = {metric.label: metric.value for metric in result.metric}
    assert labels["Restano come sono"] == "1"
    assert int(labels["Da creare"]) == 29


def test_events_page_previews_an_existing_template(monkeypatch):
    """#31: l'editor dei template mostra l'anteprima di un template valido senza scrivere niente."""
    from services import firebase_service

    monkeypatch.setattr(firebase_service, "get_recent_events", lambda limit=5: [])
    at = AppTest.from_string(RENDER.format(page="events")).run(timeout=30)
    assert not at.exception
    at.selectbox(key="tpl_pick").set_value("giramondo").run(timeout=30)
    assert not at.exception
    assert "Candidati" in [metric.label for metric in at.metric]
    assert "Tentativi al giorno" in [metric.label for metric in at.metric]


def test_every_name_imported_from_the_shared_admin_module_exists():
    """Pages import their collaborators from admin_pages/shared.py; a re-export that disappears
    (for example when a service moves to domains/, #111) would only break when the page opens."""
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    tree = ast.parse((root / "admin_pages" / "shared.py").read_text(encoding="utf-8"))
    defined = set()
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            defined.update((alias.asname or alias.name).split(".")[0] for alias in node.names)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            defined.update(name.id for target in targets for name in ast.walk(target) if isinstance(name, ast.Name))
    missing = {}
    for path in [*sorted((root / "admin_pages").glob("*.py")), root / "admin_ui.py"]:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module == "admin_pages.shared":
                absent = [alias.name for alias in node.names if alias.name not in defined]
                if absent:
                    missing[path.name] = absent
    assert not missing, missing
