import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest

from services import experiments as exp
from services import product_analytics
from services.repos import experiments as repo

NOW = datetime(2026, 9, 27, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def reset_assignment_cache():
    exp.clear_assignment_cache()
    yield
    exp.clear_assignment_cache()


def planned():
    return exp.plan("daily_intro_v1", "A shorter introduction increases Daily completion",
                    "daily_completion_rate", 7, "short introduction")


def test_only_defined_metrics_can_be_used_and_start_requires_analytics():
    with pytest.raises(ValueError, match="metric"):
        exp.plan("daily_intro_v1", "hypothesis", "made_up_rate", 7, "new copy")
    with pytest.raises(ValueError, match="active analytics"):
        exp.start(planned(), now=NOW, analytics_ready=False)
    assert exp.start(planned(), now=NOW, analytics_ready=True)["metric"] == "daily_completion_rate"


def test_lifecycle_enforces_duration_result_evidence_and_decision():
    running = exp.start(planned(), now=NOW, analytics_ready=True)
    with pytest.raises(ValueError, match="duration"):
        exp.finish(running, summary="improved", evidence_url="https://example.test/result",
                   now=NOW + timedelta(days=6))
    with pytest.raises(ValueError, match="result"):
        exp.decide(running, "ship")
    with pytest.raises(ValueError, match="evidence_url"):
        exp.finish(running, summary="improved", evidence_url="http://example.test/result",
                   now=NOW + timedelta(days=7))
    finished = exp.finish(running, summary="Improved by 3 points",
                          evidence_url="https://example.test/result", now=NOW + timedelta(days=7))
    decided = exp.decide(finished, "ship")
    assert decided["result"]["summary"] == "Improved by 3 points"
    assert decided["decision"] == "ship"
    with pytest.raises(ValueError, match="experiment has no result"):
        exp.decide(decided, "stop")


def test_assignments_are_stable_private_and_only_during_window():
    running = exp.start(planned(), now=NOW, analytics_ready=True)
    moment = NOW + timedelta(days=1)
    assigned = exp.variant_for_subject(running, user_id=42, now=moment)
    assert assigned in ("control", "treatment")
    assert exp.variant_for_subject(running, user_id="42", now=moment) == assigned
    assert exp.variant_for_subject(running, group_id=-100, now=moment) in ("control", "treatment")
    assert exp.variant_for_subject(running, now=moment) is None
    assert exp.variant_for_subject(running, user_id=42, now=NOW + timedelta(days=7)) is None
    assert exp.variant_for_subject(planned(), user_id=42, now=moment) is None


def test_corrupt_registry_is_rejected_before_any_change():
    assert repo.parse_document(None) == {}
    raw = {"schema_version": 1, "experiments": {"daily_intro_v1": planned()}}
    assert repo.parse_document(raw)["daily_intro_v1"]["status"] == "planned"
    raw["experiments"]["daily_intro_v1"]["metric"] = "unknown"
    with pytest.raises(ValueError, match="metric"):
        repo.parse_document(raw)


def test_existing_registry_records_without_stop_field_remain_readable():
    old_record = planned()
    old_record.pop("stop")
    parsed = repo.parse_document({"schema_version": 1, "experiments": {"daily_intro_v1": old_record}})
    assert parsed["daily_intro_v1"]["stop"] is None


def test_duplicate_or_missing_lifecycle_fields_rejected():
    plan = planned()
    plan["result"] = {"summary": "fabricated", "evidence_url": "https://example.test"}
    with pytest.raises(ValueError, match="planned lifecycle"):
        exp.validate(plan)
    with pytest.raises(ValueError, match="duration_days"):
        exp.plan("daily_intro_v1", "hypothesis", "daily_completion_rate", 0, "change")


def test_live_assignment_records_a_bounded_exposure(monkeypatch):
    running = exp.start(planned(), now=NOW, analytics_ready=True)
    from services.repos import experiments as store
    monkeypatch.setattr(store, "load", lambda: {"daily_intro_v1": running})
    monkeypatch.setattr(product_analytics, "is_enabled", lambda: True)
    monkeypatch.setattr(product_analytics, "settings", lambda: product_analytics.Settings(salt="test-salt"))
    captured = []
    monkeypatch.setattr(product_analytics, "capture", lambda event, **kwargs: captured.append((event, kwargs)))
    variant = exp.assign("daily_intro_v1", user_id=42, now=NOW + timedelta(days=1))
    assert variant in ("control", "treatment")
    assert captured == [(product_analytics.Event.EXPERIMENT_ASSIGNED, {
        "user_id": 42, "properties": {"experiment_key": "daily_intro_v1", "variant": variant},
    })]
    assert exp.assign("daily_intro_v1", user_id=42, now=NOW + timedelta(days=7)) is None
    assert len(captured) == 1
    monkeypatch.setattr(product_analytics, "is_enabled", lambda: False)
    assert exp.assign("daily_intro_v1", user_id=42, now=NOW + timedelta(days=1)) is None


def test_early_stop_is_audited_and_prevents_assignment():
    running = exp.start(planned(), now=NOW, analytics_ready=True)
    stopped = exp.stop(running, reason="Guardrail failed", operator="maintainer", now=NOW + timedelta(days=1))
    assert stopped["stop"] == {"at": NOW + timedelta(days=1), "reason": "Guardrail failed",
                               "operator": "maintainer"}
    assert stopped["hypothesis"] == running["hypothesis"]
    assert exp.variant_for_subject(stopped, user_id=42, now=NOW + timedelta(days=1)) is None
    with pytest.raises(ValueError, match="running"):
        exp.stop(stopped, reason="again", operator="maintainer", now=NOW + timedelta(days=2))
    with pytest.raises(ValueError, match="before expiry"):
        exp.stop(running, reason="too late", operator="maintainer", now=NOW + timedelta(days=7))


def test_operator_cli_records_stop_reason_and_identity(monkeypatch, capsys):
    from scripts import experiments as cli
    running = exp.start(planned(), now=datetime.now(timezone.utc) - timedelta(days=1), analytics_ready=True)
    monkeypatch.setattr(cli.store, "update", lambda key, change: change(running))
    assert cli.main(["stop", "daily_intro_v1", "--operator", "alice", "--reason", "Guardrail failed"]) == 0
    output = capsys.readouterr().out
    assert '"status": "stopped"' in output
    assert '"operator": "alice"' in output
    assert '"reason": "Guardrail failed"' in output


def test_assignment_cache_is_single_flight_and_expires_fail_closed(monkeypatch):
    running = exp.start(planned(), now=NOW, analytics_ready=True)
    from services.repos import experiments as store
    reads = []
    def load():
        reads.append(1)
        time.sleep(0.03)
        return {"daily_intro_v1": running}
    monkeypatch.setattr(store, "load", load)
    monkeypatch.setattr(product_analytics, "is_enabled", lambda: True)
    monkeypatch.setattr(product_analytics, "settings", lambda: product_analytics.Settings(salt="test-salt"))
    monkeypatch.setattr(product_analytics, "capture", lambda *args, **kwargs: None)
    now = NOW + timedelta(days=1)
    first_start = time.perf_counter()
    assert exp.assign("daily_intro_v1", user_id=42, now=now) is not None
    cold_latency = time.perf_counter() - first_start
    warm_start = time.perf_counter()
    assert exp.assign("daily_intro_v1", user_id=42, now=now) is not None
    warm_latency = time.perf_counter() - warm_start
    assert len(reads) == 1
    assert warm_latency < cold_latency
    exp.clear_assignment_cache()
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert all(value is not None for value in pool.map(
            lambda _: exp.assign("daily_intro_v1", user_id=42, now=now), range(8)))
    assert len(reads) == 2
    exp.clear_assignment_cache()
    monkeypatch.setattr(store, "load", lambda: (_ for _ in ()).throw(RuntimeError("Firestore down")))
    assert exp.assign("daily_intro_v1", user_id=42, now=now) is None


def test_stop_propagates_after_cache_ttl(monkeypatch):
    running = exp.start(planned(), now=NOW, analytics_ready=True)
    stopped = exp.stop(running, reason="Guardrail failed", operator="alice", now=NOW + timedelta(days=1))
    from services.repos import experiments as store
    records = {"daily_intro_v1": running}
    reads = []
    def load():
        reads.append(1)
        return records.copy()
    monkeypatch.setattr(store, "load", load)
    monkeypatch.setattr(product_analytics, "is_enabled", lambda: True)
    monkeypatch.setattr(product_analytics, "settings", lambda: product_analytics.Settings(salt="test-salt"))
    monkeypatch.setattr(product_analytics, "capture", lambda *args, **kwargs: None)
    monkeypatch.setattr(exp, "ASSIGNMENT_CACHE_TTL_SECONDS", 0.01)
    moment = NOW + timedelta(days=1)
    assert exp.assign("daily_intro_v1", user_id=42, now=moment) is not None
    records["daily_intro_v1"] = stopped
    assert exp.assign("daily_intro_v1", user_id=42, now=moment) is not None
    time.sleep(0.02)
    assert exp.assign("daily_intro_v1", user_id=42, now=moment) is None
    assert len(reads) == 2
