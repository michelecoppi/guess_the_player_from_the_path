"""PostHog delivery on Cloud Run (#138): say at startup why events would not be sent, and
flush the queue before a request returns instead of trusting the background thread."""
import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from apps.api import observe
from services import product_analytics as analytics

SALT = "analytics-salt-" + "x" * 20


@pytest.fixture(autouse=True)
def clean_analytics():
    analytics._reset_for_tests()
    yield
    analytics._reset_for_tests()


def statuses(monkeypatch):
    logged = []
    monkeypatch.setattr(analytics.observability, "log_event",
                        lambda event, level=None, **fields: logged.append((event, fields)))
    return logged


def init(monkeypatch, *, enabled=True, api_key="phc_test", salt=SALT, client=None):  # pragma: allowlist secret
    client = client if client is not None else MagicMock()
    monkeypatch.setattr(analytics, "_build_client", lambda settings: client)
    analytics.init(settings=analytics.Settings(enabled=enabled, api_key=api_key, salt=salt,
                                               environment="production" if enabled else "development"))
    return client


@pytest.mark.parametrize("kwargs, sending, reasons", [
    ({}, True, []),
    ({"salt": ""}, False, ["missing_salt"]),
    ({"api_key": "", "enabled": False}, False, ["missing_api_key"]),
    ({"enabled": False}, False, ["disabled_for_environment"]),
])
def test_startup_status_names_why_events_would_be_dropped(monkeypatch, kwargs, sending, reasons):
    logged = statuses(monkeypatch)
    init(monkeypatch, **kwargs)
    [(event, fields)] = [row for row in logged if row[0] == "product_analytics.status"]
    assert fields["sending"] is sending
    assert fields["reasons"] == reasons
    assert "phc_test" not in repr(fields) and SALT not in repr(fields)


def test_flush_pending_only_flushes_after_a_capture(monkeypatch):
    client = init(monkeypatch)
    analytics.flush_pending()
    client.flush.assert_not_called()

    analytics.capture(analytics.Event.BOT_STARTED, user_id=1)
    analytics.flush_pending()
    analytics.flush_pending()
    client.flush.assert_called_once_with(timeout_seconds=2.0)


def test_flush_pending_never_raises(monkeypatch):
    client = init(monkeypatch)
    client.flush.side_effect = RuntimeError("network down")
    analytics.capture(analytics.Event.BOT_STARTED, user_id=1)
    analytics.flush_pending()


def test_request_middleware_flushes_before_returning(monkeypatch):
    client = init(monkeypatch)
    order = []
    client.flush.side_effect = lambda **kw: order.append("flush")

    async def call_next(request):
        analytics.capture(analytics.Event.BOT_STARTED, user_id=1)
        order.append("handler")
        return SimpleNamespace(headers={}, status_code=200)

    request = SimpleNamespace(url=SimpleNamespace(path="/health"), method="GET", headers={}, scope={})
    asyncio.run(observe.observe_request(request, call_next))
    assert order == ["handler", "flush"]
