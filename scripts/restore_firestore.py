"""Validate, restore and verify Firestore backups. Safe by default: see docs/backup-recovery.md.

    # Only reads the file: structure, version, counts, digest, every value.
    python scripts/restore_firestore.py validate backup/firestore-....json [--strict]

    # Into the emulator (default and only target without extra flags). Mode `empty` refuses a
    # non-empty target; --dry-run reads the target and writes nothing.
    FIRESTORE_EMULATOR_HOST=127.0.0.1:8571 \
        python scripts/restore_firestore.py restore FILE --project demo-gtp-restore [--dry-run]

    # Real project: all guards are required, and nothing is ever deleted.
    python scripts/restore_firestore.py restore FILE --project P --allow-production \
        --confirm-project P [--mode empty|missing-only|overwrite] [--dry-run]

    # Read-only comparison of a target with a backup.
    python scripts/restore_firestore.py verify FILE --project P [--allow-production]

    # Convert a pre-#50 (v1, untyped) export into v2 so it can be validated and restored.
    python scripts/restore_firestore.py upgrade-v1 OLD.json NEW.json --source-project P --created-at 2026-09-14T03:30:00Z

Output is metadata and per-collection counts only; document ids and values are never printed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import observability  # noqa: E402
from services.firestore_backup import archive, codec, restore  # noqa: E402

EXIT_OK, EXIT_INVALID, EXIT_REFUSED, EXIT_FAILED = 0, 1, 2, 3


def _print_report(report: archive.ValidationReport, file_sha256: str | None = None) -> None:
    meta = dict(report.summary)
    if file_sha256:
        meta["file_sha256"] = file_sha256
    if meta:
        print(json.dumps(meta, indent=1, sort_keys=True))
    for warning in report.warnings:
        print(f"WARNING: {warning}")
    for error in report.errors:
        print(f"ERROR: {error}", file=sys.stderr)


def cmd_validate(args: argparse.Namespace) -> int:
    obj, report, file_sha256 = archive.load_archive(args.file)
    _print_report(report, file_sha256)
    if report.ok and args.expect_source_project and obj["source_project"] != args.expect_source_project:
        report.errors.append(f"source_project is {obj['source_project']!r}, expected {args.expect_source_project!r}")
        print(f"ERROR: {report.errors[-1]}", file=sys.stderr)
    observability.log_event("backup.validate.completed", component="backup", valid=report.ok,
                            errors=len(report.errors), warnings=len(report.warnings))
    if not report.ok:
        print("INVALID backup: do not use it.", file=sys.stderr)
        return EXIT_INVALID
    if args.strict and report.warnings:
        print("Valid, but --strict fails on warnings.", file=sys.stderr)
        return EXIT_INVALID
    print("VALID backup.")
    return EXIT_OK


def _target(args: argparse.Namespace, *, read_only: bool) -> restore.Target:
    return restore.resolve_target(project=args.project, confirm_project=getattr(args, "confirm_project", None),
                                  allow_production=args.allow_production, read_only=read_only)


def cmd_restore(args: argparse.Namespace) -> int:
    try:
        target = _target(args, read_only=False)
    except restore.RestoreSafetyError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    try:
        backup, report, file_sha256 = archive.require_valid(args.file)
    except archive.BackupValidationError as exc:
        _print_report(exc.report)
        print("INVALID backup: nothing was restored.", file=sys.stderr)
        return EXIT_INVALID
    _print_report(report, file_sha256)
    print(f"Target: {target.describe()} | mode: {args.mode} | dry-run: {args.dry_run}")
    if not target.is_emulator:
        print(f"WARNING: writing to a REAL Firestore project ({target.project}). Nothing will be deleted.")
    try:
        restore.check_source(target, backup)
        client = restore.connect(target, args.credentials)
        stats, verification = restore.restore(client, target, backup, mode=args.mode, dry_run=args.dry_run)
    except restore.RestoreSafetyError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    except restore.RestoreError as exc:
        print(f"RESTORE FAILED: {exc}", file=sys.stderr)
        print(json.dumps({"planned": exc.stats.planned, "written": exc.stats.written,
                          "batches_committed": exc.stats.batches}, indent=1), file=sys.stderr)
        print("See docs/backup-recovery.md § 8.6 (partial failures) before retrying.", file=sys.stderr)
        return EXIT_FAILED
    result = {"mode": stats.mode, "planned": stats.planned, "skipped_existing": stats.skipped_existing,
              "written": stats.written, "by_collection": stats.by_collection}
    if verification is not None:
        result["verified_documents"] = verification.checked
        result["kept_existing_different"] = verification.different
        result["extra_in_target"] = verification.extra
    print(json.dumps(result, indent=1, sort_keys=True))
    print("DRY RUN: nothing was written." if args.dry_run else "RESTORE COMPLETED AND VERIFIED.")
    return EXIT_OK


def cmd_verify(args: argparse.Namespace) -> int:
    try:
        target = _target(args, read_only=True)
        backup, _, _ = archive.require_valid(args.file)
        client = restore.connect(target, args.credentials)
    except restore.RestoreSafetyError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    except archive.BackupValidationError as exc:
        _print_report(exc.report)
        return EXIT_INVALID
    report = restore.verify(client, backup)
    print(json.dumps({"checked": report.checked, "missing": report.missing, "different": report.different,
                      "extra": report.extra}, indent=1, sort_keys=True))
    problems = report.failures(args.mode)
    observability.log_event("backup.verify.completed", component="backup", target_project=target.project,
                            checked=report.checked, problems=len(problems))
    for problem in problems:
        print(f"MISMATCH: {problem}", file=sys.stderr)
    return EXIT_FAILED if problems else EXIT_OK


def cmd_upgrade_v1(args: argparse.Namespace) -> int:
    try:
        created_at = datetime.fromisoformat(args.created_at.replace("Z", "+00:00"))
        if created_at.tzinfo is None:
            raise ValueError("timezone required")
    except ValueError:
        print("--created-at must be an ISO timestamp with timezone, e.g. 2026-09-14T03:30:00Z", file=sys.stderr)
        return EXIT_INVALID
    if os.path.exists(args.output):
        print(f"{args.output} already exists: refusing to overwrite", file=sys.stderr)
        return EXIT_REFUSED
    with open(args.input, encoding="utf-8") as handle:
        try:
            legacy = codec.loads(handle.read())
            upgraded = archive.upgrade_v1(legacy, source_project=args.source_project,
                                          created_at=created_at.astimezone(timezone.utc),
                                          source_file=os.path.basename(args.input))
        except ValueError as exc:
            print(f"cannot upgrade: {exc}", file=sys.stderr)
            return EXIT_INVALID
    report = archive.validate_archive(upgraded)
    if not report.ok:
        _print_report(report)
        return EXIT_INVALID
    with open(args.output, "x", encoding="utf-8") as handle:
        json.dump(upgraded, handle, ensure_ascii=False, indent=1, sort_keys=True, allow_nan=False)
    _print_report(report)
    print(f"Wrote {args.output}")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate, restore and verify Firestore backups")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="validate a backup file without restoring it")
    validate.add_argument("file")
    validate.add_argument("--strict", action="store_true", help="fail on warnings too")
    validate.add_argument("--expect-source-project", help="fail unless the backup comes from this project")
    validate.set_defaults(func=cmd_validate)

    def target_args(command: argparse.ArgumentParser) -> None:
        command.add_argument("file")
        command.add_argument("--project", required=True, help="target project id (never inferred)")
        command.add_argument("--allow-production", action="store_true",
                             help="allow a real (non-emulator) Firestore project")
        command.add_argument("--credentials", help="service account JSON for a real project (default: ADC)")
        command.add_argument("--mode", choices=restore.MODES, default="empty")

    restore_cmd = sub.add_parser("restore", help="restore a backup (emulator by default)")
    target_args(restore_cmd)
    restore_cmd.add_argument("--confirm-project", help="repeat --project to confirm a real target")
    restore_cmd.add_argument("--dry-run", action="store_true", help="validate and plan; write nothing")
    restore_cmd.set_defaults(func=cmd_restore)

    verify_cmd = sub.add_parser("verify", help="compare a target with a backup (read-only)")
    target_args(verify_cmd)
    verify_cmd.set_defaults(func=cmd_verify)

    upgrade = sub.add_parser("upgrade-v1", help="convert a legacy v1 export to format v2")
    upgrade.add_argument("input")
    upgrade.add_argument("output")
    upgrade.add_argument("--source-project", required=True)
    upgrade.add_argument("--created-at", required=True, help="when the v1 export was taken (ISO, with timezone)")
    upgrade.set_defaults(func=cmd_upgrade_v1)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    observability.init("backup")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
