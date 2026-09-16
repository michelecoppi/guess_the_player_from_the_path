"""tools/perf_report.py: snapshot from log entries, budgets, trend comparison (#32)."""
import json

from tools import perf_report


def request_log(path, latency_s, instance, ts, method="POST"):
    return {"timestamp": ts, "labels": {"instanceId": instance},
            "httpRequest": {"requestMethod": method, "requestUrl": f"https://bot.example{path}", "latency": f"{latency_s}s"}}


def event(name, ts, **fields):
    return {"timestamp": ts, "jsonPayload": {"event": name, **fields}}


def line(text, instance, ts):
    return {"timestamp": ts, "labels": {"instanceId": instance}, "textPayload": text}


ENTRIES = [
    line("Starting new instance. Reason: AUTOSCALING", "i1", "2026-09-16T08:00:00.000000Z"),
    line("Waiting for application startup.", "i1", "2026-09-16T08:00:04.500000Z"),
    line("Application startup complete.", "i1", "2026-09-16T08:00:04.800000Z"),
    request_log("/webhook", 5.2, "i1", "2026-09-16T08:00:05Z"),
    request_log("/webhook", 0.2, "i1", "2026-09-16T08:01:00Z"),
    request_log("/webhook", 0.4, "i1", "2026-09-16T08:02:00Z"),
    request_log("/app/v2/assets/index-abc123.js", 0.01, "i1", "2026-09-16T08:02:01Z", "GET"),
    event("api.request.completed", "2026-09-16T08:00:05Z", route="/app/api/me", duration_ms=4800, cold_start=True),
    event("api.request.completed", "2026-09-16T08:01:00Z", route="/app/api/me", duration_ms=300,
          firestore_reads=14, firestore_ms=40),
    event("api.request.completed", "2026-09-16T08:02:00Z", route="/app/api/me", duration_ms=1500,
          firestore_reads=16, firestore_ms=60),
    event("telegram.update.completed", "2026-09-16T08:03:00Z", command="top", duration_ms=420, firestore_reads=11),
    event("app.startup.completed", "2026-09-16T08:00:04.8Z", before_lifespan_ms=3900, lifespan_ms=310, startup_ms=4210),
    event("miniapp.startup.measured", "2026-09-16T08:04:00Z", app="legacy", first_data_ms=1800, ttfb_ms=90, outcome="ok"),
    event("performance.budget.exceeded", "2026-09-16T08:02:00Z", route="/app/api/me", metric="latency_ms"),
]


def test_percentile_is_nearest_rank():
    assert perf_report.percentile([], 0.5) is None
    assert perf_report.percentile([5, 1, 3, 2, 4], 0.5) == 3
    assert perf_report.percentile(list(range(1, 101)), 0.95) == 95
    assert perf_report.percentile([7], 0.99) == 7


def test_snapshot_separates_cold_starts_and_aggregates_every_source():
    snapshot = perf_report.build_snapshot(ENTRIES)

    webhook = snapshot["edge"]["POST /webhook"]
    assert webhook["count"] == 3 and webhook["cold_count"] == 1 and webhook["warm"]["p95"] == 400
    assert "GET /app/v2/assets/*" in snapshot["edge"]

    assert snapshot["container_startup"]["before_app_ms"]["p50"] == 4500
    assert snapshot["container_startup"]["lifespan_ms"]["p50"] == 300

    me = snapshot["app"]["/app/api/me"]
    assert me["cold_count"] == 1 and me["warm"]["count"] == 2 and me["over_budget"] == 1
    assert me["latency_budget_ms"] == 1200 and me["firestore_reads"]["p95"] == 16

    assert snapshot["telegram"]["top"]["duration_ms"]["p50"] == 420
    assert snapshot["app_startup"]["before_lifespan_ms"]["p50"] == 3900
    assert snapshot["miniapp"]["legacy"]["first_data_ms"]["p50"] == 1800
    assert snapshot["budget_exceeded"] == {"/app/api/me latency_ms": 1}
    assert snapshot["window"] == {"from": "2026-09-16T08:00:00.000000Z", "to": "2026-09-16T08:04:00Z"}


def test_render_and_trend_comparison():
    before = perf_report.build_snapshot(ENTRIES)
    faster = [dict(entry, jsonPayload={**entry["jsonPayload"], "duration_ms": 150})
              if entry.get("jsonPayload", {}).get("route") == "/app/api/me" and not entry["jsonPayload"].get("cold_start")
              else entry for entry in ENTRIES]
    after = perf_report.build_snapshot(faster)

    rows = {row[0]: row for row in perf_report.compare(before, after)}
    assert rows["app /app/api/me p50"][1:] == [300, 150, "-50%"]
    text = perf_report.render(after, before)
    assert "## Trend vs" in text and "| app /app/api/me p50 | 300 | 150 | -50% |" in text
    assert "## Container cold start (ms)" in text


def test_cli_reads_an_export_and_saves_a_snapshot(tmp_path, capsys):
    export = tmp_path / "logs.json"
    export.write_text(json.dumps(ENTRIES), encoding="utf-8")
    saved = tmp_path / "baseline" / "snapshot.json"
    assert perf_report.main(["--input", str(export), "--save", str(saved)]) == 0
    assert json.loads(saved.read_text(encoding="utf-8"))["version"] == perf_report.SNAPSHOT_VERSION
    assert "Cloud Run edge latency" in capsys.readouterr().out
    assert perf_report.main(["--input", str(export), "--compare", str(saved)]) == 0


def test_filter_selects_only_performance_entries_of_the_service():
    text = perf_report.log_filter("svc")
    assert 'resource.labels.service_name="svc"' in text
    for name in perf_report.APP_EVENTS:
        assert f'"{name}"' in text
