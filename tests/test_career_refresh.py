"""Test per `domains.players.career_refresh` con adapter_resolver mockato (nessuna rete)."""

import json

import pytest

from domains.players.adapters.base import AdapterResult
from domains.players.career_refresh import (
    CareerRefreshResult,
    refresh_all_active_players,
    refresh_player_career,
    refresh_players,
    select_players_for_refresh,
)


def _write_dataset(path, players):
    path.write_text(
        json.dumps({"_comment": "test", "players": players}, ensure_ascii=False), encoding="utf-8"
    )


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
            {
                "team": "Roma",
                "country": "Italia",
                "league": "Serie A",
                "start_year": 2013,
                "end_year": 2018,
                "apps": 100,
                "goals": 10,
            },
            {
                "team": "Milan",
                "country": "Italia",
                "league": "Serie A",
                "start_year": 2018,
                "end_year": None,
                "apps": 50,
                "goals": 5,
            },
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
    monkeypatch.setattr("domains.players.career_refresh._default_log_path", lambda: log_path)
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
        "mario_rossi",
        players_path=dataset_path,
        backup_dir=backup_dir,
        adapter_resolver=failing_resolver,
    )
    assert result.success is False
    assert result.changed is False

    data = json.loads(dataset_path.read_text(encoding="utf-8"))
    assert "career_last_checked_at" not in data["players"][0]


def test_refresh_player_no_changes(dataset_path, backup_dir):
    def resolver(source, source_id):
        return AdapterResult(
            source_name=source,
            source_id=source_id,
            success=True,
            player_name="Mario Rossi",
            career=[
                {
                    "team": "Roma",
                    "country": "Italia",
                    "league": "Serie A",
                    "start_year": 2013,
                    "end_year": 2018,
                    "apps": 100,
                    "goals": 10,
                },
                {
                    "team": "Milan",
                    "country": "Italia",
                    "league": "Serie A",
                    "start_year": 2018,
                    "end_year": None,
                    "apps": 50,
                    "goals": 5,
                },
            ],
        )

    result = refresh_player_career(
        "mario_rossi",
        players_path=dataset_path,
        backup_dir=backup_dir,
        adapter_resolver=resolver,
    )
    assert result.success is True
    assert result.changed is False

    data = json.loads(dataset_path.read_text(encoding="utf-8"))
    assert data["players"][0]["career_last_checked_at"] is not None


def test_refresh_player_detects_transfer_and_new_team(dataset_path, backup_dir):
    def resolver(source, source_id):
        return AdapterResult(
            source_name=source,
            source_id=source_id,
            success=True,
            player_name="Mario Rossi",
            career=[
                {
                    "team": "Roma",
                    "country": "Italia",
                    "league": "Serie A",
                    "start_year": 2013,
                    "end_year": 2018,
                    "apps": 100,
                    "goals": 10,
                },
                {
                    "team": "Milan",
                    "country": "Italia",
                    "league": "Serie A",
                    "start_year": 2018,
                    "end_year": 2023,
                    "apps": 120,
                    "goals": 15,
                },
                {
                    "team": "Juventus",
                    "country": "Italia",
                    "league": "Serie A",
                    "start_year": 2023,
                    "end_year": None,
                    "apps": 10,
                    "goals": 1,
                },
            ],
            source_metadata={"revision_id": 987, "wikidata_id": "Q123"},
        )

    result = refresh_player_career(
        "mario_rossi",
        players_path=dataset_path,
        backup_dir=backup_dir,
        adapter_resolver=resolver,
    )
    assert result.success is True
    assert result.changed is True
    assert "Juventus" in result.diff.get("new_teams", [])
    assert any(t["team"] == "Milan" for t in result.diff.get("team_changes", []))
    assert any(s["team"] == "Milan" and s["field"] == "goals" for s in result.diff.get("stat_changes", []))

    data = json.loads(dataset_path.read_text(encoding="utf-8"))
    teams = [c["team"] for c in data["players"][0]["career"]]
    assert "Juventus" in teams
    assert data["players"][0]["source_revision_id"] == 987
    assert data["players"][0]["wikidata_id"] == "Q123"


def test_refresh_player_detects_active_change(dataset_path, backup_dir):
    def resolver(source, source_id):
        return AdapterResult(
            source_name=source,
            source_id=source_id,
            success=True,
            player_name="Mario Rossi",
            career=[
                {
                    "team": "Roma",
                    "country": "Italia",
                    "league": "Serie A",
                    "start_year": 2013,
                    "end_year": 2018,
                },
                {
                    "team": "Milan",
                    "country": "Italia",
                    "league": "Serie A",
                    "start_year": 2018,
                    "end_year": 2020,
                },
            ],
        )

    result = refresh_player_career(
        "mario_rossi",
        players_path=dataset_path,
        backup_dir=backup_dir,
        adapter_resolver=resolver,
        current_year_provider=lambda: 2026,
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
            _base_player(
                id="c", full_name="Player C", source="wikipedia", source_id="Player_C", active=False
            ),
        ],
    )

    calls = []

    def resolver(source, source_id):
        calls.append(source_id)
        return AdapterResult(
            source_name=source, source_id=source_id, success=True, player_name="X", career=[]
        )

    sleeps = []

    results, without_source = refresh_all_active_players(
        players_path=path,
        backup_dir=backup_dir,
        delay_seconds=0.01,
        adapter_resolver=resolver,
        sleep_fn=lambda s: sleeps.append(s),
    )

    assert len(results) == 1
    assert results[0].player_id == "a"
    assert len(without_source) == 1
    assert without_source[0]["id"] == "b"
    # player "c" is inactive, never contacted
    assert "Player_C" not in calls


def test_refresh_all_batches_wikipedia_players(tmp_path, backup_dir):
    path = tmp_path / "players.json"
    _write_dataset(
        path,
        [
            _base_player(id="a", full_name="Player A", source_id="Player_A"),
            _base_player(id="b", full_name="Player B", source_id="Player_B"),
        ],
    )

    class _BatchWikipediaAdapter:
        def __init__(self):
            self.calls = []

        def fetch_players(self, identifiers):
            self.calls.append(identifiers)
            return {
                identifier: AdapterResult(
                    source_name="wikipedia",
                    source_id=identifier,
                    success=True,
                    player_name=identifier,
                    career=[{"team": "Roma", "start_year": 2025, "end_year": None}],
                )
                for identifier in identifiers
            }

    adapter = _BatchWikipediaAdapter()

    def unexpected_resolver(source, source_id):
        raise AssertionError(f"sequential resolver called for {source}/{source_id}")

    sleeps = []
    results, without_source = refresh_all_active_players(
        players_path=path,
        backup_dir=backup_dir,
        delay_seconds=1,
        adapter_resolver=unexpected_resolver,
        wikipedia_adapter_factory=lambda: adapter,
        sleep_fn=sleeps.append,
    )

    assert [result.success for result in results] == [True, True]
    assert adapter.calls == [["Player_A", "Player_B"]]
    assert sleeps == []
    assert without_source == []


class _ChunkAdapter:
    """Adapter bulk finto: `failing` e' l'insieme di titoli che tornano con errore."""

    def __init__(self, failing=(), retryable=True):
        self.calls = []
        self.failing = set(failing)
        self.retryable = retryable

    def fetch_players(self, identifiers):
        from domains.players.adapters.base import AdapterError, AdapterErrorType

        self.calls.append(list(identifiers))
        out = {}
        for identifier in identifiers:
            if identifier in self.failing:
                failed = AdapterResult(source_name="wikipedia", source_id=identifier)
                failed.errors.append(
                    AdapterError(
                        error_type=AdapterErrorType.TIMEOUT,
                        message="Timeout",
                        source_name="wikipedia",
                        retryable=self.retryable,
                    )
                )
                out[identifier] = failed
            else:
                out[identifier] = AdapterResult(
                    source_name="wikipedia",
                    source_id=identifier,
                    success=True,
                    player_name=identifier,
                    career=[{"team": "Juventus", "start_year": 2026, "end_year": None}],
                )
        return out


def _players(n):
    return [_base_player(id=f"p{i}", full_name=f"Player {i}", source_id=f"Player_{i}") for i in range(n)]


def test_refresh_players_writes_once_per_chunk_with_single_backup(tmp_path, backup_dir):
    path = tmp_path / "players.json"
    _write_dataset(path, _players(5))
    adapter = _ChunkAdapter()
    progress = []

    results = refresh_players(
        [f"p{i}" for i in range(5)],
        players_path=path,
        backup_dir=backup_dir,
        chunk_size=2,
        adapter_resolver=lambda s, i: pytest.fail("sequential resolver not expected"),
        wikipedia_adapter_factory=lambda: adapter,
        sleep_fn=lambda s: None,
        progress_callback=lambda done, total, r: progress.append((done, total, r.player_id)),
    )

    assert [r.success for r in results] == [True] * 5
    assert all(r.changed for r in results)
    assert adapter.calls == [["Player_0", "Player_1"], ["Player_2", "Player_3"], ["Player_4"]]
    assert progress == [(i + 1, 5, f"p{i}") for i in range(5)]
    assert len(list(backup_dir.iterdir())) == 1
    data = json.loads(path.read_text(encoding="utf-8"))
    assert all(p["career"][-1]["team"] == "Juventus" for p in data["players"])
    assert all(p["career_last_checked_at"] for p in data["players"])


def test_refresh_players_retries_transient_bulk_failure_sequentially(tmp_path, backup_dir):
    path = tmp_path / "players.json"
    _write_dataset(path, _players(3))
    adapter = _ChunkAdapter(failing={"Player_1"})
    sequential = []

    def resolver(source, source_id):
        sequential.append(source_id)
        return AdapterResult(
            source_name=source, source_id=source_id, success=True, player_name="X",
            career=[{"team": "Napoli", "start_year": 2026, "end_year": None}],
        )

    results = refresh_players(
        ["p0", "p1", "p2"],
        players_path=path,
        backup_dir=backup_dir,
        adapter_resolver=resolver,
        wikipedia_adapter_factory=lambda: adapter,
        sleep_fn=lambda s: None,
    )

    assert [r.success for r in results] == [True, True, True]
    assert sequential == ["Player_1"]


def test_refresh_players_does_not_retry_permanent_bulk_failure(tmp_path, backup_dir):
    path = tmp_path / "players.json"
    _write_dataset(path, _players(2))
    adapter = _ChunkAdapter(failing={"Player_1"}, retryable=False)

    results = refresh_players(
        ["p0", "p1"],
        players_path=path,
        backup_dir=backup_dir,
        adapter_resolver=lambda s, i: pytest.fail("permanent failure must not be retried"),
        wikipedia_adapter_factory=lambda: adapter,
        sleep_fn=lambda s: None,
    )

    assert [r.success for r in results] == [True, False]
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "career_last_checked_at" not in data["players"][1]


def test_refresh_players_stops_when_source_is_unreachable(tmp_path, backup_dir):
    path = tmp_path / "players.json"
    _write_dataset(path, _players(6))
    adapter = _ChunkAdapter(failing={f"Player_{i}" for i in range(6)})

    results = refresh_players(
        [f"p{i}" for i in range(6)],
        players_path=path,
        backup_dir=backup_dir,
        chunk_size=2,
        adapter_resolver=lambda s, i: pytest.fail("no sequential fallback when the bulk is dead"),
        wikipedia_adapter_factory=lambda: adapter,
        sleep_fn=lambda s: None,
    )

    assert len(adapter.calls) == 2
    assert [r.player_id for r in results] == [f"p{i}" for i in range(6)]
    assert not any(r.success for r in results)
    assert "Non tentato" in results[-1].message
    assert list(backup_dir.iterdir()) == []


def test_refresh_players_dry_run_does_not_write(tmp_path, backup_dir):
    path = tmp_path / "players.json"
    _write_dataset(path, _players(1))
    before = path.read_text(encoding="utf-8")

    results = refresh_players(
        ["p0"],
        players_path=path,
        backup_dir=backup_dir,
        dry_run=True,
        wikipedia_adapter_factory=lambda: _ChunkAdapter(),
        sleep_fn=lambda s: None,
    )

    assert results[0].success and results[0].changed
    assert results[0].diff["new_teams"] == ["Juventus"]
    assert path.read_text(encoding="utf-8") == before
    assert list(backup_dir.iterdir()) == []


def test_select_players_for_refresh_resume_and_inactive():
    players = [
        _base_player(id="fresh", career_last_checked_at="2026-09-24T10:00:00Z"),
        _base_player(id="stale", career_last_checked_at="2026-09-01T10:00:00Z"),
        _base_player(id="never"),
        _base_player(id="retired", active=False),
        _base_player(id="nosource", source=None, source_id=None),
    ]

    with_source, without_source = select_players_for_refresh(
        players, checked_before="2026-09-24T00:00:00Z"
    )
    assert [p["id"] for p in with_source] == ["stale", "never"]
    assert [p["id"] for p in without_source] == ["nosource"]

    with_source, _ = select_players_for_refresh(players, include_inactive=True)
    assert "retired" in [p["id"] for p in with_source]
