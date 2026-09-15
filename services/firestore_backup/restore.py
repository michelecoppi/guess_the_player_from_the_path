"""Restore a validated v2 archive into Firestore - safe by default.

Target safety (`resolve_target`):

- With `FIRESTORE_EMULATOR_HOST` set, the target is the emulator. A project id is required
  and it may not be a known production project id, so a command copied from an emulator
  rehearsal cannot become a production restore by unsetting one variable.
- Without it the target is a real Firestore project and **every** one of these is required:
  `--allow-production`, `--project`, `--confirm-project` repeating the same id; the backup
  must not come from an emulator; restoring into a known production project requires the
  backup's `source_project` to be that project. Credentials never count as permission.

Existing-data semantics (`MODES`):

- `empty` (default): refuse unless every restored collection is empty in the target, then
  write with `create()`, so even a race or an orphan subcollection fails instead of
  overwriting.
- `missing-only`: create documents that do not exist and leave existing documents untouched.
  Also the way to resume a restore interrupted half-way.
- `overwrite`: replace every document present in the backup. Documents that exist only in
  the target are never deleted.

Nothing here ever deletes data. After writing, the target is re-exported with the same
exporter and compared with the backup (`verify`).
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from google.api_core.exceptions import AlreadyExists

from services import observability
from services.firestore_backup import archive, codec, exporter

PRODUCTION_PROJECT_IDS = frozenset({"guess-the-player-from-path-bot"})
MODES = ("empty", "missing-only", "overwrite")
BATCH_SIZE = 250
MAX_BATCH_BYTES = 4_000_000
EMULATOR_ENV = "FIRESTORE_EMULATOR_HOST"


class RestoreSafetyError(RuntimeError):
    """The requested target is not allowed. Nothing has been read or written."""


class RestoreError(RuntimeError):
    def __init__(self, message: str, stats: "RestoreStats"):
        super().__init__(message)
        self.stats = stats


@dataclass(frozen=True)
class Target:
    project: str
    emulator_host: str | None

    @property
    def is_emulator(self) -> bool:
        return self.emulator_host is not None

    @property
    def is_production(self) -> bool:
        return self.project in PRODUCTION_PROJECT_IDS

    def describe(self) -> str:
        return f"emulator {self.emulator_host} project {self.project}" if self.is_emulator else f"REAL Firestore project {self.project}"


@dataclass
class RestoreStats:
    mode: str
    planned: int = 0
    written: int = 0
    skipped_existing: int = 0
    batches: int = 0
    by_collection: dict[str, int] = field(default_factory=dict)


@dataclass
class VerifyReport:
    checked: int = 0
    missing: dict[str, int] = field(default_factory=dict)
    different: dict[str, int] = field(default_factory=dict)
    extra: dict[str, int] = field(default_factory=dict)

    def failures(self, mode: str) -> list[str]:
        problems = []
        if self.missing:
            problems.append(f"documents missing in target: {self.missing}")
        if self.different and mode != "missing-only":
            problems.append(f"documents different from the backup: {self.different}")
        if self.extra and mode == "empty":
            problems.append(f"documents in target that are not in the backup: {self.extra}")
        return problems


def resolve_target(
    *,
    project: str | None,
    confirm_project: str | None,
    allow_production: bool,
    environ: Mapping[str, str] | None = None,
    read_only: bool = False,
) -> Target:
    environ = os.environ if environ is None else environ
    emulator_host = (environ.get(EMULATOR_ENV) or "").strip() or None
    if not project:
        raise RestoreSafetyError("--project is required: the target is never inferred from credentials or environment")
    if emulator_host:
        if allow_production:
            raise RestoreSafetyError(f"--allow-production contradicts {EMULATOR_ENV}={emulator_host}; unset one of them")
        if project in PRODUCTION_PROJECT_IDS:
            raise RestoreSafetyError(
                f"the emulator target uses the production project id {project!r}; use a demo- project id "
                "so this command can never point at production")
        return Target(project, emulator_host)
    if not allow_production:
        raise RestoreSafetyError(
            f"{EMULATOR_ENV} is not set, so the target would be the REAL Firestore project {project!r}. "
            "Restores go to the emulator by default; a real project needs --allow-production and "
            "--confirm-project (see docs/backup-recovery.md)")
    if not read_only and confirm_project != project:
        raise RestoreSafetyError("--confirm-project must repeat exactly the --project id of a real target")
    return Target(project, None)


def check_source(target: Target, backup: Mapping[str, Any]) -> None:
    if target.is_emulator:
        return
    if backup["source_emulator"]:
        raise RestoreSafetyError("refusing to restore a backup taken from an emulator into a real project")
    if target.is_production and backup["source_project"] != target.project:
        raise RestoreSafetyError(
            f"backup comes from {backup['source_project']!r}, not from the production project {target.project!r}")


def connect(target: Target, credentials_path: str | None = None) -> Any:
    from google.cloud import firestore

    if target.is_emulator:
        if os.environ.get(EMULATOR_ENV) != target.emulator_host:
            raise RestoreSafetyError(f"{EMULATOR_ENV} changed after the target was resolved")
        client = firestore.Client(project=target.project)
    elif credentials_path:
        client = firestore.Client.from_service_account_json(credentials_path, project=target.project)
    else:
        client = firestore.Client(project=target.project)
    if client.project != target.project:
        raise RestoreSafetyError(f"client resolved project {client.project!r}, expected {target.project!r}")
    return client


# ---------------------------------------------------------------------------
# Planning and writing
# ---------------------------------------------------------------------------

def non_empty_collections(client: Any, backup: Mapping[str, Any]) -> list[str]:
    busy = []
    for name in backup["collections"]:
        if next(iter(client.collection(name).list_documents(page_size=1)), None) is not None:
            busy.append(name)
    return busy


def _document_ref(client: Any, path: tuple[str, ...]) -> Any:
    return client.document(*path)


def _existing_paths(client: Any, paths: list[tuple[str, ...]]) -> set[tuple[str, ...]]:
    existing = set()
    for start in range(0, len(paths), exporter.GET_ALL_CHUNK):
        chunk = paths[start:start + exporter.GET_ALL_CHUNK]
        by_ref_path = {"/".join(path): path for path in chunk}
        for snapshot in client.get_all([_document_ref(client, path) for path in chunk]):
            if snapshot.exists:
                existing.add(by_ref_path[snapshot.reference.path])
    return existing


def plan(client: Any, backup: Mapping[str, Any], mode: str) -> tuple[list[tuple[tuple[str, ...], dict[str, Any]]], RestoreStats]:
    """Documents to write, after checking the target against the mode. Reads only."""
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}")
    stats = RestoreStats(mode=mode)
    documents = [(path, node) for path, node in archive.iter_nodes(backup["data"]) if node["exists"]]
    if mode == "empty":
        busy = non_empty_collections(client, backup)
        if busy:
            raise RestoreSafetyError(
                f"target is not empty for {busy}; mode 'empty' never writes over existing data. "
                "Use an empty target, or choose --mode missing-only / overwrite explicitly")
    if mode == "missing-only":
        existing = _existing_paths(client, [path for path, _ in documents])
        stats.skipped_existing = len(existing)
        documents = [(path, node) for path, node in documents if path not in existing]
    stats.planned = len(documents)
    for path, _ in documents:
        key = archive.pattern(path[:-1])
        stats.by_collection[key] = stats.by_collection.get(key, 0) + 1
    return documents, stats


def batches(documents: list[tuple[tuple[str, ...], dict[str, Any]]], batch_size: int,
            max_bytes: int = MAX_BATCH_BYTES) -> list[list[tuple[tuple[str, ...], dict[str, Any]]]]:
    """At most `batch_size` documents and roughly `max_bytes` of data per commit: Firestore caps
    a commit at 500 writes and 10 MiB, and an event or duel document can be tens of KB."""
    chunks: list[list[tuple[tuple[str, ...], dict[str, Any]]]] = []
    current: list[tuple[tuple[str, ...], dict[str, Any]]] = []
    size = 0
    for path, node in documents:
        weight = len(codec.canonical_json(node["fields"]).encode("utf-8")) + 200
        if current and (len(current) >= batch_size or size + weight > max_bytes):
            chunks.append(current)
            current, size = [], 0
        current.append((path, node))
        size += weight
    if current:
        chunks.append(current)
    return chunks


def apply(
    client: Any,
    documents: list[tuple[tuple[str, ...], dict[str, Any]]],
    stats: RestoreStats,
    *,
    batch_size: int = BATCH_SIZE,
    on_batch: Callable[[RestoreStats], None] | None = None,
) -> RestoreStats:
    for chunk in batches(documents, batch_size):
        batch = client.batch()
        for path, node in chunk:
            fields = codec.decode_fields(node["fields"], archive.pattern(path))
            reference = _document_ref(client, path)
            if stats.mode == "overwrite":
                batch.set(reference, fields)
            else:
                batch.create(reference, fields)
        try:
            batch.commit()
        except AlreadyExists as exc:
            raise RestoreError(
                "a document appeared in the target during the restore (batch aborted atomically); "
                "re-run with --mode missing-only to resume without overwriting", stats) from exc
        except Exception as exc:
            raise RestoreError(f"batch {stats.batches + 1} failed: {type(exc).__name__}", stats) from exc
        stats.batches += 1
        stats.written += len(chunk)
        if on_batch:
            on_batch(stats)
    return stats


def verify(client: Any, backup: Mapping[str, Any]) -> VerifyReport:
    """Re-export the restored collections with the backup exporter and compare, type-strict."""
    report = VerifyReport()
    actual = {name: exporter.export_collection(client, client.collection(name), (name,))
              for name in backup["collections"]}
    expected_nodes = {path: node for path, node in archive.iter_nodes(backup["data"]) if node["exists"]}
    actual_nodes = {path: node for path, node in archive.iter_nodes(actual) if node["exists"]}
    for path, node in expected_nodes.items():
        key = archive.pattern(path[:-1])
        report.checked += 1
        found = actual_nodes.get(path)
        if found is None:
            report.missing[key] = report.missing.get(key, 0) + 1
        elif codec.canonical_json(found["fields"]) != codec.canonical_json(node["fields"]):
            report.different[key] = report.different.get(key, 0) + 1
    for path in actual_nodes.keys() - expected_nodes.keys():
        key = archive.pattern(path[:-1])
        report.extra[key] = report.extra.get(key, 0) + 1
    return report


def restore(
    client: Any,
    target: Target,
    backup: Mapping[str, Any],
    *,
    mode: str = "empty",
    dry_run: bool = False,
    batch_size: int = BATCH_SIZE,
) -> tuple[RestoreStats, VerifyReport | None]:
    check_source(target, backup)
    with observability.operation("backup.restore", component="backup", target_project=target.project,
                                 target_emulator=target.is_emulator, mode=mode, dry_run=dry_run,
                                 source_project=backup["source_project"],
                                 backup_created_at=backup["created_at"]) as op:
        documents, stats = plan(client, backup, mode)
        op.update(planned=stats.planned, skipped_existing=stats.skipped_existing)
        if dry_run:
            return stats, None
        if not target.is_emulator:
            observability.log_event("backup.restore.real_target", logging.WARNING, component="backup",
                                    target_project=target.project, mode=mode, planned=stats.planned)
        try:
            apply(client, documents, stats, batch_size=batch_size)
        finally:
            op.update(written=stats.written, batches=stats.batches)
        report = verify(client, backup)
        problems = report.failures(mode)
        op.update(verified=report.checked, missing=sum(report.missing.values()),
                  different=sum(report.different.values()), extra=sum(report.extra.values()))
        if problems:
            raise RestoreError("verification failed: " + "; ".join(problems), stats)
        return stats, report
