"""CLI script for dataset regression checking and baseline maintenance (#19).

Usage:
    python -m scripts.dataset_regression --check
    python -m scripts.dataset_regression --update-baseline
    python -m scripts.dataset_regression --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from services.dataset_regression import (
    check_dataset_regression,
    compute_dataset_metrics,
    generate_baseline_from_metrics,
    load_dataset_baseline,
    save_dataset_baseline,
)

_DEFAULT_PLAYERS_PATH = Path("data/players.json")
_DEFAULT_BASELINE_PATH = Path("data/dataset_baseline.json")
_DEFAULT_REFERENCE_YEAR = 2026


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Dataset regression verification and baseline management (#19)."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--check",
        action="store_true",
        default=True,
        help="Check dataset for regressions against baseline (default).",
    )
    group.add_argument(
        "--update-baseline",
        action="store_true",
        help="Recompute and save new baseline from current dataset.",
    )
    parser.add_argument(
        "--players",
        type=Path,
        default=_DEFAULT_PLAYERS_PATH,
        help=f"Path to players dataset JSON (default: {_DEFAULT_PLAYERS_PATH}).",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=_DEFAULT_BASELINE_PATH,
        help=f"Path to baseline JSON (default: {_DEFAULT_BASELINE_PATH}).",
    )
    parser.add_argument(
        "--reference-year",
        type=int,
        default=_DEFAULT_REFERENCE_YEAR,
        help=f"Reference year for validation checks (default: {_DEFAULT_REFERENCE_YEAR}).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit output in JSON format.",
    )

    args = parser.parse_args()

    if not args.players.is_file():
        print(f"ERROR: Players file not found at {args.players}", file=sys.stderr)
        return 2

    # Load player data
    with open(args.players, "r", encoding="utf-8") as f:
        data = json.load(f)
    players_list = data.get("players", [])

    # Compute metrics
    metrics = compute_dataset_metrics(
        players_list,
        reference_year=args.reference_year,
    )

    if args.update_baseline:
        new_baseline = generate_baseline_from_metrics(
            metrics,
            source_file=str(args.players).replace("\\", "/"),
            reference_year=args.reference_year,
        )
        save_dataset_baseline(args.baseline, new_baseline)
        if args.json:
            print(json.dumps({"status": "updated", "baseline": new_baseline.to_dict()}, indent=2))
        else:
            print(f"SUCCESS: Updated baseline at {args.baseline}")
            print(f"  Valid players:            {metrics.valid_players}")
            print(f"  Unknown clubs:            {metrics.unknown_clubs}")
            print(f"  Duplicate players:        {metrics.duplicate_players}")
            print(f"  Career validation errors: {metrics.career_validation_errors}")
            print(f"  Known career error count: {len(new_baseline.known_career_error_players)}")
        return 0

    # Default: --check
    if not args.baseline.is_file():
        print(f"ERROR: Baseline file not found at {args.baseline}", file=sys.stderr)
        return 2

    baseline = load_dataset_baseline(args.baseline)
    failures = check_dataset_regression(metrics, baseline)

    if args.json:
        result = {
            "passed": len(failures) == 0,
            "metrics": metrics.to_dict(),
            "failures": [
                {
                    "metric": f.metric_name,
                    "expected": f.expected,
                    "actual": f.actual,
                    "direction": f.direction,
                    "message": f.message,
                    "diagnostics": f.diagnostics,
                }
                for f in failures
            ],
        }
        print(json.dumps(result, indent=2))
        return 0 if not failures else 1

    # Human-readable output
    print("=== Dataset Regression Check (#19) ===")
    print(f"Dataset:  {args.players} ({len(players_list)} total players)")
    print(f"Baseline: {args.baseline} (v{baseline.version}, ref year {baseline.reference_year})")
    print("-" * 50)

    for metric_name in ("valid_players", "unknown_clubs", "duplicate_players", "career_validation_errors"):
        actual = getattr(metrics, metric_name)
        tol = baseline.tolerances.get(metric_name, {})
        expected = tol.get("expected", "N/A")
        direction = tol.get("direction", "")
        dir_symbol = ">=" if direction == "at_least" else "<=" if direction == "at_most" else "=="
        status = "OK"
        if any(f.metric_name == metric_name for f in failures):
            status = "FAIL (REGRESSION)"
        print(f"  {metric_name:<26} actual={actual:<4} (target {dir_symbol} {expected}) [{status}]")

    print("-" * 50)
    if not failures:
        print("RESULT: PASS - No regressions detected. Dataset quality conforms to baseline.")
        return 0

    print("RESULT: FAIL - Dataset regression(s) detected:")
    for idx, f in enumerate(failures, 1):
        print(f"  {idx}. {f.message}")
        for diag in f.diagnostics:
            print(f"     -> {diag}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
