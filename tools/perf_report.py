"""Performance baseline and trend report (#32).

Turns Cloud Logging entries into per-route percentiles, cold-start phases, Firestore cost,
Telegram handler durations and Mini App startup timings, checks them against the budgets in
`services/performance.py`, and compares a snapshot with an earlier one. Read-only: it never
writes to GCP. See docs/performance.md for how to read the output.

Usage:
    # Fetch the last 7 days with gcloud (needs roles/logging.viewer on the project)
    python -m tools.perf_report --fetch --days 7

    # Or use an export: gcloud logging read '<filter>' --format json > logs.json
    python -m tools.perf_report --input logs.json

    # Save a snapshot, and compare a later one with it (trend)
    python -m tools.perf_report --fetch --days 7 --save docs/performance-baselines/2026-09-16.json
    python -m tools.perf_report --fetch --days 7 --compare docs/performance-baselines/2026-09-16.json

Two kinds of entries are understood, so a baseline also exists for the period before the
application emitted its own performance events:

- Cloud Run request logs (`httpRequest.latency`): edge latency per path, with the first
  request seen for each instance marked as a cold start (inferred);
- application events (`api.request.completed`, `telegram.update.completed`,
  `app.startup.completed`, `miniapp.startup.measured`, `performance.budget.exceeded`) and
  the Cloud Run/uvicorn startup lines (`Starting new instance`, `Waiting for application
  startup.`, `Application startup complete.`).
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

DEFAULT_PROJECT = "guess-the-player-from-path-bot"
DEFAULT_SERVICE = "guess-the-player"
SNAPSHOT_VERSION = 1

APP_EVENTS = (
    "api.request.completed", "telegram.update.completed", "app.startup.completed",
    "miniapp.startup.measured", "performance.budget.exceeded", "firestore.query.slow",
)
_STARTUP_LINES = (
    ("Starting new instance", "instance_started"),
    ("Waiting for application startup", "app_imported"),
    ("Application startup complete", "app_ready"),
)
# Paths with ids or hashed file names are grouped so they aggregate.
# Older logs still carry the retired /app/v2 prefix (#146).
_PATH_GROUPS = ((re.compile(r"^/app(/v2)?/assets/.+"), "/app/assets/*"),)


def log_filter(service: str = DEFAULT_SERVICE) -> str:
    events = " OR ".join(f'"{name}"' for name in APP_EVENTS)
    return (
        f'resource.type="cloud_run_revision" AND resource.labels.service_name="{service}" AND ('
        f"jsonPayload.event=({events})"
        ' OR logName:"run.googleapis.com%2Frequests"'
        ' OR textPayload:"Starting new instance"'
        ' OR jsonPayload.message:"application startup" OR textPayload:"application startup")'
    )


def fetch(days: int, project: str, service: str, limit: int) -> list[dict[str, Any]]:
    gcloud = shutil.which("gcloud") or shutil.which("gcloud.cmd")
    if not gcloud:
        raise SystemExit("gcloud not found: install the Google Cloud SDK or pass --input")
    cmd = [gcloud, "logging", "read", log_filter(service), "--project", project,
           "--freshness", f"{days}d", "--limit", str(limit), "--format", "json"]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", check=False)
    if result.returncode != 0:
        raise SystemExit(f"gcloud logging read failed: {result.stderr.strip()}")
    return json.loads(result.stdout or "[]")


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


def percentile(values: list[float], fraction: float) -> Optional[float]:
    """Nearest-rank percentile; None for an empty list."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, -(-len(ordered) * fraction // 1))  # ceil without float surprises
    return round(ordered[int(rank) - 1], 1)


def summary(values: list[float]) -> dict[str, Any]:
    return {"count": len(values), "p50": percentile(values, 0.5), "p95": percentile(values, 0.95),
            "p99": percentile(values, 0.99), "max": round(max(values), 1) if values else None}


def _timestamp(value: str) -> datetime:
    value = value.rstrip("Z")
    if "." in value:
        head, fraction = value.split(".", 1)
        value = f"{head}.{fraction[:6]}"
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def _group_path(path: str) -> str:
    for pattern, name in _PATH_GROUPS:
        if pattern.match(path):
            return name
    return path


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------


def build_snapshot(entries: Iterable[dict[str, Any]], budgets: Optional[Any] = None) -> dict[str, Any]:
    if budgets is None:
        from services import performance as budgets

    entries = sorted(entries, key=lambda entry: entry.get("timestamp", ""))
    edge: dict[str, dict[str, list[float]]] = defaultdict(lambda: {"all": [], "warm": [], "cold": []})
    app: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    telegram: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    miniapp: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    app_startup: dict[str, list[float]] = defaultdict(list)
    exceeded: dict[str, int] = defaultdict(int)
    instances: dict[str, dict[str, datetime]] = defaultdict(dict)
    seen_instances: set[str] = set()
    first_ts = last_ts = None

    for entry in entries:
        timestamp = entry.get("timestamp")
        if timestamp:
            first_ts = first_ts or timestamp
            last_ts = timestamp
        instance = (entry.get("labels") or {}).get("instanceId")
        http = entry.get("httpRequest") or {}
        payload = entry.get("jsonPayload") or {}
        text = entry.get("textPayload") or payload.get("message") or ""

        if http.get("latency") and http.get("requestUrl"):
            path = _group_path(urlparse(http["requestUrl"]).path)
            key = f'{http.get("requestMethod", "GET")} {path}'
            latency = float(str(http["latency"]).rstrip("s")) * 1000
            cold = bool(instance) and instance not in seen_instances
            if instance:
                seen_instances.add(instance)
            edge[key]["all"].append(latency)
            edge[key]["cold" if cold else "warm"].append(latency)
            continue

        event = payload.get("event")
        if event == "api.request.completed":
            route = payload.get("route", "unmatched")
            bucket = app[route]
            bucket["cold" if payload.get("cold_start") else "warm"].append(payload.get("duration_ms", 0))
            for field in ("firestore_reads", "firestore_ms", "firestore_writes"):
                if field in payload:
                    bucket[field].append(payload[field])
        elif event == "telegram.update.completed":
            key = payload.get("command") or payload.get("update_type") or "unknown"
            telegram[key]["duration_ms"].append(payload.get("duration_ms", 0))
            if "firestore_reads" in payload:
                telegram[key]["firestore_reads"].append(payload["firestore_reads"])
        elif event == "app.startup.completed":
            for field in ("before_lifespan_ms", "lifespan_ms", "startup_ms"):
                if isinstance(payload.get(field), (int, float)):
                    app_startup[field].append(payload[field])
        elif event == "miniapp.startup.measured":
            for field, value in payload.items():
                if field.endswith("_ms") or field == "transfer_kb":
                    if isinstance(value, (int, float)):
                        miniapp[payload.get("app", "unknown")][field].append(value)
        elif event == "performance.budget.exceeded":
            exceeded[f'{payload.get("route")} {payload.get("metric")}'] += 1
        elif instance and timestamp:
            for marker, phase in _STARTUP_LINES:
                if text.lower().startswith(marker.lower()):
                    instances[instance].setdefault(phase, _timestamp(timestamp))

    container: dict[str, list[float]] = defaultdict(list)
    for phases in instances.values():
        if {"instance_started", "app_imported", "app_ready"} <= phases.keys():
            ms = lambda a, b: (phases[b] - phases[a]).total_seconds() * 1000  # noqa: E731
            container["before_app_ms"].append(ms("instance_started", "app_imported"))
            container["lifespan_ms"].append(ms("app_imported", "app_ready"))
            container["total_ms"].append(ms("instance_started", "app_ready"))

    snapshot: dict[str, Any] = {
        "version": SNAPSHOT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "window": {"from": first_ts, "to": last_ts},
        "edge": {},
        "app": {},
        "telegram": {},
        "container_startup": {name: summary(values) for name, values in sorted(container.items())},
        "app_startup": {name: summary(values) for name, values in sorted(app_startup.items())},
        "miniapp": {},
        "budget_exceeded": dict(sorted(exceeded.items())),
    }
    for key, bucket in sorted(edge.items(), key=lambda item: -len(item[1]["all"])):
        snapshot["edge"][key] = {**summary(bucket["all"]), "cold_count": len(bucket["cold"]),
                                 "warm": summary(bucket["warm"])}
    for route, bucket in sorted(app.items(), key=lambda item: -len(item[1]["warm"]) - len(item[1]["cold"])):
        warm = bucket["warm"]
        budget = budgets.latency_budget_ms(route)
        row = {"warm": summary(warm), "cold_count": len(bucket["cold"]), "latency_budget_ms": budget,
               "over_budget": sum(1 for value in warm if budget is not None and value > budget)}
        if bucket.get("firestore_reads"):
            row["firestore_reads"] = summary(bucket["firestore_reads"])
            row["read_budget"] = budgets.read_budget(route)
        if bucket.get("firestore_ms"):
            row["firestore_ms"] = summary(bucket["firestore_ms"])
        snapshot["app"][route] = row
    for key, bucket in sorted(telegram.items(), key=lambda item: -len(item[1]["duration_ms"])):
        snapshot["telegram"][key] = {name: summary(values) for name, values in bucket.items()}
    for name, bucket in sorted(miniapp.items()):
        snapshot["miniapp"][name] = {metric: summary(values) for metric, values in sorted(bucket.items())}
    return snapshot


# ---------------------------------------------------------------------------
# Rendering and comparison
# ---------------------------------------------------------------------------


def _fmt(value: Any) -> str:
    if value is None:
        return "–"
    if isinstance(value, float):
        return f"{value:.0f}" if value >= 10 else f"{value:.1f}"
    return str(value)


def render(snapshot: dict[str, Any], comparison: Optional[dict[str, Any]] = None) -> str:
    lines = [f'# Performance report ({snapshot["window"]["from"]} → {snapshot["window"]["to"]})', ""]

    def table(title, header, rows):
        if not rows:
            return
        lines.extend([f"## {title}", "", "| " + " | ".join(header) + " |",
                      "|" + "|".join("---" for _ in header) + "|"])
        lines.extend("| " + " | ".join(_fmt(cell) for cell in row) + " |" for row in rows)
        lines.append("")

    table("Cloud Run edge latency (ms, includes cold starts)",
          ["request", "n", "p50", "p95", "p99", "cold n", "warm p95"],
          [[key, row["count"], row["p50"], row["p95"], row["p99"], row["cold_count"], row["warm"]["p95"]]
           for key, row in snapshot["edge"].items()])
    table("Container cold start (ms)", ["phase", "n", "p50", "p95", "max"],
          [[name, row["count"], row["p50"], row["p95"], row["max"]] for name, row in snapshot["container_startup"].items()])
    table("Application startup (ms, app.startup.completed)", ["phase", "n", "p50", "p95", "max"],
          [[name, row["count"], row["p50"], row["p95"], row["max"]] for name, row in snapshot["app_startup"].items()])
    table("Application routes, warm requests (ms)",
          ["route", "n", "p50", "p95", "budget", "over", "cold n", "reads p50", "reads p95", "fs ms p50"],
          [[route, row["warm"]["count"], row["warm"]["p50"], row["warm"]["p95"], row["latency_budget_ms"],
            row["over_budget"], row["cold_count"], (row.get("firestore_reads") or {}).get("p50"),
            (row.get("firestore_reads") or {}).get("p95"), (row.get("firestore_ms") or {}).get("p50")]
           for route, row in snapshot["app"].items()])
    table("Telegram handlers (ms)", ["command/update", "n", "p50", "p95", "reads p50"],
          [[key, row["duration_ms"]["count"], row["duration_ms"]["p50"], row["duration_ms"]["p95"],
            (row.get("firestore_reads") or {}).get("p50")] for key, row in snapshot["telegram"].items()])
    for name, metrics in snapshot["miniapp"].items():
        table(f"Mini App startup — {name} (ms, measured on device)", ["metric", "n", "p50", "p95"],
              [[metric, row["count"], row["p50"], row["p95"]] for metric, row in metrics.items()])
    table("Budget exceeded", ["route metric", "count"], [[key, count] for key, count in snapshot["budget_exceeded"].items()])

    if comparison:
        rows = compare(comparison, snapshot)
        table(f'Trend vs {comparison["window"]["from"]} → {comparison["window"]["to"]}',
              ["metric", "before", "now", "change"], rows)
    return "\n".join(lines)


def _flatten(snapshot: dict[str, Any]) -> dict[str, float]:
    flat: dict[str, float] = {}
    for key, row in snapshot.get("edge", {}).items():
        for stat in ("p50", "p95"):
            if row.get(stat) is not None:
                flat[f"edge {key} {stat}"] = row[stat]
        if row.get("warm", {}).get("p95") is not None:
            flat[f"edge {key} warm p95"] = row["warm"]["p95"]
    for section in ("container_startup", "app_startup"):
        for name, row in snapshot.get(section, {}).items():
            if row.get("p50") is not None:
                flat[f"{section} {name} p50"] = row["p50"]
    for route, row in snapshot.get("app", {}).items():
        for stat in ("p50", "p95"):
            if row["warm"].get(stat) is not None:
                flat[f"app {route} {stat}"] = row["warm"][stat]
        if (row.get("firestore_reads") or {}).get("p50") is not None:
            flat[f"app {route} reads p50"] = row["firestore_reads"]["p50"]
    for name, metrics in snapshot.get("miniapp", {}).items():
        for metric, row in metrics.items():
            if row.get("p50") is not None:
                flat[f"miniapp {name} {metric} p50"] = row["p50"]
    return flat


def compare(before: dict[str, Any], after: dict[str, Any]) -> list[list[Any]]:
    """Rows [metric, before, now, change%] for every metric present in both snapshots."""
    old, new = _flatten(before), _flatten(after)
    rows = []
    for key in sorted(old.keys() & new.keys()):
        change = None if not old[key] else f"{(new[key] - old[key]) / old[key] * 100:+.0f}%"
        rows.append([key, old[key], new[key], change])
    return rows


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--input", action="append", type=Path, help="JSON export of gcloud logging read (repeatable)")
    source.add_argument("--fetch", action="store_true", help="Read the logs with gcloud")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--service", default=DEFAULT_SERVICE)
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--save", type=Path, help="Write the snapshot JSON here")
    parser.add_argument("--compare", type=Path, help="Earlier snapshot JSON to show the trend against")
    parser.add_argument("--print-filter", action="store_true", help="Print the Cloud Logging filter and exit")
    args = parser.parse_args(argv)

    if args.print_filter:
        print(log_filter(args.service))
        return 0
    if not args.fetch and not args.input:
        parser.error("one of --input or --fetch is required")
    if args.fetch:
        entries = fetch(args.days, args.project, args.service, args.limit)
    else:
        entries = []
        for path in args.input:
            entries.extend(json.loads(path.read_text(encoding="utf-8")))
    snapshot = build_snapshot(entries)
    comparison = json.loads(args.compare.read_text(encoding="utf-8")) if args.compare else None
    if args.save:
        args.save.parent.mkdir(parents=True, exist_ok=True)
        args.save.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    print(render(snapshot, comparison))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
