"""Test per la logica di matching e per `run_backfill` in
scripts/backfill_player_source_and_activity.py, con adapter mockati (nessuna rete)."""
import json

from domains.players.adapters.base import AdapterResult, AdapterSearchResult
from scripts.backfill_player_source_and_activity import find_high_confidence_match, run_backfill


class _FakeAdapter:
    source_name = "wikipedia"

    def __init__(self, search_map=None, fetch_map=None):
        self._search_map = search_map or {}
        self._fetch_map = fetch_map or {}

    def search_player(self, query, limit=5):
        ids = self._search_map.get(query, [])
        return AdapterSearchResult(source_name=self.source_name, query=query, identifiers=ids, success=True)

    def fetch_player(self, identifier):
        return self._fetch_map.get(
            identifier,
            AdapterResult(source_name=self.source_name, source_id=identifier, success=False),
        )


class _EmptyAdapter:
    source_name = "wikidata"

    def search_player(self, query, limit=5):
        return AdapterSearchResult(source_name=self.source_name, query=query, identifiers=[], success=True)

    def fetch_player(self, identifier):
        return AdapterResult(source_name=self.source_name, source_id=identifier, success=False)


# ---------------------------------------------------------------------------
# find_high_confidence_match
# ---------------------------------------------------------------------------

def test_single_birth_year_match_is_high_confidence():
    player = {"full_name": "Mario Rossi", "birth_year": 1990}
    candidates = [
        {"identifier": "Mario_Rossi", "name": "Mario Rossi", "birth_year": 1990},
        {"identifier": "Mario_Rossi_2", "name": "Mario Rossi (footballer, born 1985)", "birth_year": 1985},
    ]
    match = find_high_confidence_match(player, candidates)
    assert match is not None
    assert match["identifier"] == "Mario_Rossi"


def test_ambiguous_birth_year_returns_none():
    player = {"full_name": "Mario Rossi", "birth_year": 1990}
    candidates = [
        {"identifier": "A", "name": "Mario Rossi", "birth_year": 1990},
        {"identifier": "B", "name": "Mario Rossi", "birth_year": 1990},
    ]
    assert find_high_confidence_match(player, candidates) is None


def test_no_birth_year_available_falls_back_to_unique_name():
    player = {"full_name": "Mario Rossi", "birth_year": None}
    candidates = [{"identifier": "A", "name": "Mario Rossi", "birth_year": None}]
    match = find_high_confidence_match(player, candidates)
    assert match is not None
    assert match["identifier"] == "A"


def test_no_birth_year_and_multiple_exact_name_matches_returns_none():
    player = {"full_name": "Mario Rossi", "birth_year": None}
    candidates = [
        {"identifier": "A", "name": "Mario Rossi", "birth_year": None},
        {"identifier": "B", "name": "  mario   rossi ", "birth_year": None},
    ]
    assert find_high_confidence_match(player, candidates) is None


def test_no_birth_year_with_one_non_matching_name_ignored():
    player = {"full_name": "Mario Rossi", "birth_year": None}
    candidates = [
        {"identifier": "A", "name": "Mario Rossi", "birth_year": None},
        {"identifier": "B", "name": "Mario Rossi (disambiguation)", "birth_year": None},
    ]
    match = find_high_confidence_match(player, candidates)
    assert match is not None
    assert match["identifier"] == "A"


def test_no_candidates_returns_none():
    assert find_high_confidence_match({"full_name": "X"}, []) is None


# ---------------------------------------------------------------------------
# run_backfill
# ---------------------------------------------------------------------------

def _write_dataset(path, players):
    path.write_text(json.dumps({"_comment": "t", "players": players}, ensure_ascii=False), encoding="utf-8")


def test_dry_run_does_not_write(tmp_path):
    path = tmp_path / "players.json"
    _write_dataset(path, [{"id": "p1", "full_name": "Mario Rossi", "birth_year": 1990, "career": []}])

    fetch_result = AdapterResult(
        source_name="wikipedia", source_id="Mario_Rossi", success=True,
        player_name="Mario Rossi", birth_year=1990,
    )
    wiki = _FakeAdapter(
        search_map={"Mario Rossi": ["Mario_Rossi"]},
        fetch_map={"Mario_Rossi": fetch_result},
    )

    outcome = run_backfill(
        players_path=path, logs_dir=tmp_path / "logs", dry_run=True, delay=0,
        wikipedia_adapter_factory=lambda: wiki, wikidata_adapter_factory=_EmptyAdapter,
        sleep_fn=lambda s: None,
    )

    assert outcome["summary"]["updated"] == 1
    assert outcome["summary"]["dry_run"] is True

    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert "source_id" not in on_disk["players"][0]
    assert not (tmp_path / "logs").exists()


def test_ambiguous_match_goes_to_needs_review(tmp_path):
    path = tmp_path / "players.json"
    _write_dataset(path, [{"id": "p1", "full_name": "Mario Rossi", "birth_year": 1990, "career": []}])

    r1 = AdapterResult(source_name="wikipedia", source_id="A", success=True, player_name="Mario Rossi", birth_year=1990)
    r2 = AdapterResult(source_name="wikipedia", source_id="B", success=True, player_name="Mario Rossi", birth_year=1990)
    wiki = _FakeAdapter(
        search_map={"Mario Rossi": ["A", "B"]},
        fetch_map={"A": r1, "B": r2},
    )

    outcome = run_backfill(
        players_path=path, logs_dir=tmp_path / "logs", dry_run=False, delay=0,
        wikipedia_adapter_factory=lambda: wiki, wikidata_adapter_factory=_EmptyAdapter,
        sleep_fn=lambda s: None,
    )

    assert outcome["summary"]["updated"] == 0
    assert outcome["summary"]["needs_review"] == 1
    assert outcome["needs_review"][0]["id"] == "p1"

    log_files = list((tmp_path / "logs").glob("source_backfill_review_*.json"))
    assert len(log_files) == 1


def test_confident_match_writes_source_and_active(tmp_path):
    path = tmp_path / "players.json"
    _write_dataset(path, [{
        "id": "p1", "full_name": "Mario Rossi", "birth_year": 1990,
        "career": [{"team": "Roma", "start_year": 2010, "end_year": 2015}],
    }])

    fetch_result = AdapterResult(
        source_name="wikipedia", source_id="Mario_Rossi", success=True,
        player_name="Mario Rossi", birth_year=1990,
    )
    wiki = _FakeAdapter(
        search_map={"Mario Rossi": ["Mario_Rossi"]},
        fetch_map={"Mario_Rossi": fetch_result},
    )

    outcome = run_backfill(
        players_path=path, logs_dir=tmp_path / "logs", dry_run=False, delay=0,
        wikipedia_adapter_factory=lambda: wiki, wikidata_adapter_factory=_EmptyAdapter,
        sleep_fn=lambda s: None,
    )

    assert outcome["summary"]["updated"] == 1
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    p = on_disk["players"][0]
    assert p["source"] == "wikipedia"
    assert p["source_id"] == "Mario_Rossi"
    assert p["active"] is False
    assert p["career"] == [{"team": "Roma", "start_year": 2010, "end_year": 2015}]  # career untouched


def test_player_error_does_not_stop_loop(tmp_path):
    path = tmp_path / "players.json"
    _write_dataset(path, [
        {"id": "p1", "full_name": "Broken Player", "birth_year": 1990, "career": []},
        {"id": "p2", "full_name": "Mario Rossi", "birth_year": 1990, "career": []},
    ])

    fetch_result = AdapterResult(
        source_name="wikipedia", source_id="Mario_Rossi", success=True,
        player_name="Mario Rossi", birth_year=1990,
    )

    class _RaisingAdapter(_FakeAdapter):
        def search_player(self, query, limit=5):
            if query == "Broken Player":
                raise RuntimeError("network down")
            return super().search_player(query, limit=limit)

    wiki = _RaisingAdapter(
        search_map={"Mario Rossi": ["Mario_Rossi"]},
        fetch_map={"Mario_Rossi": fetch_result},
    )

    outcome = run_backfill(
        players_path=path, logs_dir=tmp_path / "logs", dry_run=False, delay=0,
        wikipedia_adapter_factory=lambda: wiki, wikidata_adapter_factory=_EmptyAdapter,
        sleep_fn=lambda s: None,
    )

    assert outcome["summary"]["errors"] == 1
    assert outcome["summary"]["updated"] == 1
