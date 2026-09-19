"""Test per `domains.players.career_refresh` con adapter_resolver mockato (nessuna rete)."""
import json

import pytest

from domains.players.adapters.base import AdapterResult
from domains.players.career_refresh import (
    CareerRefreshResult,
    refresh_all_active_players,
    refresh_player_career,
)


def _write_dataset(path, players):
    path.write_text(json.dumps({"_comment": "test", "players": players}, ensure_ascii=False), encoding="utf-8")


def _base_player(**overrides):
    player = {
        "id": "mario_rossi",
        "full_name": "Mario Rossi",
        "aliases": ["mario rossi"],
        "nationality": "Italia",
        "position": "Attaccante",
        "birth_year": 1995,
        "popularity": 3,
        "verified": True,
        "active": True,
        "source": "wikipedia",
        "source_id": "Mario_Rossi",
        "career": [
            {"team": "Roma", "country": "Italia", "league": "Serie A", "start_year": 2013, "end_year": 2018,
             "apps": 100, "goals": 10},
            {"team": "Milan", "country": "Italia", "league": "Serie A", "start_year": 2018, "end_year": None,
             "apps": 50, "goals": 5},
        ],
    }
    player.update(overrides)
    return player


@pytest.fixture
def dataset_path(tmp_path):
    p = tmp_path / "players.json"
    _write_dataset(p, [_base_player()])
    return p


@pytest.fixture
def backup_dir(tmp_path):
    d = tmp_path / "backup"
    d.mkdir()
    return d


@pytest.fixture(autouse=True)
def _isolated_log_path(tmp_path, monkeypatch):
    log_path = tmp_path / "logs" / "career_refresh.log"
    monkeypatch.setattr(
        "domains.players.career_refresh._default_log_path", lambda: log_path
    )
    return log_path


def test_refresh_player_without_source_id(tmp_path, backup_dir):
    path = tmp_path / "players.json"
    _write_dataset(path, [_base_player(source=None, source_id=None)])

    result = refresh_player_career("mario_rossi", players_path=path, backup_dir=backup_dir)

    assert isinstance(result, CareerRefreshResult)
    assert result.success is False
    assert result.changed is False
    assert "fonte" in result.message.lower()


def test_refresh_player_not_found(dataset_path, backup_dir):
    result = refresh_player_career("nonexistent", players_path=dataset_path, backup_dir=backup_dir)
    assert result.success is False
    assert result.changed is False


def test_refresh_player_adapter_failure(dataset_path, backup_dir):
    def failing_resolver(source, source_id):
        return AdapterResult(source_name=source, source_id=source_id, success=False)

    result = refresh_player_career(
        "mario_rossi", players_path=dataset_path, backup_dir=backup_dir, adapter_resolver=failing_resolver,
    )
    assert result.success is False
    assert result.changed is False

    data = json.loads(dataset_path.read_text(encoding="utf-8"))
    assert "career_last_checked_at" not in data["players"][0]


def test_refresh_player_no_changes(dataset_path, backup_dir):
    def resolver(source, source_id):
        return AdapterResult(
            source_name=source, source_id=source_id, success=True, player_name="Mario Rossi",
            career=[
                {"team": "Roma", "country": "Italia", "league": "Serie A", "start_year": 2013, "end_year": 2018,
                 "apps": 100, "goals": 10},
                {"team": "Milan", "country": "Italia", "league": "Serie A", "start_year": 2018, "end_year": None,
                 "apps": 50, "goals": 5},
            ],
        )

    result = refresh_player_career(
        "mario_rossi", players_path=dataset_path, backup_dir=backup_dir, adapter_resolver=resolver,
    )
    assert result.success is True
    assert result.changed is False

    data = json.loads(dataset_path.read_text(encoding="utf-8"))
    assert data["players"][0]["career_last_checked_at"] is not None


def test_refresh_player_detects_transfer_and_new_team(dataset_path, backup_dir):
    def resolver(source, source_id):
        return AdapterResult(
            source_name=source, source_id=source_id, success=True, player_name="Mario Rossi",
            career=[
                {"team": "Roma", "country": "Italia", "league": "Serie A", "start_year": 2013, "end_year": 2018,
                 "apps": 100, "goals": 10},
                {"team": "Milan", "country": "Italia", "league": "Serie A", "start_year": 2018, "end_year": 2023,
                 "apps": 120, "goals": 15},
                {"team": "Juventus", "country": "Italia", "league": "Serie A", "start_year": 2023, "end_year": None,
                 "apps": 10, "goals": 1},
            ],
        )

    result = refresh_player_career(
        "mario_rossi", players_path=dataset_path, backup_dir=backup_dir, adapter_resolver=resolver,
    )
    assert result.success is True
    assert result.changed is True
    assert "Juventus" in result.diff.get("new_teams", [])
    assert any(t["team"] == "Milan" for t in result.diff.get("team_changes", []))
    assert any(s["team"] == "Milan" and s["field"] == "goals" for s in result.diff.get("stat_changes", []))

    data = json.loads(dataset_path.read_text(encoding="utf-8"))
    teams = [c["team"] for c in data["players"][0]["career"]]
    assert "Juventus" in teams


def test_refresh_player_detects_active_change(dataset_path, backup_dir):
    def resolver(source, source_id):
        return AdapterResult(
            source_name=source, source_id=source_id, success=True, player_name="Mario Rossi",
            career=[
                {"team": "Roma", "country": "Italia", "league": "Serie A", "start_year": 2013, "end_year": 2018},
                {"team": "Milan", "country": "Italia", "league": "Serie A", "start_year": 2018, "end_year": 2020},
            ],
        )

    result = refresh_player_career(
        "mario_rossi", players_path=dataset_path, backup_dir=backup_dir,
        adapter_resolver=resolver, current_year_provider=lambda: 2026,
    )
    assert result.success is True
    assert result.diff.get("active_changed") == {"previous": True, "new": False}

    data = json.loads(dataset_path.read_text(encoding="utf-8"))
    assert data["players"][0]["active"] is False


def test_refresh_all_active_players_separates_missing_source(tmp_path, backup_dir):
    path = tmp_path / "players.json"
    _write_dataset(
        path,
        [
            _base_player(id="a", full_name="Player A", source="wikipedia", source_id="Player_A", active=True),
            _base_player(id="b", full_name="Player B", source=None, source_id=None, active=True),
            _base_player(id="c", full_name="Player C", source="wikipedia", source_id="Player_C", active=False),
        ],
    )

    calls = []

    def resolver(source, source_id):
        calls.append(source_id)
        return AdapterResult(source_name=source, source_id=source_id, success=True, player_name="X", career=[])

    sleeps = []

    results, without_source = refresh_all_active_players(
        players_path=path, backup_dir=backup_dir, delay_seconds=0.01,
        adapter_resolver=resolver, sleep_fn=lambda s: sleeps.append(s),
    )

    assert len(results) == 1
    assert results[0].player_id == "a"
    assert len(without_source) == 1
    assert without_source[0]["id"] == "b"
    # player "c" is inactive, never contacted
    assert "Player_C" not in calls
