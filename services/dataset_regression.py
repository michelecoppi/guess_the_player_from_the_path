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


MANDATORY_BASELINE_METRICS: tuple[str, ...] = (
    "valid_players",
    "unknown_clubs",
    "duplicate_players",
    "career_validation_errors",
)
SUPPORTED_TOLERANCE_DIRECTIONS: frozenset[str] = frozenset({"at_least", "at_most", "exact"})


class DatasetBaselineValidationError(ValueError):
    """Raised when a dataset baseline schema is malformed, incomplete, or invalid."""
    pass


def validate_dataset_baseline_schema(data: Any) -> None:
    """Validates baseline dictionary against fail-closed requirements.

    Raises DatasetBaselineValidationError on any missing or invalid field.
    """
    if not isinstance(data, dict):
        raise DatasetBaselineValidationError(f"Baseline must be a JSON object, got {type(data).__name__}")

    # Top-level required fields
    if "version" not in data or not isinstance(data["version"], int) or isinstance(data["version"], bool):
        raise DatasetBaselineValidationError("Baseline missing or invalid mandatory field: 'version' (must be integer)")

    if "source_file" not in data or not isinstance(data["source_file"], str) or not data["source_file"].strip():
        raise DatasetBaselineValidationError("Baseline missing or invalid mandatory field: 'source_file' (must be non-empty string)")

    if "reference_year" not in data or not isinstance(data["reference_year"], int) or isinstance(data["reference_year"], bool):
        raise DatasetBaselineValidationError("Baseline missing or invalid mandatory field: 'reference_year' (must be integer)")

    # Metrics section
    if "metrics" not in data or not isinstance(data["metrics"], dict):
        raise DatasetBaselineValidationError("Baseline missing or invalid mandatory section: 'metrics' (must be object)")

    metrics_dict = data["metrics"]
    for m in MANDATORY_BASELINE_METRICS:
        if m not in metrics_dict:
            raise DatasetBaselineValidationError(f"Baseline 'metrics' section missing mandatory metric: '{m}'")
        val = metrics_dict[m]
        if not isinstance(val, (int, float)) or isinstance(val, bool):
            raise DatasetBaselineValidationError(f"Baseline metric '{m}' must be numeric, got {val!r}")

    # Tolerances section
    if "tolerances" not in data or not isinstance(data["tolerances"], dict):
        raise DatasetBaselineValidationError("Baseline missing or invalid mandatory section: 'tolerances' (must be object)")

    tolerances_dict = data["tolerances"]
    for m in MANDATORY_BASELINE_METRICS:
        if m not in tolerances_dict:
            raise DatasetBaselineValidationError(f"Baseline 'tolerances' section missing mandatory tolerance: '{m}'")
        tol = tolerances_dict[m]
        if not isinstance(tol, dict):
            raise DatasetBaselineValidationError(f"Baseline tolerance for '{m}' must be an object, got {type(tol).__name__}")

        if "direction" not in tol:
            raise DatasetBaselineValidationError(f"Baseline tolerance for '{m}' missing mandatory field: 'direction'")
        direction = tol["direction"]
        if direction not in SUPPORTED_TOLERANCE_DIRECTIONS:
            raise DatasetBaselineValidationError(
                f"Baseline tolerance for '{m}' has unsupported direction: {direction!r}. "
                f"Supported directions are: {sorted(SUPPORTED_TOLERANCE_DIRECTIONS)}"
            )

        if "expected" not in tol:
            raise DatasetBaselineValidationError(f"Baseline tolerance for '{m}' missing mandatory field: 'expected'")
        expected = tol["expected"]
        if not isinstance(expected, (int, float)) or isinstance(expected, bool):
            raise DatasetBaselineValidationError(f"Baseline tolerance for '{m}' has non-numeric expected value: {expected!r}")


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
        validate_dataset_baseline_schema(data)
        return cls(
            version=int(data["version"]),
            generated_at=str(data.get("generated_at", "")),
            source_file=str(data["source_file"]),
            reference_year=int(data["reference_year"]),
            metrics=dict(data["metrics"]),
            tolerances=dict(data["tolerances"]),
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

    Fails closed if any mandatory metric or tolerance is missing or invalid.
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

    for metric_name in MANDATORY_BASELINE_METRICS:
        actual = actual_values[metric_name]
        tol = tolerances.get(metric_name)
        if not tol:
            failures.append(
                RegressionFailure(
                    metric_name=metric_name,
                    expected=0,
                    actual=actual,
                    direction="fail_closed",
                    message=(
                        f"Fail-closed protection: mandatory baseline tolerance for '{metric_name}' is missing. "
                        f"CI protects this metric and will not silently skip it."
                    ),
                )
            )
            continue

        direction = tol.get("direction")
        expected_raw = tol.get("expected")

        if direction not in SUPPORTED_TOLERANCE_DIRECTIONS:
            failures.append(
                RegressionFailure(
                    metric_name=metric_name,
                    expected=0,
                    actual=actual,
                    direction=str(direction),
                    message=(
                        f"Fail-closed protection: tolerance for '{metric_name}' has unsupported direction {direction!r}. "
                        f"Must be one of {sorted(SUPPORTED_TOLERANCE_DIRECTIONS)}."
                    ),
                )
            )
            continue

        if not isinstance(expected_raw, (int, float)) or isinstance(expected_raw, bool):
            failures.append(
                RegressionFailure(
                    metric_name=metric_name,
                    expected=0,
                    actual=actual,
                    direction=str(direction),
                    message=(
                        f"Fail-closed protection: tolerance for '{metric_name}' has non-numeric expected value {expected_raw!r}."
                    ),
                )
            )
            continue

        expected = int(expected_raw)
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
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as err:
        raise DatasetBaselineValidationError(f"Malformed JSON in baseline file '{p}': {err}")
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
