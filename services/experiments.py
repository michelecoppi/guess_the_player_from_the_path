"""Operator-controlled experiment lifecycle and deterministic variant assignment (#52)."""
from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any

from services.product_analytics_query import CORE_METRICS

METRICS = frozenset(row[0] for row in CORE_METRICS)
_KEY = re.compile(r"[a-z][a-z0-9_]{2,63}\Z")
_URL = re.compile(r"https://[^\s]{1,500}\Z")


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 500:
        raise ValueError(name)
    return value.strip()


def plan(key: str, hypothesis: str, metric: str, duration_days: int,
         treatment: str) -> dict[str, Any]:
    """Only named metrics already defined by product analytics can be selected."""
    if not isinstance(key, str) or not _KEY.fullmatch(key):
        raise ValueError("key")
    if metric not in METRICS:
        raise ValueError("metric")
    if isinstance(duration_days, bool) or not isinstance(duration_days, int) or not 1 <= duration_days <= 90:
        raise ValueError("duration_days")
    return {"key": key, "hypothesis": _text(hypothesis, "hypothesis"),
            "metric": metric, "duration_days": duration_days,
            "variants": {"control": "current behavior", "treatment": _text(treatment, "treatment")},
            "status": "planned", "started_at": None, "ends_at": None,
            "result": None, "decision": None}


def validate(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, Mapping) or set(raw) != {
        "key", "hypothesis", "metric", "duration_days", "variants", "status",
        "started_at", "ends_at", "result", "decision",
    }:
        raise ValueError("experiment fields")
    variants = raw["variants"]
    if not isinstance(variants, Mapping) or set(variants) != {"control", "treatment"} or variants["control"] != "current behavior":
        raise ValueError("variants")
    planned = plan(raw["key"], raw["hypothesis"], raw["metric"], raw["duration_days"], variants["treatment"])
    state = raw["status"]
    if state not in ("planned", "running", "finished", "decided"):
        raise ValueError("status")
    if state == "planned":
        if any(raw[field] is not None for field in ("started_at", "ends_at", "result", "decision")):
            raise ValueError("planned lifecycle")
    else:
        started, ends = raw["started_at"], raw["ends_at"]
        if not isinstance(started, datetime) or not isinstance(ends, datetime) or started.tzinfo is None or ends.tzinfo is None:
            raise ValueError("dates")
        if ends != started + timedelta(days=planned["duration_days"]):
            raise ValueError("ends_at")
        if state == "running" and (raw["result"] is not None or raw["decision"] is not None):
            raise ValueError("running lifecycle")
        if state in ("finished", "decided"):
            result = raw["result"]
            if not isinstance(result, Mapping) or set(result) != {"summary", "evidence_url"}:
                raise ValueError("result")
            _text(result["summary"], "result summary")
            if not isinstance(result["evidence_url"], str) or not _URL.fullmatch(result["evidence_url"]):
                raise ValueError("evidence_url")
            if state == "finished" and raw["decision"] is not None:
                raise ValueError("decision")
            if state == "decided" and raw["decision"] not in ("ship", "iterate", "stop"):
                raise ValueError("decision")
    return dict(raw)


def start(raw: Any, *, now: datetime, analytics_ready: bool) -> dict[str, Any]:
    record = validate(raw)
    if record["status"] != "planned" or not analytics_ready or now.tzinfo is None:
        raise ValueError("experiment cannot start without a defined metric and active analytics")
    record.update(status="running", started_at=now, ends_at=now + timedelta(days=record["duration_days"]))
    return validate(record)


def finish(raw: Any, *, summary: str, evidence_url: str,
           now: datetime) -> dict[str, Any]:
    record = validate(raw)
    if record["status"] != "running" or now.tzinfo is None or now < record["ends_at"]:
        raise ValueError("experiment duration has not elapsed")
    record.update(status="finished", result={"summary": _text(summary, "result summary"),
                  "evidence_url": evidence_url})
    return validate(record)


def decide(raw: Any, decision: str) -> dict[str, Any]:
    record = validate(raw)
    if record["status"] != "finished":
        raise ValueError("experiment has no result")
    record.update(status="decided", decision=decision)
    return validate(record)


def variant_for_subject(raw: Mapping[str, Any], *, user_id: Any = None,
                        group_id: Any = None, now: datetime | None = None) -> str | None:
    """Stable 50/50 assignment only during the scheduled running window."""
    record = validate(raw)
    moment = now or datetime.now(timezone.utc)
    if record["status"] != "running" or moment.tzinfo is None or not record["started_at"] <= moment < record["ends_at"]:
        return None
    from services.feature_flags import normalize_target_id
    try:
        if user_id is not None:
            kind, subject = "user", normalize_target_id(user_id)
        elif group_id is not None:
            kind, subject = "group", normalize_target_id(group_id)
        else:
            return None
    except ValueError:
        return None
    digest = hashlib.sha256(f"{record['key']}:{kind}:{subject}".encode()).digest()
    return ("control", "treatment")[int.from_bytes(digest[:8], "big") % 2]


def assign(key: str, *, user_id: Any, now: datetime | None = None) -> str | None:
    """Resolve a live treatment and capture exposure for variant-segmented metrics.

    Call this at the treatment boundary, never on an unrelated page load. If the
    registry cannot be read, the caller receives no treatment.
    """
    if not isinstance(key, str) or not _KEY.fullmatch(key):
        return None
    try:
        from services import product_analytics
        if not product_analytics.is_enabled() or not product_analytics.settings().salt:
            return None
        from services.repos import experiments as repository
        record = repository.load().get(key)
        if record is None:
            return None
        variant = variant_for_subject(record, user_id=user_id, now=now)
        if variant is not None:
            product_analytics.capture(
                product_analytics.Event.EXPERIMENT_ASSIGNED, user_id=user_id,
                properties={"experiment_key": key, "variant": variant},
            )
        return variant
    except Exception:
        # Experiment infrastructure may not interrupt the product.
        return None
