"""Performance measurement (#32): Firestore cost per request, budgets and startup phases.

Measure first, optimise second. This module only *observes*; it never changes what a
request does. Everything it produces ends up as fields on structured log records
(`services/observability.py`), which `tools/perf_report.py` turns into a baseline and a
trend. See docs/performance.md.

How the pieces fit:

- **Firestore usage** is counted at the GAPIC layer (`instrument_firestore`): every
  document read, query, and committed write goes through the generated `FirestoreClient`,
  whatever repository or transaction issued it. Counts accumulate on the `FirestoreUsage`
  of the enclosing `track()` block (one per HTTP request, set by the middleware in
  `bot.py`). The object is shared by reference through a `ContextVar`, so work moved to
  threads (`run_in_threadpool`, `asyncio.to_thread`, which copy the context) adds to the
  same totals. Outside a `track()` block (Admin, scripts) nothing is counted.
- **Reads** follow Firestore billing closely enough to compare requests with each other:
  one read per document returned by a get or a query, and at least one per query or
  aggregation even when it returns nothing. It is an estimate, not an invoice.
- **Budgets** (`LATENCY_BUDGETS_MS`, `READ_BUDGETS`) are the thresholds a warm request
  should stay under. Crossing one emits `performance.budget.exceeded`; the first request
  of a new instance is a cold start and is reported, not judged.
- **Startup** (`startup_phases`) splits a cold start into the part before the application
  code ran (interpreter and imports, from `/proc` on Linux) and the FastAPI lifespan.

Instrumentation must never break the application: counting errors are swallowed.
"""
from __future__ import annotations

import logging
import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Optional

from services import observability

# A single query/get slower than this is logged on its own (`firestore.query.slow`).
SLOW_FIRESTORE_CALL_MS = 500.0

# p95 thresholds for a warm request, in milliseconds. Derived from the production baseline
# of 2026-09-07..16 (docs/performance.md#baseline) with headroom: a route that crosses its
# budget is slower than it has ever normally been, not merely "slow". A route that is not
# listed uses the default for its prefix.
LATENCY_BUDGETS_MS: dict[str, float] = {
    "/webhook": 1000,
    "/internal/telegram-update": 2500,
    "/internal/daily-job": 20000,
    "/internal/broadcast": 10000,
    "/internal/monthly-close": 10000,
    "/app/api/me": 1200,
    "/app/api/guess": 1500,
    "/app/api/hint": 1000,
    "/app/api/card": 2000,
    "/app/api/shop/buy": 1500,
    "/app/api/perf": 300,
}
DEFAULT_API_LATENCY_BUDGET_MS = 1000.0

# Maximum Firestore reads for one request. Read counts are deterministic for a given code
# path and data shape, so crossing one is a regression (an N+1 loop, a lost limit), not
# noise. Only *measured* worst cases are listed - a guessed budget would either cry wolf or
# hide a regression. Measure a route before adding it (tests/test_performance.py shows how).
READ_BUDGETS: dict[str, int] = {
    # user + feature flags + daily path + top 10 + 5 leagues x (league + 20 members) = 118,
    # measured on the emulator by test_profile_read_cost_stays_within_its_budget.
    "/app/api/me": 120,
    # Signature only: a metric must never cost a read.
    "/app/api/perf": 0,
}


@dataclass
class FirestoreUsage:
    """Firestore work done inside one `track()` block."""

    reads: int = 0
    gets: int = 0
    queries: int = 0
    writes: int = 0
    commits: int = 0
    rpc_ms: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def add(self, **amounts: float) -> None:
        with self._lock:
            for name, amount in amounts.items():
                setattr(self, name, getattr(self, name) + amount)

    def fields(self) -> dict[str, Any]:
        """Log fields; empty when the request never touched Firestore."""
        if not (self.reads or self.gets or self.queries or self.commits):
            return {}
        return {
            "firestore_reads": self.reads,
            "firestore_gets": self.gets,
            "firestore_queries": self.queries,
            "firestore_writes": self.writes,
            "firestore_ms": round(self.rpc_ms, 1),
        }


_usage: ContextVar[Optional[FirestoreUsage]] = ContextVar("gtp_firestore_usage", default=None)


@contextmanager
def track() -> Iterator[FirestoreUsage]:
    """Count Firestore work done inside the block (and in threads started from it)."""
    usage = FirestoreUsage()
    token = _usage.set(usage)
    try:
        yield usage
    finally:
        _usage.reset(token)


def current_usage() -> Optional[FirestoreUsage]:
    return _usage.get()


# ---------------------------------------------------------------------------
# Firestore instrumentation (GAPIC layer)
# ---------------------------------------------------------------------------

_INSTRUMENTED = "_gtp_performance_instrumented"


def instrument_firestore(client: Any) -> Any:
    """Wrap the GAPIC methods of a `google.cloud.firestore.Client`. Idempotent.

    Only the instance is patched (never the class), so other clients - the emulator client
    of a test, a backup script - are untouched unless passed here too. Returns the client."""
    try:
        api = client._firestore_api
        if getattr(api, _INSTRUMENTED, False):
            return client
        for name, kind in (("batch_get_documents", "get"), ("run_query", "query"),
                           ("run_aggregation_query", "aggregation")):
            original = getattr(api, name, None)
            if original is not None:
                setattr(api, name, _streaming_wrapper(original, kind))
        commit = getattr(api, "commit", None)
        if commit is not None:
            setattr(api, "commit", _commit_wrapper(commit))
        setattr(api, _INSTRUMENTED, True)
    except Exception:  # noqa: BLE001 - measurement must never stop Firestore from working
        logging.getLogger("gtp.performance").warning("firestore instrumentation unavailable", exc_info=True)
    return client


def _streaming_wrapper(original, kind):
    def wrapper(*args, **kwargs):
        usage = _usage.get()
        if usage is None:
            return original(*args, **kwargs)
        started = perf_counter()
        try:
            stream = original(*args, **kwargs)
        finally:
            elapsed = (perf_counter() - started) * 1000
        # A get is charged per document in the response; a query at least once even if empty.
        if kind == "get":
            usage.add(gets=1, rpc_ms=elapsed)
        else:
            usage.add(queries=1, reads=1, rpc_ms=elapsed)
        return _CountingStream(stream, usage, kind, elapsed, _collection_of(kwargs.get("request")))
    return wrapper


def _commit_wrapper(original):
    def wrapper(*args, **kwargs):
        usage = _usage.get()
        if usage is None:
            return original(*args, **kwargs)
        started = perf_counter()
        try:
            return original(*args, **kwargs)
        finally:
            usage.add(commits=1, writes=_write_count(kwargs.get("request")),
                      rpc_ms=(perf_counter() - started) * 1000)
    return wrapper


class _CountingStream:
    """Transparent proxy over a server-streaming response that counts documents."""

    def __init__(self, inner, usage: FirestoreUsage, kind: str, elapsed_ms: float, collection: Optional[str]):
        self._inner = inner
        self._usage = usage
        self._kind = kind
        self._elapsed_ms = elapsed_ms
        self._collection = collection
        self._documents = 0

    def __iter__(self):
        return self

    def __next__(self):
        started = perf_counter()
        try:
            item = next(self._inner)
        except StopIteration:
            self._account(started)
            self._finished()
            raise
        except BaseException:
            self._account(started)
            raise
        self._account(started)
        try:
            if self._kind == "get":
                self._usage.add(reads=1)
            elif self._kind == "query" and _has_document(item):
                self._documents += 1
                # The first document is covered by the minimum read counted at call time.
                if self._documents > 1:
                    self._usage.add(reads=1)
        except Exception:  # noqa: BLE001
            pass
        return item

    def _account(self, started: float) -> None:
        elapsed = (perf_counter() - started) * 1000
        self._elapsed_ms += elapsed
        self._usage.add(rpc_ms=elapsed)

    def _finished(self) -> None:
        if self._elapsed_ms >= SLOW_FIRESTORE_CALL_MS:
            observability.log_event(
                "firestore.query.slow", logging.WARNING, kind=self._kind, collection=self._collection,
                documents=self._documents, duration_ms=round(self._elapsed_ms, 1),
            )

    def __getattr__(self, name):
        return getattr(self._inner, name)


def _has_document(response: Any) -> bool:
    pb = getattr(response, "_pb", None)
    if pb is not None and hasattr(pb, "HasField"):
        return bool(pb.HasField("document"))
    return bool(getattr(response, "document", None))


def _collection_of(request: Any) -> Optional[str]:
    """The queried collection id (never a document path, which would carry user ids)."""
    try:
        if not isinstance(request, dict):
            return None
        structured = request.get("structured_query")
        if structured is None:
            structured = getattr(request.get("structured_aggregation_query"), "structured_query", None)
        selectors = getattr(structured, "from_", None) or []
        return selectors[0].collection_id if selectors else None
    except Exception:  # noqa: BLE001
        return None


def _write_count(request: Any) -> int:
    try:
        writes = request.get("writes") if isinstance(request, dict) else getattr(request, "writes", None)
        return len(writes or ())
    except Exception:  # noqa: BLE001
        return 0


# ---------------------------------------------------------------------------
# Budgets
# ---------------------------------------------------------------------------


def latency_budget_ms(route: str) -> Optional[float]:
    if route in LATENCY_BUDGETS_MS:
        return LATENCY_BUDGETS_MS[route]
    if route.startswith("/app/api/"):
        return DEFAULT_API_LATENCY_BUDGET_MS
    return None


def read_budget(route: str) -> Optional[int]:
    return READ_BUDGETS.get(route)


def check_budgets(route: str, duration_ms: float, usage: Optional[FirestoreUsage], *, cold_start: bool) -> list[str]:
    """Log `performance.budget.exceeded` for each budget a warm request crossed.

    Returns the names of the exceeded metrics (for tests). A cold start is expected to be slow
    and is measured separately, so it is never judged on latency; reads are deterministic and
    are always checked."""
    exceeded = []
    latency = latency_budget_ms(route)
    if latency is not None and not cold_start and duration_ms > latency:
        exceeded.append(("latency_ms", round(duration_ms, 1), latency))
    reads = read_budget(route)
    if reads is not None and usage is not None and usage.reads > reads:
        exceeded.append(("firestore_reads", usage.reads, reads))
    for metric, value, budget in exceeded:
        observability.log_event(
            "performance.budget.exceeded", logging.WARNING, route=route, metric=metric, value=value, budget=budget,
        )
    return [metric for metric, _, _ in exceeded]


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------


def process_age_ms() -> Optional[float]:
    """Milliseconds since this process was exec'd, from /proc (Linux, Cloud Run). None elsewhere."""
    try:
        with open("/proc/self/stat", encoding="ascii") as stat:
            # The command name (field 2) may contain spaces: split after its closing paren.
            fields = stat.read().rsplit(")", 1)[1].split()
        start_ticks = int(fields[19])  # field 22 overall: starttime, in clock ticks since boot
        with open("/proc/uptime", encoding="ascii") as uptime:
            uptime_s = float(uptime.read().split()[0])
        return round((uptime_s - start_ticks / getattr(os, "sysconf")("SC_CLK_TCK")) * 1000, 1)
    except (OSError, ValueError, IndexError, AttributeError):
        return None


@contextmanager
def startup_phases() -> Iterator[dict[str, Any]]:
    """Time the FastAPI lifespan and emit `app.startup.completed` once it is done.

    `before_lifespan_ms` is the process age when the lifespan began (interpreter start,
    imports, module-level setup); `lifespan_ms` is the lifespan itself (Telegram
    initialisation and webhook registration). The yielded dict takes extra fields."""
    details: dict[str, Any] = {"before_lifespan_ms": process_age_ms()}
    started = perf_counter()
    yield details
    observability.log_event(
        "app.startup.completed", component="api",
        lifespan_ms=round((perf_counter() - started) * 1000, 1),
        startup_ms=process_age_ms(), **details,
    )


_first_request_lock = threading.Lock()
_first_request_seen = False


def claim_first_request() -> bool:
    """True exactly once per process: the request that paid for the cold start."""
    global _first_request_seen
    with _first_request_lock:
        if _first_request_seen:
            return False
        _first_request_seen = True
        return True


# ---------------------------------------------------------------------------
# Mini App startup beacon
# ---------------------------------------------------------------------------

MINIAPP_METRICS = ("ttfb_ms", "dom_ready_ms", "first_data_ms", "api_me_ms", "api_me_server_ms", "transfer_kb")
MINIAPP_APPS = frozenset({"legacy", "v2"})
_MAX_METRIC_VALUE = 120_000


def miniapp_startup_fields(payload: Any) -> Optional[dict[str, Any]]:
    """The accepted, bounded subset of a Mini App startup report, or None if unusable.

    Only known numeric keys survive; anything else sent by the client is ignored, so the log
    record can never carry free text or identifiers from the browser."""
    if not isinstance(payload, dict) or payload.get("app") not in MINIAPP_APPS:
        return None
    metrics = payload.get("metrics")
    if not isinstance(metrics, dict):
        return None
    fields: dict[str, Any] = {"app": payload["app"]}
    for name in MINIAPP_METRICS:
        value = metrics.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if value != value or value < 0 or value > _MAX_METRIC_VALUE:  # NaN or out of range
            continue
        fields[name] = round(float(value), 1)
    if len(fields) == 1:
        return None
    fields["outcome"] = "ok" if payload.get("outcome") != "error" else "error"
    return fields
