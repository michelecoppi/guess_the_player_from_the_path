"""HTTP boundary of POST /internal/daily-job: only Cloud Scheduler, with the shared secret.

The endpoint is not changed here; these tests pin down that it fails closed."""
import asyncio
import importlib.util
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest

import config

SECRET = "g" * 48


def load_bot(monkeypatch, generation_secret):
    monkeypatch.setattr(config, "BOT_TOKEN", "123456:test-token")
    monkeypatch.setattr(config, "WEBHOOK_SECRET", "a" * 48)
    monkeypatch.setattr(config, "TASK_SECRET", "b" * 48)
    monkeypatch.setattr(config, "GENERATION_SECRET", generation_secret)
    spec = importlib.util.spec_from_file_location("cron_bot", Path(__file__).parents[1] / "bot.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    job = AsyncMock(return_value={"day": "2026-09-14", "status": "queued"})
    monkeypatch.setattr(module, "update_daily_challenge", job)
    return module, job


def trigger(server, headers=None):
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test") as client:
            return await client.post("/internal/daily-job", headers=headers or {})
    return asyncio.run(run())


def test_missing_cron_header_is_forbidden(monkeypatch):
    server, job = load_bot(monkeypatch, SECRET)
    assert trigger(server).status_code == 403
    job.assert_not_called()


@pytest.mark.parametrize("supplied", ["wrong", "", SECRET[:-1], SECRET + "x", SECRET.upper()])
def test_incorrect_cron_secret_is_forbidden(monkeypatch, supplied):
    server, job = load_bot(monkeypatch, SECRET)
    assert trigger(server, {"x-cron-secret": supplied}).status_code == 403
    job.assert_not_called()


def test_correct_cron_secret_runs_the_daily_job(monkeypatch):
    server, job = load_bot(monkeypatch, SECRET)
    response = trigger(server, {"x-cron-secret": SECRET})
    assert response.status_code == 200 and response.json() == {"status": "ok"}
    job.assert_awaited_once_with()


@pytest.mark.parametrize("configured", [None, ""])
@pytest.mark.parametrize("supplied", [None, "", "anything"])
def test_without_generation_secret_the_endpoint_fails_closed(monkeypatch, configured, supplied):
    server, job = load_bot(monkeypatch, configured)
    headers = {} if supplied is None else {"x-cron-secret": supplied}
    assert trigger(server, headers).status_code == 403
    job.assert_not_called()
