import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

import config
from apps.api import miniapp
from services import firebase_service


@pytest.fixture
def server(monkeypatch):
    monkeypatch.setattr(config, "BOT_TOKEN", "123456:test-token")
    monkeypatch.setattr(config, "WEBHOOK_SECRET", "a" * 48)
    monkeypatch.setattr(config, "TASK_SECRET", "b" * 48)
    spec = importlib.util.spec_from_file_location("report_bot", Path(__file__).parents[1] / "bot.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def request(server, path, **kwargs):
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test") as client:
            return await client.post(path, **kwargs)
    return asyncio.run(run())


def test_report_reaches_every_admin(server, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TELEGRAM_IDS", [7, 8])
    monkeypatch.setattr(miniapp, "user_id_from_init_data", lambda *args: 42)
    monkeypatch.setattr(firebase_service, "get_user_data", lambda uid: {"first_name": "Anna"})
    sent = []

    async def send_message(**kwargs):
        sent.append(kwargs)

    monkeypatch.setattr(server.telegram_app, "bot", SimpleNamespace(send_message=send_message))

    response = request(server, "/app/api/support/report", json={"message": "Le presenze del Milan sono sbagliate"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert [item["chat_id"] for item in sent] == [7, 8]
    assert all("Telegram ID: 42" in item["text"] for item in sent)
    assert all("Le presenze del Milan sono sbagliate" in item["text"] for item in sent)
    assert all("/admin_report_reply 42" in item["text"] for item in sent)


def test_report_requires_a_message(server, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TELEGRAM_IDS", [7])
    monkeypatch.setattr(miniapp, "user_id_from_init_data", lambda *args: 42)
    monkeypatch.setattr(firebase_service, "get_user_data", lambda uid: {"first_name": "Anna"})

    response = request(server, "/app/api/support/report", json={"message": "   "})

    assert response.status_code == 400


def test_report_fails_closed_without_admins(server, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TELEGRAM_IDS", [])
    monkeypatch.setattr(miniapp, "user_id_from_init_data", lambda *args: 42)
    monkeypatch.setattr(firebase_service, "get_user_data", lambda uid: {"first_name": "Anna"})

    response = request(server, "/app/api/support/report", json={"message": "Qualcosa non va"})

    assert response.status_code == 503


def test_report_requires_registration(server, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TELEGRAM_IDS", [7])
    monkeypatch.setattr(miniapp, "user_id_from_init_data", lambda *args: 42)
    monkeypatch.setattr(firebase_service, "get_user_data", lambda uid: None)

    response = request(server, "/app/api/support/report", json={"message": "Qualcosa non va"})

    assert response.status_code == 404
