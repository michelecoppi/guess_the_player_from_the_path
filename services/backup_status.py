"""Backup visibility for the admin dashboard (#38).

The weekly Firestore backup (`.github/workflows/backup.yml`) uploads its file as a GitHub
Actions artifact - it never lands anywhere this process (or any Cloud Run instance) can
read. The only backups this module can see are files a maintainer produced **on this
machine** with `scripts/backup_firestore.py`, typically before a risky manual operation.

This is deliberately not a reimplementation of backup/recovery logic (that stays in
`services/firestore_backup/`, per #20): it only reads what `archive.py` already knows how
to validate and summarize, plus the two links an admin actually needs to see the rest -
the weekly run history and the restore drill - without building a GitHub API client for a
status that already has a UI of its own.
"""
import glob
import os

from services.firestore_backup import archive

BACKUP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backup")

BACKUP_WORKFLOW_URL = "https://github.com/michelecoppi/guess_the_player_from_the_path/actions/workflows/backup.yml"
RESTORE_VERIFICATION_WORKFLOW_URL = (
    "https://github.com/michelecoppi/guess_the_player_from_the_path/actions/workflows/restore-verification.yml"
)


def list_local_backups():
    """Ogni `firestore-*.json` in backup/, dal più recente, con solo metadati (mai
    contenuto dei documenti): formato, completezza, conteggi per collezione e qualità di
    ripristino, così come li calcola già `services/firestore_backup/archive.py`."""
    paths = sorted(
        glob.glob(os.path.join(BACKUP_DIR, "firestore-*.json")),
        key=os.path.getmtime,
        reverse=True,
    )
    rows = []
    for path in paths:
        row = {"file": os.path.basename(path), "modified_at": os.path.getmtime(path)}
        obj, report, _ = archive.load_archive(path)
        row["valid"] = report.ok
        row["issues"] = list(report.errors) + list(report.warnings)
        if obj:
            row.update(archive.summary(obj))
            if report.ok:
                quality, quality_issues = archive.restore_quality(obj)
                row["quality"] = quality
                row["quality_issues"] = quality_issues
        rows.append(row)
    return rows
