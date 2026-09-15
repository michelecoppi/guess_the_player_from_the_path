"""Feature flags (#51): registry, schema validation, pure evaluation, bucketing and the cache.

Everything here runs without Firestore: the evaluator is pure and the service reads through
an injected loader with an injected clock. Firestore itself (persisted state, transactions,
two replicas) is covered in tests/test_feature_flags_emulator.py.
"""
import hashlib
import logging
import os
import subprocess
import sys
import threading

import pytest
from firebase_admin import firestore

from services import feature_flags as ff
from services.feature_flags import (
    Flag,
    FlagConfig,
    FlagRule,
    evaluate,
    parse_document,
)
from services.repos import feature_flags as repo

ALL_KEYS = {"arena", "shop", "daily_ui", "hints", "player_pipeline", "events_v2", "leaderboard"}


def doc(flags=None, revision=1, **extra):
    return {"schema_version": ff.SCHEMA_VERSION, "revision": revision, "flags": flags or {}, **extra}


def config_of(flags, revision=1):
    report = parse_document(doc(flags, revision))
    assert not report.invalid
    return report.config


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class Loader:
    def __init__(self, value=None):
        self.value = value
        self.calls = 0
        self.error = None

    def __call__(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.value


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def test_the_registry_covers_exactly_the_issue_scope_with_stable_names():
    assert {flag.value for flag in Flag} == ALL_KEYS
    assert set(ff.REGISTRY) == set(Flag)


def test_every_existing_feature_defaults_to_enabled_so_deploying_changes_nothing():
    assert all(definition.default is True for definition in ff.REGISTRY.values())
    assert ff.resolve_all(FlagConfig()) == {key: True for key in ALL_KEYS}


# ---------------------------------------------------------------------------
# Evaluation precedence
# ---------------------------------------------------------------------------

def test_missing_config_uses_the_repository_default():
    assert evaluate(Flag.SHOP, FlagConfig(), user_id=1) is True
    assert evaluate(Flag.SHOP, parse_document(None).config) is True


def test_a_flag_without_a_stored_rule_uses_its_default_even_when_others_are_stored():
    config = config_of({"arena": {"enabled": False}})
    assert evaluate(Flag.ARENA, config, user_id=1) is False
    assert evaluate(Flag.SHOP, config, user_id=1) is True


def test_master_disable_beats_rollout_and_allowlists():
    config = config_of({"shop": {"enabled": False, "rollout_percentage": 100,
                                 "allow_users": ["7"], "allow_groups": ["-100"]}})
    assert evaluate(Flag.SHOP, config, user_id=7, group_id=-100) is False
    assert evaluate(Flag.SHOP, config) is False


def test_explicit_deny_turns_off_a_fully_rolled_out_flag():
    config = config_of({"hints": {"deny_users": ["7"]}})
    assert evaluate(Flag.HINTS, config, user_id=7) is False
    assert evaluate(Flag.HINTS, config, user_id=8) is True


def test_explicit_allow_turns_on_a_zero_percent_rollout():
    config = config_of({"arena": {"rollout_percentage": 0, "allow_users": [7]}})
    assert evaluate(Flag.ARENA, config, user_id=7) is True
    assert evaluate(Flag.ARENA, config, user_id=8) is False


@pytest.mark.parametrize("rule, context", [
    ({"allow_users": ["7"], "deny_users": ["7"]}, {"user_id": 7}),
    ({"allow_users": ["7"], "deny_groups": ["-100"]}, {"user_id": 7, "group_id": -100}),
    ({"allow_groups": ["-100"], "deny_users": ["7"]}, {"user_id": 7, "group_id": -100}),
])
def test_deny_wins_over_allow_across_users_and_groups(rule, context):
    config = config_of({"leaderboard": {"rollout_percentage": 0, **rule}})
    assert evaluate(Flag.LEADERBOARD, config, **context) is False


def test_zero_percent_is_off_for_everyone_and_hundred_is_on_for_everyone():
    zero = config_of({"events_v2": {"rollout_percentage": 0}})
    full = config_of({"events_v2": {"rollout_percentage": 100}})
    for user in range(200):
        assert evaluate(Flag.EVENTS_V2, zero, user_id=user) is False
        assert evaluate(Flag.EVENTS_V2, full, user_id=user) is True
    assert evaluate(Flag.EVENTS_V2, full) is True
    assert evaluate(Flag.EVENTS_V2, zero) is False


def test_a_partial_rollout_without_any_subject_is_conservatively_off():
    config = config_of({"daily_ui": {"rollout_percentage": 99}})
    assert evaluate(Flag.DAILY_UI, config) is False
    assert evaluate(Flag.DAILY_UI, config, user_id=None, group_id="") is False


def test_unparseable_context_ids_count_as_no_subject_instead_of_crashing():
    config = config_of({"daily_ui": {"rollout_percentage": 50, "deny_users": ["1"]}})
    assert evaluate(Flag.DAILY_UI, config, user_id="not-a-number") is False
    assert evaluate(Flag.DAILY_UI, config, user_id=object()) is False
    assert evaluate(Flag.DAILY_UI, config, user_id=True) is False


def test_user_and_group_ids_match_as_strings_whatever_their_type():
    config = config_of({"shop": {"rollout_percentage": 0, "allow_users": [42], "allow_groups": ["-1001"]}})
    assert evaluate(Flag.SHOP, config, user_id="42") is True
    assert evaluate(Flag.SHOP, config, user_id=42) is True
    assert evaluate(Flag.SHOP, config, group_id=-1001) is True
    assert evaluate(Flag.SHOP, config, group_id="-1001") is True
    assert evaluate(Flag.SHOP, config, group_id=-1002) is False


def test_group_targeting_applies_to_users_without_their_own_rule():
    config = config_of({"leaderboard": {"deny_groups": ["-100"]}})
    assert evaluate(Flag.LEADERBOARD, config, user_id=1, group_id=-100) is False
    assert evaluate(Flag.LEADERBOARD, config, user_id=1, group_id=-200) is True
    assert evaluate(Flag.LEADERBOARD, config, user_id=1) is True


def test_group_rollout_is_used_when_there_is_no_user():
    config = config_of({"leaderboard": {"rollout_percentage": 50}})
    groups = [-(1000 + n) for n in range(400)]
    expected = [ff.bucket(Flag.LEADERBOARD, "group", str(g)) < 5000 for g in groups]
    assert [evaluate(Flag.LEADERBOARD, config, group_id=g) for g in groups] == expected
    assert 0 < sum(expected) < len(groups)


# ---------------------------------------------------------------------------
# Deterministic bucketing
# ---------------------------------------------------------------------------

def test_the_bucket_is_sha256_of_flag_type_and_id():
    digest = hashlib.sha256(b"shop:user:123456789").digest()
    assert ff.bucket(Flag.SHOP, "user", "123456789") == int.from_bytes(digest[:8], "big") % 10_000


def test_the_bucket_is_the_same_in_another_process_with_another_hash_seed():
    """`hash()` is salted per process; the bucket must not be."""
    code = "from services import feature_flags as f; print(f.bucket(f.Flag.ARENA, 'user', '987654321'))"
    outputs = {
        subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True,
                       env={**os.environ, "PYTHONHASHSEED": seed}).stdout.strip()
        for seed in ("1", "2", "3")
    }
    assert outputs == {str(ff.bucket(Flag.ARENA, "user", "987654321"))}


def test_a_percentage_rollout_is_stable_across_calls_and_roughly_proportional():
    config = config_of({"arena": {"rollout_percentage": 30}})
    users = range(1, 5001)
    first = [evaluate(Flag.ARENA, config, user_id=u) for u in users]
    assert first == [evaluate(Flag.ARENA, config, user_id=u) for u in users]
    assert 0.27 < sum(first) / len(first) < 0.33


def test_raising_the_percentage_only_adds_users():
    low = config_of({"arena": {"rollout_percentage": 10}})
    high = config_of({"arena": {"rollout_percentage": 60}})
    for user in range(1, 3000):
        if evaluate(Flag.ARENA, low, user_id=user):
            assert evaluate(Flag.ARENA, high, user_id=user)


def test_different_subjects_and_different_flags_land_in_independent_buckets():
    buckets = {ff.bucket(Flag.SHOP, "user", str(u)) for u in range(1, 200)}
    assert len(buckets) > 190
    assert ff.bucket(Flag.SHOP, "user", "5") != ff.bucket(Flag.ARENA, "user", "5")
    assert ff.bucket(Flag.SHOP, "user", "5") != ff.bucket(Flag.SHOP, "group", "5")


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw", [
    [], "flags", 3,
    {"flags": {}},
    {"schema_version": 2, "flags": {}},
    {"schema_version": "1", "flags": {}},
    {"schema_version": True, "flags": {}},
    {"schema_version": 1, "flags": []},
    {"schema_version": 1, "revision": "7", "flags": {}},
    {"schema_version": 1, "revision": -1, "flags": {}},
])
def test_an_unusable_document_is_rejected_as_a_whole(raw):
    with pytest.raises(ff.ConfigError):
        parse_document(raw)


def test_unknown_flags_are_ignored_and_never_become_features():
    report = parse_document(doc({"new_checkout": {"enabled": True}, "shop": {"enabled": False}}))
    assert report.unknown == ("new_checkout",)
    assert set(report.config.rules) == {Flag.SHOP}
    assert not ff.is_enabled("new_checkout")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        ff.parse_flag("new_checkout")


@pytest.mark.parametrize("entry, field", [
    ({"enabled": "false"}, "enabled"),
    ({"enabled": 0}, "enabled"),
    ({"rollout_percentage": 101}, "rollout_percentage"),
    ({"rollout_percentage": -1}, "rollout_percentage"),
    ({"rollout_percentage": 50.5}, "rollout_percentage"),
    ({"rollout_percentage": "50"}, "rollout_percentage"),
    ({"rollout_percentage": True}, "rollout_percentage"),
    ({"allow_users": "123"}, "allow_users"),
    ({"allow_users": ["abc"]}, "allow_users"),
    ({"deny_users": [True]}, "deny_users"),
    ({"allow_groups": [1.5]}, "allow_groups"),
    ({"deny_groups": [None]}, "deny_groups"),
    ({"allow_users": [str(n) for n in range(ff.MAX_TARGETS_PER_LIST + 1)]}, "allow_users"),
    ({"rollout_percent": 10}, "unknown_field"),
    ("off", "entry"),
])
def test_a_malformed_entry_is_reported_by_field_and_left_out(entry, field):
    report = parse_document(doc({"arena": entry, "shop": {"enabled": False}}))
    assert report.invalid == {"arena": field}
    assert Flag.ARENA not in report.config.rules
    assert report.config.rules[Flag.SHOP].enabled is False


def test_a_valid_kill_switch_survives_a_malformed_sibling_field():
    report = parse_document(doc({"shop": {"enabled": False, "rollout_percentage": 250}}))
    assert report.invalid == {"shop": "rollout_percentage"}
    assert report.kill_switch_kept == (Flag.SHOP,)
    assert evaluate(Flag.SHOP, report.config, user_id=1) is False


def test_missing_fields_take_safe_defaults():
    rule = parse_document(doc({"hints": {}})).config.rules[Flag.HINTS]
    assert rule == FlagRule(enabled=True, rollout_percentage=100)


def test_serialized_rules_round_trip():
    rule = FlagRule(enabled=True, rollout_percentage=25, allow_users=frozenset({"10", "9"}),
                    deny_groups=frozenset({"-100"}))
    stored = ff.serialize_rule(rule)
    assert stored["allow_users"] == ["9", "10"]
    assert ff.parse_rule(stored, True) == rule


# ---------------------------------------------------------------------------
# Cached service: TTL, last-known-good, failures
# ---------------------------------------------------------------------------

def service_with(loader, ttl=30.0):
    clock = Clock()
    return ff.FeatureFlagService(loader, ttl=ttl, clock=clock), clock


def test_no_document_means_repository_defaults():
    service, _ = service_with(Loader(None))
    assert service.resolved(user_id=1) == {key: True for key in ALL_KEYS}
    assert service.snapshot().source == ff.SOURCE_DEFAULT


def test_firestore_failure_before_the_first_load_serves_defaults(caplog):
    loader = Loader()
    loader.error = RuntimeError("unavailable")
    service, _ = service_with(loader)
    with caplog.at_level(logging.WARNING):
        assert service.is_enabled(Flag.SHOP, user_id=1) is True
    assert service.snapshot().source == ff.SOURCE_DEFAULT
    assert "feature_flags.refresh.failed" in caplog.text


def test_firestore_failure_after_a_good_load_keeps_the_emergency_disable():
    loader = Loader(doc({"shop": {"enabled": False}}))
    service, clock = service_with(loader)
    assert service.is_enabled(Flag.SHOP, user_id=1) is False

    loader.error = TimeoutError("deadline exceeded")
    clock.now += 31
    assert service.is_enabled(Flag.SHOP, user_id=1) is False
    assert service.snapshot().source == ff.SOURCE_LAST_KNOWN_GOOD


def test_an_unusable_fetch_does_not_replace_the_last_known_good():
    loader = Loader(doc({"arena": {"enabled": False}}, revision=4))
    service, clock = service_with(loader)
    assert service.is_enabled(Flag.ARENA, user_id=1) is False

    loader.value = {"schema_version": 99, "flags": {}}
    clock.now += 31
    snapshot = service.snapshot()
    assert snapshot.source == ff.SOURCE_LAST_KNOWN_GOOD and snapshot.config.revision == 4
    assert service.is_enabled(Flag.ARENA, user_id=1) is False


def test_a_malformed_entry_keeps_that_flags_last_known_good_rule_only():
    loader = Loader(doc({"arena": {"enabled": False}, "shop": {"rollout_percentage": 0}}, revision=1))
    service, clock = service_with(loader)
    assert service.is_enabled(Flag.ARENA, user_id=1) is False

    loader.value = doc({"arena": {"enabled": "yes"}, "shop": {"rollout_percentage": 100}}, revision=2)
    clock.now += 31
    assert service.is_enabled(Flag.ARENA, user_id=1) is False  # kept from last-known-good
    assert service.is_enabled(Flag.SHOP, user_id=1) is True  # valid change applied


def test_a_malformed_entry_on_cold_start_falls_back_to_the_default():
    service, _ = service_with(Loader(doc({"arena": {"rollout_percentage": "ten"}})))
    assert service.is_enabled(Flag.ARENA, user_id=1) is True


def test_config_warnings_never_contain_target_ids(caplog):
    secret_ids = ["55501234", "-100987654"]
    loader = Loader(doc({"shop": {"allow_users": [secret_ids[0], "bad"], "deny_groups": [secret_ids[1]]},
                         "mystery_flag": {"allow_users": [secret_ids[0]]}}))
    service, _ = service_with(loader)
    with caplog.at_level(logging.INFO):
        service.snapshot()
    assert "feature_flags.config.invalid" in caplog.text
    for record in caplog.records:
        rendered = f"{record.getMessage()} {record.__dict__}"
        assert all(value not in rendered for value in secret_ids)
        assert "mystery_flag" not in rendered


def test_repeated_identical_problems_are_warned_once(caplog):
    loader = Loader()
    loader.error = RuntimeError("down")
    service, clock = service_with(loader)
    with caplog.at_level(logging.WARNING):
        for _ in range(5):
            service.snapshot()
            clock.now += 31
    assert caplog.text.count("feature_flags.refresh.failed") == 1
    assert loader.calls == 5


def test_the_cache_serves_one_read_per_ttl():
    loader = Loader(doc({"hints": {"enabled": False}}))
    service, clock = service_with(loader, ttl=30)
    for _ in range(50):
        service.is_enabled(Flag.HINTS, user_id=1)
    assert loader.calls == 1

    loader.value = doc({"hints": {"enabled": True}}, revision=2)
    clock.now += 29.9
    assert service.is_enabled(Flag.HINTS, user_id=1) is False
    clock.now += 0.2
    assert service.is_enabled(Flag.HINTS, user_id=1) is True
    assert loader.calls == 2


def test_a_failed_read_is_retried_only_after_another_ttl():
    loader = Loader()
    loader.error = RuntimeError("down")
    service, clock = service_with(loader, ttl=30)
    service.snapshot()
    service.snapshot()
    assert loader.calls == 1
    loader.error = None
    loader.value = doc({"shop": {"enabled": False}})
    clock.now += 31
    assert service.is_enabled(Flag.SHOP) is False


def test_invalidate_forces_a_refresh_but_keeps_last_known_good_on_failure():
    loader = Loader(doc({"shop": {"enabled": False}}))
    service, _ = service_with(loader, ttl=300)
    assert service.is_enabled(Flag.SHOP) is False
    loader.error = RuntimeError("down")
    service.invalidate()
    assert service.is_enabled(Flag.SHOP) is False
    assert loader.calls == 2

    loader.error = None
    loader.value = None  # document deleted: a valid state, back to defaults
    service.invalidate()
    assert service.is_enabled(Flag.SHOP) is True


def test_a_cold_start_stampede_reads_once():
    started, release = threading.Event(), threading.Event()

    def slow_loader():
        started.set()
        release.wait(5)
        return doc({"arena": {"enabled": False}})

    counting = Loader()
    service = ff.FeatureFlagService(lambda: (counting(), slow_loader())[1], ttl=30)
    results = []
    threads = [threading.Thread(target=lambda: results.append(service.is_enabled(Flag.ARENA))) for _ in range(8)]
    for thread in threads:
        thread.start()
    started.wait(5)
    release.set()
    for thread in threads:
        thread.join(5)
    assert results == [False] * 8
    assert counting.calls == 1


def test_while_one_thread_refreshes_the_others_keep_the_current_snapshot():
    clock = Clock()
    gate = threading.Event()
    state = {"value": doc({"arena": {"enabled": False}}, revision=1), "block": False}

    def loader():
        if state["block"]:
            gate.wait(5)
        return state["value"]

    service = ff.FeatureFlagService(loader, ttl=30, clock=clock)
    assert service.is_enabled(Flag.ARENA) is False

    state.update(block=True, value=doc({"arena": {"enabled": True}}, revision=2))
    clock.now += 31
    refresher = threading.Thread(target=service.snapshot)
    refresher.start()
    for _ in range(100):
        if service._lock.locked():
            break
        threading.Event().wait(0.01)
    assert service.is_enabled(Flag.ARENA) is False  # served from the current snapshot, not blocked
    gate.set()
    refresher.join(5)
    assert service.is_enabled(Flag.ARENA) is True


# ---------------------------------------------------------------------------
# Internal failures: never crash, never re-enable a known kill switch
# ---------------------------------------------------------------------------

def boom(*args, **kwargs):
    raise RuntimeError("internal failure for user 555000111")


KILL_SWITCH_DOC = doc({
    "shop": {"enabled": False},                                   # known kill switch
    "hints": {"enabled": True},                                   # stored, fully on, no deny
    "leaderboard": {"deny_users": ["555000111"]},                 # stored, deny list
    "arena": {"rollout_percentage": 40},                          # stored, partial rollout
})


def loaded_service():
    service, clock = service_with(Loader(KILL_SWITCH_DOC))
    assert service.is_enabled(Flag.SHOP, user_id=1) is False
    return service, clock


def test_cold_process_with_a_broken_snapshot_path_uses_defaults_without_raising(monkeypatch):
    service, _ = service_with(Loader(None))
    monkeypatch.setattr(service, "snapshot", boom)
    assert service.is_enabled(Flag.SHOP, user_id=1) is True
    assert service.resolved(user_id=1) == {key: True for key in ALL_KEYS}


def test_cold_process_with_a_failing_loader_uses_defaults_without_raising():
    loader = Loader()
    loader.error = RuntimeError("down")
    service, _ = service_with(loader)
    assert service.resolved(user_id=1) == {key: True for key in ALL_KEYS}


def test_a_known_kill_switch_survives_snapshot_raising(monkeypatch):
    service, _ = loaded_service()
    monkeypatch.setattr(service, "snapshot", boom)
    assert service.is_enabled(Flag.SHOP, user_id=1) is False
    assert service.resolved(user_id=1)["shop"] is False
    # Unaffected flags keep their real evaluation from the retained configuration.
    assert service.is_enabled(Flag.HINTS, user_id=1) is True
    assert service.is_enabled(Flag.LEADERBOARD, user_id=555000111) is False
    assert service.is_enabled(Flag.LEADERBOARD, user_id=1) is True
    assert service.is_enabled(Flag.DAILY_UI, user_id=1) is True


def test_a_known_kill_switch_survives_a_refresh_that_raises_after_the_load(monkeypatch):
    """A bug past the loader (post-processing) escapes `_refresh`, so `snapshot()` raises."""
    service, clock = loaded_service()
    clock.now += 31
    monkeypatch.setattr(ff, "parse_document", boom)
    monkeypatch.setattr(service, "_refresh", boom)
    assert service.is_enabled(Flag.SHOP, user_id=1) is False
    assert service.resolved(user_id=1)["shop"] is False


def test_last_known_good_is_used_when_there_is_no_snapshot_to_fall_back_on(monkeypatch):
    service, _ = loaded_service()
    service._snapshot = None
    monkeypatch.setattr(service, "snapshot", boom)
    assert service.is_enabled(Flag.SHOP, user_id=1) is False
    assert service.is_enabled(Flag.HINTS, user_id=1) is True


def test_a_known_kill_switch_survives_evaluate_raising(monkeypatch):
    service, _ = loaded_service()
    monkeypatch.setattr(ff, "evaluate", boom)
    assert service.is_enabled(Flag.SHOP, user_id=1) is False
    # Conservative per flag, never a global switch-off:
    assert service.is_enabled(Flag.DAILY_UI, user_id=1) is True        # no stored rule → default
    assert service.is_enabled(Flag.HINTS, user_id=1) is True           # could not have refused anyone
    assert service.is_enabled(Flag.LEADERBOARD, user_id=1) is False    # deny list cannot be checked
    assert service.is_enabled(Flag.ARENA, user_id=1) is False          # partial rollout cannot be checked


def test_resolved_keeps_known_disabled_flags_during_the_same_failures(monkeypatch):
    service, _ = loaded_service()
    monkeypatch.setattr(ff, "evaluate", boom)
    resolved = service.resolved(user_id=1)
    assert resolved == {"arena": False, "shop": False, "daily_ui": True, "hints": True,
                        "player_pipeline": True, "events_v2": True, "leaderboard": False}
    assert all(isinstance(value, bool) for value in resolved.values())

    monkeypatch.setattr(ff, "evaluate", evaluate)
    monkeypatch.setattr(service, "snapshot", boom)
    assert service.resolved(user_id=1)["shop"] is False


def test_evaluate_failing_on_a_cold_process_still_answers_with_defaults(monkeypatch):
    service, _ = service_with(Loader(None))
    monkeypatch.setattr(service, "snapshot", boom)
    monkeypatch.setattr(ff, "evaluate", boom)
    assert service.resolved(user_id=1) == {key: True for key in ALL_KEYS}


def test_even_a_broken_retained_configuration_cannot_re_enable_anything(monkeypatch):
    service, _ = loaded_service()

    class BrokenRules:
        def get(self, flag):
            raise RuntimeError("corrupted in memory")

    broken = FlagConfig(rules=BrokenRules())  # type: ignore[arg-type]
    service._snapshot = ff.Snapshot(broken, ff.SOURCE_FIRESTORE, 0.0, float("inf"))
    monkeypatch.setattr(ff, "evaluate", boom)
    assert service.is_enabled(Flag.SHOP, user_id=1) is False
    assert service.is_enabled(Flag.DAILY_UI, user_id=1) is False


def test_the_snapshot_path_is_not_retried_once_per_flag(monkeypatch):
    service, _ = loaded_service()
    calls = []
    monkeypatch.setattr(service, "snapshot", lambda: calls.append(1) or boom())
    service.resolved(user_id=1)
    assert len(calls) == 1


def test_unknown_keys_stay_false_even_during_failures(monkeypatch):
    service, _ = service_with(Loader(None))
    monkeypatch.setattr(service, "snapshot", boom)
    monkeypatch.setattr(ff, "evaluate", boom)
    for key in ("new_checkout", "shop", None, 3):
        assert service.is_enabled(key, user_id=1) is False  # type: ignore[arg-type]
        assert ff.is_enabled(key) is False  # type: ignore[arg-type]


def test_internal_fallbacks_are_reported_once_without_ids_or_messages(monkeypatch, caplog):
    service, _ = loaded_service()
    monkeypatch.setattr(service, "snapshot", boom)
    monkeypatch.setattr(ff, "evaluate", boom)
    with caplog.at_level(logging.WARNING):
        for _ in range(50):
            service.is_enabled(Flag.SHOP, user_id=555000111, group_id=-100987)
            service.resolved(user_id=555000111)
    records = [r for r in caplog.records if r.getMessage() == "feature_flags.evaluation.fallback"]
    # snapshot stage: once for shop, once for resolved(); evaluate stage: once per flag.
    assert len(records) == 2 + len(ALL_KEYS)
    assert all(r.levelno == logging.ERROR for r in records)
    for record in records:
        rendered = f"{record.getMessage()} {record.__dict__}"
        for leaked in ("555000111", "-100987", "internal failure", "deny_users"):
            assert leaked not in rendered
    contexts = [getattr(r, "_gtp_context", {}) for r in records]
    assert {c.get("stage") for c in contexts} == {"snapshot", "evaluate"}
    assert {c.get("source") for c in contexts} == {ff.SOURCE_CURRENT_SNAPSHOT, ff.SOURCE_CONSERVATIVE}
    assert {c.get("error_type") for c in contexts} == {"RuntimeError"}


def test_module_entry_points_use_the_installed_service():
    ff.set_service(ff.FeatureFlagService(Loader(doc({"leaderboard": {"enabled": False}})), ttl=30))
    assert ff.is_enabled(Flag.LEADERBOARD, user_id=1) is False
    with pytest.raises(ff.FeatureDisabled) as raised:
        ff.ensure_enabled(Flag.LEADERBOARD, user_id=1)
    assert raised.value.flag is Flag.LEADERBOARD and raised.value.code == "FEATURE_DISABLED"
    ff.ensure_enabled(Flag.SHOP, user_id=1)


def test_resolved_features_expose_only_booleans():
    ff.set_service(ff.FeatureFlagService(Loader(doc({
        "shop": {"rollout_percentage": 0, "allow_users": ["1"], "deny_groups": ["-5"]},
    })), ttl=30))
    resolved = ff.resolved_features(user_id=1)
    assert set(resolved) == ALL_KEYS
    assert all(isinstance(value, bool) for value in resolved.values())
    assert resolved["shop"] is True
    assert ff.resolved_features(user_id=2)["shop"] is False


@pytest.mark.parametrize("raw, expected", [
    (None, 30.0), ("", 30.0), ("abc", 30.0), ("nan", 30.0), ("10", 10.0), ("0", 1.0), ("99999", 300.0),
])
def test_ttl_is_configurable_and_bounded(raw, expected):
    environ = {} if raw is None else {ff.TTL_ENV: raw}
    assert ff.ttl_from_env(environ) == expected


# ---------------------------------------------------------------------------
# Operator changes and revision safety (planning; Firestore transactions on the emulator)
# ---------------------------------------------------------------------------

def test_changes_validate_their_input():
    rule = FlagRule()
    with pytest.raises(ValueError):
        ff.change_rollout(rule, 101)
    with pytest.raises(ValueError):
        ff.change_rollout(rule, True)
    with pytest.raises(ValueError):
        ff.change_enabled(rule, "no")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        ff.change_target(rule, "allow_users", "abc", add=True)
    with pytest.raises(ValueError):
        ff.change_target(rule, "vip_users", "1", add=True)
    assert ff.change_target(rule, "deny_groups", -100, add=True).deny_groups == {"-100"}
    both = FlagRule(allow_users=frozenset({"1", "2"}), deny_users=frozenset({"1"}))
    cleared = ff.clear_targets(both, ["1"], groups=False)
    assert cleared.allow_users == {"2"} and cleared.deny_users == frozenset()


def test_the_first_change_creates_a_valid_document():
    mode, payload, result = repo.plan_update(None, Flag.SHOP, lambda r: ff.change_enabled(r, False))
    assert mode == "set"
    assert parse_document(payload).config.rules[Flag.SHOP].enabled is False
    assert (result.previous_revision, result.revision, result.before) == (0, 1, None)


def test_a_change_touches_only_its_own_flag_and_bumps_the_revision():
    stored = doc({"arena": {"enabled": False}, "shop": {"allow_users": ["1"]}}, revision=7)
    mode, payload, result = repo.plan_update(stored, Flag.SHOP, lambda r: ff.change_target(r, "allow_users", 2, add=True))
    assert mode == "update"
    assert set(payload) == {"flags.shop", "revision"}
    assert payload["revision"] == 8
    assert payload["flags.shop"]["allow_users"] == ["1", "2"]


def test_changes_are_applied_to_the_current_document_not_a_stale_copy():
    """What the transaction does on retry: the second operator's change is re-planned on the
    document that already contains the first one, so neither is lost."""
    base = doc({"shop": {"allow_users": []}}, revision=3)
    _, first, _ = repo.plan_update(base, Flag.SHOP, lambda r: ff.change_target(r, "allow_users", 1, add=True))
    after_first = doc({"shop": first["flags.shop"]}, revision=first["revision"])
    _, second, result = repo.plan_update(after_first, Flag.SHOP,
                                         lambda r: ff.change_target(r, "allow_users", 2, add=True))
    assert second["flags.shop"]["allow_users"] == ["1", "2"]
    assert result.revision == 5


def test_an_expected_revision_refuses_a_concurrent_change():
    with pytest.raises(repo.RevisionConflict):
        repo.plan_update(doc({}, revision=5), Flag.ARENA, lambda r: r, expected_revision=4)
    repo.plan_update(doc({}, revision=5), Flag.ARENA, lambda r: r, expected_revision=5)


def test_an_invalid_stored_document_is_not_built_upon_unless_explicitly_replaced():
    broken = {"schema_version": 9, "flags": {"shop": {"enabled": False}}}
    with pytest.raises(repo.StoredConfigInvalid):
        repo.plan_update(broken, Flag.ARENA, lambda r: ff.change_enabled(r, False))
    mode, payload, _ = repo.plan_update(broken, Flag.ARENA, lambda r: ff.change_enabled(r, False),
                                        replace_invalid_document=True)
    assert mode == "set" and set(payload["flags"]) == {"arena"}


def test_an_invalid_entry_must_be_reset_before_it_is_changed():
    stored = doc({"shop": {"rollout_percentage": "lots"}})
    with pytest.raises(repo.StoredConfigInvalid):
        repo.plan_update(stored, Flag.SHOP, lambda r: ff.change_rollout(r, 10))
    mode, payload, result = repo.plan_update(stored, Flag.SHOP, None)
    assert mode == "update" and payload["flags.shop"] is firestore.DELETE_FIELD
    assert result.after is None


def test_the_actor_label_is_sanitised():
    assert repo.clean_actor("ops <script>@team") == "opsscript@team"
    assert repo.clean_actor("") == "operator"
    assert len(repo.clean_actor("x" * 500)) == 64
