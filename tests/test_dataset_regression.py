"""Tests for dataset regression engine and baseline assertions (#19)."""
from __future__ import annotations

import json
from pathlib import Path

from services.dataset_regression import (
    DatasetBaseline,
    DatasetMetrics,
    check_dataset_regression,
    compute_dataset_metrics,
    generate_baseline_from_metrics,
    load_dataset_baseline,
    save_dataset_baseline,
)


def _sample_valid_player(pid="p1", name="Player One") -> dict:
    return {
        "id": pid,
        "full_name": name,
        "aliases": [name.lower()],
        "nationality": "Italia",
        "position": "Attaccante",
        "birth_year": 1990,
        "career": [
            {
                "team": "Roma",
                "country": "Italia",
                "league": "Serie A",
                "start_year": 2010,
                "end_year": 2015,
                "loan": False,
            },
            {
                "team": "Milan",
                "country": "Italia",
                "league": "Serie A",
                "start_year": 2015,
                "end_year": 2020,
                "loan": False,
            },
        ],
    }


def test_compute_metrics_empty():
    metrics = compute_dataset_metrics([])
    assert metrics.total_players == 0
    assert metrics.valid_players == 0
    assert metrics.unknown_clubs == 0
    assert metrics.duplicate_players == 0
    assert metrics.career_validation_errors == 0


def test_compute_metrics_valid_player():
    player = _sample_valid_player()
    metrics = compute_dataset_metrics([player])
    assert metrics.total_players == 1
    assert metrics.valid_players == 1
    assert metrics.unknown_clubs == 0
    assert metrics.duplicate_players == 0
    assert metrics.career_validation_errors == 0


def test_duplicate_players_detection():
    p1 = _sample_valid_player("p1", "Player One")
    p2 = _sample_valid_player("p2", "Player One")  # same name
    p3 = _sample_valid_player("p1", "Player Three")  # same id
    metrics = compute_dataset_metrics([p1, p2, p3])
    assert metrics.duplicate_players >= 2


def test_unknown_clubs_detection():
    player = _sample_valid_player()
    player["career"][0]["country"] = None
    player["career"][1]["league"] = ""
    metrics = compute_dataset_metrics([player])
    assert metrics.unknown_clubs == 2


def test_career_validation_errors_detection():
    player = _sample_valid_player()
    # Create an invalid chronological range: start_year > end_year
    player["career"][0]["start_year"] = 2018
    player["career"][0]["end_year"] = 2012
    metrics = compute_dataset_metrics([player], reference_year=2026)
    assert metrics.career_validation_errors >= 1
    assert player["full_name"] in metrics.career_error_players


def test_check_dataset_regression_improvements_pass():
    baseline = DatasetBaseline(
        version=1,
        generated_at="2026-09-12T00:00:00Z",
        source_file="data/players.json",
        reference_year=2026,
        metrics={
            "valid_players": 100,
            "unknown_clubs": 5,
            "duplicate_players": 2,
            "career_validation_errors": 10,
        },
        tolerances={
            "valid_players": {"direction": "at_least", "expected": 100},
            "unknown_clubs": {"direction": "at_most", "expected": 5},
            "duplicate_players": {"direction": "at_most", "expected": 2},
            "career_validation_errors": {"direction": "at_most", "expected": 10},
        },
        known_career_error_players=["Old Error Player"],
    )

    # Improved metrics: more valid players, fewer errors
    improved_metrics = DatasetMetrics(
        valid_players=110,
        unknown_clubs=2,
        duplicate_players=0,
        career_validation_errors=6,
        total_players=110,
        career_error_players=["Old Error Player"],
    )

    failures = check_dataset_regression(improved_metrics, baseline)
    assert len(failures) == 0, f"Expected 0 failures on improvement, got: {failures}"


def test_check_dataset_regression_regressions_fail():
    baseline = DatasetBaseline(
        version=1,
        generated_at="2026-09-12T00:00:00Z",
        source_file="data/players.json",
        reference_year=2026,
        metrics={
            "valid_players": 100,
            "unknown_clubs": 0,
            "duplicate_players": 0,
            "career_validation_errors": 5,
        },
        tolerances={
            "valid_players": {"direction": "at_least", "expected": 100},
            "unknown_clubs": {"direction": "at_most", "expected": 0},
            "duplicate_players": {"direction": "at_most", "expected": 0},
            "career_validation_errors": {"direction": "at_most", "expected": 5},
        },
        known_career_error_players=["Known Bad 1"],
    )

    regressed_metrics = DatasetMetrics(
        valid_players=95,  # dropped from 100
        unknown_clubs=2,  # increased from 0
        duplicate_players=1,  # increased from 0
        career_validation_errors=6,  # increased from 5
        total_players=95,
        career_error_players=["Known Bad 1", "New Regressed Player"],
    )

    failures = check_dataset_regression(regressed_metrics, baseline)
    assert len(failures) == 4

    failure_map = {f.metric_name: f for f in failures}
    assert "valid_players" in failure_map
    assert failure_map["valid_players"].actual == 95

    assert "unknown_clubs" in failure_map
    assert failure_map["unknown_clubs"].actual == 2

    assert "duplicate_players" in failure_map
    assert failure_map["duplicate_players"].actual == 1

    assert "career_validation_errors" in failure_map
    assert failure_map["career_validation_errors"].actual == 6
    assert any("New Regressed Player" in diag for diag in failure_map["career_validation_errors"].diagnostics)


def test_baseline_io_roundtrip(tmp_path):
    target = tmp_path / "baseline.json"
    metrics = DatasetMetrics(
        valid_players=50,
        unknown_clubs=0,
        duplicate_players=0,
        career_validation_errors=2,
        total_players=50,
        career_error_players=["Err Player"],
    )
    baseline = generate_baseline_from_metrics(metrics, source_file="dummy.json", reference_year=2026)
    save_dataset_baseline(target, baseline)

    loaded = load_dataset_baseline(target)
    assert loaded.version == baseline.version
    assert loaded.reference_year == 2026
    assert loaded.metrics == baseline.metrics
    assert loaded.known_career_error_players == ["Err Player"]


def test_production_dataset_conforms_to_baseline():
    """Ensures production data/players.json matches or improves on data/dataset_baseline.json."""
    players_file = Path("data/players.json")
    baseline_file = Path("data/dataset_baseline.json")

    assert players_file.is_file(), "data/players.json must exist"
    assert baseline_file.is_file(), "data/dataset_baseline.json must exist"

    with open(players_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    players = data.get("players", [])

    metrics = compute_dataset_metrics(players, reference_year=2026)
    baseline = load_dataset_baseline(baseline_file)

    failures = check_dataset_regression(metrics, baseline)
    assert len(failures) == 0, f"Production dataset regressed against baseline: {failures}"
    assert metrics.valid_players >= baseline.metrics["valid_players"]
    assert metrics.unknown_clubs <= baseline.metrics["unknown_clubs"]
    assert metrics.duplicate_players <= baseline.metrics["duplicate_players"]
    assert metrics.career_validation_errors <= baseline.metrics["career_validation_errors"]
