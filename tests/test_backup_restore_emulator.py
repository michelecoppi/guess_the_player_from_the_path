"""Backup -> restore -> compare, on a REAL Firestore (the emulator). Issue #50.

This is the restore test that makes "we have a backup" mean something: it runs the same
entry points an operator runs (`scripts/backup_firestore.py`, `scripts/restore_firestore.py`)
and therefore the same serializer/deserializer, against two isolated emulator projects, and
compares what comes back with what was written - type by type, not through the codec.

The fixture is synthetic but shaped like production: every backed-up collection, the nested
subcollections the game uses, `SERVER_TIMESTAMP`/`Increment`/`ArrayUnion` writes, timezone
aware datetimes, floats that are whole numbers, int64-sized ids, a map key named `$type`, and a
subcollection under a parent document that does not exist.

The scheduled workflow `.github/workflows/restore-verification.yml` repeats this file weekly;
CI runs it on every push. Locally it skips without FIRESTORE_EMULATOR_HOST, in CI it fails.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone

import pytest
from google.cloud import firestore
from google.cloud.firestore_v1 import GeoPoint
from google.cloud.firestore_v1.batch import WriteBatch

from scripts import backup_firestore, restore_firestore
from services.firestore_backup import archive, inventory, restore

SOURCE = "demo-gtp-backup-source"
TARGET = "demo-gtp-restore-target"
# Same shapes as production ids: a SHA-256 hex referral key and a 24-hex-char duel code.
REFERRAL_KEY = hashlib.sha256(b"synthetic-referral").hexdigest()
DUEL_CODE = hashlib.sha256(b"synthetic-duel").hexdigest()[:24]


@pytest.fixture
def emulator():
    host = os.environ.get("FIRESTORE_EMULATOR_HOST")
    if not host:
        if os.environ.get("CI"):
            pytest.fail("FIRESTORE_EMULATOR_HOST non impostata: in CI l'emulatore deve esserci")
        pytest.skip("FIRESTORE_EMULATOR_HOST non impostata: emulatore Firestore non disponibile")
    clients = firestore.Client(project=SOURCE), firestore.Client(project=TARGET)
    for client in clients:
        _wipe(client, host)
    yield clients
    for client in clients:
        _wipe(client, host)


def _wipe(client, host):
    import urllib.request

    url = f"http://{host}/emulator/v1/projects/{client.project}/databases/(default)/documents"
    urllib.request.urlopen(urllib.request.Request(url, method="DELETE"), timeout=10).close()


def seed(db):
    stamp = datetime(2026, 9, 14, 21, 45, 12, 345678, tzinfo=timezone.utc)
    user = db.collection("users").document("1001")
    user.set({
        "telegram_id": 1001, "first_name": "Ånna ⚽", "language": "it", "chat_id": 1001,
        "points_totali": 120, "monthly_points": 0, "notifications_enabled": True,
        "last_played_day": "2026-09-14", "archive_day": None, "trophies": ["MON_August_2_2026_1"],
        "solved_in": {"2": 3}, "monthly_earned": {"2026-09": 15},
        "cosmetics": {"owned": ["frame_gold"], "earned": [], "equipped": {"frame": "frame_gold"}},
        "leagues": ["LEGA01"], "app_duel": DUEL_CODE,
        "app_duel_record": {"1002": {"name": "Bruno", "wins": 1, "ended_at": "2026-09-10T10:00:00+00:00"}},
        "shop_checkout": {"item": "frame_gold", "expires": 1757890000.25},
        "ratio": 1.0, "big_id": 2**53 + 1, "negative": -7, "empty_list": [], "empty_map": {},
        "date_created": firestore.SERVER_TIMESTAMP,
    })
    user.update({"points_totali": firestore.Increment(5), "trophies": firestore.ArrayUnion(["EVT_x"])})
    user.collection("history").document("2026-09-14").set({"day": "2026-09-14", "solved": True, "attempts": 2})
    user.collection("history").document("2026-09-13").set({"day": "2026-09-13", "solved": False, "attempts": 3})
    user.collection("archive").document("2026-09-01").set({"day": "2026-09-01", "solved": True, "hints": 1})
    db.collection("users").document("1002").set({"telegram_id": 1002, "first_name": "Bruno"})

    db.collection("daily_path").document("2026-09-14").set({
        "day": "2026-09-14", "player_id": "maldini", "correct_answers": ["maldini", "paolo maldini"],
        "career_path": [{"team": "Milan", "years": "1985-2009", "apps": 647}], "difficulty": "easy",
        "first_correct_user": True, "players_count": 10, "solved_count": 4,
        "generated_at": datetime(2026, 9, 14, 0, 0, 1, tzinfo=timezone(timedelta(hours=2))),
    })
    event = db.collection("events").document("giramondo")
    event.set({"name": "Giramondo", "dates": ["2026-09-14", "2026-09-15"], "active": True,
               "daily_data": {"2026-09-14": {"player_id": "kaka"}}, "generated_at": stamp})
    event.collection("participants").document("1001").set({"telegram_id": 1001, "points": 30, "attempts": {"2026-09-14": 1}})
    db.collection("seasons").document("2026-September").set({"month": "September", "year": "2026",
                                                             "season_number": 3, "created_at": firestore.SERVER_TIMESTAMP})
    league = db.collection("leagues").document("LEGA01")
    league.set({"name": "Amici", "owner_id": 1001, "members_count": 2, "created_at": firestore.SERVER_TIMESTAMP})
    league.collection("members").document("1001").set({"telegram_id": 1001, "points": 44, "joined_at": stamp})
    league.collection("members").document("1002").set({"telegram_id": 1002, "points": 0, "joined_at": firestore.SERVER_TIMESTAMP})
    group = db.collection("group_rounds").document("-1001234567890")
    group.set({"chat_id": -1001234567890, "number": 7, "key": "daily:2026-09-14", "solved_by": None,
               "correct_answers": ["totti"], "recent_keys": ["a", "b"], "started_at": firestore.SERVER_TIMESTAMP})
    group.collection("players").document("1001").set({"telegram_id": 1001, "round": 7, "attempts": 1,
                                                      "points": firestore.Increment(3), "rounds_won": 2})
    db.collection("purchases").document("stxCHARGE-123_abc").set({
        "user_id": 1001, "item_id": "frame_gold", "amount": 50, "day": "2026-09-12", "refunded": False,
        "refunded_at": None, "granted": ["frame_gold"], "created_at": firestore.SERVER_TIMESTAMP})
    db.collection("referrals").document(REFERRAL_KEY).set({
        "inviter_id": 1001, "invitee_id": 1002, "name": "Bruno", "joined_day": "2026-09-10",
        "joined_at": firestore.SERVER_TIMESTAMP, "days": ["2026-09-10", "2026-09-11"], "status": "pending",
        "qualified_at": None})
    db.collection("app_duels").document(DUEL_CODE).set({
        "code": DUEL_CODE, "members": [1001, 1002], "expires_at": stamp + timedelta(days=7),
        "challenges": [{"key": "p1", "career_path": [{"team": "Roma"}]}],
        "seats": {"1001": {"name": "Ånna", "moves": [], "revision": 0}}})
    db.collection("admin_settings").document("dataset_overrides").set({"blocked_player_ids": ["x1", "x2"]})
    db.collection("admin_settings").document("codec_edge_cases").set({
        "map_with_type_key": {"$type": "timestamp", "value": "not a timestamp, just data"},
        "list_of_maps": [{"$type": "x"}, {"n": 1.5}]})
    db.collection("father_son_pairs").document("autoPairId123").set({
        "father": "Cesare Maldini", "son": "Paolo Maldini", "file_id": "AgACAgQAAxk", "used_in_events": [],
        "created_at": stamp})
    db.collection("daily_jobs").document("2026-09-14").set({
        "reference_day": "2026-09-13", "stats": [10, 4], "monthly_result": None, "current_event": None,
        "sent_total": firestore.Increment(9)})
    db.collection("monthly_closures").document("2026-08").set({
        "closed_month": "2026-08", "new_month": "2026-09", "month_name": "August", "year": "2026",
        "winners": [{"telegram_id": 1001, "position": 1, "monthly_points": 300, "trophy_code": "MON_August_2_2026_1"}]})
    # A subcollection whose parent document does not exist (e.g. an event deleted by hand).
    db.collection("events").document("deleted_event").collection("participants").document("1002").set(
        {"telegram_id": 1002, "points": 5})
    # Ephemeral state that must NOT travel.
    db.collection("work_receipts").document("telegram-99").set(
        {"status": "processing", "expires": 1757890000.0, "serial_key": "1001",
         "delete_after": stamp + timedelta(days=30)})
    db.collection("update_locks").document("1001").set({"owner": "telegram-99", "expires": 1757890000.0})


def snapshot_tree(client, collections=None):
    """{document path: fields} read with the plain client, independent of the backup codec."""
    tree = {}

    def walk(collection_ref):
        for reference in collection_ref.list_documents():
            snap = reference.get()
            if snap.exists:
                tree[reference.path] = snap.to_dict()
            for sub in reference.collections():
                walk(sub)

    for collection_ref in client.collections():
        if collections is None or collection_ref.id in collections:
            walk(collection_ref)
    return tree


def assert_same(expected, actual, where="<root>"):
    assert type(expected) is type(actual), f"{where}: {type(expected).__name__} != {type(actual).__name__}"
    if isinstance(expected, dict):
        assert expected.keys() == actual.keys(), where
        for key in expected:
            assert_same(expected[key], actual[key], f"{where}.{key}")
    elif isinstance(expected, list):
        assert len(expected) == len(actual), where
        for index, (left, right) in enumerate(zip(expected, actual)):
            assert_same(left, right, f"{where}[{index}]")
    else:
        assert expected == actual, where


def run_backup(tmp_path):
    assert backup_firestore.main(["--out", str(tmp_path), "--project", SOURCE, "--quiet"]) == 0
    files = glob.glob(str(tmp_path / "firestore-*.json"))
    assert len(files) == 1 and not glob.glob(str(tmp_path / "*.partial"))
    return files[0]


def backed_up_tree(client):
    return snapshot_tree(client, set(inventory.backed_up_names()))


def test_full_backup_restore_round_trip_preserves_every_document_and_type(emulator, tmp_path, capsys):
    source, target = emulator
    seed(source)
    path = run_backup(tmp_path)

    with open(path, encoding="utf-8") as handle:
        backup = json.load(handle)
    assert backup["format_version"] == archive.FORMAT_VERSION
    assert backup["source_project"] == SOURCE and backup["source_emulator"] is True
    assert backup["complete"] is True
    for name in ("referrals", "app_duels", "group_rounds", "monthly_closures", "daily_jobs"):
        assert name in backup["collections"]
    for name in ("work_receipts", "update_locks"):
        assert name not in backup["data"]
    assert backup["document_counts"]["group_rounds/*/players"] == 1
    assert backup["document_counts"]["events/*/participants"] == 2
    assert restore_firestore.main(["validate", path, "--strict"]) == 0

    assert restore_firestore.main(["restore", path, "--project", TARGET]) == 0
    output = capsys.readouterr().out
    assert "RESTORE COMPLETED AND VERIFIED" in output
    assert "Ånna" not in output and "stxCHARGE" not in output  # counts only, never contents or ids

    expected, actual = backed_up_tree(source), snapshot_tree(target)
    assert sorted(actual) == sorted(expected)
    for doc_path in expected:
        assert_same(expected[doc_path], actual[doc_path], doc_path)

    user = actual["users/1001"]
    assert isinstance(user["date_created"], datetime) and user["date_created"].tzinfo is not None
    assert isinstance(user["ratio"], float) and user["big_id"] == 2**53 + 1
    assert user["points_totali"] == 125 and "EVT_x" in user["trophies"]
    assert actual["app_duels/" + DUEL_CODE]["expires_at"] == datetime(2026, 9, 21, 21, 45, 12, 345678, tzinfo=timezone.utc)
    assert actual["admin_settings/codec_edge_cases"]["map_with_type_key"]["$type"] == "timestamp"
    assert "events/deleted_event/participants/1002" in actual
    assert not target.collection("events").document("deleted_event").get().exists
    assert not any(doc_path.startswith(("work_receipts/", "update_locks/")) for doc_path in actual)

    # Independent read-only verification, as an operator would run after a restore.
    assert restore_firestore.main(["verify", path, "--project", TARGET]) == 0


def test_restore_refuses_a_non_empty_target_and_writes_nothing(emulator, tmp_path):
    source, target = emulator
    seed(source)
    path = run_backup(tmp_path)
    target.collection("users").document("1001").set({"first_name": "live data"})

    assert restore_firestore.main(["restore", path, "--project", TARGET]) == restore_firestore.EXIT_REFUSED
    assert snapshot_tree(target) == {"users/1001": {"first_name": "live data"}}


def test_dry_run_plans_but_writes_nothing(emulator, tmp_path):
    source, target = emulator
    seed(source)
    path = run_backup(tmp_path)

    assert restore_firestore.main(["restore", path, "--project", TARGET, "--dry-run"]) == 0
    assert snapshot_tree(target) == {}


def test_interrupted_restore_is_resumed_with_missing_only(emulator, tmp_path, monkeypatch):
    source, target = emulator
    seed(source)
    path = run_backup(tmp_path)
    backup, _, _ = archive.require_valid(path)

    original_commit = WriteBatch.commit
    calls = {"n": 0}

    def flaky_commit(self, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("simulated network failure")
        return original_commit(self, *args, **kwargs)

    monkeypatch.setattr(WriteBatch, "commit", flaky_commit)
    target_ref = restore.resolve_target(project=TARGET, confirm_project=None, allow_production=False)
    with pytest.raises(restore.RestoreError) as failure:
        restore.restore(target, target_ref, backup, batch_size=4)
    assert failure.value.stats.written == 8
    monkeypatch.setattr(WriteBatch, "commit", original_commit)

    # The default mode refuses the half-restored target; the explicit resume completes it.
    assert restore_firestore.main(["restore", path, "--project", TARGET]) == restore_firestore.EXIT_REFUSED
    assert restore_firestore.main(["restore", path, "--project", TARGET, "--mode", "missing-only"]) == 0
    expected, actual = backed_up_tree(source), snapshot_tree(target)
    assert sorted(actual) == sorted(expected)
    for doc_path in expected:
        assert_same(expected[doc_path], actual[doc_path], doc_path)


def test_missing_only_never_touches_existing_documents(emulator, tmp_path):
    source, target = emulator
    seed(source)
    path = run_backup(tmp_path)
    target.collection("users").document("1001").set({"first_name": "changed after the backup"})

    assert restore_firestore.main(["restore", path, "--project", TARGET, "--mode", "missing-only"]) == 0
    assert target.collection("users").document("1001").get().to_dict() == {"first_name": "changed after the backup"}
    assert target.collection("users").document("1001").collection("history").document("2026-09-14").get().exists


def test_overwrite_replaces_backed_up_documents_but_deletes_nothing(emulator, tmp_path):
    source, target = emulator
    seed(source)
    path = run_backup(tmp_path)
    target.collection("users").document("1001").set({"first_name": "changed"})
    target.collection("users").document("3003").set({"first_name": "joined after the backup"})

    assert restore_firestore.main(["restore", path, "--project", TARGET, "--mode", "overwrite"]) == 0
    assert_same(source.collection("users").document("1001").get().to_dict(),
                target.collection("users").document("1001").get().to_dict())
    assert target.collection("users").document("3003").get().exists


def test_a_corrupted_backup_is_refused_before_touching_the_target(emulator, tmp_path):
    source, target = emulator
    seed(source)
    path = run_backup(tmp_path)
    with open(path, encoding="utf-8") as handle:
        backup = json.load(handle)
    backup["data"]["purchases"]["stxCHARGE-123_abc"]["fields"]["amount"] = 5000
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(backup, handle)

    assert restore_firestore.main(["validate", path]) == restore_firestore.EXIT_INVALID
    assert restore_firestore.main(["restore", path, "--project", TARGET]) == restore_firestore.EXIT_INVALID
    assert snapshot_tree(target) == {}


def test_an_unsupported_firestore_type_fails_the_backup_instead_of_stringifying_it(emulator, tmp_path):
    source, _ = emulator
    source.collection("users").document("1").set({"where": GeoPoint(45.46, 9.19)})

    assert backup_firestore.main(["--out", str(tmp_path), "--project", SOURCE, "--quiet"]) == 1
    assert os.listdir(tmp_path) == []
