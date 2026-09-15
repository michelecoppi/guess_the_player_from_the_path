"""Firestore I/O for `admin_settings/feature_flags` (#51).

Reads are a single document get with a bounded timeout and no client-side retry, so a slow
Firestore cannot hold a request for long: the cache in services/feature_flags.py keeps
serving its last-known-good configuration instead.

Writes change **one flag entry** inside a transaction: the change is applied to the entry
as it is *now* in Firestore (not to a copy the operator read earlier), `revision` is
incremented, and an optional `expected_revision` refuses the write if anyone else changed
the document in between. Two operators adding different users at the same time both land;
the transaction retries on contention instead of overwriting.
"""
from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Optional

from firebase_admin import firestore

from services.feature_flags import (
    REGISTRY,
    SCHEMA_VERSION,
    ConfigError,
    Flag,
    FlagRule,
    parse_document,
    parse_rule,
    serialize_rule,
)

READ_TIMEOUT_SECONDS = 5.0
# Operator writes are rare but may collide (two people reacting to the same incident): a few
# more attempts than the client default before surfacing an error. A failed transaction
# writes nothing, so an update is either applied on fresh data or reported, never lost.
TRANSACTION_ATTEMPTS = 10
_ACTOR = re.compile(r"[^A-Za-z0-9_.@:-]")


class RevisionConflict(Exception):
    def __init__(self, expected: int, current: int):
        super().__init__(f"revision changed: expected {expected}, current {current}")
        self.expected = expected
        self.current = current


class StoredConfigInvalid(Exception):
    """The stored document (or the entry being changed) is not valid, so building on it
    would persist unknown data. The message names the field, never its value."""


@dataclass(frozen=True)
class ChangeResult:
    flag: Flag
    before: Optional[FlagRule]
    after: Optional[FlagRule]
    previous_revision: int
    revision: int


def _ref():
    from services import firebase_service as fs
    return fs.db.collection(fs.ADMIN_SETTINGS_COLLECTION).document(fs.FEATURE_FLAGS_DOC)


def load_document() -> Optional[dict[str, Any]]:
    """The raw document, or None if it does not exist. Exceptions propagate to the cache."""
    snapshot = _ref().get(timeout=READ_TIMEOUT_SECONDS, retry=None)
    return snapshot.to_dict() if snapshot.exists else None


def clean_actor(actor: Any) -> str:
    text = _ACTOR.sub("", str(actor or ""))[:64]
    return text or "operator"


def plan_update(
    raw: Optional[Mapping[str, Any]],
    flag: Flag,
    change: Optional[Callable[[FlagRule], FlagRule]],
    *,
    expected_revision: Optional[int] = None,
    replace_invalid_document: bool = False,
) -> tuple[str, dict[str, Any], ChangeResult]:
    """Pure planning of one change against the current stored document.

    `change=None` resets the flag (removes its entry → repository default). Returns
    `(mode, payload, result)`: mode `"update"` means field-path updates on the existing valid
    document (other flags untouched); `"set"` means writing a whole new document (none
    existed, or an invalid one is explicitly being replaced). Metadata is added by the caller."""
    if raw is not None:
        try:
            parse_document(raw)
        except ConfigError as exc:
            if not replace_invalid_document:
                raise StoredConfigInvalid(f"stored document is invalid ({exc})") from None
            raw = None

    stored_revision = (raw or {}).get("revision") or 0
    current_revision = stored_revision if isinstance(stored_revision, int) else 0
    if expected_revision is not None and expected_revision != current_revision:
        raise RevisionConflict(expected_revision, current_revision)

    entry = ((raw or {}).get("flags") or {}).get(flag.value)
    before: Optional[FlagRule] = None
    if entry is not None:
        try:
            before = parse_rule(entry, REGISTRY[flag].default)
        except ValueError as exc:
            if change is not None:
                raise StoredConfigInvalid(
                    f"stored entry for '{flag.value}' is invalid ({exc}); reset it first") from None

    after = None if change is None else change(before or FlagRule(enabled=REGISTRY[flag].default))
    revision = current_revision + 1
    result = ChangeResult(flag, before, after, current_revision, revision)

    if raw is not None:
        return "update", {
            f"flags.{flag.value}": firestore.DELETE_FIELD if after is None else serialize_rule(after),
            "revision": revision,
        }, result
    return "set", {
        "schema_version": SCHEMA_VERSION,
        "revision": revision,
        "flags": {} if after is None else {flag.value: serialize_rule(after)},
    }, result


def update_flag(
    flag: Flag,
    change: Optional[Callable[[FlagRule], FlagRule]],
    *,
    actor: str,
    expected_revision: Optional[int] = None,
    replace_invalid_document: bool = False,
) -> ChangeResult:
    """Apply one change transactionally. `change=None` resets the flag to its default."""
    from services import firebase_service as fs

    ref = _ref()
    metadata = {"updated_at": firestore.SERVER_TIMESTAMP, "updated_by": clean_actor(actor)}

    @firestore.transactional
    def run(transaction):
        snapshot = ref.get(transaction=transaction)
        mode, payload, result = plan_update(
            snapshot.to_dict() if snapshot.exists else None, flag, change,
            expected_revision=expected_revision, replace_invalid_document=replace_invalid_document,
        )
        if mode == "update":
            transaction.update(ref, {**payload, **metadata})
        else:
            transaction.set(ref, {**payload, **metadata})
        return result

    return run(fs.db.transaction(max_attempts=TRANSACTION_ATTEMPTS))
