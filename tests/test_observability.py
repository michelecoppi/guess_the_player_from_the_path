"""Observability contract: structured records, Sentry reporting, context and redaction.

Sentry is exercised through the real SDK with an in-memory transport: `before_send`, the
logging integration and deduplication run exactly as in production, and nothing ever leaves
the process. A DSN on `example.invalid` would not resolve anyway.
"""
import asyncio
import importlib.util
import io
import json
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
import sentry_sdk
from sentry_sdk.transport import Transport

import config
from handlers import daily_job, error_handler, shop_handler
from services import observability, shop, task_queue
from services.observability import REDACTED, Settings

FAKE_DSN = "https://publickey@o0.ingest.example.invalid/1"
BOT_TOKEN_LIKE = "123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw1"
INIT_DATA = "query_id=AAH&user=%7B%22id%22%3A42%7D&auth_date=1700000000&hash=" + "ab" * 32


class MemoryTransport(Transport):
    def __init__(self, options=None):
        super().__init__(options)
        self.events = []

    def capture_envelope(self, envelope):
        for item in envelope.items:
            if item.type == "event":
                self.events.append(item.payload.json)


@pytest.fixture(autouse=True)
def clean_observability():
    observability._reset_for_tests()
    yield
    observability._reset_for_tests()


@pytest.fixture
def sentry():
    transport = MemoryTransport()
    observability.init(
        "bot", web=True, transport=transport,
        settings=Settings(service="bot", dsn=FAKE_DSN, environment="test", release="rev-42"),
    )
    assert observability.sentry_enabled()
    return transport


@pytest.fixture
def records():
    """Structured JSON lines, formatted exactly as on Cloud Run."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(observability._ContextFilter())
    handler.setFormatter(observability.JsonFormatter())
    root = logging.getLogger()
    previous_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    observability._state.settings = Settings(service="bot", environment="test", release="rev-42")

    def read():
        return [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]

    yield read
    root.removeHandler(handler)
    root.setLevel(previous_level)


def by_event(lines, name):
    return [line for line in lines if line.get("event") == name]


def event_data(event):
    """The event without stack-frame source lines: those quote this test file, secrets included."""
    clean = json.loads(json.dumps(event))
    for value in (clean.get("exception") or {}).get("values", []):
        for frame in (value.get("stacktrace") or {}).get("frames", []):
            for key in ("pre_context", "context_line", "post_context"):
                frame.pop(key, None)
    return json.dumps(clean)


# ---------------------------------------------------------------------------
# Structured records
# ---------------------------------------------------------------------------

def test_structured_record_has_stable_queryable_fields(records):
    with observability.bind(component="job", job="daily_job", request_id="req-1"):
        observability.log_event("daily.job.completed", day="2026-09-14", duration_ms=12.5, status="completed")

    [line] = by_event(records(), "daily.job.completed")
    assert line["severity"] == "INFO"
    assert line["message"] == "daily.job.completed"
    assert line["component"] == "job" and line["job"] == "daily_job"
    assert line["environment"] == "test" and line["release"] == "rev-42" and line["service"] == "bot"
    assert line["request_id"] == "req-1" and line["duration_ms"] == 12.5 and line["status"] == "completed"
    assert line["logger"] == "gtp.job" and line["time"]


def test_context_does_not_leak_outside_the_bound_block(records):
    with observability.bind(component="payment"):
        pass
    observability.log_event("broadcast.completed", component="broadcast")
    [line] = by_event(records(), "broadcast.completed")
    assert line["component"] == "broadcast"
    assert observability.current_context() == {}


def test_text_format_stays_readable_locally():
    record = logging.LogRecord("gtp.api", logging.WARNING, __file__, 1, "api.request.completed", None, None)
    with observability.bind(component="api", status_code=503):
        record._gtp_context = observability.current_context()
    line = observability.TextFormatter().format(record)
    assert line.startswith("WARNING gtp.api: api.request.completed [")
    assert "component=api" in line and "status_code=503" in line


def test_operation_records_duration_and_final_status(records):
    with observability.operation("broadcast.batch", component="broadcast", day="2026-09-14") as op:
        op["sent"] = 3
    [line] = by_event(records(), "broadcast.batch.completed")
    assert line["status"] == "completed" and line["sent"] == 3 and line["duration_ms"] >= 0

    with pytest.raises(ValueError):
        with observability.operation("daily.job", component="job"):
            raise ValueError("boom")
    [failed] = by_event(records(), "daily.job.failed")
    assert failed["severity"] == "ERROR" and failed["error_type"] == "ValueError" and "exception" in failed


def test_settings_default_to_json_on_cloud_run_and_text_locally():
    cloud = Settings.from_env(environ={"K_SERVICE": "bot", "K_REVISION": "bot-00042-abc"})
    assert (cloud.log_format, cloud.environment, cloud.release, cloud.dsn) == ("json", "production", "bot-00042-abc", "")
    local = Settings.from_env(environ={})
    assert (local.log_format, local.environment, local.release) == ("text", "development", None)
    explicit = Settings.from_env(environ={"K_REVISION": "r", "SENTRY_RELEASE": "1.2.3", "SENTRY_ENVIRONMENT": "staging",
                                          "LOG_FORMAT": "TEXT"})
    assert (explicit.release, explicit.environment, explicit.log_format) == ("1.2.3", "staging", "text")


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------

def test_nested_secrets_are_redacted_without_mutating_the_payload():
    payload = {
        "Authorization": "Bearer abc.def",
        "headers": {"Cookie": "session=1", "X-Task-Secret": "t" * 40, "x-cron-secret": "c" * 40},
        "items": [{"initData": INIT_DATA, "init_data": "x"}, {"telegram_bot_token": BOT_TOKEN_LIKE}],
        "nested": {"deeper": {"webhook_secret": "w", "generation_secret": "g", "sentry_dsn": FAKE_DSN,
                              "password": "p", "task_secret": "s", "token": "t", "item_id": "neon"}},
    }
    original = json.loads(json.dumps(payload))

    clean = observability.sanitize(payload)

    assert payload == original, "the application payload must never be mutated"
    assert clean["Authorization"] == REDACTED
    assert clean["headers"] == {"Cookie": REDACTED, "X-Task-Secret": REDACTED, "x-cron-secret": REDACTED}
    assert clean["items"][0] == {"initData": REDACTED, "init_data": REDACTED}
    assert clean["items"][1] == {"telegram_bot_token": REDACTED}
    deeper = clean["nested"]["deeper"]
    assert deeper.pop("item_id") == "neon"
    assert set(deeper.values()) == {REDACTED}


def test_secrets_inside_free_text_are_scrubbed(monkeypatch):
    assert observability.scrub_text(INIT_DATA) == REDACTED + " (initData)"
    url = f"https://api.telegram.org/bot{BOT_TOKEN_LIKE}/refundStarPayment"
    assert BOT_TOKEN_LIKE not in observability.scrub_text(url)
    assert "publickey" not in observability.scrub_text(f"bad dsn {FAKE_DSN}")
    assert "abc.def" not in observability.scrub_text("Authorization: Bearer abc.def")
    assert "Coppi" not in observability.scrub_text(r"Permission denied: 'C:\Users\Coppi\data\players.json'")
    monkeypatch.setenv("TASK_SECRET", "a-task-secret-that-has-no-pattern")
    assert "a-task-secret" not in observability.scrub_text("header value a-task-secret-that-has-no-pattern")


def test_structured_logs_never_contain_secrets(records):
    observability.log_event(
        "webapp.request.failed", logging.WARNING,
        headers={"authorization": "Bearer abc.def", "cookie": "sid=1"}, initData=INIT_DATA,
        detail=f"GET https://api.telegram.org/bot{BOT_TOKEN_LIKE}/getMe",
    )
    try:
        raise RuntimeError(f"telegram said no for bot{BOT_TOKEN_LIKE}")
    except RuntimeError as exc:
        observability.log_event("payment.refund.failed", logging.ERROR, exc_info=exc)

    raw = json.dumps(records())
    for secret in ("abc.def", "sid=1", BOT_TOKEN_LIKE, "ab" * 32):
        assert secret not in raw


def test_user_ref_is_stable_and_not_the_raw_id():
    ref = observability.user_ref(42)
    assert ref == observability.user_ref("42") and "42" != ref and len(ref) == 16
    assert observability.user_ref(None) is None


# ---------------------------------------------------------------------------
# Sentry initialisation
# ---------------------------------------------------------------------------

def test_without_dsn_sentry_is_never_initialised(monkeypatch):
    monkeypatch.setattr(sentry_sdk, "init", lambda *a, **kw: pytest.fail("Sentry must stay off without a DSN"))
    observability.init("bot", web=True, settings=Settings(dsn=""))
    assert observability.sentry_enabled() is False
    observability.log_event("daily.job.failed", logging.ERROR, exc_info=RuntimeError("x"))  # no client, no call


def test_initialisation_is_idempotent(monkeypatch):
    calls = []
    real_init = sentry_sdk.init
    monkeypatch.setattr(sentry_sdk, "init", lambda **kw: calls.append(kw) or real_init(**kw))
    settings = Settings(dsn=FAKE_DSN, environment="test")
    for _ in range(3):
        observability.init("bot", settings=settings, transport=MemoryTransport())
    assert len(calls) == 1
    handlers = [h for h in logging.getLogger().handlers if getattr(h, "_gtp_handler", False)]
    assert len(handlers) == 1


def test_sentry_privacy_defaults(monkeypatch):
    captured = {}
    monkeypatch.setattr(sentry_sdk, "init", lambda **kw: captured.update(kw))
    observability.init("bot", web=True, settings=Settings(dsn=FAKE_DSN))
    assert captured["send_default_pii"] is False
    assert captured["include_local_variables"] is False
    assert captured["max_request_body_size"] == "never"
    assert captured["auto_enabling_integrations"] is False
    assert captured["traces_sample_rate"] is None


def test_a_broken_sentry_setup_does_not_stop_the_app(monkeypatch):
    def explode(**kwargs):
        raise RuntimeError("cannot reach sentry")
    monkeypatch.setattr(sentry_sdk, "init", explode)
    observability.init("bot", settings=Settings(dsn=FAKE_DSN))
    assert observability.sentry_enabled() is False


def test_captured_errors_carry_component_tags_and_sanitised_context(sentry):
    with observability.bind(component="payment", route="/app/api/shop/buy", method="POST", request_id="req-9"):
        try:
            raise RuntimeError(f"refund failed for bot{BOT_TOKEN_LIKE}")
        except RuntimeError as exc:
            observability.log_event("payment.refund.failed", logging.ERROR, exc_info=exc,
                                    charge_id="ch_1", initData=INIT_DATA)

    [event] = sentry.events
    tags = event["tags"]
    assert tags["component"] == "payment" and tags["event"] == "payment.refund.failed"
    assert tags["route"] == "/app/api/shop/buy" and tags["method"] == "POST" and tags["request_id"] == "req-9"
    assert event["environment"] == "test" and event["release"] == "rev-42"
    assert event["contexts"]["observability"]["charge_id"] == "ch_1"
    assert event["contexts"]["observability"]["initData"] == REDACTED
    raw = event_data(event)
    assert BOT_TOKEN_LIKE not in raw and "ab" * 32 not in raw
    assert "user" not in event
    assert all("vars" not in frame for frame in event["exception"]["values"][0]["stacktrace"]["frames"])


def test_warnings_and_info_do_not_become_sentry_events(sentry):
    observability.log_event("payment.precheckout.rejected", reason="already_owned")
    observability.log_event("broadcast.delivery.failed", logging.WARNING, error_type="RetryAfter")
    assert sentry.events == []


# ---------------------------------------------------------------------------
# FastAPI
# ---------------------------------------------------------------------------

@pytest.fixture
def server(monkeypatch):
    monkeypatch.setattr(config, "BOT_TOKEN", "123456:test-token")
    monkeypatch.setattr(config, "WEBHOOK_SECRET", "a" * 48)
    monkeypatch.setattr(config, "TASK_SECRET", "b" * 48)
    spec = importlib.util.spec_from_file_location("observed_bot", Path(__file__).parents[1] / "bot.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def call(server, path, **kwargs):
    async def run():
        transport = httpx.ASGITransport(app=server.app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(kwargs.pop("method", "POST"), path, **kwargs)
    return asyncio.run(run())


def test_unexpected_api_exception_is_reported_once_with_route_and_request_id(sentry, server, monkeypatch, records):
    monkeypatch.setattr(server, "_webapp_user", lambda payload, cost=1: (42, {"language": "it"}))

    def broken(*args, **kwargs):
        raise RuntimeError("catalogue exploded")
    monkeypatch.setattr(server.shop, "catalogue_for", broken)

    response = call(server, "/app/api/shop", json={"initData": INIT_DATA, "note": "private"},
                    headers={"Authorization": "Bearer abc.def", "Cookie": "sid=1", "X-Task-Secret": "b" * 48})

    assert response.status_code == 500
    [event] = sentry.events
    assert event["tags"]["component"] == "api"
    assert event["tags"]["event"] == "api.request.failed"
    assert event["tags"]["route"] == "/app/api/shop" and event["tags"]["method"] == "POST"
    assert len(event["tags"]["request_id"]) == 32
    raw = event_data(event)
    for secret in ("abc.def", "sid=1", "b" * 48, "ab" * 32, "private"):
        assert secret not in raw
    headers = {k.lower(): v for k, v in event["request"]["headers"].items()}
    assert headers.get("x-task-secret") in (None, REDACTED)
    assert headers.get("authorization") in (None, REDACTED) and headers.get("cookie") in (None, REDACTED)
    assert "data" not in event["request"] and "cookies" not in event["request"]
    [line] = by_event(records(), "api.request.failed")
    assert line["request_id"] == event["tags"]["request_id"] and line["status_code"] == 500


def test_expected_client_errors_do_not_reach_sentry(sentry, server, monkeypatch, records):
    assert call(server, "/app/api/me", json={}).status_code == 401
    assert call(server, "/internal/broadcast", json={"day": "2026-09-14"}).status_code == 403
    monkeypatch.setattr(server.work_receipts, "claim", lambda key, **kw: "busy")
    busy = call(server, "/internal/telegram-update", json={"update_id": 7},
                headers={"X-Task-Secret": server.TASK_SECRET})
    assert busy.status_code == 503
    assert sentry.events == []
    statuses = {(line["route"], line["status_code"]) for line in by_event(records(), "api.request.completed")}
    assert ("/app/api/me", 401) in statuses and ("/internal/telegram-update", 503) in statuses


def test_responses_carry_a_server_generated_request_id(server, records):
    response = call(server, "/app/api/me", json={}, headers={"X-Request-ID": "client-chosen"})
    request_id = response.headers["X-Request-ID"]
    assert request_id != "client-chosen" and len(request_id) == 32
    [line] = by_event(records(), "api.request.completed")
    assert line["request_id"] == request_id and line["component"] == "api" and line["method"] == "POST"
    assert "Server-Timing" in response.headers


def test_cloud_task_metadata_is_bound_to_the_request(server, monkeypatch, records):
    monkeypatch.setattr(server, "broadcast_batch", AsyncMock(return_value={"sent": 0, "next_cursor": None}))
    response = call(server, "/internal/broadcast", json={"day": "2026-09-14"}, headers={
        "X-Task-Secret": server.TASK_SECRET, "X-CloudTasks-TaskName": "abc123",
        "X-CloudTasks-TaskRetryCount": "2", "X-CloudTasks-QueueName": "broadcast",
    })
    assert response.status_code == 200
    [line] = by_event(records(), "api.request.completed")
    assert line["component"] == "broadcast" and line["task_name"] == "abc123" and line["task_retry_count"] == 2


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

def telegram_update(text=None, **extra):
    message = SimpleNamespace(text=text, caption=None, successful_payment=extra.pop("payment", None),
                              reply_text=AsyncMock())
    return SimpleNamespace(
        update_id=77, effective_message=message, callback_query=None, pre_checkout_query=None,
        effective_user=SimpleNamespace(id=42, language_code="it"),
        effective_chat=SimpleNamespace(type="private"), **extra,
    )


def test_describe_update_keeps_only_safe_context():
    fields = error_handler.describe_update(telegram_update("/admin_support_reply 42 very private words"))
    assert fields["component"] == "admin" and fields["command"] == "admin_support_reply"
    assert fields["update_type"] == "message" and fields["chat_type"] == "private"
    assert "42" not in json.dumps(fields) and "private words" not in json.dumps(fields)
    assert error_handler.describe_update(telegram_update("/admin_refund ch_1"))["component"] == "payment"
    plain = error_handler.describe_update(telegram_update("Del Piero"))
    assert plain["component"] == "telegram" and "command" not in plain


def test_telegram_handler_failure_is_reported_with_update_context(sentry, monkeypatch):
    monkeypatch.setattr(error_handler, "ADMIN_TELEGRAM_IDS", [])
    update = telegram_update("/shop my secret message")
    context = SimpleNamespace(error=KeyError("missing"), bot=SimpleNamespace(send_message=AsyncMock()))

    asyncio.run(error_handler.on_error(update, context))

    [event] = sentry.events
    assert event["tags"]["component"] == "telegram" and event["tags"]["command"] == "shop"
    assert event["tags"]["event"] == "telegram.update.failed" and event["tags"]["update_type"] == "message"
    assert "my secret message" not in event_data(event)
    update.effective_message.reply_text.assert_awaited()


def test_already_reported_failures_are_not_reported_twice(sentry, monkeypatch):
    monkeypatch.setattr(error_handler, "ADMIN_TELEGRAM_IDS", [])
    error = RuntimeError("delivery failed")
    observability.log_event("payment.delivery.failed", logging.ERROR, exc_info=error, component="payment")
    context = SimpleNamespace(error=error, bot=SimpleNamespace(send_message=AsyncMock()))

    asyncio.run(error_handler.on_error(telegram_update(payment=SimpleNamespace()), context))

    assert [e["tags"]["event"] for e in sentry.events] == ["payment.delivery.failed"]


# ---------------------------------------------------------------------------
# Jobs and Cloud Tasks
# ---------------------------------------------------------------------------

def test_daily_job_failure_is_reported_and_reraised(sentry, monkeypatch):
    def unavailable(day):
        raise RuntimeError("firestore down")
    monkeypatch.setattr(daily_job.broadcast_store, "get_job", unavailable)

    with pytest.raises(RuntimeError, match="firestore down"):
        asyncio.run(daily_job.update_daily_challenge())

    [event] = sentry.events
    assert event["tags"]["event"] == "daily.job.failed"
    assert event["tags"]["component"] == "job" and event["tags"]["job"] == "daily_job"


def test_a_failure_reported_deeper_is_not_reported_again_by_the_job(sentry, monkeypatch, records):
    monkeypatch.setattr(daily_job.broadcast_store, "get_job", lambda day: {"monthly_result": None})

    def refuse(**kwargs):
        raise RuntimeError("queue unavailable")
    monkeypatch.setattr(config, "TASKS_QUEUE", "projects/p/locations/l/queues/tasks")
    monkeypatch.setattr(config, "BROADCAST_QUEUE", "projects/p/locations/l/queues/broadcast")
    monkeypatch.setattr(config, "PUBLIC_BASE_URL", "https://example.invalid")
    monkeypatch.setattr(config, "TASK_SECRET", "s" * 40)
    monkeypatch.setattr(task_queue, "client", lambda: SimpleNamespace(create_task=refuse))

    with pytest.raises(RuntimeError):
        asyncio.run(daily_job.update_daily_challenge())

    assert [e["tags"]["event"] for e in sentry.events] == ["cloud_task.enqueue.failed"]
    [job] = by_event(records(), "daily.job.failed")
    assert job["severity"] == "WARNING" and "exception" not in job


def _failing_broadcast(monkeypatch):
    monkeypatch.setattr(daily_job.broadcast_store, "get_job", lambda day: {"reference_day": "2026-09-13"})
    monkeypatch.setattr(daily_job.broadcast_store, "page", lambda day, cursor: ([], None))
    monkeypatch.setattr(daily_job.broadcast_store, "add_sent", lambda day, sent: None)
    monkeypatch.setattr(daily_job, "_broadcast", AsyncMock(return_value=(1, 2)))


def test_a_retryable_broadcast_page_is_a_warning_until_retries_pile_up(sentry, monkeypatch, records):
    _failing_broadcast(monkeypatch)
    with pytest.raises(RuntimeError, match="Transient broadcast failure"):
        asyncio.run(daily_job.broadcast_batch("2026-09-14"))
    assert sentry.events == []
    [line] = by_event(records(), "broadcast.batch.retry")
    assert line["severity"] == "WARNING" and line["sent"] == 1 and line["errors"] == 2

    with observability.bind(task_retry_count=observability.RETRY_ESCALATION):
        with pytest.raises(RuntimeError):
            asyncio.run(daily_job.broadcast_batch("2026-09-14"))
    [event] = sentry.events
    assert event["tags"]["event"] == "broadcast.batch.retry" and event["tags"]["component"] == "broadcast"


def test_enqueue_failure_is_reported_without_the_task_payload(sentry, monkeypatch):
    def refuse(**kwargs):
        raise RuntimeError("queue unavailable")
    monkeypatch.setattr(config, "TASKS_QUEUE", "projects/p/locations/l/queues/tasks")
    monkeypatch.setattr(config, "BROADCAST_QUEUE", "projects/p/locations/l/queues/broadcast")
    monkeypatch.setattr(config, "PUBLIC_BASE_URL", "https://example.invalid")
    monkeypatch.setattr(config, "TASK_SECRET", "s" * 40)
    monkeypatch.setattr(task_queue, "client", lambda: SimpleNamespace(create_task=refuse))

    with pytest.raises(RuntimeError):
        task_queue.enqueue("/internal/telegram-update", {"message": {"text": "private chat text"}}, "telegram-1")

    [event] = sentry.events
    assert event["tags"]["event"] == "cloud_task.enqueue.failed"
    raw = event_data(event)
    assert "private chat text" not in raw and "s" * 40 not in raw


# ---------------------------------------------------------------------------
# Candidate ingestion
# ---------------------------------------------------------------------------

def test_candidate_source_failure_is_reported_with_ingestion_component(sentry, tmp_path):
    from services.candidate_player import CandidatePlayer, CandidateState
    from services.candidate_review import AdminIdentity, CandidateReviewService, ReviewStatus
    from services.repos.candidates import FileCandidatePlayerRepository

    players = tmp_path / "players.json"
    players.write_text(json.dumps({"players": []}), encoding="utf-8")
    repo = FileCandidatePlayerRepository(storage_dir=tmp_path / "candidates")
    candidate = CandidatePlayer(candidate_id="cand_obs", source="wikipedia", source_id="Some_Page",
                                full_name="Raw Provider Name")
    candidate.transition_to(CandidateState.FETCHED, reason="fetched")
    candidate.transition_to(CandidateState.REVIEW_REQUIRED, reason="needs review")
    repo.save(candidate)
    service = CandidateReviewService(candidate_repo=repo, players_path=players, backup_dir=tmp_path / "backup",
                                     admin_ids=[100], current_year_provider=lambda: 2026)

    def provider_down(source, source_id):
        raise ConnectionError("provider down")

    result = service.retry_ingestion(AdminIdentity(user_id=100, username="a"), "cand_obs",
                                     expected_revision=repo.get_by_id("cand_obs").revision,
                                     adapter_fetcher=provider_down)

    assert result.status == ReviewStatus.SOURCE_ERROR
    [event] = sentry.events
    assert event["tags"]["event"] == "candidate.ingestion.source_failed"
    assert event["tags"]["component"] == "ingestion" and event["tags"]["operation"] == "retry_ingestion"
    assert event["tags"]["source"] == "wikipedia"
    assert "Raw Provider Name" not in event_data(event)


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------

def payment_update(payload, charge_id="ch_obs", stars=25):
    payment = SimpleNamespace(invoice_payload=payload, telegram_payment_charge_id=charge_id, total_amount=stars)
    message = SimpleNamespace(successful_payment=payment, reply_text=AsyncMock())
    return SimpleNamespace(effective_user=SimpleNamespace(id=42, first_name="Anna", language_code="it"),
                           effective_message=message)


@pytest.fixture
def shop_store(monkeypatch):
    monkeypatch.setattr(shop_handler.firebase_service, "save_user", lambda *a: None)
    monkeypatch.setattr("handlers.keyboards.get_user_data", lambda uid: {})


def test_undeliverable_payment_is_reported_without_the_signed_payload(sentry, shop_store):
    payload = "cosmetic:sparito:42"
    asyncio.run(shop_handler.successful_payment_callback(payment_update(payload), None))

    [event] = sentry.events
    assert event["tags"]["event"] == "payment.delivery.failed" and event["tags"]["component"] == "payment"
    assert event["contexts"]["observability"]["charge_id"] == "ch_obs"
    assert payload not in event_data(event)


def test_delivery_exception_is_reported_and_reraised(sentry, shop_store, monkeypatch):
    def firestore_down(*args, **kwargs):
        raise RuntimeError("firestore down")
    monkeypatch.setattr(shop.firebase_service, "deliver_purchase", firestore_down)

    with pytest.raises(RuntimeError):
        asyncio.run(shop_handler.successful_payment_callback(payment_update(shop.payload_for(42, "neon")), None))

    [event] = sentry.events
    assert event["tags"]["event"] == "payment.delivery.failed" and event["tags"]["status"] == "failed"
    assert event["contexts"]["observability"]["item_id"] == "neon"


def test_business_refusals_at_precheckout_are_not_errors(sentry, shop_store, monkeypatch, records):
    monkeypatch.setattr(shop_handler.firebase_service, "get_user_data",
                        lambda uid: {"cosmetics": {"owned": ["neon"], "equipped": {}}})
    query = SimpleNamespace(invoice_payload=shop.payload_for(42, "neon"), id="c1", currency="XTR", total_amount=25,
                            from_user=SimpleNamespace(id=42, language_code="it"), answer=AsyncMock())
    update = SimpleNamespace(pre_checkout_query=query, effective_user=query.from_user)

    asyncio.run(shop_handler.precheckout_callback(update, None))

    assert sentry.events == []
    [line] = by_event(records(), "payment.precheckout.rejected")
    assert line["severity"] == "INFO" and line["reason"] != "invalid_payload"
    assert "invoice_payload" not in line


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

def test_unexpected_admin_action_failure_is_reported(sentry, monkeypatch):
    from admin_pages import shared

    shown = []
    monkeypatch.setattr(shared.st, "error", shown.append)

    def broken_write():
        raise OSError("disk full")

    shared.guarded(broken_write, "ok")

    [event] = sentry.events
    assert event["tags"]["event"] == "admin.action.failed" and event["tags"]["component"] == "admin"
    assert shown and "disk full" in shown[0]


def test_expected_admin_refusals_are_not_errors(sentry, monkeypatch):
    from admin_pages import shared

    monkeypatch.setattr(shared.st, "error", lambda message: None)

    def refused():
        raise shared.ContentAdminError("giorno gia' assegnato")

    shared.guarded(refused, "ok")
    assert sentry.events == []
