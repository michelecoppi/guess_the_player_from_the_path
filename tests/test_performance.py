"""Performance measurement contract (#32): Firestore accounting, budgets, startup, beacon.

The Firestore counters are tested twice: against a fake GAPIC client (every branch, no
services) and against the emulator (the real SDK really goes through the wrapped methods,
so a library upgrade that bypasses them fails here instead of silently reporting zero).
"""
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from google.cloud.firestore_v1.base_query import FieldFilter

from services import performance
from tests.test_observability import by_event, call, clean_observability, records, server  # noqa: F401


@pytest.fixture(autouse=True)
def fresh_process(monkeypatch):
    monkeypatch.setattr(performance, "_first_request_seen", False)


# ---------------------------------------------------------------------------
# Firestore accounting on a fake GAPIC client
# ---------------------------------------------------------------------------


def _doc(found=True):
    return SimpleNamespace(document=object() if found else None)


class FakeGapic:
    def __init__(self):
        self.responses = {}

    def batch_get_documents(self, request=None, metadata=None, **kwargs):
        return iter(self.responses["get"])

    def run_query(self, request=None, metadata=None, **kwargs):
        return iter(self.responses["query"])

    def run_aggregation_query(self, request=None, metadata=None, **kwargs):
        return iter([SimpleNamespace(result=1)])

    def commit(self, request=None, metadata=None, **kwargs):
        return SimpleNamespace(write_results=request["writes"])


def fake_client():
    return SimpleNamespace(_firestore_api=FakeGapic())


def test_reads_queries_and_writes_are_counted_inside_track_only():
    client = performance.instrument_firestore(fake_client())
    api = client._firestore_api
    api.responses = {"get": [_doc(), _doc(found=False)], "query": [_doc(), _doc(), _doc()]}

    assert list(api.run_query(request={})) and performance.current_usage() is None  # outside: untouched

    with performance.track() as usage:
        assert len(list(api.batch_get_documents(request={}))) == 2
        assert len(list(api.run_query(request={}))) == 3
        api.responses["query"] = []
        assert list(api.run_query(request={})) == []  # an empty query still costs one read
        list(api.run_aggregation_query(request={}))
        api.commit(request={"writes": [1, 2, 3]})

    assert (usage.gets, usage.queries, usage.reads, usage.commits, usage.writes) == (1, 3, 2 + 3 + 1 + 1, 1, 3)
    assert usage.fields()["firestore_reads"] == 7 and usage.fields()["firestore_writes"] == 3


def test_a_single_document_get_counts_even_if_the_stream_is_not_exhausted():
    client = performance.instrument_firestore(fake_client())
    client._firestore_api.responses = {"get": [_doc()]}
    with performance.track() as usage:
        next(client._firestore_api.batch_get_documents(request={}))  # what DocumentReference.get does
    assert usage.reads == 1 and usage.gets == 1


def test_threads_started_from_the_block_add_to_the_same_totals():
    import contextvars

    client = performance.instrument_firestore(fake_client())
    client._firestore_api.responses = {"get": [_doc()]}
    with performance.track() as usage:
        threads = [threading.Thread(target=contextvars.copy_context().run,
                                    args=(lambda: list(client._firestore_api.batch_get_documents(request={})),))
                   for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    assert usage.reads == 8


def test_instrumentation_is_idempotent_and_never_breaks_a_client_without_gapic():
    client = performance.instrument_firestore(fake_client())
    wrapped = client._firestore_api.run_query
    assert performance.instrument_firestore(client)._firestore_api.run_query is wrapped
    broken = SimpleNamespace()  # no _firestore_api at all
    assert performance.instrument_firestore(broken) is broken


def test_usage_fields_are_empty_when_firestore_was_not_touched():
    assert performance.FirestoreUsage().fields() == {}


def test_slow_queries_are_logged_with_the_collection_name_only(monkeypatch, records):  # noqa: F811
    monkeypatch.setattr(performance, "SLOW_FIRESTORE_CALL_MS", 0)
    client = performance.instrument_firestore(fake_client())
    client._firestore_api.responses = {"query": [_doc()]}
    structured = SimpleNamespace(from_=[SimpleNamespace(collection_id="users")])
    with performance.track():
        list(client._firestore_api.run_query(request={"parent": "projects/p/databases/(default)/documents/users/42",
                                                      "structured_query": structured}))
    [line] = by_event(records(), "firestore.query.slow")
    assert line["collection"] == "users" and line["documents"] == 1 and "42" not in str(line.get("parent"))


# ---------------------------------------------------------------------------
# Budgets
# ---------------------------------------------------------------------------


def test_warm_request_over_latency_budget_is_reported(records):  # noqa: F811
    assert performance.check_budgets("/app/api/me", 5000, None, cold_start=False) == ["latency_ms"]
    [line] = by_event(records(), "performance.budget.exceeded")
    assert line["route"] == "/app/api/me" and line["metric"] == "latency_ms"
    assert line["budget"] == performance.LATENCY_BUDGETS_MS["/app/api/me"] and line["severity"] == "WARNING"


def test_cold_start_is_not_judged_on_latency_but_reads_always_are():
    usage = performance.FirestoreUsage(reads=performance.READ_BUDGETS["/app/api/me"] + 1)
    assert performance.check_budgets("/app/api/me", 9000, usage, cold_start=True) == ["firestore_reads"]
    assert performance.check_budgets("/app/api/me", 10, performance.FirestoreUsage(reads=3), cold_start=False) == []


def test_budget_defaults_and_unbudgeted_routes():
    assert performance.latency_budget_ms("/app/api/whatever") == performance.DEFAULT_API_LATENCY_BUDGET_MS
    assert performance.latency_budget_ms("/app") is None
    assert performance.read_budget("/internal/broadcast") is None  # unmeasured routes are not judged
    assert performance.read_budget("/app/api/perf") == 0


def test_first_request_is_claimed_once_per_process():
    assert performance.claim_first_request() is True
    assert performance.claim_first_request() is False


def test_process_age_is_a_positive_number_or_unavailable():
    age = performance.process_age_ms()
    assert age is None or age > 0


def test_startup_phases_emit_one_record(records):  # noqa: F811
    with performance.startup_phases() as details:
        details["webhook"] = True
    [line] = by_event(records(), "app.startup.completed")
    assert line["lifespan_ms"] >= 0 and line["webhook"] is True
    # /proc exists only on Linux: elsewhere the phase is unknown, never invented.
    before = line.get("before_lifespan_ms")
    assert before is None or before > 0


# ---------------------------------------------------------------------------
# Mini App startup beacon
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("payload", [
    None, {}, {"app": "v3", "metrics": {"ttfb_ms": 1}}, {"app": "v2", "metrics": "fast"},
    {"app": "v2", "metrics": {"ttfb_ms": -1, "api_me_ms": float("nan"), "dom_ready_ms": 10**9, "x": 5}},
    {"app": "v2", "metrics": {"first_data_ms": True}},
])
def test_unusable_miniapp_reports_are_rejected(payload):
    assert performance.miniapp_startup_fields(payload) is None


def test_miniapp_report_keeps_only_known_bounded_numbers():
    fields = performance.miniapp_startup_fields({
        "app": "legacy", "outcome": "weird", "user_id": 42,
        "metrics": {"first_data_ms": 812.345, "ttfb_ms": 120, "name": "Anna", "transfer_kb": 0},
    })
    assert fields == {"app": "legacy", "first_data_ms": 812.3, "ttfb_ms": 120.0, "transfer_kb": 0.0, "outcome": "ok"}


def test_perf_endpoint_requires_a_signature_and_reads_nothing(server, monkeypatch, records):  # noqa: F811
    assert call(server, "/app/api/perf", json={"app": "v2", "metrics": {"ttfb_ms": 1}}).status_code == 401

    monkeypatch.setattr(server, "user_id_from_init_data", lambda *args: 42)
    monkeypatch.setattr(server.firebase_service, "get_user_data", lambda uid: pytest.fail("no user read for a metric"))
    assert call(server, "/app/api/perf", json={"app": "v2", "metrics": {"x": 1}}).status_code == 422

    response = call(server, "/app/api/perf", json={
        "initData": "signed", "app": "v2", "outcome": "ok", "metrics": {"first_data_ms": 950, "api_me_ms": 400},
    })
    assert response.status_code == 200
    [line] = by_event(records(), "miniapp.startup.measured")
    assert line["app"] == "v2" and line["first_data_ms"] == 950 and line["api_me_ms"] == 400
    assert "initData" not in line and "user_id" not in line


# ---------------------------------------------------------------------------
# HTTP integration
# ---------------------------------------------------------------------------


def test_request_records_carry_firestore_usage_server_timing_and_cold_start(server, monkeypatch, records):  # noqa: F811
    gapic = performance.instrument_firestore(fake_client())._firestore_api
    gapic.responses = {"get": [_doc()], "query": [_doc(), _doc()]}

    def shop_with_reads(payload, cost=1):
        list(gapic.batch_get_documents(request={}))
        list(gapic.run_query(request={}))
        return 42, {"language": "it"}

    monkeypatch.setattr(server, "_webapp_user", shop_with_reads)
    monkeypatch.setattr(server.shop, "catalogue_for", lambda *args: {"sections": []})
    first = call(server, "/app/api/shop", json={})
    second = call(server, "/app/api/shop", json={})

    assert first.status_code == second.status_code == 200
    assert 'fs;dur=' in first.headers["Server-Timing"] and 'desc="reads=3"' in first.headers["Server-Timing"]
    cold, warm = by_event(records(), "api.request.completed")
    assert cold["cold_start"] is True and "cold_start" not in warm
    assert cold["firestore_reads"] == 3 and cold["firestore_gets"] == 1 and cold["firestore_queries"] == 1


def test_request_without_firestore_keeps_the_plain_server_timing(server, records):  # noqa: F811
    response = call(server, "/app/api/me", json={})
    assert response.headers["Server-Timing"].startswith("app;dur=") and "fs;" not in response.headers["Server-Timing"]
    [line] = by_event(records(), "api.request.completed")
    assert "firestore_reads" not in line


def test_telegram_update_records_handler_duration(server, monkeypatch, records):  # noqa: F811
    monkeypatch.setattr(server.work_receipts, "claim", lambda *args, **kwargs: "claimed")
    monkeypatch.setattr(server.work_receipts, "finish", lambda *args, **kwargs: None)
    monkeypatch.setattr(server.telegram_app, "process_update", AsyncMock())
    update = {"update_id": 7, "message": {"message_id": 1, "date": 0, "chat": {"id": 5, "type": "private"},
                                          "from": {"id": 5, "is_bot": False, "first_name": "A"}, "text": "/top"}}
    response = call(server, "/internal/telegram-update", json=update, headers={"X-Task-Secret": server.TASK_SECRET})
    assert response.status_code == 200
    [line] = by_event(records(), "telegram.update.completed")
    assert line["command"] == "top" and line["duration_ms"] >= 0


def test_telegram_client_is_shared_between_api_calls_and_get_updates(server):  # noqa: F811
    requests = server.telegram_app.bot._request
    assert requests[0] is requests[1]


# ---------------------------------------------------------------------------
# Real SDK against the emulator
# ---------------------------------------------------------------------------


def test_real_firestore_sdk_goes_through_the_counted_methods(emulator_db):
    client = performance.instrument_firestore(emulator_db)
    users = client.collection("users")
    with performance.track() as setup:
        batch = client.batch()
        for uid in ("1", "2", "3"):
            batch.set(users.document(uid), {"points": int(uid)})
        batch.commit()
    assert setup.commits == 1 and setup.writes == 3 and setup.reads == 0

    with performance.track() as usage:
        assert users.document("1").get().exists
        assert not users.document("missing").get().exists
        assert len(list(users.where(filter=FieldFilter("points", ">=", 2)).stream())) == 2
        assert list(users.where(filter=FieldFilter("points", ">", 99)).stream()) == []
        snapshots = client.get_all([users.document("2"), users.document("3")])
        assert len(list(snapshots)) == 2
    # 2 single gets + 2 (query) + 1 (empty query minimum) + 2 (get_all)
    assert usage.reads == 7 and usage.gets == 3 and usage.queries == 2
    assert usage.rpc_ms > 0


def _seed_worst_case_profile(client, user_id=1):
    """The heaviest /app/api/me the product allows: a full top 10 and the user in the maximum
    number of shown leagues, each with a full standings page."""
    from services import firebase_service, webapp_api
    from services.dates import today_iso

    batch = client.batch()
    codes = [f"L{index}" for index in range(webapp_api.MAX_LEAGUES_SHOWN)]
    for uid in range(1, webapp_api.LEADERBOARD_SIZE + 3):
        document = firebase_service.new_user_document(uid, f"U{uid}")
        document.update({"points_totali": uid, "leagues": codes if uid == user_id else []})
        batch.set(firebase_service.user_ref(uid), document)
    batch.set(firebase_service.daily_path_ref(today_iso()), {"player_id": "none", "career": []})
    batch.commit()
    for code in codes:
        batch = client.batch()
        batch.set(firebase_service.league_ref(code), {"code": code, "name": code, "members_count": 20})
        for member in range(20):
            batch.set(firebase_service.member_ref(code, member + 1), {"telegram_id": member + 1, "points": member})
        batch.commit()


@pytest.mark.parametrize("include_social", [True, False])
def test_profile_read_cost_stays_within_its_budget(emulator_db, include_social):
    """Measured, not estimated: the budget for /app/api/me is the worst case the product allows."""
    from services import firebase_service, webapp_api

    performance.instrument_firestore(emulator_db)
    _seed_worst_case_profile(emulator_db)
    user = firebase_service.get_user_data(1)
    with performance.track() as usage:
        profile = webapp_api.build_profile(1, user=user, include_social=include_social)
    assert profile is not None
    budget = performance.READ_BUDGETS["/app/api/me"]
    # The route reads the user document first (_webapp_user), hence the +1.
    if include_social:
        assert usage.reads + 1 == 118, usage.fields()  # the measured worst case the budget is based on
        assert usage.reads + 1 <= budget
    else:
        assert usage.reads + 1 <= 3, usage.fields()  # user, feature flags, daily path
