"""Read-only PostHog HogQL queries for the admin dashboard (#39).

Every test fakes `requests.post`: this module never talks to a real PostHog project in
tests, the same discipline `test_product_analytics.py` applies to the capture client.
"""
import pytest

from services import product_analytics_query as paq


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text or str(payload)

    def json(self):
        return self._payload


def _settings(**overrides):
    base = {"POSTHOG_PERSONAL_API_KEY": "phx_test_key", "POSTHOG_PROJECT_ID": "12345"}  # pragma: allowlist secret
    base.update(overrides)
    return paq.Settings.from_env(base)


def test_settings_from_env_requires_both_key_and_project_id():
    assert paq.Settings.from_env({}).configured is False
    assert paq.Settings.from_env({"POSTHOG_PERSONAL_API_KEY": "k"}).configured is False
    assert paq.Settings.from_env({"POSTHOG_PROJECT_ID": "1"}).configured is False
    assert _settings().configured is True


def test_settings_default_host_matches_the_capture_clients_default():
    assert _settings().host == paq.DEFAULT_HOST == "https://eu.i.posthog.com"


def test_unconfigured_settings_refuse_to_query_without_any_network_call(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("must not call PostHog when unconfigured")
    monkeypatch.setattr(paq.requests, "post", boom)

    with pytest.raises(paq.QueryError):
        paq.daily_completion_rate(paq.Settings.from_env({}), days=7)


def test_run_hogql_sends_a_bearer_token_and_the_project_scoped_url(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured.update(url=url, headers=headers, json=json, timeout=timeout)
        return FakeResponse(200, {"results": [[1, 2]]})
    monkeypatch.setattr(paq.requests, "post", fake_post)

    paq._run_hogql(_settings(), "SELECT 1")

    assert captured["url"] == f"{paq.DEFAULT_HOST}/api/projects/12345/query/"
    assert captured["headers"]["Authorization"] == "Bearer phx_test_key"
    assert captured["json"]["query"]["kind"] == "HogQLQuery"
    assert captured["timeout"] == paq.REQUEST_TIMEOUT_SECONDS


def test_a_non_200_response_is_a_readable_query_error(monkeypatch):
    monkeypatch.setattr(paq.requests, "post", lambda *a, **k: FakeResponse(401, text="invalid key"))

    with pytest.raises(paq.QueryError, match="401"):
        paq.daily_completion_rate(_settings(), days=7)


def test_a_network_failure_is_a_readable_query_error(monkeypatch):
    import requests as real_requests

    def raise_network_error(*args, **kwargs):
        raise real_requests.ConnectionError("dns lookup failed")
    monkeypatch.setattr(paq.requests, "post", raise_network_error)

    with pytest.raises(paq.QueryError, match="dns lookup failed"):
        paq.daily_completion_rate(_settings(), days=7)


def test_daily_completion_rate_divides_completed_by_participants(monkeypatch):
    monkeypatch.setattr(paq.requests, "post", lambda *a, **k: FakeResponse(200, {"results": [[30, 120]]}))

    assert paq.daily_completion_rate(_settings(), days=7) == 0.25


def test_a_zero_denominator_is_none_not_a_division_error(monkeypatch):
    monkeypatch.setattr(paq.requests, "post", lambda *a, **k: FakeResponse(200, {"results": [[0, 0]]}))

    assert paq.daily_completion_rate(_settings(), days=7) is None


def test_no_rows_at_all_is_also_none(monkeypatch):
    monkeypatch.setattr(paq.requests, "post", lambda *a, **k: FakeResponse(200, {"results": []}))

    assert paq.daily_completion_rate(_settings(), days=7) is None


def test_hint_usage_rate_uses_unique_users_not_raw_event_counts(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["query"] = json["query"]["query"]
        return FakeResponse(200, {"results": [[5, 20]]})
    monkeypatch.setattr(paq.requests, "post", fake_post)

    result = paq.hint_usage_rate(_settings(), days=7)

    assert result == 0.25
    assert "uniqIf(distinct_id" in captured["query"]
    assert "hint_used" in captured["query"]
    assert "daily_guess_submitted" in captured["query"]


def test_referral_conversion_rate_filters_on_attached_true(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["query"] = json["query"]["query"]
        return FakeResponse(200, {"results": [[2, 8]]})
    monkeypatch.setattr(paq.requests, "post", fake_post)

    result = paq.referral_conversion_rate(_settings(), days=30)

    assert result == 0.25
    assert "referral_attached = true" in captured["query"]
    assert "referral_converted" in captured["query"]
    assert "referral_opened" in captured["query"]


def test_guesses_per_completed_daily_returns_the_average(monkeypatch):
    monkeypatch.setattr(paq.requests, "post", lambda *a, **k: FakeResponse(200, {"results": [[1.8]]}))

    assert paq.guesses_per_completed_daily(_settings(), days=7) == 1.8


def test_guesses_per_completed_daily_with_no_data_is_none(monkeypatch):
    monkeypatch.setattr(paq.requests, "post", lambda *a, **k: FakeResponse(200, {"results": [[None]]}))

    assert paq.guesses_per_completed_daily(_settings(), days=7) is None


def test_fetch_core_metrics_isolates_one_failing_query_from_the_rest(monkeypatch):
    def flaky_post(url, headers=None, json=None, timeout=None):
        if "attempts_used" in json["query"]["query"]:
            return FakeResponse(500, text="server error")
        return FakeResponse(200, {"results": [[1, 2]]})
    monkeypatch.setattr(paq.requests, "post", flaky_post)

    rows = paq.fetch_core_metrics(_settings(), days=7)
    by_key = {row["key"]: row for row in rows}

    assert by_key["guesses_per_completed_daily"]["error"] is not None
    assert by_key["guesses_per_completed_daily"]["value"] is None
    assert by_key["daily_completion_rate"]["error"] is None
    assert by_key["daily_completion_rate"]["value"] == 0.5
    assert len(rows) == len(paq.CORE_METRICS)
