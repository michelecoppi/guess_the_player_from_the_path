"""Feature flags (#51) on a real Firestore (the emulator).

What a fake cannot prove: that `admin_settings/feature_flags` is read and written with the
real client, that two replicas (two independent caches) converge on the persisted state,
that concurrent operator changes are not lost inside the transaction, and that a runtime
boundary actually flips when the stored document changes.
"""
import threading

import pytest
from starlette.testclient import TestClient

from apps.api import miniapp
from domains.shop import service as shop
from services import feature_flags as ff
from services.feature_flags import Flag
from services.repos import feature_flags as repo


def stored(emulator_db):
    snapshot = emulator_db.collection("admin_settings").document("feature_flags").get()
    return snapshot.to_dict() if snapshot.exists else None


def test_the_first_change_creates_the_document_with_schema_revision_and_metadata(emulator_db):
    assert repo.load_document() is None
    result = repo.update_flag(Flag.SHOP, lambda rule: ff.change_enabled(rule, False), actor="ops-cli")

    raw = stored(emulator_db)
    assert raw["schema_version"] == 1 and raw["revision"] == 1 == result.revision
    assert raw["flags"]["shop"]["enabled"] is False
    assert raw["updated_by"] == "ops-cli" and raw["updated_at"] is not None
    assert repo.load_document()["flags"] == raw["flags"]


def test_updates_change_one_flag_and_keep_the_others(emulator_db):
    repo.update_flag(Flag.ARENA, lambda rule: ff.change_rollout(rule, 25), actor="a")
    repo.update_flag(Flag.SHOP, lambda rule: ff.change_target(rule, "deny_users", 99, add=True), actor="b")
    repo.update_flag(Flag.ARENA, lambda rule: ff.change_target(rule, "allow_groups", -100, add=True), actor="c")

    raw = stored(emulator_db)
    assert raw["revision"] == 3
    assert raw["flags"]["arena"] == {"enabled": True, "rollout_percentage": 25, "allow_users": [],
                                     "deny_users": [], "allow_groups": ["-100"], "deny_groups": []}
    assert raw["flags"]["shop"]["deny_users"] == ["99"]

    repo.update_flag(Flag.ARENA, None, actor="d")  # reset
    raw = stored(emulator_db)
    assert "arena" not in raw["flags"] and raw["revision"] == 4
    assert ff.parse_document(raw).invalid == {}


def test_two_replicas_converge_on_the_persisted_state(emulator_db):
    replica_a = ff.FeatureFlagService(repo.load_document, ttl=0)
    replica_b = ff.FeatureFlagService(repo.load_document, ttl=0)
    assert replica_a.is_enabled(Flag.LEADERBOARD, user_id=1) is True

    repo.update_flag(Flag.LEADERBOARD, lambda rule: ff.change_enabled(rule, False), actor="ops")
    assert replica_a.is_enabled(Flag.LEADERBOARD, user_id=1) is False
    assert replica_b.is_enabled(Flag.LEADERBOARD, user_id=1) is False
    assert replica_a.snapshot().source == ff.SOURCE_FIRESTORE

    repo.update_flag(Flag.LEADERBOARD, lambda rule: ff.change_rollout(ff.change_enabled(rule, True), 50), actor="ops")
    users = range(1, 300)
    assert [replica_a.is_enabled(Flag.LEADERBOARD, user_id=u) for u in users] == \
           [replica_b.is_enabled(Flag.LEADERBOARD, user_id=u) for u in users]


def test_a_change_made_after_someone_else_committed_does_not_erase_it(emulator_db):
    """The realistic race: operator A looks at the flags, operator B commits a change, then A
    applies its own. A's change is re-applied to the document as it is now, so B's survives."""
    repo.update_flag(Flag.HINTS, lambda rule: rule, actor="init")
    seen_by_a = repo.load_document()

    repo.update_flag(Flag.HINTS, lambda rule: ff.change_target(rule, "allow_users", 2, add=True), actor="b")
    repo.update_flag(Flag.HINTS, lambda rule: ff.change_target(rule, "allow_users", 1, add=True), actor="a")

    raw = stored(emulator_db)
    assert raw["flags"]["hints"]["allow_users"] == ["1", "2"] and raw["revision"] == 3
    with pytest.raises(repo.RevisionConflict):
        repo.update_flag(Flag.HINTS, lambda rule: ff.change_rollout(rule, 0), actor="a",
                         expected_revision=seen_by_a["revision"])


def test_simultaneous_operator_changes_commit_or_fail_but_never_vanish(emulator_db):
    """Writers truly racing on the same document. The emulator may abort all of them (the
    same give-up tolerated in tests/test_firestore_transactions.py); what must hold is that
    every committed change is stored and the revision counts exactly the commits."""
    repo.update_flag(Flag.HINTS, lambda rule: rule, actor="init")
    committed, lock = [], threading.Lock()

    def add(user_id):
        try:
            repo.update_flag(Flag.HINTS, lambda rule: ff.change_target(rule, "allow_users", user_id, add=True),
                             actor=f"op{user_id}")
        except ValueError:  # attempts exhausted: reported to the caller, nothing written
            return
        with lock:
            committed.append(str(user_id))

    threads = [threading.Thread(target=add, args=(uid,)) for uid in range(1, 5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(60)

    raw = stored(emulator_db)
    assert sorted(raw["flags"]["hints"]["allow_users"], key=int) == sorted(committed, key=int)
    assert raw["revision"] == 1 + len(committed)


def test_an_expected_revision_refuses_a_stale_change(emulator_db):
    repo.update_flag(Flag.DAILY_UI, lambda rule: rule, actor="a")
    repo.update_flag(Flag.DAILY_UI, lambda rule: ff.change_rollout(rule, 10), actor="b")
    with pytest.raises(repo.RevisionConflict):
        repo.update_flag(Flag.DAILY_UI, lambda rule: ff.change_rollout(rule, 90), actor="c", expected_revision=1)
    assert stored(emulator_db)["flags"]["daily_ui"]["rollout_percentage"] == 10


def test_an_invalid_stored_document_is_kept_out_of_evaluation_and_writes(emulator_db):
    ref = emulator_db.collection("admin_settings").document("feature_flags")
    ref.set({"schema_version": 1, "revision": 1, "flags": {"events_v2": {"enabled": False}}})
    service = ff.FeatureFlagService(repo.load_document, ttl=0)
    assert service.is_enabled(Flag.EVENTS_V2) is False

    ref.set({"schema_version": 7, "flags": {"events_v2": {"enabled": True}}})
    assert service.is_enabled(Flag.EVENTS_V2) is False  # last-known-good
    assert service.snapshot().source == ff.SOURCE_LAST_KNOWN_GOOD
    with pytest.raises(repo.StoredConfigInvalid):
        repo.update_flag(Flag.SHOP, lambda rule: ff.change_enabled(rule, False), actor="ops")

    repo.update_flag(Flag.EVENTS_V2, lambda rule: ff.change_enabled(rule, False), actor="ops",
                     replace_invalid_document=True)
    assert ff.parse_document(stored(emulator_db)).config.rules[Flag.EVENTS_V2].enabled is False


def test_a_runtime_boundary_follows_the_stored_flag(emulator_db, monkeypatch):
    import bot
    monkeypatch.setattr(miniapp, "_webapp_user", lambda payload, cost=1: (42, {"language": "en"}))
    monkeypatch.setattr(shop, "catalogue_for", lambda user, lang: {"sections": []})
    client = TestClient(bot.app)

    assert client.post("/app/api/shop", json={"initData": "x"}).status_code == 200
    repo.update_flag(Flag.SHOP, lambda rule: ff.change_enabled(rule, False), actor="ops")
    refused = client.post("/app/api/shop", json={"initData": "x"})
    assert refused.status_code == 403 and refused.json()["code"] == "FEATURE_DISABLED"

    repo.update_flag(Flag.SHOP, lambda rule: ff.change_target(ff.change_enabled(rule, True), "deny_users", 42, add=True),
                     actor="ops")
    assert client.post("/app/api/shop", json={"initData": "x"}).status_code == 403
    repo.update_flag(Flag.SHOP, lambda rule: ff.clear_targets(rule, [42], groups=False), actor="ops")
    assert client.post("/app/api/shop", json={"initData": "x"}).status_code == 200


def test_the_operator_cli_round_trips_through_firestore(emulator_db):
    from scripts import feature_flags as cli
    lines = []
    assert cli.main(["disable", "arena", "--yes", "--actor", "incident"], out=lines.append) == 0
    assert cli.main(["allow", "arena", "--user", "777000", "--yes"], out=lines.append) == 0
    assert cli.main(["list"], out=lines.append) == 0

    raw = stored(emulator_db)
    assert raw["flags"]["arena"]["enabled"] is False and raw["flags"]["arena"]["allow_users"] == ["777000"]
    assert raw["updated_by"] == "operator-cli" and raw["revision"] == 2
    assert "777000" not in "\n".join(lines)
    # The kill switch still wins over the allow list for the targeted user.
    assert ff.FeatureFlagService(repo.load_document, ttl=0).is_enabled(Flag.ARENA, user_id=777000) is False
