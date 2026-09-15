"""Backup file format v2: envelope, validation and the v1 upgrade.

    {
      "format": "guess-the-player.firestore-backup",
      "format_version": 2,
      "created_at": "...Z", "completed_at": "...Z",
      "source_project": "...", "source_emulator": false,
      "generator": {"tool": ..., "git_sha": ..., "run_id": ...},
      "inventory": {"backed_up": [...], "excluded": [...], "unclassified": [...]},
      "collections": [...], "complete": true,
      "document_counts": {"users": 3, "users/*/history": 12, ...}, "total_documents": 15,
      "integrity": {"algorithm": "sha256", "data_sha256": "..."},
      "legacy_conversion": null,
      "data": {"users": {"<id>": {"exists": true, "fields": {...},
                                  "subcollections": {"history": {"<id>": {...}}}}}}
    }

`exists: false` marks a parent path that has no document but does have subcollections
(Firestore allows it); restore recreates the subcollections and never invents the parent.

A file is usable only if `validate_archive` returns no errors: structure, version, metadata,
counts, digest and the decoding of every single value are checked. Warnings (an unclassified
collection, a subcollection not declared in the inventory, an incomplete backup) do not make
the file unusable, but `validate --strict` fails on them.
"""
from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterator

from services.firestore_backup import codec, inventory

FORMAT_NAME = "guess-the-player.firestore-backup"
FORMAT_VERSION = 2

_TOP_LEVEL_KEYS = {
    "format", "format_version", "created_at", "completed_at", "source_project", "source_emulator",
    "generator", "inventory", "collections", "complete", "document_counts", "total_documents",
    "integrity", "legacy_conversion", "data",
}
_NODE_KEYS = {"exists", "fields", "subcollections"}
_PROJECT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$")

# Pre-#50 (v1) exports turned every datetime into `isoformat()` text and every other
# Firestore-specific value into `str(value)`. The code of that time wrote timestamps only in
# these top-level fields, so an upgrade can type them back. The list is frozen: v1 files are no
# longer produced, and new timestamp fields are covered by the typed v2 codec.
LEGACY_V1_TIMESTAMP_FIELDS: dict[str, tuple[str, ...]] = {
    "users": ("date_created",),
    "daily_path": ("generated_at",),
    "events": ("generated_at",),
    "seasons": ("created_at",),
    "leagues": ("created_at",),
    "leagues/*/members": ("joined_at",),
    "purchases": ("created_at", "refunded_at"),
    "father_son_pairs": ("created_at",),
}


class BackupValidationError(ValueError):
    def __init__(self, report: "ValidationReport"):
        super().__init__("; ".join(report.errors[:5]) or "invalid backup")
        self.report = report


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def valid_id(value: Any) -> bool:
    return (isinstance(value, str) and 0 < len(value.encode("utf-8")) <= 1500 and "/" not in value
            and value not in (".", "..") and not (value.startswith("__") and value.endswith("__")))


def pattern(segments: tuple[str, ...]) -> str:
    """`("users", "42", "history")` -> `users/*/history`: counts and errors never carry ids."""
    return "/".join(part if index % 2 == 0 else "*" for index, part in enumerate(segments))


def iter_nodes(data: dict[str, Any], prefix: tuple[str, ...] = ()) -> Iterator[tuple[tuple[str, ...], dict[str, Any]]]:
    """Every document node, parents before their subcollections, in a stable order."""
    for collection_id in sorted(data):
        documents = data[collection_id]
        for doc_id in sorted(documents):
            path = prefix + (collection_id, doc_id)
            node = documents[doc_id]
            yield path, node
            yield from iter_nodes(node.get("subcollections") or {}, path)


def document_counts(data: dict[str, Any]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for path, node in iter_nodes(data):
        if node.get("exists"):
            counts[pattern(path[:-1])] += 1
    return dict(sorted(counts.items()))


def data_digest(data: dict[str, Any]) -> str:
    return hashlib.sha256(codec.canonical_json(data).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Building
# ---------------------------------------------------------------------------

def build_archive(
    data: dict[str, Any],
    *,
    source_project: str,
    source_emulator: bool,
    created_at: datetime,
    completed_at: datetime,
    generator: dict[str, Any],
    unclassified: list[str] | tuple[str, ...] = (),
    legacy_conversion: dict[str, Any] | None = None,
) -> dict[str, Any]:
    backed_up = list(inventory.backed_up_names())
    counts = document_counts(data)
    return {
        "format": FORMAT_NAME,
        "format_version": FORMAT_VERSION,
        "created_at": codec.format_timestamp(created_at),
        "completed_at": codec.format_timestamp(completed_at),
        "source_project": source_project,
        "source_emulator": source_emulator,
        "generator": generator,
        "inventory": {
            "backed_up": backed_up,
            "excluded": list(inventory.excluded_names()),
            "unclassified": sorted(unclassified),
        },
        "collections": sorted(data),
        "complete": set(backed_up) <= set(data),
        "document_counts": counts,
        "total_documents": sum(counts.values()),
        "integrity": {"algorithm": "sha256", "data_sha256": data_digest(data)},
        "legacy_conversion": legacy_conversion,
        "data": data,
    }


def summary(archive: dict[str, Any]) -> dict[str, Any]:
    """Metadata only - safe to print or log: no document ids, no field values."""
    return {key: archive.get(key) for key in (
        "format", "format_version", "created_at", "completed_at", "source_project", "source_emulator",
        "generator", "collections", "complete", "document_counts", "total_documents", "integrity",
        "legacy_conversion",
    )}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def looks_like_v1(obj: Any) -> bool:
    if not isinstance(obj, dict) or "format" in obj or not obj:
        return False
    for documents in obj.values():
        if not isinstance(documents, dict):
            return False
        if any(not isinstance(node, dict) or "_data" not in node for node in documents.values()):
            return False
    return True


def validate_archive(obj: Any) -> ValidationReport:
    report = ValidationReport()
    errors, warnings = report.errors, report.warnings
    if looks_like_v1(obj):
        errors.append("legacy v1 backup (lossy, untyped): convert it first with "
                      "`python scripts/restore_firestore.py upgrade-v1`")
        return report
    if not isinstance(obj, dict):
        errors.append("backup root must be a JSON object")
        return report
    if obj.get("format") != FORMAT_NAME:
        errors.append(f"not a {FORMAT_NAME} file")
        return report
    version = obj.get("format_version")
    if version != FORMAT_VERSION:
        errors.append(f"unsupported format_version {version!r} (this tool reads {FORMAT_VERSION})")
        return report
    unknown = set(obj) - _TOP_LEVEL_KEYS
    missing = _TOP_LEVEL_KEYS - set(obj)
    if unknown:
        errors.append(f"unknown top-level keys: {sorted(unknown)}")
    if missing:
        errors.append(f"missing top-level keys: {sorted(missing)}")
        return report

    report.summary = summary(obj)
    stamps = {}
    for key in ("created_at", "completed_at"):
        try:
            stamps[key] = codec.parse_timestamp(obj[key])
        except codec.BackupFormatError as exc:
            errors.append(f"{key}: {exc}")
    if len(stamps) == 2 and stamps["completed_at"] < stamps["created_at"]:
        errors.append("completed_at is before created_at")
    if not isinstance(obj["source_project"], str) or not _PROJECT.match(obj["source_project"]):
        errors.append("source_project must be a project id")
    if not isinstance(obj["source_emulator"], bool):
        errors.append("source_emulator must be a boolean")
    if not isinstance(obj["generator"], dict) or not isinstance(obj["generator"].get("tool"), str):
        errors.append("generator.tool is required")
    if obj["legacy_conversion"] is not None and not isinstance(obj["legacy_conversion"], dict):
        errors.append("legacy_conversion must be null or an object")
    elif obj["legacy_conversion"]:
        warnings.append("converted from a legacy v1 export: values not typed by the conversion may differ")

    archived_inventory = obj["inventory"]
    if (not isinstance(archived_inventory, dict)
            or any(not isinstance(archived_inventory.get(key), list) for key in ("backed_up", "excluded", "unclassified"))):
        errors.append("inventory must list backed_up, excluded and unclassified collections")
        archived_inventory = {"backed_up": [], "excluded": [], "unclassified": []}

    data = obj["data"]
    if not isinstance(data, dict):
        errors.append("data must be an object")
        return report
    if obj["collections"] != sorted(data):
        errors.append("collections does not match the collections present in data")
    if obj["complete"] is not (set(archived_inventory["backed_up"]) <= set(data)):
        errors.append("complete flag does not match the collections present")
    for name in sorted(data):
        if name in inventory.excluded_names():
            errors.append(f"{name}: collection is excluded by the inventory and must not be restored")
        elif inventory.policy(name) is None:
            warnings.append(f"{name}: collection is not classified in services/firestore_backup/inventory.py")
    uncovered = sorted(set(inventory.backed_up_names()) - set(data))
    if uncovered:
        warnings.append(f"incomplete backup, not covered: {uncovered}")

    _validate_tree(data, (), report)
    if errors:
        return report

    counts = document_counts(data)
    if obj["document_counts"] != counts:
        errors.append("document_counts do not match the documents in data")
    if obj["total_documents"] != sum(counts.values()):
        errors.append("total_documents does not match the documents in data")
    integrity = obj["integrity"]
    if not isinstance(integrity, dict) or integrity.get("algorithm") != "sha256":
        errors.append("integrity.algorithm must be sha256")
    elif integrity.get("data_sha256") != data_digest(data):
        errors.append("integrity digest mismatch: the data section was modified or corrupted")
    return report


def _validate_tree(collections: Any, prefix: tuple[str, ...], report: ValidationReport) -> None:
    if not isinstance(collections, dict):
        report.errors.append(f"{pattern(prefix) or '<root>'}: collections must be an object")
        return
    for collection_id, documents in collections.items():
        path = prefix + (collection_id,)
        where = pattern(path)
        if not valid_id(collection_id):
            report.errors.append(f"{where}: invalid collection id")
            continue
        if prefix:
            declared = inventory.declared_subcollections(prefix[0])
            if inventory.policy(prefix[0]) and len(prefix) == 2 and collection_id not in declared:
                report.warnings.append(f"{where}: subcollection not declared in the inventory")
        if not isinstance(documents, dict):
            report.errors.append(f"{where}: documents must be an object")
            continue
        for doc_id, node in documents.items():
            location = f"{where}/*"
            if not valid_id(doc_id):
                report.errors.append(f"{location}: invalid document id")
                continue
            _validate_node(node, path + (doc_id,), location, report)
            if len(report.errors) > 50:
                report.errors.append("too many errors, stopping")
                return


def _validate_node(node: Any, path: tuple[str, ...], location: str, report: ValidationReport) -> None:
    if not isinstance(node, dict) or set(node) - _NODE_KEYS or not isinstance(node.get("exists"), bool):
        report.errors.append(f"{location}: document node must have a boolean exists and only fields/subcollections")
        return
    subcollections = node.get("subcollections")
    if subcollections is not None and (not isinstance(subcollections, dict) or not subcollections):
        report.errors.append(f"{location}: subcollections, when present, must be a non-empty object")
        return
    if node["exists"]:
        try:
            codec.decode_fields(node.get("fields"), location)
        except codec.BackupFormatError as exc:
            report.errors.append(str(exc))
    else:
        if "fields" in node:
            report.errors.append(f"{location}: a missing parent document cannot have fields")
        if not subcollections:
            report.errors.append(f"{location}: a missing parent document must have subcollections")
    if subcollections:
        _validate_tree(subcollections, path, report)


def load_archive(path: str) -> tuple[Any, ValidationReport, str]:
    """(parsed file or None, report, sha256 of the file bytes)."""
    with open(path, "rb") as handle:
        raw = handle.read()
    file_sha256 = hashlib.sha256(raw).hexdigest()
    try:
        obj = codec.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        report = ValidationReport(errors=[f"not valid JSON: {type(exc).__name__}"])
        return None, report, file_sha256
    return obj, validate_archive(obj), file_sha256


def require_valid(path: str) -> tuple[dict[str, Any], ValidationReport, str]:
    obj, report, file_sha256 = load_archive(path)
    if not report.ok:
        raise BackupValidationError(report)
    return obj, report, file_sha256


# ---------------------------------------------------------------------------
# v1 upgrade
# ---------------------------------------------------------------------------

def upgrade_v1(obj: Any, *, source_project: str, created_at: datetime, source_file: str | None = None) -> dict[str, Any]:
    """Convert a pre-#50 export to v2. Lossy by nature: see LEGACY_V1_TIMESTAMP_FIELDS."""
    if not looks_like_v1(obj):
        raise codec.BackupFormatError("input is not a legacy v1 export")
    stats = Counter[str]()
    excluded = set(inventory.excluded_names())
    data = {name: _upgrade_collection(documents, (name,), stats)
            for name, documents in obj.items() if name not in excluded}
    return build_archive(
        data,
        source_project=source_project,
        source_emulator=False,
        created_at=created_at,
        completed_at=created_at,
        generator={"tool": "scripts/restore_firestore.py upgrade-v1", "git_sha": None, "run_id": None,
                   "source_file": source_file},
        unclassified=[name for name in data if inventory.policy(name) is None],
        legacy_conversion={
            "from_format_version": 1,
            "lossy": True,
            "timestamp_fields_converted": stats["converted"],
            "timestamp_fields_left_as_text": stats["left_as_text"],
            "note": "v1 stored datetimes as ISO text and other Firestore types as str(); only the "
                    "known timestamp fields listed in services/firestore_backup/archive.py were typed back.",
        },
    )


def _upgrade_collection(documents: Any, path: tuple[str, ...], stats: Counter[str]) -> dict[str, Any]:
    if not isinstance(documents, dict):
        raise codec.BackupFormatError(f"{pattern(path)}: documents must be an object")
    converted = {}
    timestamp_fields = LEGACY_V1_TIMESTAMP_FIELDS.get(pattern(path), ())
    for doc_id, node in documents.items():
        location = f"{pattern(path)}/*"
        if not valid_id(doc_id) or not isinstance(node, dict) or not isinstance(node.get("_data"), dict):
            raise codec.BackupFormatError(f"{location}: invalid v1 document")
        fields = dict(node["_data"])
        for name in timestamp_fields:
            if isinstance(fields.get(name), str):
                try:
                    parsed = datetime.fromisoformat(fields[name])
                except ValueError:
                    parsed = None
                if parsed is not None and parsed.tzinfo is not None:
                    fields[name] = parsed
                    stats["converted"] += 1
                else:
                    stats["left_as_text"] += 1
        entry: dict[str, Any] = {"exists": True, "fields": codec.encode_fields(fields, location)}
        subcollections = node.get("_subcollections") or {}
        if subcollections:
            entry["subcollections"] = {
                name: _upgrade_collection(children, path + (doc_id, name), stats)
                for name, children in subcollections.items()
            }
        converted[doc_id] = entry
    return converted
