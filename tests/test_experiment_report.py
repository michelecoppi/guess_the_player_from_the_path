from datetime import datetime, timedelta, timezone

import pytest

from scripts import experiments as cli
from services import experiment_report as reports
from services import experiments
from services import product_analytics_query as paq

NOW = datetime(2026, 9, 27, tzinfo=timezone.utc)


def planned(metric="daily_completion_rate"):
    return experiments.plan("daily_intro_v1", "A shorter intro helps", metric, 7, "short intro")


def running(metric="daily_completion_rate"):
    return experiments.start(planned(metric), now=NOW, analytics_ready=True)


def test_query_deduplicates_exposures_and_uses_post_exposure_window():
    sql = reports.query("daily_intro_v1", "daily_completion_rate", NOW, NOW + timedelta(days=1))
    assert "argMin(properties.variant, timestamp)" in sql
    assert "GROUP BY distinct_id" in sql
    assert "e.timestamp >= x.first_exposure" in sql
    assert "uniqIf(tuple(toDate(e.timestamp), e.distinct_id)" in sql
    assert "countIf(e.event = 'daily_completed'" in sql
    assert "experiment_key = 'daily_intro_v1'" in sql


@pytest.mark.parametrize("metric,fragment", [
    ("guesses_per_completed_daily", "toFloatOrZero(e.properties.attempts_used)"),
    ("hint_usage_rate", "uniqIf(e.distinct_id, e.event = 'hint_used'"),
    ("referral_conversion_rate", "e.properties.referral_attached = true"),
    ("shop_purchase_conversion_rate", "e.event = 'shop_purchase_completed'"),
    ("miniapp_activation_rate", "uniqIf(e.distinct_id, e.event = 'miniapp_opened'"),
])
def test_registered_metric_query(metric, fragment):
    assert fragment in reports.query("daily_intro_v1", metric, NOW, NOW + timedelta(days=1))


def test_rate_and_mean_results_separate_variants(monkeypatch):
    monkeypatch.setattr(paq, "_run_hogql", lambda *a: [["control", 12, 4, 8], ["treatment", 15, 9, 10]])
    result = reports.report(paq.Settings(), running(), now=NOW + timedelta(days=2))
    assert result["status"] == "ok"
    assert [row["value"] for row in result["variants"]] == [0.5, 0.9]
    monkeypatch.setattr(paq, "_run_hogql", lambda *a: [["control", 12, 18.0, 10], ["treatment", 15, 22.5, 10]])
    result = reports.report(paq.Settings(), running("guesses_per_completed_daily"),
                            now=NOW + timedelta(days=2))
    assert [row["value"] for row in result["variants"]] == [1.8, 2.25]


def test_empty_insufficient_and_malformed_results_are_explicit(monkeypatch):
    monkeypatch.setattr(paq, "_run_hogql", lambda *a: [])
    assert reports.report(paq.Settings(), running(), now=NOW + timedelta(days=1))["status"] == "empty"
    monkeypatch.setattr(paq, "_run_hogql", lambda *a: [["control", 2, 0, 0]])
    result = reports.report(paq.Settings(), running(), now=NOW + timedelta(days=1))
    assert result["status"] == "insufficient_data"
    assert result["variants"][0]["value"] is None
    monkeypatch.setattr(paq, "_run_hogql", lambda *a: [["control", 2, 1]])
    assert reports.report(paq.Settings(), running(), now=NOW + timedelta(days=1))["status"] == "query_error"


def test_stop_bounds_report_interval(monkeypatch):
    row = experiments.stop(running(), reason="guardrail", operator="alice", now=NOW + timedelta(days=1))
    monkeypatch.setattr(paq, "_run_hogql", lambda *a: [])
    result = reports.report(paq.Settings(), row, now=NOW + timedelta(days=3))
    assert result["interval"]["end"] == (NOW + timedelta(days=1)).isoformat()


def test_start_rejects_unqueryable_metric_before_transaction(monkeypatch):
    monkeypatch.setattr(cli, "_analytics_ready", lambda: True)
    monkeypatch.setattr(cli.store, "load", lambda: {"daily_intro_v1": planned()})
    monkeypatch.setattr(cli.store, "update", lambda *a: pytest.fail("must not write"))
    def fail(*a):
        raise paq.QueryError("metric unavailable")
    monkeypatch.setattr(reports, "preflight", fail)
    with pytest.raises(paq.QueryError, match="metric unavailable"):
        cli.main(["start", "daily_intro_v1"])


def test_preflight_accepts_empty_but_rejects_malformed(monkeypatch):
    monkeypatch.setattr(paq, "_run_hogql", lambda *a: [])
    reports.preflight(paq.Settings(), "daily_intro_v1", "daily_completion_rate", NOW)
    monkeypatch.setattr(paq, "_run_hogql", lambda *a: [["control", 1]])
    with pytest.raises(paq.QueryError, match="malformata"):
        reports.preflight(paq.Settings(), "daily_intro_v1", "daily_completion_rate", NOW)
