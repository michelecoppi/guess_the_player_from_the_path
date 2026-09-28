"""Read-only, exposure-cohort reports for the registered experiment metrics."""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any

from services import product_analytics_query as analytics

_KEY = re.compile(r"[a-z][a-z0-9_]{2,63}\Z")
_METRIC_EVENTS = {
    "daily_completion_rate": ("daily_completed", "daily_guess_submitted"),
    "guesses_per_completed_daily": ("daily_completed", None),
    "hint_usage_rate": ("hint_used", "daily_guess_submitted"),
    "referral_conversion_rate": ("referral_converted", "referral_opened"),
    "shop_purchase_conversion_rate": ("shop_purchase_completed", "shop_viewed"),
    "miniapp_activation_rate": ("miniapp_opened", "bot_started"),
}

# These denominator events are emitted during /start, before a treatment assigned
# at a later product boundary can expose the user. The dashboard's global metric
# remains valid; its denominator is incompatible with this post-exposure report.
_PRE_EXPOSURE_DENOMINATORS = frozenset({"bot_started", "referral_opened"})


def validate_metric_window(metric: str) -> None:
    """Reject metrics whose denominator cannot follow a product exposure."""
    if metric not in _METRIC_EVENTS:
        raise ValueError(f"unknown experiment report metric: {metric}")
    denominator = _METRIC_EVENTS[metric][1]
    if denominator in _PRE_EXPOSURE_DENOMINATORS:
        raise ValueError(
            f"{metric}: denominator '{denominator}' is emitted during /start, "
            "before the treatment exposure; the report counts only events from "
            "first experiment_assigned through the experiment end"
        )


def _stamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("timezone required")
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def query(key: str, metric: str, start: datetime, end: datetime) -> str:
    """First exposure fixes each pseudonymous user in one variant for the window."""
    if not _KEY.fullmatch(key) or metric not in _METRIC_EVENTS or start >= end:
        raise ValueError("invalid experiment report")
    begin, finish = _stamp(start), _stamp(end)
    numerator, denominator = _METRIC_EVENTS[metric]
    active = f"e.timestamp >= x.first_exposure AND e.timestamp < toDateTime('{finish}')"
    if metric == "guesses_per_completed_daily":
        num = f"sumIf(toFloatOrZero(e.properties.attempts_used), e.event = '{numerator}' AND {active})"
        den = f"countIf(e.event = '{numerator}' AND {active})"
    elif metric in ("hint_usage_rate", "miniapp_activation_rate"):
        num = f"uniqIf(e.distinct_id, e.event = '{numerator}' AND {active})"
        den = f"uniqIf(e.distinct_id, e.event = '{denominator}' AND {active})"
    else:
        num = f"countIf(e.event = '{numerator}' AND {active})"
        extra = " AND e.properties.referral_attached = true" if metric == "referral_conversion_rate" else ""
        if metric == "daily_completion_rate":
            den = ("uniqIf(tuple(toDate(e.timestamp), e.distinct_id), "
                   f"e.event = '{denominator}' AND {active})")
        else:
            den = f"countIf(e.event = '{denominator}' AND {active}{extra})"
    return (
        "SELECT x.variant, uniq(x.distinct_id) AS sample, "
        f"{num} AS numerator, {den} AS denominator "
        "FROM (SELECT distinct_id, argMin(properties.variant, timestamp) AS variant, "
        "min(timestamp) AS first_exposure FROM events "
        f"WHERE event = 'experiment_assigned' AND properties.experiment_key = '{key}' "
        f"AND timestamp >= toDateTime('{begin}') AND timestamp < toDateTime('{finish}') "
        "GROUP BY distinct_id) AS x LEFT JOIN events AS e ON e.distinct_id = x.distinct_id "
        "WHERE x.variant IN ('control', 'treatment') GROUP BY x.variant ORDER BY x.variant"
    )


def _number(value: Any, *, integral: bool) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise analytics.QueryError("Risposta di PostHog malformata: aggregato non valido")
    if integral and (not float(value).is_integer()):
        raise analytics.QueryError("Risposta di PostHog malformata: conteggio non intero")
    return int(value) if integral else float(value)


def _rows(rows: list[list[Any]], metric: str) -> list[dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {
        variant: {"variant": variant, "sample": 0, "numerator": 0,
                  "denominator": 0, "value": None, "state": "empty"}
        for variant in ("control", "treatment")
    }
    seen = set()
    for row in rows:
        if len(row) != 4 or row[0] not in output or row[0] in seen:
            raise analytics.QueryError("Risposta di PostHog malformata: variante o colonne non valide")
        variant = row[0]
        seen.add(variant)
        sample = _number(row[1], integral=True)
        numerator = _number(row[2], integral=metric != "guesses_per_completed_daily")
        denominator = _number(row[3], integral=True)
        if not sample and (numerator or denominator):
            raise analytics.QueryError("Risposta di PostHog malformata: aggregati incoerenti")
        output[variant].update(sample=sample, numerator=numerator, denominator=denominator,
                               value=numerator / denominator if denominator else None,
                               state="ok" if denominator else "insufficient_data" if sample else "empty")
    return list(output.values())


def preflight(config: analytics.Settings, key: str, metric: str, now: datetime) -> None:
    """Execute the actual metric query; empty results are valid before any exposure."""
    from datetime import timedelta
    validate_metric_window(metric)
    rows = analytics._run_hogql(config, query(key, metric, now, now + timedelta(seconds=1)))
    _rows(rows, metric)


def report(config: analytics.Settings, record: dict[str, Any], *, now: datetime) -> dict[str, Any]:
    from services import experiments
    record = experiments.validate(record)
    if record["status"] == "planned":
        raise ValueError("experiment has not started")
    end = min(now, record["ends_at"])
    if record["stop"] is not None:
        end = min(end, record["stop"]["at"])
    begin = record["started_at"]
    result: dict[str, Any] = {"key": record["key"], "metric": record["metric"],
                              "interval": {"start": begin.isoformat(), "end": end.isoformat()},
                              "status": "ok", "variants": []}
    if end <= begin:
        result["status"] = "empty"
        result["variants"] = _rows([], record["metric"])
        return result
    try:
        rows = analytics._run_hogql(config, query(record["key"], record["metric"], begin, end))
        result["variants"] = _rows(rows, record["metric"])
        if all(row["state"] == "empty" for row in result["variants"]):
            result["status"] = "empty"
        elif any(row["state"] != "ok" for row in result["variants"]):
            result["status"] = "insufficient_data"
    except analytics.QueryError as error:
        result.update(status="query_error", error=str(error))
    return result
