"""Read Firestore into a v2 archive.

Documents are discovered with `list_documents()` (which also returns parent paths that have
no document but do have subcollections) and read in chunks with `get_all()`. The previous
exporter streamed collections, so a subcollection under a deleted parent was silently
skipped.

The export is not a point-in-time snapshot: collections are read one after another, so a
write that lands during the few seconds of an export can be seen in one collection and not
in a related one (for example `leagues.members_count` vs the `members` subcollection). The
emulator does not honour `read_time`, so a consistent read could not be verified by the
round-trip test and is deliberately not used.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Callable, Iterable

from services import observability
from services.firestore_backup import archive, codec, inventory

GET_ALL_CHUNK = 200


class ExportError(RuntimeError):
    pass


def _chunks(items: list[Any], size: int) -> Iterable[list[Any]]:
    for start in range(0, len(items), size):
        yield items[start:start + size]


def export_collection(client: Any, collection_ref: Any, path: tuple[str, ...]) -> dict[str, Any]:
    references = list(collection_ref.list_documents())
    snapshots: dict[str, Any] = {}
    for chunk in _chunks(references, GET_ALL_CHUNK):
        for snapshot in client.get_all(chunk):
            snapshots[snapshot.reference.path] = snapshot

    documents: dict[str, Any] = {}
    for reference in references:
        doc_path = path + (reference.id,)
        location = archive.pattern(doc_path)
        snapshot = snapshots.get(reference.path)
        node: dict[str, Any] = {"exists": bool(snapshot is not None and snapshot.exists)}
        if node["exists"]:
            node["fields"] = codec.encode_fields(snapshot.to_dict() or {}, location)
        subcollections = {}
        for subcollection in reference.collections():
            children = export_collection(client, subcollection, doc_path + (subcollection.id,))
            if children:
                subcollections[subcollection.id] = children
        if subcollections:
            node["subcollections"] = subcollections
        if node["exists"] or subcollections:
            documents[reference.id] = node
    return documents


def resolve_collections(present: Iterable[str], requested: Iterable[str] | None) -> tuple[list[str], list[str]]:
    """(collections to export, unclassified collections present in the database).

    Default: everything the inventory backs up, plus any collection nobody classified yet -
    unknown data is exported (and flagged) rather than lost. An explicit subset may only name
    collections the inventory backs up."""
    present = set(present)
    known = set(inventory.all_names())
    unclassified = sorted(present - known)
    if requested is None:
        return sorted(set(inventory.backed_up_names()) | set(unclassified)), unclassified
    requested = list(dict.fromkeys(requested))
    refused = [name for name in requested if name not in inventory.backed_up_names()]
    if refused:
        raise ExportError(f"not backed-up collections per the inventory: {refused}")
    return sorted(requested), unclassified


def export_archive(
    client: Any,
    *,
    source_project: str,
    source_emulator: bool,
    requested: Iterable[str] | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> dict[str, Any]:
    created_at = clock()
    present = [collection.id for collection in client.collections()]
    collections, unclassified = resolve_collections(present, requested)
    with observability.operation("backup.export", component="backup", source_project=source_project,
                                 source_emulator=source_emulator) as op:
        data = {}
        for name in collections:
            documents = export_collection(client, client.collection(name), (name,))
            data[name] = documents
            observability.log_event("backup.export.collection", component="backup", collection=name,
                                    documents=len(documents))
        for name in unclassified:
            observability.log_event("backup.export.unclassified_collection", 30, component="backup",
                                    collection=name)
        result = archive.build_archive(
            data,
            source_project=source_project,
            source_emulator=source_emulator,
            created_at=created_at,
            completed_at=max(clock(), created_at),
            generator={"tool": "scripts/backup_firestore.py", "git_sha": os.environ.get("GITHUB_SHA"),
                       "run_id": os.environ.get("GITHUB_RUN_ID")},
            unclassified=unclassified,
        )
        report = archive.validate_archive(result)
        if not report.ok:
            raise archive.BackupValidationError(report)
        op.update(collections=len(collections), total_documents=result["total_documents"],
                  complete=result["complete"], unclassified=len(unclassified))
    return result
