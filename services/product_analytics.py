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
- **Taxonomy** (`Event`, `EVENT_PROPERTIES`, `PROPERTY_VALIDATORS`): one flat registry of
  snake_case verb-object event names, each with its own allowed-property set and, per
  property, a type/enum/catalogue validator - adapted from what the bot and Mini App
  actually do (see `docs/product-analytics.md` for the trigger/source/idempotency of every
  event - that document, not this docstring, is authoritative). `capture()` refuses events
  that are not in the registry, and drops any property that is not on *that event's*
  allow-list or whose value fails its validator, so a runtime dict - or a value that merely
  looks plausible, like a fabricated Shop item id - can never leak into PostHog.
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
import re
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from services import observability, version

_logger = logging.getLogger("gtp.analytics")

ENV_ENABLED = "PRODUCT_ANALYTICS_ENABLED"
ENV_API_KEY = "POSTHOG_API_KEY"  # pragma: allowlist secret
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


# ---------------------------------------------------------------------------
# Property schema: per-property VALUE validators, and per-EVENT allowed-key sets.
#
# Two layers, both required for a property to reach PostHog (see `_clean_properties`):
#
# 1. `EVENT_PROPERTIES[event]` says which keys that specific event may carry at all - so
#    `BOT_STARTED` cannot carry `item_id` even though `item_id` is a perfectly valid key
#    for `SHOP_ITEM_PREVIEWED`. A global allow-list (the old design) could not express this;
#    a key valid for one event is not automatically safe or meaningful for another.
# 2. `PROPERTY_VALIDATORS[key]` says what a *legitimate value* of that key looks like: a
#    fixed enum, a bool, a bounded int, or - for `item_id`/`item_kind` - a live check
#    against the real Shop catalogue (`services/shop.py`), not just a shape/regex. A
#    property whose name is allowed but whose value fails its validator is dropped, exactly
#    like an unknown key. This is what stops a malformed or attacker-shaped request (e.g. a
#    Mini App payload with `item="anything"`) from ever turning into an analytics dimension:
#    the value has to be a real catalogue id, not merely a string that looks like one.
#
# Both layers apply on top of `observability.is_sensitive_key` (defense in depth: a key
# accidentally added here that also looks like a secret is still refused) and
# `observability.sanitize` (value-level scrubbing/bounding).
# ---------------------------------------------------------------------------

SUPPORTED_LANGUAGES = ("it", "es", "en")
_CATALOG_ID = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_EVENT_CODE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_DUEL_CODE = re.compile(r"^[a-f0-9]{24}$")


def _enum(*values: str) -> Callable[[Any], bool]:
    allowed = frozenset(values)
    return lambda value: isinstance(value, str) and value in allowed


def _pattern(compiled: re.Pattern[str]) -> Callable[[Any], bool]:
    return lambda value: isinstance(value, str) and bool(compiled.fullmatch(value))


def _bool(value: Any) -> bool:
    return isinstance(value, bool)


def _int(minimum: int, maximum: int) -> Callable[[Any], bool]:
    def check(value: Any) -> bool:
        # bool is an int subclass in Python; a bool value here is a type mismatch, not a
        # valid 0/1.
        return isinstance(value, int) and not isinstance(value, bool) and minimum <= value <= maximum
    return check


def _catalog_item_id(value: Any) -> bool:
    """A real, currently-existing Shop catalogue id - never merely a well-shaped string.

    Lazy import: `services/shop.py` never imports this module, so there is no cycle, but
    importing it eagerly at module load would still be an unnecessary coupling for a check
    that only Shop-related events ever exercise."""
    if not isinstance(value, str) or not _CATALOG_ID.fullmatch(value):
        return False
    try:
        from services import shop
        return shop.get_item(value) is not None
    except Exception:  # noqa: BLE001 - a catalogue import/lookup failure must reject, not raise
        return False


def _item_kind(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        from services import shop
        return value in shop.KINDS or value == "bundle"
    except Exception:  # noqa: BLE001
        return False


# One validator per property NAME (the same name means the same shape everywhere it is
# allowed to appear - only EVENT_PROPERTIES decides *where* it may appear).
PROPERTY_VALIDATORS: dict[str, Callable[[Any], bool]] = {
    "surface": _enum("telegram_chat", "miniapp"),
    "language": _enum(*SUPPORTED_LANGUAGES),
    "is_new_user": _bool,
    "referral_attached": _bool,
    "scope": _enum("global", "monthly"),
    "status": _enum("correct", "wrong", "refused", "failed"),
    "reason": _enum(
        "not_registered", "already_guessed", "no_attempts",  # Daily / Events attempts
        "feature_disabled", "price_changed", "unknown_item", "not_for_sale",
        "welcome_only", "checkout_busy",  # Shop refusals (services/shop.py::purchase_status,
                                          # services/repos/shop.py::reserve_checkout)
    ),
    "attempt_index": _int(1, 1000),
    "attempts_used": _int(0, 1000),
    "attempts_left": _int(0, 1000),
    "hints_used": _int(0, 1000),
    "hint_index": _int(1, 1000),
    "streak": _int(0, 100_000),
    "bonus_awarded": _bool,
    "typo": _bool,
    "event_type": _enum("path", "career", "father_son", "transfer_guess"),
    "event_code": _pattern(_EVENT_CODE),
    "duel_code": _pattern(_DUEL_CODE),
    "qualified_days": _int(1, 3650),
    "reward_item_count": _int(0, 100),
    "item_kind": _item_kind,
    "item_id": _catalog_item_id,
    "price_stars": _int(0, 1_000_000),
    "success": _bool,
}

# Exactly which of the properties above a given event may carry. An event not listed here
# (or a key not in its set) carries no extra properties at all - only the automatic
# enrichment (`environment`, `app_version`, `app_revision`, `$process_person_profile`).
#
# `hint_type`, `difficulty_band`, `source` and `game_mode` are deliberately absent from
# every set below: nothing in the current bot/Mini App code emits them (see
# docs/product-analytics.md §6/§16 - `difficulty_band` in particular is reserved for #21,
# not invented ahead of it). A property with no event that allows it can never be sent.
EVENT_PROPERTIES: dict[Event, frozenset[str]] = {
    Event.BOT_STARTED: frozenset({"language", "is_new_user"}),
    Event.MINIAPP_OPENED: frozenset({"language"}),
    Event.DAILY_VIEWED: frozenset({"surface", "language"}),
    Event.DAILY_GUESS_SUBMITTED: frozenset({
        "surface", "status", "reason", "attempts_used", "attempts_left", "hints_used", "typo",
    }),
    Event.DAILY_GUESS_CORRECT: frozenset({"surface", "attempts_used", "hints_used", "streak", "bonus_awarded"}),
    Event.DAILY_COMPLETED: frozenset({"surface", "status", "attempts_used", "hints_used"}),
    Event.DAILY_ARCHIVE_VIEWED: frozenset({"surface"}),
    Event.HINT_REQUESTED: frozenset({"surface"}),
    Event.HINT_USED: frozenset({"surface", "hint_index", "hints_used"}),
    Event.TRAINING_STARTED: frozenset({"surface"}),
    Event.TRAINING_GUESS_SUBMITTED: frozenset({"surface", "status", "attempt_index"}),
    Event.TRAINING_COMPLETED: frozenset({"surface", "status", "attempts_used"}),
    Event.ARENA_VIEWED: frozenset({"surface"}),
    Event.DUEL_CREATED: frozenset({"surface"}),
    Event.DUEL_JOINED: frozenset({"surface"}),
    Event.DUEL_COMPLETED: frozenset({"surface"}),
    Event.EVENT_VIEWED: frozenset({"surface", "event_code", "event_type"}),
    Event.EVENT_STARTED: frozenset({"surface", "event_code", "event_type"}),
    Event.EVENT_COMPLETED: frozenset({"surface", "event_code", "event_type", "attempts_used", "bonus_awarded"}),
    Event.LEADERBOARD_VIEWED: frozenset({"surface", "scope"}),
    Event.REFERRAL_OPENED: frozenset({"referral_attached"}),
    Event.REFERRAL_CONVERTED: frozenset({"qualified_days"}),
    Event.REFERRAL_REWARD_GRANTED: frozenset({"reward_item_count"}),
    Event.SHOP_VIEWED: frozenset({"surface"}),
    Event.SHOP_ITEM_PREVIEWED: frozenset({"surface", "item_id", "item_kind"}),
    Event.SHOP_PURCHASE_STARTED: frozenset({"surface", "item_id", "item_kind", "price_stars"}),
    Event.SHOP_PURCHASE_REFUSED: frozenset({"surface", "item_id", "reason", "success"}),
    # No `surface`: successful_payment is delivered through one handler regardless of where
    # the invoice was opened (see docs/product-analytics.md §6) - recording a surface here
    # would either be a guess or require plumbing state across the pre-checkout round trip
    # for no product benefit.
    Event.SHOP_PURCHASE_COMPLETED: frozenset({"item_id", "item_kind", "price_stars", "success"}),
    Event.SHOP_ITEM_EQUIPPED: frozenset({"surface", "item_id", "item_kind"}),
}


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
        # posthog-python 7.x renamed the constructor's first argument from `api_key` to
        # `project_api_key` (verified against the installed 7.54.0 - the current PyPI
        # stable release at the time this was written; re-check before assuming it still
        # holds after any future `posthog` bump, the same way any pinned dependency needs
        # re-verifying). Passing the old `api_key=` kwarg now raises TypeError.
        project_api_key=settings.api_key,
        host=settings.host,
        # Deliberately conservative: no autocapture/session-replay/feature-flags client here
        # (autocapture and session replay do not exist server-side in posthog-python; this
        # flag concerns *feature flag evaluation requests* the client could make on our
        # behalf, which we do not want - #51 already owns feature flags).
        disable_geoip=True,
        enable_exception_autocapture=False,
    )


def _call_capture(client: Any, event_name: str, distinct_id: str, properties: Mapping[str, Any]) -> Any:
    """The one line that actually talks to the posthog-python SDK's `capture()`.

    Split out from `capture()` on purpose: `capture()` swallows every exception (analytics
    must never break product code), which would silently hide a future SDK signature change
    from the test suite. `tests/test_product_analytics.py`'s real-SDK smoke test calls this
    function directly, against the genuine installed `posthog.Posthog` client (built with
    `disabled=True`, so nothing reaches the network), so a keyword this SDK version no longer
    accepts fails that test loudly instead of being caught here and merely logged. The
    return value is passed through (not used by `capture()`) purely so that smoke test can
    also assert on it."""
    return client.capture(event=event_name, distinct_id=distinct_id, properties=dict(properties))


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

def _clean_properties(event: Event, raw: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    """Keep only keys this *specific* event is allowed to carry, and only when their value
    passes that key's validator. A key valid for a different event, an unknown key, a
    sensitive-looking key, or a value that fails its type/enum/catalogue check are all
    dropped the same way - the caller never learns which case it was, by design."""
    allowed_keys = EVENT_PROPERTIES.get(event, frozenset())
    if not raw:
        return {}
    cleaned: dict[str, Any] = {}
    dropped: list[str] = []
    for key, value in raw.items():
        name = str(key)
        validator = PROPERTY_VALIDATORS.get(name)
        if (
            name not in allowed_keys
            or validator is None
            or observability.is_sensitive_key(name)
            or not validator(value)
        ):
            dropped.append(name)
            continue
        cleaned[name] = value
    if dropped:
        _state.warn_once(
            "dropped:" + event.value + ":" + ",".join(sorted(dropped)),
            "product_analytics.property.dropped",
            product_event=event.value, properties=sorted(dropped),
        )
    # Defense in depth: sanitize() scrubs stray secrets/tokens out of values and bounds
    # size/depth, on top of the per-event schema above.
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
        enriched = _clean_properties(event, properties)
        enriched["environment"] = _state.settings.environment
        if _state.settings.release:
            enriched["app_version"] = _state.settings.release
        if _state.settings.revision:
            enriched["app_revision"] = _state.settings.revision
        # Data-minimization (issue #29 item 6): we intentionally never call `identify()` and
        # only ever send a pseudonymous id, so PostHog should not build a Person profile for
        # it either. `$process_person_profile: False` is the SDK-recognised sentinel
        # property (posthog/capture_v1.py) that marks an event "personless" regardless of
        # whether `distinct_id` was supplied - verified against the installed 7.54.0 source,
        # not assumed from older SDK behaviour. See docs/product-analytics.md §7 for the
        # provider-side setting this still cannot replace (Person profile mode is also a
        # PostHog *project* setting an operator must confirm).
        enriched["$process_person_profile"] = False
        _call_capture(_state.client, event.value, distinct_id, enriched)
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
