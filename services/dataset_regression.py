"""Dataset regression engine for Guess The Player (#19).

Provides deterministic regression tracking for core dataset quality metrics:
- valid_players: total valid players in the pool (improves when >= baseline)
- unknown_clubs: clubs missing league/country metadata (improves when <= baseline)
- duplicate_players: duplicate IDs or player names (improves when <= baseline)
- career_validation_errors: career anomalies detected by Candidate Player validation (improves when <= baseline)

Directional regression assertions:
- Improvements pass and are reported with clear info;
- Regressions fail CI with structured entity-level diagnostics;
- Preserves historical quirks without failing CI;
- Baseline updates must be committed explicitly to version control.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from services.candidate_finding import CandidateFinding, FindingSeverity
from services.candidate_player import CandidatePlayer
from services.candidate_validation import validate_candidate_data
from services.player_pool import validate_player


@dataclass(frozen=True)
class RegressionFailure:
    metric_name: str
    expected: int
    actual: int
    direction: str
    message: str
    diagnostics: list[str] = field(default_factory=list)


@dataclass
class DatasetMetrics:
    valid_players: int
    unknown_clubs: int
    duplicate_players: int
    career_validation_errors: int
    total_players: int = 0
    career_warnings: int = 0
    career_error_players: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid_players": self.valid_players,
            "unknown_clubs": self.unknown_clubs,
            "duplicate_players": self.duplicate_players,
            "career_validation_errors": self.career_validation_errors,
            "total_players": self.total_players,
            "career_warnings": self.career_warnings,
            "career_error_players": list(self.career_error_players),
        }


@dataclass
class DatasetBaseline:
    version: int
    generated_at: str
    source_file: str
    reference_year: int
    metrics: dict[str, int]
    tolerances: dict[str, dict[str, Any]]
    known_career_error_players: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "generated_at": self.generated_at,
            "source_file": self.source_file,
            "reference_year": self.reference_year,
            "metrics": dict(self.metrics),
            "tolerances": dict(self.tolerances),
            "known_career_error_players": list(self.known_career_error_players),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DatasetBaseline:
        return cls(
            version=int(data.get("version", 1)),
            generated_at=str(data.get("generated_at", "")),
            source_file=str(data.get("source_file", "data/players.json")),
            reference_year=int(data.get("reference_year", 2026)),
            metrics=dict(data.get("metrics", {})),
            tolerances=dict(data.get("tolerances", {})),
            known_career_error_players=list(data.get("known_career_error_players", [])),
        )


def compute_dataset_metrics(
    players_data: list[dict[str, Any]],
    reference_year: int = 2026,
    year_provider: Optional[Callable[[], int]] = None,
) -> DatasetMetrics:
    """Computes deterministic quality metrics for a given list of player records."""
    total_players = len(players_data)
    current_year_func = year_provider or (lambda: reference_year)

    # 1. Valid players (using player_pool validation rules)
    valid_count = 0
    for p in players_data:
        problems = validate_player(p)
        if not problems:
            valid_count += 1

    # 2. Duplicate players (by ID or normalized full_name)
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    dup_count = 0
    for p in players_data:
        pid = str(p.get("id", "")).strip()
        pname = str(p.get("full_name", "")).strip().lower()
        is_dup = False
        if pid:
            if pid in seen_ids:
                is_dup = True
            seen_ids.add(pid)
        if pname:
            if pname in seen_names:
                is_dup = True
            seen_names.add(pname)
        if is_dup:
            dup_count += 1

    # 3. Unknown clubs (career stops missing team, country, or league)
    unknown_clubs_count = 0
    for p in players_data:
        for stint in p.get("career", []):
            team = stint.get("team")
            country = stint.get("country")
            league = stint.get("league")
            if not team or not country or not league:
                unknown_clubs_count += 1

    # 4. Career validation errors and warnings (via CandidateValidationService logic)
    career_errors_total = 0
    career_warnings_total = 0
    career_error_players_set: set[str] = set()

    for p in players_data:
        pid = str(p.get("id", "0"))
        cand = CandidatePlayer(
            candidate_id=f"prod_{pid}",
            source="dataset",
            source_id=pid,
            full_name=p.get("full_name", ""),
            career=list(p.get("career") or []),
            nationality=p.get("nationality", ""),
            position=p.get("position", ""),
            birth_year=p.get("birth_year"),
            aliases=list(p.get("aliases") or []),
            metadata={"one_club_career": p.get("one_club_career", False)},
        )
        findings: list[CandidateFinding] = validate_candidate_data(
            cand, current_year_provider=current_year_func
        )

        has_career_error = False
        for f in findings:
            code_str = f.code.value if hasattr(f.code, "value") else str(f.code)
            if code_str.startswith("CAREER_"):
                if f.severity == FindingSeverity.ERROR:
                    career_errors_total += 1
                    has_career_error = True
                elif f.severity == FindingSeverity.WARNING:
                    career_warnings_total += 1

        if has_career_error:
            name = p.get("full_name") or f"ID:{pid}"
            career_error_players_set.add(name)

    return DatasetMetrics(
        valid_players=valid_count,
        unknown_clubs=unknown_clubs_count,
        duplicate_players=dup_count,
        career_validation_errors=career_errors_total,
        total_players=total_players,
        career_warnings=career_warnings_total,
        career_error_players=sorted(career_error_players_set),
    )


def check_dataset_regression(
    metrics: DatasetMetrics,
    baseline: DatasetBaseline,
) -> list[RegressionFailure]:
    """Compares current dataset metrics against baseline tolerances.

    Returns a list of RegressionFailure objects if any regression is detected.
    Empty list means all checks passed (improvements are allowed and pass).
    """
    failures: list[RegressionFailure] = []
    tolerances = baseline.tolerances

    actual_values = {
        "valid_players": metrics.valid_players,
        "unknown_clubs": metrics.unknown_clubs,
        "duplicate_players": metrics.duplicate_players,
        "career_validation_errors": metrics.career_validation_errors,
    }

    for metric_name, actual in actual_values.items():
        tol = tolerances.get(metric_name)
        if not tol:
            continue

        direction = tol.get("direction", "at_most")
        expected = int(tol.get("expected", 0))
        diags: list[str] = []

        if direction == "at_least":
            if actual < expected:
                diff = expected - actual
                msg = (
                    f"Regression in '{metric_name}': actual {actual} < expected minimum {expected} "
                    f"(-{diff} valid players dropped from dataset)"
                )
                failures.append(
                    RegressionFailure(
                        metric_name=metric_name,
                        expected=expected,
                        actual=actual,
                        direction=direction,
                        message=msg,
                        diagnostics=diags,
                    )
                )
        elif direction == "at_most":
            if actual > expected:
                diff = actual - expected
                msg = (
                    f"Regression in '{metric_name}': actual {actual} > expected maximum {expected} "
                    f"(+{diff} errors/issues introduced)"
                )
                if metric_name == "career_validation_errors":
                    known = set(baseline.known_career_error_players)
                    current = set(metrics.career_error_players)
                    new_players = sorted(current - known)
                    if new_players:
                        diags.append(f"Newly introduced career error players: {', '.join(new_players)}")
                failures.append(
                    RegressionFailure(
                        metric_name=metric_name,
                        expected=expected,
                        actual=actual,
                        direction=direction,
                        message=msg,
                        diagnostics=diags,
                    )
                )
        elif direction == "exact":
            if actual != expected:
                msg = f"Regression in '{metric_name}': actual {actual} != expected {expected}"
                failures.append(
                    RegressionFailure(
                        metric_name=metric_name,
                        expected=expected,
                        actual=actual,
                        direction=direction,
                        message=msg,
                        diagnostics=diags,
                    )
                )

    return failures


def load_dataset_baseline(path: str | Path) -> DatasetBaseline:
    """Loads and deserializes a DatasetBaseline from JSON file."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Baseline file not found at: {p}")
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    return DatasetBaseline.from_dict(data)


def save_dataset_baseline(path: str | Path, baseline: DatasetBaseline) -> None:
    """Serializes a DatasetBaseline to a pretty-formatted JSON file."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(baseline.to_dict(), f, indent=2, ensure_ascii=False)
        f.write("\n")


def generate_baseline_from_metrics(
    metrics: DatasetMetrics,
    source_file: str = "data/players.json",
    reference_year: int = 2026,
) -> DatasetBaseline:
    """Creates a new DatasetBaseline instance based on computed metrics."""
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return DatasetBaseline(
        version=1,
        generated_at=now_iso,
        source_file=source_file,
        reference_year=reference_year,
        metrics={
            "valid_players": metrics.valid_players,
            "unknown_clubs": metrics.unknown_clubs,
            "duplicate_players": metrics.duplicate_players,
            "career_validation_errors": metrics.career_validation_errors,
        },
        tolerances={
            "valid_players": {
                "direction": "at_least",
                "expected": metrics.valid_players,
            },
            "unknown_clubs": {
                "direction": "at_most",
                "expected": metrics.unknown_clubs,
            },
            "duplicate_players": {
                "direction": "at_most",
                "expected": metrics.duplicate_players,
            },
            "career_validation_errors": {
                "direction": "at_most",
                "expected": metrics.career_validation_errors,
            },
        },
        known_career_error_players=list(metrics.career_error_players),
    )
