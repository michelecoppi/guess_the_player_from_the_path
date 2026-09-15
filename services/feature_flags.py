"""Operational feature flags (#51): registry, schema, pure evaluation and a TTL cache.

Flags live in one Firestore document, `admin_settings/feature_flags`, next to
`admin_settings/dataset_overrides` (`/admin_block`): a change takes effect on every replica
within the cache TTL, without a deploy. Only the server evaluates them; the Mini App receives
resolved booleans for the authenticated user and nothing else. Full contract, operator
procedure and limitations: docs/feature-flags.md.

The module is split in three layers so each can be tested on its own:

- **Registry** (`Flag`, `REGISTRY`): the only supported keys and their repository defaults.
  Every current feature defaults to *enabled*: deploying with no document changes nothing.
- **Schema + evaluation** (`parse_document`, `evaluate`, `bucket`): pure functions over plain
  data. Firestore content is untrusted operational input and is validated field by field.
- **Service** (`FeatureFlagService`): a per-process cache with a bounded TTL and a
  last-known-good configuration, reading through an injected loader
  (`services/repos/feature_flags.py` in production).

Evaluation precedence, for a flag with a stored rule:

1. master `enabled` is false → **off** (the emergency kill switch beats everything below);
2. user or group in a deny list → **off** (deny beats allow);
3. user or group in an allow list → **on**;
4. `rollout_percentage` 100 → on, 0 → off; in between the stable bucket of the subject
   (user, else group) decides, and a context with no subject is **off**;

and without a stored rule the repository default applies. This is not an experimentation
framework (#52): there are no variants, metrics or assignments recorded anywhere.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Optional

from services import observability

SCHEMA_VERSION = 1
BUCKETS = 10_000
MAX_TARGETS_PER_LIST = 1000
DEFAULT_TTL_SECONDS = 30.0
MIN_TTL_SECONDS = 1.0
MAX_TTL_SECONDS = 300.0
TTL_ENV = "FEATURE_FLAGS_CACHE_TTL_SECONDS"

# Telegram user ids are positive, group/supergroup chat ids negative; both fit in 20 digits.
_TARGET_ID = re.compile(r"-?\d{1,20}")

TARGET_LISTS = ("allow_users", "deny_users", "allow_groups", "deny_groups")
RULE_FIELDS = frozenset({"enabled", "rollout_percentage", *TARGET_LISTS})

SOURCE_FIRESTORE = "firestore"
SOURCE_DEFAULT = "default"
SOURCE_LAST_KNOWN_GOOD = "last_known_good"


class Flag(str, Enum):
    """Supported flag keys. Stable machine names: they are Firestore keys and API fields."""

    ARENA = "arena"
    SHOP = "shop"
    DAILY_UI = "daily_ui"
    HINTS = "hints"
    PLAYER_PIPELINE = "player_pipeline"
    EVENTS_V2 = "events_v2"
    LEADERBOARD = "leaderboard"


@dataclass(frozen=True)
class FlagDefinition:
    key: Flag
    default: bool
    description: str


REGISTRY: Mapping[Flag, FlagDefinition] = {
    definition.key: definition
    for definition in (
        FlagDefinition(Flag.ARENA, True, "Mini App Arena: training and duels (/app/api/arena modes training, duel)"),
        FlagDefinition(Flag.SHOP, True, "Shop browsing, equipping and purchase initiation (API, /shop, pre-checkout)"),
        FlagDefinition(Flag.DAILY_UI, True, "Mini App Daily surface: today's guess via /app/api/guess"),
        FlagDefinition(Flag.HINTS, True, "Daily hint acquisition (/app/api/hint, chat hint button)"),
        FlagDefinition(Flag.PLAYER_PIPELINE, True, "Candidate ingestion from external sources (retry_ingestion)"),
        FlagDefinition(Flag.EVENTS_V2, True, "Mini App events experience (/app/api/arena mode events)"),
        FlagDefinition(Flag.LEADERBOARD, True, "Global/monthly leaderboard retrieval (/me leaderboard, /top)"),
    )
}


class FeatureDisabled(Exception):
    """An expected refusal: the feature is switched off for this context. Not an error."""

    code = "FEATURE_DISABLED"

    def __init__(self, flag: Flag):
        super().__init__(flag.value)
        self.flag = flag


class ConfigError(ValueError):
    """The document as a whole cannot be used (not a map, unsupported schema...)."""


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FlagRule:
    enabled: bool = True
    rollout_percentage: int = 100
    allow_users: frozenset[str] = frozenset()
    deny_users: frozenset[str] = frozenset()
    allow_groups: frozenset[str] = frozenset()
    deny_groups: frozenset[str] = frozenset()


@dataclass(frozen=True)
class FlagConfig:
    """A validated configuration. `rules` holds only flags that have a stored rule."""

    rules: Mapping[Flag, FlagRule] = field(default_factory=dict)
    revision: Optional[int] = None


@dataclass(frozen=True)
class ParseReport:
    config: FlagConfig
    # flag key -> field that failed (never the value: target lists are identifiers).
    invalid: Mapping[str, str] = field(default_factory=dict)
    unknown: tuple[str, ...] = ()
    # Flags whose rule was rejected but whose valid `enabled: false` was honoured.
    kill_switch_kept: tuple[Flag, ...] = ()


def parse_flag(key: str) -> Flag:
    try:
        return Flag(key)
    except ValueError:
        raise ValueError(f"unknown feature flag '{key}'") from None


def normalize_target_id(value: Any) -> str:
    """A user/group id as the canonical string. bool is rejected even though it is an int."""
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError("target id must be an integer or a string of digits")
    text = str(value).strip()
    if not _TARGET_ID.fullmatch(text):
        raise ValueError("target id must be an integer or a string of digits")
    return str(int(text))


def parse_rule(raw: Any, default: bool) -> FlagRule:
    """One flag entry. Raises ValueError naming the offending field (never its value)."""
    if not isinstance(raw, Mapping):
        raise ValueError("entry")
    extra = set(raw) - RULE_FIELDS
    if extra:
        # Unknown fields are refused: a typo such as `rollout_percent: 10` must not silently
        # mean "100%".
        raise ValueError("unknown_field")
    enabled = raw.get("enabled", default)
    if not isinstance(enabled, bool):
        raise ValueError("enabled")
    percentage = raw.get("rollout_percentage", 100)
    if isinstance(percentage, bool) or not isinstance(percentage, int) or not 0 <= percentage <= 100:
        raise ValueError("rollout_percentage")
    lists: dict[str, Any] = {}
    for name in TARGET_LISTS:
        values = raw.get(name, [])
        if not isinstance(values, (list, tuple)) or len(values) > MAX_TARGETS_PER_LIST:
            raise ValueError(name)
        try:
            lists[name] = frozenset(normalize_target_id(value) for value in values)
        except ValueError:
            raise ValueError(name) from None
    return FlagRule(enabled=enabled, rollout_percentage=percentage, **lists)


def parse_document(raw: Optional[Mapping[str, Any]]) -> ParseReport:
    """Validate `admin_settings/feature_flags`.

    `None` (no document) is a valid, empty configuration. A document that is unusable as a
    whole raises ConfigError. A single malformed flag entry is reported in `invalid` and left
    out of `rules`, except that a valid boolean `enabled: false` is still honoured as a kill
    switch: a broken rollout field must never re-enable an emergency-disabled feature."""
    if raw is None:
        return ParseReport(FlagConfig())
    if not isinstance(raw, Mapping):
        raise ConfigError("document")
    version = raw.get("schema_version")
    if isinstance(version, bool) or version != SCHEMA_VERSION:
        raise ConfigError("schema_version")
    revision = raw.get("revision")
    if revision is not None and (isinstance(revision, bool) or not isinstance(revision, int) or revision < 0):
        raise ConfigError("revision")
    flags = raw.get("flags", {})
    if not isinstance(flags, Mapping):
        raise ConfigError("flags")

    rules: dict[Flag, FlagRule] = {}
    invalid: dict[str, str] = {}
    unknown: list[str] = []
    kept: list[Flag] = []
    for key, entry in flags.items():
        try:
            flag = Flag(key)
        except ValueError:
            unknown.append(str(key)[:64])
            continue
        try:
            rules[flag] = parse_rule(entry, REGISTRY[flag].default)
        except ValueError as exc:
            invalid[flag.value] = str(exc)
            if isinstance(entry, Mapping) and entry.get("enabled") is False:
                rules[flag] = FlagRule(enabled=False)
                kept.append(flag)
    return ParseReport(FlagConfig(rules=rules, revision=revision), invalid, tuple(sorted(unknown)), tuple(kept))


def serialize_rule(rule: FlagRule) -> dict[str, Any]:
    """The Firestore shape of a rule (sorted lists, so writes are deterministic)."""
    return {
        "enabled": rule.enabled,
        "rollout_percentage": rule.rollout_percentage,
        **{name: sorted(getattr(rule, name), key=lambda v: (len(v), v)) for name in TARGET_LISTS},
    }


# ---------------------------------------------------------------------------
# Pure evaluation
# ---------------------------------------------------------------------------

def _subject(value: Any) -> Optional[str]:
    if value is None or value == "":
        return None
    try:
        return normalize_target_id(value)
    except ValueError:
        return None


def bucket(flag: Flag, subject_type: str, subject_id: str) -> int:
    """Stable bucket in [0, BUCKETS): SHA-256 of `flag:type:id`, never Python's `hash()`.

    Same flag + subject → same bucket on every process, replica and deploy. Different flags
    hash independently, so being early in one rollout says nothing about another."""
    digest = hashlib.sha256(f"{flag.value}:{subject_type}:{subject_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big") % BUCKETS


def evaluate(flag: Flag, config: FlagConfig, *, user_id: Any = None, group_id: Any = None) -> bool:
    """Resolve one flag for a context. Pure: no I/O, no logging, never raises for bad ids."""
    rule = config.rules.get(flag)
    if rule is None:
        return REGISTRY[flag].default
    if not rule.enabled:
        return False
    user = _subject(user_id)
    group = _subject(group_id)
    if (user is not None and user in rule.deny_users) or (group is not None and group in rule.deny_groups):
        return False
    if (user is not None and user in rule.allow_users) or (group is not None and group in rule.allow_groups):
        return True
    if rule.rollout_percentage >= 100:
        return True
    if rule.rollout_percentage <= 0:
        return False
    if user is not None:
        return bucket(flag, "user", user) < rule.rollout_percentage * (BUCKETS // 100)
    if group is not None:
        return bucket(flag, "group", group) < rule.rollout_percentage * (BUCKETS // 100)
    # Partial rollout without a subject: conservative and deterministic.
    return False


def resolve_all(config: FlagConfig, *, user_id: Any = None, group_id: Any = None) -> dict[str, bool]:
    return {flag.value: evaluate(flag, config, user_id=user_id, group_id=group_id) for flag in Flag}


# ---------------------------------------------------------------------------
# Operator changes (pure; the repository applies them inside a transaction)
# ---------------------------------------------------------------------------

def rule_or_default(raw_entry: Any, flag: Flag) -> FlagRule:
    """The current stored rule, or the default one if absent. A malformed stored entry is
    refused: the operator must `reset` it first instead of building on unknown data."""
    if raw_entry is None:
        return FlagRule(enabled=REGISTRY[flag].default)
    return parse_rule(raw_entry, REGISTRY[flag].default)


def change_enabled(rule: FlagRule, enabled: bool) -> FlagRule:
    if not isinstance(enabled, bool):
        raise ValueError("enabled must be a boolean")
    return replace(rule, enabled=enabled)


def change_rollout(rule: FlagRule, percentage: int) -> FlagRule:
    if isinstance(percentage, bool) or not isinstance(percentage, int) or not 0 <= percentage <= 100:
        raise ValueError("rollout percentage must be an integer between 0 and 100")
    return replace(rule, rollout_percentage=percentage)


def change_target(rule: FlagRule, list_name: str, target_id: Any, *, add: bool) -> FlagRule:
    if list_name not in TARGET_LISTS:
        raise ValueError(f"unknown target list '{list_name}'")
    target = normalize_target_id(target_id)
    current: frozenset[str] = getattr(rule, list_name)
    updated = current | {target} if add else current - {target}
    if len(updated) > MAX_TARGETS_PER_LIST:
        raise ValueError(f"{list_name} cannot hold more than {MAX_TARGETS_PER_LIST} ids")
    changes: dict[str, Any] = {list_name: updated}
    return replace(rule, **changes)


def clear_targets(rule: FlagRule, target_ids: Iterable[Any], *, groups: bool) -> FlagRule:
    """Remove ids from both the allow and the deny list of one subject type."""
    ids = {normalize_target_id(value) for value in target_ids}
    names = ("allow_groups", "deny_groups") if groups else ("allow_users", "deny_users")
    changes: dict[str, Any] = {name: getattr(rule, name) - ids for name in names}
    return replace(rule, **changes)


# ---------------------------------------------------------------------------
# Cached service
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Snapshot:
    config: FlagConfig
    source: str
    fetched_at: float
    expires_at: float


def ttl_from_env(environ: Optional[Mapping[str, str]] = None) -> float:
    raw = ((environ if environ is not None else os.environ).get(TTL_ENV) or "").strip()
    if not raw:
        return DEFAULT_TTL_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_TTL_SECONDS
    if value != value:  # NaN
        return DEFAULT_TTL_SECONDS
    return min(max(value, MIN_TTL_SECONDS), MAX_TTL_SECONDS)


Loader = Callable[[], Optional[Mapping[str, Any]]]


class FeatureFlagService:
    """Per-process flag cache.

    - A fresh snapshot is served for `ttl` seconds; then the next caller refreshes it.
    - While one thread refreshes, others keep using the current snapshot (no pile-up on a
      slow Firestore); only a cold process with no snapshot at all waits for the first read.
    - A failed or unusable read keeps the last-known-good configuration, so an emergency
      disable is never undone by a Firestore outage. With no last-known-good (cold start)
      it serves repository defaults. Either way the next attempt waits another `ttl`.
    """

    def __init__(self, loader: Loader, *, ttl: Optional[float] = None,
                 clock: Callable[[], float] = time.monotonic):
        self._loader = loader
        self._ttl = ttl_from_env() if ttl is None else min(max(float(ttl), 0.0), MAX_TTL_SECONDS)
        self._clock = clock
        self._lock = threading.Lock()
        self._snapshot: Optional[Snapshot] = None
        self._last_known_good: Optional[FlagConfig] = None
        self._warned: Optional[tuple[Any, ...]] = None

    @property
    def ttl(self) -> float:
        return self._ttl

    def invalidate(self) -> None:
        """Force the next evaluation to re-read (keeps the last-known-good)."""
        with self._lock:
            if self._snapshot is not None:
                self._snapshot = replace(self._snapshot, expires_at=float("-inf"))

    def snapshot(self) -> Snapshot:
        current = self._snapshot
        if current is not None and self._clock() < current.expires_at:
            return current
        if current is not None:
            if not self._lock.acquire(blocking=False):
                return current
        else:
            self._lock.acquire()
        try:
            current = self._snapshot
            if current is not None and self._clock() < current.expires_at:
                return current
            self._snapshot = self._refresh(current)
            return self._snapshot
        finally:
            self._lock.release()

    def _refresh(self, previous: Optional[Snapshot]) -> Snapshot:
        try:
            raw = self._loader()
            report = parse_document(raw)
        except ConfigError as exc:
            self._warn_once("feature_flags.config.rejected", ("rejected", str(exc)),
                            reason=str(exc), source=self._fallback_source())
            return self._fallback()
        except Exception as exc:  # noqa: BLE001 - flags must never take a request down
            self._warn_once("feature_flags.refresh.failed", ("failed", type(exc).__name__),
                            error_type=type(exc).__name__, source=self._fallback_source())
            return self._fallback()

        source = SOURCE_FIRESTORE if raw is not None else SOURCE_DEFAULT
        config = report.config
        if report.invalid:
            merged = dict(config.rules)
            for key in report.invalid:
                flag = Flag(key)
                if flag in report.kill_switch_kept:
                    continue
                if self._last_known_good is not None and flag in self._last_known_good.rules:
                    merged[flag] = self._last_known_good.rules[flag]
            config = FlagConfig(rules=merged, revision=config.revision)
        problems = (tuple(sorted(report.invalid.items())), report.unknown)
        if report.invalid or report.unknown:
            # Flag names and field names only: never values, never target ids.
            self._warn_once(
                "feature_flags.config.invalid", ("invalid", config.revision, problems),
                flags=sorted(report.invalid), fields=[report.invalid[k] for k in sorted(report.invalid)],
                kill_switch_kept=[flag.value for flag in report.kill_switch_kept],
                unknown_count=len(report.unknown), revision=config.revision,
            )
        else:
            self._warned = None

        if previous is None or previous.source != source or previous.config.revision != config.revision:
            observability.log_event("feature_flags.config.loaded", revision=config.revision,
                                    stored_flags=len(config.rules), source=source)
        self._last_known_good = config
        now = self._clock()
        return Snapshot(config, source, now, now + self._ttl)

    def _warn_once(self, event: str, signature: tuple[Any, ...], **fields: Any) -> None:
        """One WARNING per distinct problem, not one per TTL on every replica."""
        if self._warned == signature:
            return
        self._warned = signature
        observability.log_event(event, logging.WARNING, **fields)

    def _fallback_source(self) -> str:
        return SOURCE_LAST_KNOWN_GOOD if self._last_known_good is not None else SOURCE_DEFAULT

    def _fallback(self) -> Snapshot:
        now = self._clock()
        config = self._last_known_good if self._last_known_good is not None else FlagConfig()
        return Snapshot(config, self._fallback_source(), now, now + self._ttl)

    def is_enabled(self, flag: Flag, *, user_id: Any = None, group_id: Any = None) -> bool:
        try:
            return evaluate(flag, self.snapshot().config, user_id=user_id, group_id=group_id)
        except Exception:  # noqa: BLE001 - last line of defence: the repository default
            return REGISTRY[flag].default if flag in REGISTRY else False

    def resolved(self, *, user_id: Any = None, group_id: Any = None) -> dict[str, bool]:
        try:
            return resolve_all(self.snapshot().config, user_id=user_id, group_id=group_id)
        except Exception:  # noqa: BLE001
            return {flag.value: REGISTRY[flag].default for flag in Flag}


# ---------------------------------------------------------------------------
# Process-wide entry points used by the runtime
# ---------------------------------------------------------------------------

def _firestore_loader() -> Optional[Mapping[str, Any]]:
    from services.repos.feature_flags import load_document
    return load_document()


_service_lock = threading.Lock()
_service: Optional[FeatureFlagService] = None


def get_service() -> FeatureFlagService:
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                _service = FeatureFlagService(_firestore_loader)
    return _service


def set_service(service: Optional[FeatureFlagService]) -> None:
    """Replace the process-wide service (tests, local previews). None restores Firestore."""
    global _service
    with _service_lock:
        _service = service


def is_enabled(flag: Flag, *, user_id: Any = None, group_id: Any = None) -> bool:
    """Never raises: on any internal failure it answers with the repository default."""
    if not isinstance(flag, Flag):
        return False
    return get_service().is_enabled(flag, user_id=user_id, group_id=group_id)


def ensure_enabled(flag: Flag, *, user_id: Any = None, group_id: Any = None) -> None:
    if not is_enabled(flag, user_id=user_id, group_id=group_id):
        raise FeatureDisabled(flag)


def resolved_features(*, user_id: Any = None, group_id: Any = None) -> dict[str, bool]:
    """Only booleans for this context: never rules, target lists, rollout or metadata."""
    return get_service().resolved(user_id=user_id, group_id=group_id)
