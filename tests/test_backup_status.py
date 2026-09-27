import json
from datetime import datetime, timedelta, timezone

from services import backup_status
from services.firestore_backup import archive, inventory

UTC = timezone.utc
CREATED = datetime(2026, 9, 14, 3, 30, tzinfo=UTC)


def _write_archive(path, **overrides):
    data = {name: {} for name in inventory.backed_up_names()}
    built = archive.build_archive(
        data, source_project="guess-the-player-from-path-bot", source_emulator=False,
        created_at=CREATED, completed_at=CREATED + timedelta(seconds=5), generator={"tool": "test"},
    )
    built.update(overrides)
    path.write_text(json.dumps(built), encoding="utf-8")
    return built


def test_no_local_backups_is_an_empty_list(tmp_path, monkeypatch):
    monkeypatch.setattr(backup_status, "BACKUP_DIR", str(tmp_path))

    assert backup_status.list_local_backups() == []


def test_only_firestore_prefixed_files_are_listed(tmp_path, monkeypatch):
    monkeypatch.setattr(backup_status, "BACKUP_DIR", str(tmp_path))
    _write_archive(tmp_path / "firestore-guess-the-player-from-path-bot-20260914T033000Z.json")
    (tmp_path / "players-20260914-090000.json").write_text("{}", encoding="utf-8")

    rows = backup_status.list_local_backups()

    assert [row["file"] for row in rows] == ["firestore-guess-the-player-from-path-bot-20260914T033000Z.json"]


def test_a_valid_complete_backup_is_disaster_recovery_quality(tmp_path, monkeypatch):
    monkeypatch.setattr(backup_status, "BACKUP_DIR", str(tmp_path))
    _write_archive(tmp_path / "firestore-a.json")

    row = backup_status.list_local_backups()[0]

    assert row["valid"] is True
    assert row["complete"] is True
    assert row["quality"] == archive.QUALITY_DISASTER_RECOVERY
    assert row["quality_issues"] == []


def test_an_incomplete_backup_is_exceptional_quality_with_a_reason(tmp_path, monkeypatch):
    monkeypatch.setattr(backup_status, "BACKUP_DIR", str(tmp_path))
    incomplete_data = {name: {} for name in inventory.backed_up_names()}
    incomplete_data.pop(next(iter(incomplete_data)))  # una collezione backed-up manca davvero
    built = archive.build_archive(
        incomplete_data, source_project="guess-the-player-from-path-bot", source_emulator=False,
        created_at=CREATED, completed_at=CREATED + timedelta(seconds=5), generator={"tool": "test"},
    )
    (tmp_path / "firestore-b.json").write_text(json.dumps(built), encoding="utf-8")

    row = backup_status.list_local_backups()[0]

    assert row["valid"] is True
    assert row["complete"] is False
    assert row["quality"] == archive.QUALITY_EXCEPTIONAL
    assert any("not complete" in issue for issue in row["quality_issues"])


def test_a_corrupt_file_is_reported_as_invalid_with_its_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(backup_status, "BACKUP_DIR", str(tmp_path))
    (tmp_path / "firestore-broken.json").write_text('{"format": "not-a-real-format"}', encoding="utf-8")

    row = backup_status.list_local_backups()[0]

    assert row["valid"] is False
    assert row["issues"]
    assert "quality" not in row
