"""Verify that experiment lifecycle updates persist through Firestore transactions."""
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
