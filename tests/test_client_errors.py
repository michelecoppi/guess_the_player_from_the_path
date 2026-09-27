"""Mini App JavaScript error reports: validation (#180).

The HTTP endpoint is tested in tests/test_performance.py, next to the `/perf` beacon: it needs
the observability fixtures, which reset logging and must not run before tests that rely on it.
"""
import pytest

from services import client_errors, performance


def test_only_a_closed_bounded_set_of_fields_survives():
    fields = client_errors.client_error_fields({
        "kind": "error",
        "message": "TypeError: x is undefined " + "a" * 1000,
        "source": "https://example.com/app/assets/index-abc.js?initData=user%3D1&hash=x",
        "line": 12, "col": 7,
        "stack": "at render (https://example.com/app/assets/index-abc.js?v=1#frag:12:7)",
        "screen": "shop",
        "user_id": 42, "name": "Anna",
    })
    assert set(fields) == {"kind", "error_message", "source", "line", "col", "stack", "screen"}
    assert len(fields["error_message"]) == client_errors.MAX_MESSAGE
    assert fields["source"] == "https://example.com/app/assets/index-abc.js"
    assert "?" not in fields["stack"] and "#" not in fields["stack"]
    assert fields["line"] == 12 and fields["col"] == 7


@pytest.mark.parametrize("payload", [
    None, [], {}, {"kind": "error"}, {"kind": "crash", "message": "x"},
    {"kind": "error", "message": 12}, {"kind": "error", "message": "   "},
])
def test_unusable_reports_are_rejected(payload):
    assert client_errors.client_error_fields(payload) is None


def test_invalid_optional_fields_are_dropped_not_rejected():
    fields = client_errors.client_error_fields({
        "kind": "unhandledrejection", "message": "boom",
        "line": -1, "col": True, "screen": "Shop <b>", "source": 5, "stack": "",
    })
    assert fields == {"kind": "unhandledrejection", "error_message": "boom"}


def test_secrets_in_the_message_are_scrubbed(monkeypatch):
    monkeypatch.setattr(client_errors.observability, "scrub_text", lambda text: text.replace("s3cret", "[REDACTED]"))
    fields = client_errors.client_error_fields({"kind": "error", "message": "token s3cret leaked"})
    assert fields["error_message"] == "token [REDACTED] leaked"


def test_error_reports_have_the_beacon_budgets():
    assert performance.read_budget("/app/api/client-error") == 0
