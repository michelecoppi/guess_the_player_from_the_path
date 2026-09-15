"""Restore safety guard, existing-data semantics and dry-run, without any real Firestore (#50)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from scripts import restore_firestore
from services.firestore_backup import archive, codec, exporter, inventory, restore
from tests.backup_fakes import FakeClient

PROD = "guess-the-player-from-path-bot"
EMULATOR = {"FIRESTORE_EMULATOR_HOST": "127.0.0.1:8571"}
CREATED = datetime(2026, 9, 14, 3, 30, tzinfo=timezone.utc)


def _backup(source_project=PROD, source_emulator=False, docs=None):
    client = FakeClient(project=source_project, docs=docs or {
        "users/1": {"name": "A", "at": CREATED},
        "users/1/history/2026-09-14": {"solved": True},
        "users/2": {"name": "B"},
        "referrals/k": {"inviter_id": 1},
    })
    return exporter.export_archive(client, source_project=source_project, source_emulator=source_emulator,
                                   clock=lambda: CREATED)


# ---------------------------------------------------------------------------
# Target guard
# ---------------------------------------------------------------------------

def test_the_emulator_is_the_default_target():
    target = restore.resolve_target(project="demo-gtp", confirm_project=None, allow_production=False, environ=EMULATOR)
    assert target.is_emulator and target.project == "demo-gtp"


def test_without_the_emulator_a_real_project_is_refused_by_default():
    with pytest.raises(restore.RestoreSafetyError, match="REAL Firestore"):
        restore.resolve_target(project=PROD, confirm_project=PROD, allow_production=False, environ={})


def test_credentials_alone_never_authorise_a_real_target():
    environ = {"GOOGLE_APPLICATION_CREDENTIALS": "/secrets/key.json", "GOOGLE_CLOUD_PROJECT": PROD}
    with pytest.raises(restore.RestoreSafetyError):
        restore.resolve_target(project=PROD, confirm_project=PROD, allow_production=False, environ=environ)


def test_the_project_is_never_inferred():
    with pytest.raises(restore.RestoreSafetyError, match="--project is required"):
        restore.resolve_target(project=None, confirm_project=None, allow_production=True, environ={})


@pytest.mark.parametrize("confirm", [None, "", "guess-the-player-from-path-b0t", PROD.upper()])
def test_a_real_target_needs_the_exact_confirmation(confirm):
    with pytest.raises(restore.RestoreSafetyError, match="confirm-project"):
        restore.resolve_target(project=PROD, confirm_project=confirm, allow_production=True, environ={})


def test_a_fully_confirmed_real_target_is_allowed():
    target = restore.resolve_target(project=PROD, confirm_project=PROD, allow_production=True, environ={})
    assert not target.is_emulator and target.is_production


def test_allow_production_with_the_emulator_is_contradictory():
    with pytest.raises(restore.RestoreSafetyError, match="contradicts"):
        restore.resolve_target(project="demo-gtp", confirm_project=None, allow_production=True, environ=EMULATOR)


def test_the_emulator_may_not_reuse_the_production_project_id():
    with pytest.raises(restore.RestoreSafetyError, match="production project id"):
        restore.resolve_target(project=PROD, confirm_project=None, allow_production=False, environ=EMULATOR)


def test_an_emulator_backup_never_goes_into_a_real_project():
    target = restore.Target("staging-project", None)
    with pytest.raises(restore.RestoreSafetyError, match="emulator"):
        restore.check_source(target, _backup(source_project="demo-x", source_emulator=True))


def test_production_only_accepts_its_own_backups():
    with pytest.raises(restore.RestoreSafetyError, match="not from the production project"):
        restore.check_source(restore.Target(PROD, None), _backup(source_project="staging-project"))
    restore.check_source(restore.Target(PROD, None), _backup())


def test_the_cli_refuses_a_real_target_before_reading_the_file_or_connecting(monkeypatch, capsys):
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    monkeypatch.setattr(restore, "connect", lambda *a, **k: pytest.fail("must not connect"))
    code = restore_firestore.main(["restore", "does-not-exist.json", "--project", PROD])
    assert code == restore_firestore.EXIT_REFUSED
    assert "REAL Firestore" in capsys.readouterr().err


def test_the_cli_refuses_a_typo_in_the_confirmation(monkeypatch):
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    monkeypatch.setattr(restore, "connect", lambda *a, **k: pytest.fail("must not connect"))
    code = restore_firestore.main(["restore", "x.json", "--project", PROD, "--allow-production",
                                   "--confirm-project", PROD + "x"])
    assert code == restore_firestore.EXIT_REFUSED


def test_the_cli_refuses_an_emulator_backup_into_production_before_connecting(monkeypatch, tmp_path):
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    monkeypatch.setattr(restore, "connect", lambda *a, **k: pytest.fail("must not connect"))
    path = tmp_path / "b.json"
    path.write_text(json.dumps(_backup(source_project="demo-x", source_emulator=True)), encoding="utf-8")
    code = restore_firestore.main(["restore", str(path), "--project", PROD, "--allow-production",
                                   "--confirm-project", PROD])
    assert code == restore_firestore.EXIT_REFUSED


# ---------------------------------------------------------------------------
# Existing-data semantics and dry-run
# ---------------------------------------------------------------------------

EMULATOR_TARGET = restore.Target("demo-gtp", "127.0.0.1:8571")


def test_empty_mode_refuses_any_existing_document_and_writes_nothing():
    backup = _backup()
    target = FakeClient(docs={"referrals/other": {"x": 1}})
    with pytest.raises(restore.RestoreSafetyError, match="not empty"):
        restore.restore(target, EMULATOR_TARGET, backup)
    assert target.commits == 0 and target.docs == {("referrals", "other"): {"x": 1}}


def test_empty_mode_counts_an_orphan_subcollection_as_existing_data():
    target = FakeClient(docs={"users/9/history/2026-01-01": {"solved": True}})
    with pytest.raises(restore.RestoreSafetyError):
        restore.restore(target, EMULATOR_TARGET, _backup())


def test_dry_run_plans_without_writing():
    target = FakeClient()
    stats, verification = restore.restore(target, EMULATOR_TARGET, _backup(), dry_run=True)
    assert stats.planned == 4 and verification is None
    assert target.commits == 0 and target.docs == {}


def test_restore_recreates_ids_values_and_subcollections():
    target = FakeClient()
    stats, verification = restore.restore(target, EMULATOR_TARGET, _backup(), batch_size=2)
    assert stats.written == 4 and stats.batches == 2
    assert target.docs[("users", "1", "history", "2026-09-14")] == {"solved": True}
    assert target.docs[("users", "1")]["at"] == CREATED
    assert verification.checked == 4 and not verification.failures("empty")


def test_missing_only_skips_existing_documents_and_keeps_them():
    target = FakeClient(docs={"users/1": {"name": "changed"}})
    stats, verification = restore.restore(target, EMULATOR_TARGET, _backup(), mode="missing-only")
    assert stats.skipped_existing == 1 and stats.written == 3
    assert target.docs[("users", "1")] == {"name": "changed"}
    assert verification.different == {"users": 1} and not verification.failures("missing-only")


def test_overwrite_replaces_documents_and_never_deletes_extras():
    target = FakeClient(docs={"users/1": {"name": "changed"}, "users/3": {"name": "new"}})
    stats, verification = restore.restore(target, EMULATOR_TARGET, _backup(), mode="overwrite")
    assert stats.written == 4
    assert target.docs[("users", "1")]["name"] == "A" and ("users", "3") in target.docs
    assert verification.extra == {"users": 1} and not verification.failures("overwrite")


def test_a_create_collision_during_the_restore_is_reported_not_overwritten(monkeypatch):
    target = FakeClient()
    original_plan = restore.plan

    def plan_then_race(client, backup, mode):
        planned = original_plan(client, backup, mode)
        client.docs[("users", "2")] = {"name": "raced in"}
        return planned

    monkeypatch.setattr(restore, "plan", plan_then_race)
    with pytest.raises(restore.RestoreError, match="missing-only"):
        restore.restore(target, EMULATOR_TARGET, _backup(), batch_size=10)
    assert target.docs[("users", "2")] == {"name": "raced in"}


def test_verification_failure_is_an_error(monkeypatch):
    target = FakeClient()
    original_apply = restore.apply

    def lossy_apply(client, documents, stats, **kwargs):
        result = original_apply(client, documents, stats, **kwargs)
        client.docs[("users", "2")] = {"name": "tampered"}
        return result

    monkeypatch.setattr(restore, "apply", lossy_apply)
    with pytest.raises(restore.RestoreError, match="verification failed"):
        restore.restore(target, EMULATOR_TARGET, _backup())


def test_real_targets_log_a_warning_but_no_contents(caplog):
    target = FakeClient(project=PROD)
    backup = _backup(docs={"users/1": {"name": "Very Private Name"}})
    restore.restore(target, restore.Target(PROD, None), backup)
    text = caplog.text
    assert "backup.restore.real_target" in text and "Very Private Name" not in text


def test_batches_are_capped_by_count_and_by_size():
    small = [(("users", str(n)), {"exists": True, "fields": {"n": n}}) for n in range(5)]
    assert [len(chunk) for chunk in restore.batches(small, 2)] == [2, 2, 1]
    large = [(("events", str(n)), {"exists": True, "fields": {"blob": "x" * 1000}}) for n in range(5)]
    assert [len(chunk) for chunk in restore.batches(large, 250, max_bytes=2500)] == [2, 2, 1]
    assert sum(map(len, restore.batches(large, 250, max_bytes=10))) == 5  # one oversized doc still goes alone


def test_missing_parent_documents_are_not_invented():
    backup = _backup(docs={"events/gone/participants/1": {"points": 1}})
    target = FakeClient()
    restore.restore(target, EMULATOR_TARGET, backup)
    assert list(target.docs) == [("events", "gone", "participants", "1")]


def test_validate_command_reports_metadata_and_counts_only(tmp_path, capsys):
    backup = _backup(docs={"users/1": {"name": "Very Private Name"}})
    path = tmp_path / "b.json"
    path.write_text(json.dumps(backup), encoding="utf-8")
    assert restore_firestore.main(["validate", str(path), "--expect-source-project", PROD]) == 0
    out = capsys.readouterr().out
    assert "VALID" in out and '"users": 1' in out and "Very Private Name" not in out
    assert restore_firestore.main(["validate", str(path), "--expect-source-project", "other"]) == 1


def test_validate_strict_fails_on_warnings(tmp_path):
    data = {name: {} for name in inventory.backed_up_names() if name != "referrals"}
    backup = archive.build_archive(data, source_project=PROD, source_emulator=False, created_at=CREATED,
                                   completed_at=CREATED + timedelta(seconds=1), generator={"tool": "t"})
    path = tmp_path / "partial.json"
    path.write_text(json.dumps(backup), encoding="utf-8")
    assert restore_firestore.main(["validate", str(path)]) == 0
    assert restore_firestore.main(["validate", str(path), "--strict"]) == 1


def test_upgrade_v1_command_writes_a_valid_v2_file_and_never_overwrites(tmp_path):
    legacy = tmp_path / "firestore-20260914-033000.json"
    legacy.write_text(json.dumps({"users": {"1": {"_data": {"date_created": "2026-01-01T00:00:00+00:00"}}}}),
                      encoding="utf-8")
    out = tmp_path / "v2.json"
    args = ["upgrade-v1", str(legacy), str(out), "--source-project", PROD, "--created-at", "2026-09-14T03:30:00Z"]
    assert restore_firestore.main(args) == 0
    obj, report, _ = archive.load_archive(str(out))
    assert report.ok and codec.decode_value(obj["data"]["users"]["1"]["fields"])["date_created"].year == 2026
    assert restore_firestore.main(args) == restore_firestore.EXIT_REFUSED
