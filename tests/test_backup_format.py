"""Backup format v2: typed codec, validation, corrupt-file rejection and the v1 upgrade (#50)."""
from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone

import pytest

from services.firestore_backup import archive, codec, exporter, inventory
from tests.backup_fakes import FakeClient

UTC = timezone.utc
CREATED = datetime(2026, 9, 14, 3, 30, tzinfo=UTC)


def _archive(data=None, **overrides):
    data = data if data is not None else {name: {} for name in inventory.backed_up_names()}
    built = archive.build_archive(data, source_project="guess-the-player-from-path-bot", source_emulator=False,
                                  created_at=CREATED, completed_at=CREATED + timedelta(seconds=5),
                                  generator={"tool": "test"})
    built.update(overrides)
    return built


def _users(fields, subcollections=None):
    node = {"exists": True, "fields": codec.encode_fields(fields, "users/*")}
    if subcollections:
        node["subcollections"] = subcollections
    return {name: {} for name in inventory.backed_up_names()} | {"users": {"42": node}}


# ---------------------------------------------------------------------------
# Codec
# ---------------------------------------------------------------------------

def test_primitives_nested_values_and_nulls_are_plain_json():
    value = {"n": 1, "f": 1.0, "b": False, "s": "è", "none": None, "list": [1, "a", None, {"x": []}], "map": {}}
    assert codec.encode_value(value) == value
    decoded = codec.decode_value(json.loads(json.dumps(codec.encode_value(value))))
    assert decoded == value and isinstance(decoded["f"], float) and isinstance(decoded["n"], int)


def test_timestamps_round_trip_as_utc_aware_datetimes():
    rome = datetime(2026, 9, 14, 23, 59, 59, 123456, tzinfo=timezone(timedelta(hours=2)))
    encoded = codec.encode_value({"at": rome})
    assert encoded == {"at": {"$type": "timestamp", "value": "2026-09-14T21:59:59.123456Z"}}
    decoded = codec.decode_value(encoded)["at"]
    assert decoded == rome and decoded.tzinfo == UTC


def test_a_map_containing_the_type_key_is_escaped_and_restored_verbatim():
    value = {"$type": "timestamp", "value": "2026-01-01T00:00:00.000000Z"}
    encoded = codec.encode_value(value)
    assert encoded == {"$type": "map", "value": value}
    assert codec.decode_value(encoded) == value


@pytest.mark.parametrize("value", [
    float("nan"), float("inf"), b"bytes", object(), datetime(2026, 1, 1), 2**63, [[1]], {1: "non-string key"},
])
def test_values_that_cannot_be_restored_faithfully_are_rejected(value):
    with pytest.raises(codec.BackupFormatError):
        codec.encode_value({"field": value}, "users/*")


def test_rejection_messages_mask_ids_in_paths():
    with pytest.raises(codec.BackupFormatError) as error:
        codec.encode_value({"app_duel_record": {"123456": {"where": object()}}}, "users/*")
    assert "123456" not in str(error.value) and "app_duel_record.*.where" in str(error.value)


@pytest.mark.parametrize("value", [
    {"$type": "geopoint", "value": [1, 2]},
    {"$type": "timestamp", "value": "2026-01-01"},
    {"$type": "timestamp", "value": "2026-01-01T00:00:00Z", "extra": 1},
    {"$type": "map", "value": {"no": "type key"}},
    [[1, 2]],
    2**64,
])
def test_decoding_fails_closed_on_malformed_values(value):
    with pytest.raises(codec.BackupFormatError):
        codec.decode_value({"x": value})


def test_json_nan_constants_are_refused():
    with pytest.raises(codec.BackupFormatError):
        codec.loads('{"x": NaN}')


# ---------------------------------------------------------------------------
# Archive validation
# ---------------------------------------------------------------------------

def test_a_freshly_built_archive_is_valid_and_complete():
    data = _users({"points": 3, "at": CREATED},
                  {"history": {"2026-09-14": {"exists": True, "fields": {"solved": True}}}})
    report = archive.validate_archive(_archive(data))
    assert report.ok, report.errors
    assert report.warnings == []
    assert report.summary["document_counts"] == {"users": 1, "users/*/history": 1}
    assert report.summary["complete"] is True


def test_metadata_summary_carries_no_ids_or_values():
    data = _users({"first_name": "Secret Name"})
    text = json.dumps(archive.summary(_archive(data)))
    assert "Secret Name" not in text and '"42"' not in text


@pytest.mark.parametrize("mutate, message", [
    (lambda a: a.update(format_version=3), "format_version"),
    (lambda a: a.update(format="other"), "not a"),
    (lambda a: a.pop("integrity"), "missing top-level"),
    (lambda a: a.update(surprise=1), "unknown top-level"),
    (lambda a: a.update(created_at="yesterday"), "created_at"),
    (lambda a: a.update(completed_at="2020-01-01T00:00:00.000000Z"), "before created_at"),
    (lambda a: a.update(total_documents=99), "total_documents"),
    (lambda a: a["document_counts"].update(users=7), "document_counts"),
    (lambda a: a.update(collections=["users"]), "collections does not match"),
    (lambda a: a.update(complete=False), "complete flag"),
    (lambda a: a["data"]["users"]["42"]["fields"].update(points=4), "digest mismatch"),
    (lambda a: a["data"]["users"]["42"].update(exists="yes"), "boolean exists"),
    (lambda a: a["data"]["users"]["42"]["fields"].update(bad={"$type": "vector", "value": []}), "unsupported tagged"),
    (lambda a: a["data"]["users"].update({"a/b": {"exists": True, "fields": {}}}), "invalid document id"),
    (lambda a: a["data"]["users"].update({"ghost": {"exists": False}}), "must have subcollections"),
    (lambda a: a["data"]["users"]["42"].update(subcollections={}), "non-empty object"),
    (lambda a: a["data"].update(work_receipts={}), "excluded by the inventory"),
    (lambda a: a.update(source_project=""), "source_project"),
])
def test_corrupt_or_inconsistent_archives_are_rejected(mutate, message):
    backup = _archive(_users({"points": 3}))
    mutate(backup)
    report = archive.validate_archive(backup)
    assert not report.ok
    assert any(message in error for error in report.errors), report.errors


def test_warnings_flag_unclassified_collections_undeclared_subcollections_and_gaps():
    data = _users({"points": 1}, {"notes": {"n1": {"exists": True, "fields": {}}}})
    del data["referrals"]
    data["mystery"] = {"m": {"exists": True, "fields": {}}}
    report = archive.validate_archive(_archive(data))
    assert report.ok, report.errors
    joined = " | ".join(report.warnings)
    assert "mystery" in joined and "users/*/notes" in joined and "referrals" in joined


def test_missing_parent_documents_keep_their_subcollections():
    data = {name: {} for name in inventory.backed_up_names()}
    data["events"] = {"gone": {"exists": False, "subcollections": {
        "participants": {"7": {"exists": True, "fields": {"points": 1}}}}}}
    backup = _archive(data)
    assert archive.validate_archive(backup).ok
    assert backup["document_counts"] == {"events/*/participants": 1}


def test_load_archive_rejects_truncated_json(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text(json.dumps(_archive())[:-10], encoding="utf-8")
    obj, report, digest = archive.load_archive(str(path))
    assert obj is None and not report.ok and len(digest) == 64
    with pytest.raises(archive.BackupValidationError):
        archive.require_valid(str(path))


def test_the_integrity_digest_ignores_formatting_but_not_content():
    backup = _archive(_users({"points": 3}))
    reformatted = json.loads(json.dumps(backup, indent=4, sort_keys=False))
    assert archive.validate_archive(reformatted).ok


# ---------------------------------------------------------------------------
# Exporter with a fake client
# ---------------------------------------------------------------------------

def test_the_exporter_follows_subcollections_and_skips_ephemeral_collections():
    client = FakeClient(docs={
        "users/1": {"at": CREATED},
        "users/1/history/2026-09-14": {"solved": True},
        "events/gone/participants/1": {"points": 2},
        "work_receipts/telegram-1": {"status": "done"},
        "update_locks/1": {"owner": "x"},
    })
    backup = exporter.export_archive(client, source_project="demo-fake", source_emulator=True,
                                     clock=lambda: CREATED)
    assert "work_receipts" not in backup["data"] and "update_locks" not in backup["data"]
    assert backup["data"]["users"]["1"]["subcollections"]["history"]["2026-09-14"]["fields"] == {"solved": True}
    assert backup["data"]["events"]["gone"]["exists"] is False
    assert backup["complete"] is True
    assert codec.decode_value(backup["data"]["users"]["1"]["fields"])["at"] == CREATED


def test_unclassified_collections_are_exported_and_flagged_not_lost():
    client = FakeClient(docs={"brand_new/x": {"x": 1}})
    backup = exporter.export_archive(client, source_project="demo-fake", source_emulator=True, clock=lambda: CREATED)
    assert backup["inventory"]["unclassified"] == ["brand_new"]
    assert backup["data"]["brand_new"]["x"]["fields"] == {"x": 1}


def test_a_partial_export_may_only_name_backed_up_collections():
    with pytest.raises(exporter.ExportError):
        exporter.resolve_collections([], ["work_receipts"])
    assert exporter.resolve_collections([], ["users"]) == (["users"], [])


def test_an_unsupported_value_aborts_the_export():
    client = FakeClient(docs={"users/1": {"blob": b"raw"}})
    with pytest.raises(codec.BackupFormatError):
        exporter.export_archive(client, source_project="demo-fake", source_emulator=True, clock=lambda: CREATED)


# ---------------------------------------------------------------------------
# v1 upgrade
# ---------------------------------------------------------------------------

V1 = {
    "users": {"42": {"_data": {"date_created": "2026-01-02T03:04:05.678901+00:00", "name": "A",
                               "free_text": "2026-01-02T03:04:05+00:00"},
                     "_subcollections": {"history": {"2026-01-02": {"_data": {"solved": True}}}}}},
    "leagues": {"L1": {"_data": {"created_at": "not a date"},
                       "_subcollections": {"members": {"42": {"_data": {"joined_at": "2026-01-02T00:00:00+00:00"}}}}}},
    "purchases": {},
}


def test_v1_files_are_detected_and_refused_until_upgraded():
    report = archive.validate_archive(copy.deepcopy(V1))
    assert not report.ok and "upgrade-v1" in report.errors[0]


def test_v1_upgrade_types_known_timestamps_and_marks_the_result_lossy():
    upgraded = archive.upgrade_v1(copy.deepcopy(V1), source_project="guess-the-player-from-path-bot",
                                  created_at=CREATED)
    report = archive.validate_archive(upgraded)
    assert report.ok, report.errors
    assert any("legacy v1" in warning for warning in report.warnings)
    user = codec.decode_value(upgraded["data"]["users"]["42"]["fields"])
    assert user["date_created"] == datetime(2026, 1, 2, 3, 4, 5, 678901, tzinfo=UTC)
    assert user["free_text"] == "2026-01-02T03:04:05+00:00"  # not a known timestamp field
    member = upgraded["data"]["leagues"]["L1"]["subcollections"]["members"]["42"]["fields"]
    assert member["joined_at"]["$type"] == "timestamp"
    assert upgraded["legacy_conversion"]["timestamp_fields_converted"] == 2
    assert upgraded["legacy_conversion"]["timestamp_fields_left_as_text"] == 1
    assert upgraded["complete"] is False


def test_v1_upgrade_rejects_non_v1_input():
    with pytest.raises(codec.BackupFormatError):
        archive.upgrade_v1(_archive(), source_project="p-roject", created_at=CREATED)
