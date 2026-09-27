"""Typed, reversible JSON encoding of Firestore values.

JSON already distinguishes what this repository stores most: null, booleans, integers,
floats (`1.0` stays a float), strings, lists and maps. The one Firestore type it cannot
express, and that the code does write (`SERVER_TIMESTAMP`, `expires_at`, `delete_after`,
`generated_at`...), is the timestamp. It is written as a tagged object:

    {"$type": "timestamp", "value": "2026-09-15T03:30:00.123456Z"}

A real map that happens to contain the key `$type` is wrapped as
`{"$type": "map", "value": {...}}`, so decoding is never ambiguous.

Everything else Firestore can hold (references, geo points, bytes, vectors, non-finite
floats) is not used by the game and is **rejected** at export time instead of being turned
into a string: a backup that looks valid but restores different types is worse than a
failed backup that someone notices.
"""
from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from typing import Any

TYPE_KEY = "$type"
INT64_MIN = -(2**63)
INT64_MAX = 2**63 - 1
_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")
_PLAIN_SEGMENT = re.compile(r"^[A-Za-z_]+$")


class BackupFormatError(ValueError):
    """The value or file cannot be represented faithfully (export) or decoded (restore)."""


def mask_segment(segment: str) -> str:
    """Field names are schema; map keys that look like ids are user data, so they are masked."""
    return segment if _PLAIN_SEGMENT.match(segment) else "*"


def _where(location: str, field: tuple[str, ...]) -> str:
    return f"{location}:{'.'.join(mask_segment(part) for part in field) or '<root>'}"


def format_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def parse_timestamp(text: str) -> datetime:
    if not isinstance(text, str) or not _TIMESTAMP.match(text):
        raise BackupFormatError("timestamp must be RFC 3339 UTC with microseconds")
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)


def encode_value(value: Any, location: str = "", field: tuple[str, ...] = ()) -> Any:
    """Firestore value (as returned by the Python client) -> JSON-safe value."""
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        if not INT64_MIN <= value <= INT64_MAX:
            raise BackupFormatError(f"{_where(location, field)}: integer outside int64")
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise BackupFormatError(f"{_where(location, field)}: non-finite float is not supported")
        return value
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise BackupFormatError(f"{_where(location, field)}: naive datetime (no timezone)")
        return {TYPE_KEY: "timestamp", "value": format_timestamp(value)}
    if isinstance(value, dict):
        encoded = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise BackupFormatError(f"{_where(location, field)}: map key is not a string")
            encoded[key] = encode_value(item, location, field + (key,))
        return {TYPE_KEY: "map", "value": encoded} if TYPE_KEY in encoded else encoded
    if isinstance(value, (list, tuple)):
        items = []
        for item in value:
            if isinstance(item, (list, tuple)):
                raise BackupFormatError(f"{_where(location, field)}: nested arrays are not valid in Firestore")
            items.append(encode_value(item, location, field))
        return items
    raise BackupFormatError(
        f"{_where(location, field)}: unsupported Firestore value type {type(value).__name__}; "
        "extend services/firestore_backup/codec.py before backing it up"
    )


def decode_value(value: Any, location: str = "", field: tuple[str, ...] = (), *, in_array: bool = False) -> Any:
    """JSON value from a backup -> Python value the Firestore client writes back identically."""
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        if not INT64_MIN <= value <= INT64_MAX:
            raise BackupFormatError(f"{_where(location, field)}: integer outside int64")
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise BackupFormatError(f"{_where(location, field)}: non-finite float")
        return value
    if isinstance(value, list):
        if in_array:
            raise BackupFormatError(f"{_where(location, field)}: nested arrays are not valid in Firestore")
        return [decode_value(item, location, field, in_array=True) for item in value]
    if isinstance(value, dict):
        if TYPE_KEY not in value:
            return {key: decode_value(item, location, field + (key,)) for key, item in value.items()}
        if set(value) != {TYPE_KEY, "value"}:
            raise BackupFormatError(f"{_where(location, field)}: tagged value must have exactly $type and value")
        kind = value[TYPE_KEY]
        if kind == "timestamp":
            try:
                return parse_timestamp(value["value"])
            except BackupFormatError as exc:
                raise BackupFormatError(f"{_where(location, field)}: {exc}") from None
        if kind == "map":
            inner = value["value"]
            if not isinstance(inner, dict) or TYPE_KEY not in inner:
                raise BackupFormatError(f"{_where(location, field)}: $type map wrapper used without a $type key")
            return {key: decode_value(item, location, field + (key,)) for key, item in inner.items()}
        raise BackupFormatError(f"{_where(location, field)}: unsupported tagged type")
    raise BackupFormatError(f"{_where(location, field)}: unsupported JSON value")


def encode_fields(fields: dict[str, Any], location: str) -> dict[str, Any]:
    """Document fields: the top level is always a plain map, never wrapped."""
    return {key: encode_value(item, location, (key,)) for key, item in fields.items()}


def decode_fields(fields: Any, location: str) -> dict[str, Any]:
    if not isinstance(fields, dict):
        raise BackupFormatError(f"{location}: fields must be an object")
    return {key: decode_value(item, location, (key,)) for key, item in fields.items()}


def canonical_json(value: Any) -> str:
    """Stable text used for the integrity digest and for type-strict comparisons."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _reject_constant(name: str) -> Any:
    raise BackupFormatError(f"non-standard JSON constant {name} in backup")


def loads(text: str) -> Any:
    """`json.loads` that refuses NaN/Infinity instead of accepting them silently."""
    return json.loads(text, parse_constant=_reject_constant)
