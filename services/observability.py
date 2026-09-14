"""Runtime observability: structured logs, Sentry error tracking, context and redaction.

One module owns all of it, so handlers never configure Sentry or formatters themselves.

How the pieces fit:

- **Context** lives in a `ContextVar` (`bind`). A request, a Cloud Task or a Telegram
  update binds its fields once (component, route, request_id, update_type...) and every log
  line emitted underneath carries them, including lines from threads started with
  `asyncio.to_thread` / `run_in_threadpool`, which copy the context.
- **Structured events** (`log_event`, `operation`) are ordinary `logging` records whose
  message is a stable event name (`payment.delivery.failed`). The formatter adds the bound
  fields: JSON on Cloud Run, a readable line locally.
- **Sentry** is optional. Without `SENTRY_DSN` the SDK is never initialised and nothing
  leaves the process. With it, the logging integration turns ERROR records (with their
  exception) into Sentry events; `_before_send` adds the bound context as tags and
  sanitises the whole event. There is exactly one path to Sentry, so the same failure is
  not reported twice: a failure logged at ERROR is marked as reported, and outer layers
  (the HTTP middleware, the Telegram error handler) downgrade their own record.
- **Redaction** (`sanitize`, `scrub_text`) works on copies: application payloads are never
  mutated. If sanitising a Sentry event fails the event is dropped, never sent raw.

Observability must never take the application down: initialisation and reporting failures
are swallowed after a local warning.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import sys
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import date, datetime, timezone
from time import perf_counter
from typing import Any, Optional

REDACTED = "[REDACTED]"

# Fields promoted to Sentry tags (short, low-cardinality, safe). Everything else that is
# bound stays in the structured log and in the sanitised `observability` Sentry context.
TAG_FIELDS = (
    "component", "event", "route", "method", "handler", "command", "job", "operation",
    "update_type", "status", "request_id", "task_name", "task_retry_count", "source",
)

COMPONENTS = frozenset({"telegram", "api", "job", "admin", "ingestion", "payment", "broadcast"})

# A retryable failure (Cloud Tasks will try again) is a WARNING until the task has been
# retried this many times; from then on it is an ERROR and reaches Sentry.
RETRY_ESCALATION = 5

# Normalised key fragments (lowercase, only a-z0-9) whose values are always redacted.
_SENSITIVE_KEY_PARTS = (
    "token", "secret", "password", "passwd", "authorization", "cookie", "initdata",
    "dsn", "credential", "apikey", "privatekey", "signature", "invoicepayload", "sessionid",
)
_SENSITIVE_EXACT_KEYS = frozenset({"hash", "auth"})
# Environment variables whose literal values are scrubbed from any observability text.
_SECRET_ENV_VARS = (
    "BOT_TOKEN", "TELEGRAM_BOT_TOKEN", "WEBHOOK_SECRET", "TASK_SECRET", "GENERATION_SECRET",
    "SENTRY_DSN", "OBSERVABILITY_USER_SALT",
)

_TEXT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # Telegram bot token (also inside https://api.telegram.org/bot<token>/method).
    (re.compile(r"\d{5,}:[A-Za-z0-9_-]{30,}"), REDACTED),
    # Credentials embedded in URLs, including a Sentry DSN key.
    (re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)[^\s/@:]+(?::[^\s/@]*)?@"), r"\1" + REDACTED + "@"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+"), "Bearer " + REDACTED),
    # Telegram WebApp initData signature and similar query-string secrets.
    (re.compile(r"(?i)\b(hash|signature|token|secret)=[^&\s\"']+"), r"\1=" + REDACTED),
    # The user name in home-directory paths (local Admin runs on a personal machine).
    (re.compile(r"(?i)([a-z]:\\\\?users\\\\?|/home/|/users/)[^\\/\s'\"]+"), r"\1" + REDACTED),
)
_INIT_DATA_MARKERS = ("auth_date=", "hash=")

_MAX_DEPTH = 12
_MAX_STRING = 2000

_context: ContextVar[Mapping[str, Any]] = ContextVar("gtp_observability_context", default={})
_logger = logging.getLogger("gtp")


@dataclass(frozen=True)
class Settings:
    service: str = "bot"
    dsn: str = ""
    environment: str = "development"
    release: Optional[str] = None
    log_format: str = "text"
    log_level: str = "INFO"
    user_salt: str = ""

    @classmethod
    def from_env(cls, service: str = "bot", environ: Optional[Mapping[str, str]] = None) -> "Settings":
        env = os.environ if environ is None else environ
        on_cloud_run = bool(env.get("K_SERVICE"))
        log_format = (env.get("LOG_FORMAT") or "").strip().lower()
        if log_format not in ("json", "text"):
            log_format = "json" if on_cloud_run else "text"
        return cls(
            service=service,
            dsn=(env.get("SENTRY_DSN") or "").strip(),
            environment=(env.get("SENTRY_ENVIRONMENT") or "").strip()
            or ("production" if on_cloud_run else "development"),
            # SENTRY_RELEASE is the explicit hook; Cloud Run always provides its revision.
            release=(env.get("SENTRY_RELEASE") or "").strip() or (env.get("K_REVISION") or "").strip() or None,
            log_format=log_format,
            log_level=(env.get("LOG_LEVEL") or "INFO").strip().upper(),
            user_salt=env.get("OBSERVABILITY_USER_SALT") or "",
        )


class _State:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.initialized = False
        self.sentry_enabled = False
        self.settings = Settings()
        self.secret_values: tuple[str, ...] = ()


_state = _State()


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------

def is_sensitive_key(key: Any) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
    if normalized in _SENSITIVE_EXACT_KEYS:
        return True
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def _known_secret_values() -> tuple[str, ...]:
    values = {os.environ.get(name, "") for name in _SECRET_ENV_VARS}
    return tuple(sorted((v for v in values if len(v) >= 8), key=len, reverse=True))


def scrub_text(text: str) -> str:
    """Remove secrets from free text (exception messages, log messages, URLs)."""
    if not text:
        return text
    if all(marker in text for marker in _INIT_DATA_MARKERS):
        return REDACTED + " (initData)"
    for secret in _state.secret_values or _known_secret_values():
        if secret in text:
            text = text.replace(secret, REDACTED)
    for pattern, replacement in _TEXT_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def sanitize(value: Any, *, _depth: int = 0, _seen: Optional[set[int]] = None) -> Any:
    """A redacted **copy** of `value`: sensitive keys masked, strings scrubbed, depth bounded."""
    if isinstance(value, str):
        scrubbed = scrub_text(value)
        return scrubbed if len(scrubbed) <= _MAX_STRING else scrubbed[:_MAX_STRING] + "...[truncated]"
    if value is None or isinstance(value, (bool, int, float, date)):
        return value
    if isinstance(value, bytes):
        return f"<{len(value)} bytes>"
    if _depth >= _MAX_DEPTH:
        return "[TRUNCATED]"
    seen = _seen if _seen is not None else set()
    if id(value) in seen:
        return "[CYCLE]"
    if isinstance(value, Mapping):
        seen.add(id(value))
        result = {
            str(key): REDACTED if is_sensitive_key(key) else sanitize(item, _depth=_depth + 1, _seen=seen)
            for key, item in value.items()
        }
        seen.discard(id(value))
        return result
    if isinstance(value, (list, tuple, set, frozenset)):
        seen.add(id(value))
        items = [sanitize(item, _depth=_depth + 1, _seen=seen) for item in value]
        seen.discard(id(value))
        return items
    return scrub_text(repr(value))


def user_ref(user_id: Any) -> Optional[str]:
    """Stable pseudonymous reference for a Telegram user id, for correlating log lines.

    Keyed with OBSERVABILITY_USER_SALT when configured. Without a salt the reference is only
    pseudonymous (Telegram ids are guessable), which is why it is never a Sentry user."""
    if user_id is None or user_id == "":
        return None
    key = (_state.settings.user_salt or "gtp-observability").encode()
    return hmac.new(key, str(user_id).encode(), hashlib.sha256).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------

def current_context() -> dict[str, Any]:
    return dict(_context.get())


@contextmanager
def bind(**fields: Any) -> Iterator[dict[str, Any]]:
    """Add fields to the observability context for the duration of the block."""
    merged = {**_context.get(), **{key: value for key, value in fields.items() if value is not None}}
    token = _context.set(merged)
    try:
        yield merged
    finally:
        _context.reset(token)


def mark_reported(exc: BaseException) -> None:
    try:
        setattr(exc, "_gtp_observability_reported", True)
    except Exception:  # noqa: BLE001 - some exception types refuse attributes
        pass


def is_reported(exc: Optional[BaseException]) -> bool:
    return bool(exc is not None and getattr(exc, "_gtp_observability_reported", False))


def log_event(
    event: str,
    level: int = logging.INFO,
    *,
    exc_info: Optional[BaseException] = None,
    **fields: Any,
) -> None:
    """Emit one structured record named `event`. ERROR and above reach Sentry (when enabled)."""
    try:
        component = fields.get("component") or _context.get().get("component") or "app"
        logger = _logger.getChild(str(component))
        with bind(event=event, **fields):
            logger.log(level, event, exc_info=exc_info, stacklevel=2)
        if exc_info is not None and level >= logging.ERROR:
            mark_reported(exc_info)
    except Exception:  # noqa: BLE001 - logging must never break the caller
        pass


@contextmanager
def operation(
    name: str,
    *,
    component: str,
    retryable: tuple[type[BaseException], ...] = (),
    **fields: Any,
) -> Iterator[dict[str, Any]]:
    """Time a meaningful operation and record `<name>.completed|retry|failed`.

    The yielded dict collects result fields (counts, ids) for the final record. Exceptions
    are always re-raised unchanged: observing an operation never alters its semantics."""
    details: dict[str, Any] = {}
    started = perf_counter()
    with bind(component=component, **fields):
        try:
            yield details
        except retryable as exc:
            retries = _context.get().get("task_retry_count")
            escalate = isinstance(retries, int) and retries >= RETRY_ESCALATION
            level = logging.ERROR if escalate else logging.WARNING
            log_event(
                f"{name}.retry", level, exc_info=exc if escalate else None, status="retry",
                duration_ms=_elapsed_ms(started), error_type=type(exc).__name__, **details,
            )
            mark_reported(exc)
            raise
        except Exception as exc:
            # Gia' registrato a ERROR piu' in basso (es. cloud_task.enqueue.failed): qui resta
            # il contesto dell'operazione, senza un secondo traceback ne' un secondo evento.
            reported = is_reported(exc)
            log_event(
                f"{name}.failed", logging.WARNING if reported else logging.ERROR,
                exc_info=None if reported else exc, status="failed",
                duration_ms=_elapsed_ms(started), error_type=type(exc).__name__, **details,
            )
            raise
        else:
            log_event(f"{name}.completed", status="completed", duration_ms=_elapsed_ms(started), **details)


def _elapsed_ms(started: float) -> float:
    return round((perf_counter() - started) * 1000, 1)


def cloud_task_fields(headers: Mapping[str, str]) -> dict[str, Any]:
    """Cloud Tasks metadata for correlation only (never used for authorisation)."""
    fields: dict[str, Any] = {}
    name = headers.get("x-cloudtasks-taskname")
    if name:
        fields["task_name"] = name[:128]
    for header, key in (("x-cloudtasks-taskretrycount", "task_retry_count"),
                        ("x-cloudtasks-taskexecutioncount", "task_execution_count")):
        raw = headers.get(header)
        if raw and raw.isdigit():
            fields[key] = int(raw)
    queue = headers.get("x-cloudtasks-queuename")
    if queue:
        fields["task_queue"] = queue[:128]
    trace = headers.get("x-cloud-trace-context", "").split("/", 1)[0]
    if re.fullmatch(r"[0-9a-f]{32}", trace):
        fields["trace_id"] = trace
    return fields


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

_RESERVED_RECORD_FIELDS = frozenset({"severity", "message", "time", "logger", "exception"})


def _record_fields(record: logging.LogRecord) -> dict[str, Any]:
    settings = _state.settings
    fields: dict[str, Any] = {"service": settings.service, "environment": settings.environment}
    if settings.release:
        fields["release"] = settings.release
    context = getattr(record, "_gtp_context", None)
    if context is None:
        context = _context.get()
    for key, value in sanitize(dict(context)).items():
        if key not in _RESERVED_RECORD_FIELDS:
            fields[key] = value
    return fields


class _ContextFilter(logging.Filter):
    """Snapshot the context on the record (formatting may happen later, elsewhere)."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "_gtp_context"):
            setattr(record, "_gtp_context", _context.get())
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line; Cloud Logging maps `severity` and `message` natively."""

    def format(self, record: logging.LogRecord) -> str:
        try:
            payload: dict[str, Any] = {
                "severity": record.levelname,
                "message": scrub_text(record.getMessage()),
                "time": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
                "logger": record.name,
            }
            payload.update(_record_fields(record))
            if record.exc_info:
                payload["exception"] = scrub_text(self.formatException(record.exc_info))
            return json.dumps(payload, ensure_ascii=False, default=str)
        except Exception:  # noqa: BLE001 - never lose the line because of the formatter
            return json.dumps({"severity": record.levelname, "message": "log formatting failed",
                               "logger": record.name})


class TextFormatter(logging.Formatter):
    """Readable local format: `LEVEL logger: message key=value ...`."""

    _SKIP = frozenset({"service", "environment"})

    def format(self, record: logging.LogRecord) -> str:
        try:
            fields = " ".join(f"{k}={v}" for k, v in _record_fields(record).items() if k not in self._SKIP)
            line = f"{record.levelname} {record.name}: {scrub_text(record.getMessage())}"
            if fields:
                line += f" [{fields}]"
            if record.exc_info:
                line += "\n" + scrub_text(self.formatException(record.exc_info))
            return line
        except Exception:  # noqa: BLE001
            return f"{record.levelname} {record.name}: log formatting failed"


def configure_logging(settings: Settings) -> None:
    root = logging.getLogger()
    root.setLevel(getattr(logging, settings.log_level, logging.INFO))
    handler = next((h for h in root.handlers if getattr(h, "_gtp_handler", False)), None)
    if handler is None:
        handler = logging.StreamHandler(sys.stdout)
        handler._gtp_handler = True  # type: ignore[attr-defined]
        handler.addFilter(_ContextFilter())
        root.addHandler(handler)
    handler.setFormatter(JsonFormatter() if settings.log_format == "json" else TextFormatter())
    # httpx logs every request URL at INFO, and Telegram API URLs contain the bot token.
    logging.getLogger("httpx").setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Sentry
# ---------------------------------------------------------------------------

def _before_send(event: dict[str, Any], hint: dict[str, Any]) -> Optional[dict[str, Any]]:
    try:
        context = dict(_context.get())
        event.pop("user", None)
        request = event.get("request")
        if isinstance(request, dict):
            for key in ("data", "cookies", "env"):
                request.pop(key, None)
        tags = dict(event.get("tags") or {})
        for key in TAG_FIELDS:
            if context.get(key) is not None:
                tags[key] = str(context[key])[:200]
        settings = _state.settings
        tags.setdefault("service", settings.service)
        event["tags"] = tags
        if context:
            event.setdefault("contexts", {})["observability"] = context
        return sanitize(event)
    except Exception:  # noqa: BLE001 - privacy fails closed: drop rather than send raw
        return None


def _before_breadcrumb(crumb: dict[str, Any], hint: dict[str, Any]) -> Optional[dict[str, Any]]:
    try:
        return sanitize(crumb)
    except Exception:  # noqa: BLE001
        return None


def _init_sentry(settings: Settings, *, web: bool, transport: Any = None) -> bool:
    import sentry_sdk
    from sentry_sdk.integrations.logging import LoggingIntegration

    integrations: list[Any] = [LoggingIntegration(level=logging.INFO, event_level=logging.ERROR)]
    if web:
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
        # Only unhandled exceptions: a deliberate 503 (update in progress) is a retry signal.
        integrations += [StarletteIntegration(failed_request_status_codes=set()),
                         FastApiIntegration(failed_request_status_codes=set())]
    options: dict[str, Any] = {
        "dsn": settings.dsn,
        "environment": settings.environment,
        "release": settings.release,
        "integrations": integrations,
        # No auto-enabled integrations: e.g. httpx breadcrumbs would carry the bot token URL.
        "auto_enabling_integrations": False,
        "send_default_pii": False,
        "include_local_variables": False,
        "max_request_body_size": "never",
        "traces_sample_rate": None,
        "before_send": _before_send,
        "before_breadcrumb": _before_breadcrumb,
    }
    if transport is not None:
        options["transport"] = transport
    sentry_sdk.init(**options)
    return True


def init(service: str = "bot", *, settings: Optional[Settings] = None, web: bool = False,
         transport: Any = None) -> Settings:
    """Configure logging and (optionally) Sentry once per process. Safe to call repeatedly."""
    with _state.lock:
        if _state.initialized:
            return _state.settings
        _state.settings = settings or Settings.from_env(service)
        _state.secret_values = _known_secret_values()
        try:
            configure_logging(_state.settings)
        except Exception:  # noqa: BLE001
            pass
        if _state.settings.dsn:
            try:
                _state.sentry_enabled = _init_sentry(_state.settings, web=web, transport=transport)
            except Exception as exc:  # noqa: BLE001 - a bad DSN must not stop the bot
                _state.sentry_enabled = False
                logging.getLogger("gtp.app").warning(
                    "observability.sentry.init_failed error_type=%s", type(exc).__name__)
        _state.initialized = True
        return _state.settings


def sentry_enabled() -> bool:
    return _state.sentry_enabled


def settings() -> Settings:
    return _state.settings


def _reset_for_tests() -> None:
    """Forget initialisation and detach any Sentry client (tests only)."""
    with _state.lock:
        if _state.sentry_enabled:
            try:
                import sentry_sdk
                client = sentry_sdk.get_client()
                sentry_sdk.get_global_scope().set_client(None)
                client.close()
            except Exception:  # noqa: BLE001
                pass
        root = logging.getLogger()
        for handler in [h for h in root.handlers if getattr(h, "_gtp_handler", False)]:
            root.removeHandler(handler)
        _state.initialized = False
        _state.sentry_enabled = False
        _state.settings = Settings()
        _state.secret_values = ()
