"""Product analytics (#29): one small, typed capture surface in front of PostHog.

Why this exists next to `services/observability.py` (#18) and not inside it: observability
answers "is the app healthy" (structured logs, Sentry errors, request tracing).  Product
analytics answers "how are people actually using the product" (which surface, which mode,
did a purchase actually deliver).  The two must never merge - an ERROR log is not a product
event, and a product event is never routed through Sentry - so this module owns its own
settings, its own client and its own privacy rules, and only borrows two things from
observability on purpose: `services.version` (the same release/revision every other
subsystem reports) and `observability.is_sensitive_key` / `observability.sanitize` (so a
typo'd property name is caught by the same redaction rules as everything else, instead of a
second, slightly different denylist).

Design, in order:

- **Settings** (`Settings.from_env`): no `POSTHOG_API_KEY` -> analytics is off, full stop.
  The app must behave identically with analytics on or off; nothing here may ever raise into
  a Telegram handler or a FastAPI endpoint.
- **Taxonomy** (`Event`, `ALLOWED_PROPERTIES`): one flat registry of snake_case verb-object
  event names, adapted from what the bot and Mini App actually do (see
  `docs/product-analytics.md` for the trigger/source/idempotency of every event - that
  document, not this docstring, is authoritative). `capture()` refuses events that are not in
  the registry and drops any property key that is not on the allow-list, so a runtime dict
  can never leak into PostHog just because someone passed it in.
- **Identity** (`distinct_id_for_user`): a keyed HMAC-SHA256 of the Telegram user id with a
  *dedicated* `PRODUCT_ANALYTICS_SALT` - never the raw id, never `observability.user_ref`'s
  salt (different purpose, different blast radius if it ever leaked). Without a salt,
  `capture()` is a safe no-op: we will not invent an identity.
- **Delivery**: the official `posthog-python` client, built once and reused (it batches and
  flushes on its own background thread - see `posthog.Posthog` in `_client()`). Every public
  function here is wrapped so a PostHog outage, a bad property, or a client that was never
  built cannot affect gameplay, payments or referrals.
"""
from __future__ import annotations

import logging
import os
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from services import observability, version

_logger = logging.getLogger("gtp.analytics")

ENV_ENABLED = "PRODUCT_ANALYTICS_ENABLED"
ENV_API_KEY = "POSTHOG_API_KEY"
ENV_HOST = "POSTHOG_HOST"
ENV_ENVIRONMENT = "PRODUCT_ANALYTICS_ENVIRONMENT"
ENV_SALT = "PRODUCT_ANALYTICS_SALT"
DEFAULT_HOST = "https://eu.i.posthog.com"

_TRUTHY = {"1", "true", "yes", "on"}
_FALSY = {"0", "false", "no", "off"}


# ---------------------------------------------------------------------------
# Taxonomy
# ---------------------------------------------------------------------------

class Event(str, Enum):
    """The only event names this process will ever send. See docs/product-analytics.md for
    the exact trigger, source (server/client) and idempotency contract of each one."""

    # Lifecycle
    BOT_STARTED = "bot_started"
    MINIAPP_OPENED = "miniapp_opened"
    # Daily
    DAILY_VIEWED = "daily_viewed"
    DAILY_GUESS_SUBMITTED = "daily_guess_submitted"
    DAILY_GUESS_CORRECT = "daily_guess_correct"
    DAILY_COMPLETED = "daily_completed"
    DAILY_ARCHIVE_VIEWED = "daily_archive_viewed"
    # Hints
    HINT_REQUESTED = "hint_requested"
    HINT_USED = "hint_used"
    # Training
    TRAINING_STARTED = "training_started"
    TRAINING_GUESS_SUBMITTED = "training_guess_submitted"
    TRAINING_COMPLETED = "training_completed"
    # Arena / duels
    ARENA_VIEWED = "arena_viewed"
    DUEL_CREATED = "duel_created"
    DUEL_JOINED = "duel_joined"
    DUEL_COMPLETED = "duel_completed"
    # Events
    EVENT_VIEWED = "event_viewed"
    EVENT_STARTED = "event_started"
    EVENT_COMPLETED = "event_completed"
    # Leaderboard
    LEADERBOARD_VIEWED = "leaderboard_viewed"
    # Referral
    REFERRAL_OPENED = "referral_opened"
    REFERRAL_CONVERTED = "referral_converted"
    REFERRAL_REWARD_GRANTED = "referral_reward_granted"
    # Shop / payments
    SHOP_VIEWED = "shop_viewed"
    SHOP_ITEM_PREVIEWED = "shop_item_previewed"
    SHOP_PURCHASE_STARTED = "shop_purchase_started"
    SHOP_PURCHASE_REFUSED = "shop_purchase_refused"
    SHOP_PURCHASE_COMPLETED = "shop_purchase_completed"
    SHOP_ITEM_EQUIPPED = "shop_item_equipped"


# Properties every capture() call may carry, on top of what is enriched automatically
# (environment, release, revision, surface come from Settings / the call site, never from a
# runtime dict). Anything not listed here is dropped before the event ever reaches
# `posthog.capture`; see `_clean_properties`. Kept deliberately small and product-shaped -
# no ids, no free text, no full objects.
ALLOWED_PROPERTIES = frozenset({
    "surface",              # "telegram_chat" | "miniapp"
    "source",                # e.g. "referral", "direct", "deep_link"
    "language",
    "is_new_user",
    "referral_attached",
    "game_mode",             # "daily" | "archive" | "training" | "duel" | "event"
    "scope",                 # leaderboard scope: "global" | "monthly"
    "status",                # bounded outcome enum (e.g. "correct", "wrong", "refused")
    "reason",                 # bounded refusal/failure reason enum
    "attempt_index",
    "attempts_used",
    "attempts_left",
    "hints_used",
    "hint_index",
    "hint_type",
    "difficulty_band",
    "streak",
    "bonus_awarded",
    "typo",
    "event_type",
    "event_code",
    "duel_code",
    "qualified_days",
    "reward_item_count",
    "item_kind",
    "item_id",
    "price_stars",
    "success",
})


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Settings:
    enabled: bool = False
    api_key: str = ""
    host: str = DEFAULT_HOST
    environment: str = "development"
    release: Optional[str] = None
    revision: Optional[str] = None
    salt: str = ""

    @classmethod
    def from_env(cls, environ: Optional[Mapping[str, str]] = None) -> "Settings":
        env = os.environ if environ is None else environ
        api_key = (env.get(ENV_API_KEY) or "").strip()
        on_cloud_run = bool(env.get("K_SERVICE"))
        under_pytest = bool(env.get("PYTEST_CURRENT_TEST"))
        environment = (env.get(ENV_ENVIRONMENT) or env.get("SENTRY_ENVIRONMENT") or "").strip()
        if not environment:
            environment = "test" if under_pytest else ("production" if on_cloud_run else "development")

        raw_flag = (env.get(ENV_ENABLED) or "").strip().lower()
        if raw_flag in _TRUTHY:
            explicit: Optional[bool] = True
        elif raw_flag in _FALSY:
            explicit = False
        else:
            explicit = None

        # No key -> off, no exceptions. Local/test default off even with a key, unless the
        # operator opts in explicitly: analytics traffic must never be an accident of a
        # developer's shell environment.
        if explicit is not None:
            wants_on = explicit
        else:
            wants_on = environment not in ("local", "test", "development")
        enabled = bool(api_key) and wants_on

        return cls(
            enabled=enabled,
            api_key=api_key,
            host=(env.get(ENV_HOST) or DEFAULT_HOST).strip() or DEFAULT_HOST,
            environment=environment,
            release=version.get_version(),
            revision=version.get_build_revision() if environ is None else (env.get("K_REVISION") or None),
            salt=(env.get(ENV_SALT) or "").strip(),
        )


class _State:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.initialized = False
        self.settings = Settings()
        self.client: Any = None
        self._warned: set[str] = set()

    def warn_once(self, key: str, event: str, **fields: Any) -> None:
        if key in self._warned:
            return
        self._warned.add(key)
        observability.log_event(event, logging.WARNING, component="analytics", **fields)


_state = _State()


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------

def distinct_id_for_user(user_id: Any) -> Optional[str]:
    """A stable pseudonymous PostHog `distinct_id` for a Telegram user id.

    Keyed HMAC-SHA256 with a *dedicated* analytics salt: without our secret the mapping back
    to a Telegram id is not feasible. Never plain `hash()`, never the raw id. Returns None
    (never a fallback identity) when no salt is configured or the id is missing."""
    salt = _state.settings.salt
    if not salt or user_id is None or user_id == "":
        return None
    import hashlib
    import hmac
    return "u_" + hmac.new(salt.encode(), str(user_id).encode(), hashlib.sha256).hexdigest()[:24]


def distinct_id_for_anonymous(session_id: str) -> Optional[str]:
    """A distinct_id for a genuinely unauthenticated surface (no such flow exists yet in this
    codebase - every Mini App and bot event today comes from an id already verified by
    initData or a Telegram update). Kept as a documented extension point, not wired to any
    call site: see docs/product-analytics.md."""
    if not isinstance(session_id, str) or not session_id:
        return None
    return "a_" + session_id[:64]


# ---------------------------------------------------------------------------
# Client lifecycle
# ---------------------------------------------------------------------------

def _build_client(settings: Settings) -> Any:
    from posthog import Posthog

    return Posthog(
        api_key=settings.api_key,
        host=settings.host,
        # Deliberately conservative: no autocapture/session-replay/feature-flags client here
        # (autocapture and session replay do not exist server-side in posthog-python; this
        # flag concerns *feature flag evaluation requests* the client could make on our
        # behalf, which we do not want - #51 already owns feature flags).
        disable_geoip=True,
        enable_exception_autocapture=False,
    )


def init(*, settings: Optional[Settings] = None) -> Settings:
    """Configure the analytics client once per process. Safe to call repeatedly and safe to
    call when analytics is disabled (in which case it does nothing but record the settings)."""
    with _state.lock:
        if _state.initialized:
            return _state.settings
        _state.settings = settings if settings is not None else Settings.from_env()
        if _state.settings.enabled:
            try:
                _state.client = _build_client(_state.settings)
            except Exception as exc:  # noqa: BLE001 - a bad key/host must not stop the app
                _state.client = None
                _state.warn_once("init_failed", "product_analytics.init_failed",
                                 error_type=type(exc).__name__)
        _state.initialized = True
        return _state.settings


def is_enabled() -> bool:
    return bool(_state.settings.enabled and _state.client is not None)


def settings() -> Settings:
    return _state.settings


# ---------------------------------------------------------------------------
# Capture
# ---------------------------------------------------------------------------

def _clean_properties(raw: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    if not raw:
        return {}
    cleaned: dict[str, Any] = {}
    dropped: list[str] = []
    for key, value in raw.items():
        name = str(key)
        if name not in ALLOWED_PROPERTIES or observability.is_sensitive_key(name):
            dropped.append(name)
            continue
        cleaned[name] = value
    if dropped:
        _state.warn_once(
            "dropped:" + ",".join(sorted(dropped)), "product_analytics.property.dropped",
            properties=sorted(dropped),
        )
    # Defense in depth: sanitize() scrubs stray secrets/tokens out of values and bounds
    # size/depth, on top of the key allow-list above.
    return observability.sanitize(cleaned)


def capture(
    event: Event,
    *,
    user_id: Any = None,
    anonymous_id: Optional[str] = None,
    properties: Optional[Mapping[str, Any]] = None,
) -> None:
    """Record one product event. Never raises, never blocks a caller on network I/O
    (posthog-python queues and flushes on its own background thread), and is a pure no-op
    when analytics is disabled, misconfigured, or the event/identity cannot be resolved."""
    try:
        if not is_enabled():
            return
        if not isinstance(event, Event):
            _state.warn_once("unknown_event:" + str(event), "product_analytics.event.unknown")
            return
        distinct_id = (
            distinct_id_for_anonymous(anonymous_id) if anonymous_id is not None
            else distinct_id_for_user(user_id)
        )
        if not distinct_id:
            _state.warn_once("no_identity:" + event.value, "product_analytics.identity.missing",
                             product_event=event.value)
            return
        enriched = _clean_properties(properties)
        enriched["environment"] = _state.settings.environment
        if _state.settings.release:
            enriched["app_version"] = _state.settings.release
        if _state.settings.revision:
            enriched["app_revision"] = _state.settings.revision
        _state.client.capture(distinct_id=distinct_id, event=event.value, properties=enriched)
    except Exception as exc:  # noqa: BLE001 - analytics must never break the caller
        try:
            _state.warn_once("capture_failed:" + type(exc).__name__, "product_analytics.capture_failed",
                             error_type=type(exc).__name__)
        except Exception:  # noqa: BLE001
            pass


def flush() -> None:
    """Best-effort flush (e.g. before a short-lived process exits). Never raises."""
    try:
        if _state.client is not None:
            _state.client.flush()
    except Exception:  # noqa: BLE001
        pass


def shutdown() -> None:
    """Stop the background worker cleanly. Never raises."""
    try:
        if _state.client is not None:
            _state.client.shutdown()
    except Exception:  # noqa: BLE001
        pass


def _reset_for_tests() -> None:
    with _state.lock:
        if _state.client is not None:
            try:
                _state.client.shutdown()
            except Exception:  # noqa: BLE001
                pass
        _state.initialized = False
        _state.settings = Settings()
        _state.client = None
        _state._warned = set()
