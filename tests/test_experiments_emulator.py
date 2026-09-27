"""Verify that experiment lifecycle updates persist through Firestore transactions."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest

from services import experiments
from services.repos import experiments as repo


def test_experiment_registry_lifecycle_in_firestore(emulator_db):
    planned = experiments.plan("daily_intro_v1", "Shorter intro increases completion",
                               "daily_completion_rate", 7, "Short intro")
    repo.create(planned)
    assert repo.load()["daily_intro_v1"]["status"] == "planned"
    with pytest.raises(ValueError, match="already exists"):
        repo.create(planned)

    now = datetime(2026, 9, 27, tzinfo=timezone.utc)
    repo.update("daily_intro_v1", lambda row: experiments.start(
        row, now=now, analytics_ready=True))
    assert repo.load()["daily_intro_v1"]["ends_at"] == now + timedelta(days=7)
    with pytest.raises(ValueError, match="duration"):
        repo.update("daily_intro_v1", lambda row: experiments.finish(
            row, now=now, summary="early", evidence_url="https://example.test/result"))
    assert repo.load()["daily_intro_v1"]["status"] == "running"

    repo.update("daily_intro_v1", lambda row: experiments.finish(
        row, now=now + timedelta(days=7), summary="completed",
        evidence_url="https://example.test/result"))
    repo.update("daily_intro_v1", lambda row: experiments.decide(row, "iterate"))
    assert repo.load()["daily_intro_v1"]["decision"] == "iterate"


def test_early_stop_during_concurrent_reads_is_durable(emulator_db):
    now = datetime(2026, 9, 27, tzinfo=timezone.utc)
    repo.create(experiments.plan("daily_intro_v1", "Shorter intro increases completion",
                                 "daily_completion_rate", 7, "Short intro"))
    repo.update("daily_intro_v1", lambda row: experiments.start(
        row, now=now, analytics_ready=True))

    def assign_from_store(_):
        return experiments.variant_for_subject(
            repo.load()["daily_intro_v1"], user_id=42, now=now + timedelta(days=1))

    with ThreadPoolExecutor(max_workers=3) as pool:
        reads = [pool.submit(assign_from_store, index) for index in range(2)]
        stopped = pool.submit(repo.update, "daily_intro_v1", lambda row: experiments.stop(
            row, reason="Guardrail failed", operator="alice", now=now + timedelta(days=1)))
        assert stopped.result()["status"] == "stopped"
        assert all(read.result() in (None, "control", "treatment") for read in reads)
    persisted = repo.load()["daily_intro_v1"]
    assert persisted["status"] == "stopped"
    assert persisted["stop"]["reason"] == "Guardrail failed"
    assert persisted["stop"]["operator"] == "alice"
    assert experiments.variant_for_subject(persisted, user_id=42, now=now + timedelta(days=1)) is None
    with pytest.raises(ValueError, match="running"):
        repo.update("daily_intro_v1", lambda row: experiments.stop(
            row, reason="again", operator="bob", now=now + timedelta(days=1)))
