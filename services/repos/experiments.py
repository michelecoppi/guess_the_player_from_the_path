"""Transactional Firestore registry for operator-controlled experiments."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from firebase_admin import firestore

from services import experiments

SCHEMA_VERSION = 1
MAX_EXPERIMENTS = 100


def parse_document(raw: Any) -> dict[str, dict[str, Any]]:
    if raw is None:
        return {}
    if (not isinstance(raw, Mapping) or isinstance(raw.get("schema_version"), bool)
            or raw.get("schema_version") != SCHEMA_VERSION
            or not isinstance(raw.get("experiments"), Mapping)):
        raise ValueError("experiment document")
    records = raw["experiments"]
    if len(records) > MAX_EXPERIMENTS:
        raise ValueError("too many experiments")
    parsed = {key: experiments.validate(value) for key, value in records.items()}
    if any(key != record["key"] for key, record in parsed.items()):
        raise ValueError("experiment key mismatch")
    return parsed


def _ref():
    from services import firebase_service as fs
    return fs.db.collection(fs.ADMIN_SETTINGS_COLLECTION).document("experiments")


def load() -> dict[str, dict[str, Any]]:
    snapshot = _ref().get(timeout=5, retry=None)
    return parse_document(snapshot.to_dict() if snapshot.exists else None)


def create(record: Mapping[str, Any]) -> dict[str, Any]:
    candidate = experiments.validate(record)
    key = candidate["key"]
    def add(current: dict[str, Any] | None) -> dict[str, Any]:
        if current is not None:
            raise ValueError("experiment already exists")
        return candidate
    return update(key, add)


def update(key: str, change: Callable[[dict[str, Any] | None], dict[str, Any]]) -> dict[str, Any]:
    """Read and write one registry entry atomically; reject corrupt stored state."""
    from services import firebase_service as fs
    ref = _ref()

    @firestore.transactional
    def run(transaction):
        snapshot = ref.get(transaction=transaction)
        records = parse_document(snapshot.to_dict() if snapshot.exists else None)
        updated = experiments.validate(change(records.get(key)))
        if updated["key"] != key:
            raise ValueError("experiment key mismatch")
        records[key] = updated
        if len(records) > MAX_EXPERIMENTS:
            raise ValueError("too many experiments")
        transaction.set(ref, {"schema_version": SCHEMA_VERSION,
                              "experiments": records, "updated_at": firestore.SERVER_TIMESTAMP})
        return updated

    updated = run(fs.db.transaction(max_attempts=10))
    experiments.clear_assignment_cache()
    return updated
