import asyncio
import importlib.util
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from google.api_core.exceptions import AlreadyExists

import config
from handlers import error_handler, guess_handler
from services import rate_limit, task_queue, work_receipts


@pytest.fixture
def server(monkeypatch):
    monkeypatch.setattr(config, "BOT_TOKEN", "123456:test-token")
    monkeypatch.setattr(config, "WEBHOOK_SECRET", "a" * 48)
    monkeypatch.setattr(config, "TASK_SECRET", "b" * 48)
    spec = importlib.util.spec_from_file_location("hardened_bot", Path(__file__).parents[1] / "bot.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def request(server, path, *, method="POST", **kwargs):
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test") as client:
            return await client.request(method, path, **kwargs)
    return asyncio.run(run())


@pytest.mark.parametrize("secret", [None, "wrong", "", "a" * 47])
def test_forged_webhook_is_rejected_before_parsing(server, monkeypatch, secret):
    calls = []
    monkeypatch.setattr(server.task_queue, "enqueue", lambda *a, **kw: calls.append(a))
    headers = {"X-Telegram-Bot-Api-Secret-Token": secret} if secret is not None else {}
    response = request(server, "/webhook", content=b"not even json", headers=headers)
    assert response.status_code == 403
    assert calls == []


def test_webhook_acknowledges_durable_enqueue_without_processing(server, monkeypatch):
    calls = []
    monkeypatch.setattr(server.task_queue, "enqueue", lambda *a, **kw: calls.append(a))
    processor = AsyncMock()
    monkeypatch.setattr(server.telegram_app, "process_update", processor)
    update = {"update_id": 123}
    for _ in range(2):
        response = request(server, "/webhook", json=update,
                           headers={"X-Telegram-Bot-Api-Secret-Token": server.WEBHOOK_SECRET})
        assert response.status_code == 200
    assert calls == [("/internal/telegram-update", update, "telegram-123")] * 2
    processor.assert_not_called()


def test_webhook_queue_failure_is_not_acknowledged(server, monkeypatch):
    def fail(*a, **kw):
        raise RuntimeError("queue unavailable")
    monkeypatch.setattr(server.task_queue, "enqueue", fail)

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app, raise_app_exceptions=False),
                                     base_url="http://test") as client:
            response = await client.post("/webhook", json={"update_id": 123},
                                         headers={"X-Telegram-Bot-Api-Secret-Token": server.WEBHOOK_SECRET})
            assert response.status_code == 500
    asyncio.run(run())


def test_lifespan_registers_secret_and_shuts_down(server, monkeypatch):
    initialize, shutdown, register = AsyncMock(), AsyncMock(), AsyncMock()
    monkeypatch.setattr(server, "WEBHOOK_URL", "https://example.test/webhook")
    monkeypatch.setattr(server.telegram_app, "initialize", initialize)
    monkeypatch.setattr(server.telegram_app, "shutdown", shutdown)
    monkeypatch.setattr(type(server.telegram_app.bot), "set_webhook", register)
    monkeypatch.setattr(server, "_register_bot_commands", AsyncMock())
    monkeypatch.setattr(server.task_queue, "validate_configuration", lambda: None)

    async def run():
        async with server.lifespan(server.app):
            assert initialize.await_count == 1
    asyncio.run(run())
    register.assert_awaited_once_with(server.WEBHOOK_URL, secret_token=server.WEBHOOK_SECRET)
    shutdown.assert_awaited_once()


def test_missing_webhook_secret_fails_closed_at_startup(server, monkeypatch):
    monkeypatch.setattr(server, "WEBHOOK_SECRET", "")
    async def run():
        async with server.lifespan(server.app):
            pytest.fail("Should never start without a secret")
    with pytest.raises(RuntimeError, match="WEBHOOK_SECRET"):
        asyncio.run(run())


@pytest.mark.parametrize("path", ["/internal/telegram-update", "/internal/broadcast", "/internal/monthly-close"])
def test_workers_require_separate_secret(server, path):
    assert request(server, path, json={"update_id": 1, "day": "2026-09-09"},
                   headers={"X-Task-Secret": server.WEBHOOK_SECRET}).status_code == 403


def test_worker_skips_delivered_or_uncertain_updates(server, monkeypatch):
    process = AsyncMock()
    finished = []
    states = iter(["claimed", "done", "uncertain", "busy"])
    monkeypatch.setattr(server.telegram_app, "process_update", process)
    monkeypatch.setattr(work_receipts, "claim", lambda key, **kw: next(states))
    monkeypatch.setattr(work_receipts, "finish", finished.append)
    codes = [request(server, "/internal/telegram-update", json={"update_id": 1},
                     headers={"X-Task-Secret": server.TASK_SECRET}).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 503]
    assert process.await_count == 1
    assert finished == ["telegram-1"]


def test_authenticated_rate_limit_precedes_firestore(server, monkeypatch):
    reads = []
    monkeypatch.setattr(server, "user_id_from_init_data", lambda *args: 42)
    monkeypatch.setattr(server.firebase_service, "get_user_data", lambda uid: reads.append(uid) or {})
    monkeypatch.setattr(server, "api_limiter", rate_limit.TokenBucket(capacity=1, refill=0.01))
    assert request(server, "/app/api/shop", json={}).status_code == 200
    response = request(server, "/app/api/shop", json={})
    assert response.status_code == 429
    assert int(response.headers["retry-after"]) > 0
    assert reads == [42]


@pytest.mark.parametrize("path", ["/app", "/privacy", "/terms", "/legal.css", "/app/client.js"])
def test_static_etag_revalidation(server, path):
    first = request(server, path, method="GET")
    assert first.status_code == 200
    assert "must-revalidate" in first.headers["cache-control"]
    second = request(server, path, method="GET", headers={"If-None-Match": first.headers["etag"]})
    assert second.status_code == 304
    assert second.content == b""
    assert request(server, path, method="GET", headers={"If-None-Match": '"old-deploy"'}).status_code == 200


def test_token_bucket_is_atomic_refills_and_bounds_memory():
    clock = [0.0]
    bucket = rate_limit.TokenBucket(capacity=3, refill=1, max_users=2, clock=lambda: clock[0])
    with ThreadPoolExecutor(max_workers=8) as pool:
        waits = list(pool.map(lambda _: bucket.retry_after(1), range(100)))
    assert waits.count(0) == 3
    assert bucket.retry_after(2, 3) == 0
    clock[0] = 2
    assert bucket.retry_after(1, 3) == 1
    clock[0] = 3
    assert bucket.retry_after(1, 3) == 0
    bucket.retry_after(3)
    assert len(bucket._users) == 2


def test_actual_guess_handler_keeps_event_loop_responsive(monkeypatch):
    entered = threading.Event()
    release = threading.Event()

    def read_user(uid):
        entered.set()
        assert release.wait(3)
        return None

    monkeypatch.setattr(guess_handler.firebase_service, "get_user_data", read_user)
    monkeypatch.setattr(guess_handler, "get_today_challenge", lambda: None)
    update = SimpleNamespace(effective_user=SimpleNamespace(id=42, language_code="it"),
                             effective_chat=SimpleNamespace(type="private"),
                             effective_message=SimpleNamespace(text="Messi", chat=SimpleNamespace(type="private"),
                                                               reply_text=AsyncMock()))

    async def run():
        pending = asyncio.create_task(guess_handler.free_text_guess(update, SimpleNamespace(args=[])))
        try:
            assert await asyncio.to_thread(entered.wait, 1)
            assert not pending.done()
            await asyncio.wait_for(asyncio.sleep(0), 0.1)
        finally:
            release.set()
            await pending
    asyncio.run(run())


def test_error_handler_reports_reference_and_survives_delivery_failure(monkeypatch):
    monkeypatch.setattr(error_handler, "ADMIN_TELEGRAM_IDS", [7, 8])
    message = AsyncMock(side_effect=RuntimeError("blocked"))
    bot = SimpleNamespace(send_message=AsyncMock(side_effect=[RuntimeError("unavailable"), None]))
    update = SimpleNamespace(update_id=123, effective_message=SimpleNamespace(reply_text=message))
    asyncio.run(error_handler.on_error(update, SimpleNamespace(error=ValueError("private payload"), bot=bot)))
    assert "123" in message.call_args.args[0]
    assert bot.send_message.await_count == 2
    assert "private payload" not in str(bot.send_message.call_args_list)


def test_error_handler_speaks_the_language_of_the_client(monkeypatch):
    """Il bot e' trilingue anche quando si rompe.

    La lingua arriva da `language_code`, che e' gia' dentro l'update: leggere quella
    salvata con /language vorrebbe dire un accesso a Firestore dentro il gestore che gira
    **dopo** un guasto, cioe' un secondo modo di fallire proprio dove non si puo'."""
    monkeypatch.setattr(error_handler, "ADMIN_TELEGRAM_IDS", [])
    seen = {}
    for code, expected in (("es-MX", "Algo ha salido mal"), ("pt-BR", "Something went wrong"), (None, "Qualcosa")):
        message = AsyncMock()
        update = SimpleNamespace(update_id=9, effective_message=SimpleNamespace(reply_text=message),
                                 effective_user=SimpleNamespace(language_code=code))
        asyncio.run(error_handler.on_error(update, SimpleNamespace(error=ValueError("x"), bot=None)))
        seen[code] = message.call_args.args[0]
        assert expected in seen[code] and "9" in seen[code]


def test_cloud_task_names_and_duplicate_producer(monkeypatch):
    monkeypatch.setattr(config, "TASKS_QUEUE", "projects/p/locations/r/queues/telegram")
    monkeypatch.setattr(config, "BROADCAST_QUEUE", "projects/p/locations/r/queues/broadcast")
    monkeypatch.setattr(config, "PUBLIC_BASE_URL", "https://example.test")
    monkeypatch.setattr(config, "TASK_SECRET", "b" * 48)
    calls = []

    def create_task(**kwargs):
        calls.append(kwargs)
        raise AlreadyExists("same task")

    monkeypatch.setattr(task_queue, "client", lambda: SimpleNamespace(create_task=create_task))
    for _ in range(2):
        task_queue.enqueue("/internal/broadcast", {"day": "2026-09-09"}, "same-key", broadcast=True)
    assert calls[0] == calls[1]
    task = calls[0]["request"]["task"]
    assert "/queues/broadcast/tasks/" in task["name"]
    assert task["http_request"]["headers"]["X-Task-Secret"] == config.TASK_SECRET


def test_an_interrupted_update_reaches_an_admin(server, monkeypatch):
    """La ricevuta `uncertain` e' il solo guasto che nessuno vedrebbe mai.

    La richiesta torna 200, l'utente non riceve niente e non viene sollevata nessuna
    eccezione: senza questo avviso resterebbe una riga di logging.error dentro Cloud Run,
    che si va a cercare solo se si sa gia' di doverlo fare."""
    sent = []
    monkeypatch.setattr(config, "ADMIN_TELEGRAM_IDS", [7])
    monkeypatch.setattr(server.alerts, "ADMIN_TELEGRAM_IDS", [7])
    monkeypatch.setattr(server.alerts, "get_bot",
                        lambda: SimpleNamespace(send_message=AsyncMock(side_effect=lambda **kw: sent.append(kw))))
    monkeypatch.setattr(work_receipts, "claim", lambda key, **kw: "uncertain")

    response = request(server, "/internal/telegram-update",
                       json={"update_id": 55, "message": {"message_id": 1, "date": 0,
                                                          "chat": {"id": 3, "type": "private"},
                                                          "from": {"id": 42, "is_bot": False, "first_name": "T"}}},
                       headers={"X-Task-Secret": server.TASK_SECRET})

    assert response.status_code == 200 and response.json() == {"status": "uncertain"}
    assert len(sent) == 1 and sent[0]["chat_id"] == 7
    assert "55" in sent[0]["text"] and "42" in sent[0]["text"]


def test_a_normal_update_does_not_wake_an_admin(server, monkeypatch):
    """Se ogni guasto diventasse un messaggio, il canale degli avvisi smetterebbe di voler
    dire 'guarda questo'. Qui l'update passa: nessun avviso."""
    sent = []
    monkeypatch.setattr(server.alerts, "ADMIN_TELEGRAM_IDS", [7])
    monkeypatch.setattr(server.alerts, "get_bot",
                        lambda: SimpleNamespace(send_message=AsyncMock(side_effect=lambda **kw: sent.append(kw))))
    monkeypatch.setattr(server.telegram_app, "process_update", AsyncMock())
    monkeypatch.setattr(work_receipts, "claim", lambda key, **kw: "claimed")
    monkeypatch.setattr(work_receipts, "finish", lambda key: None)

    assert request(server, "/internal/telegram-update", json={"update_id": 56},
                   headers={"X-Task-Secret": server.TASK_SECRET}).status_code == 200
    assert sent == []
