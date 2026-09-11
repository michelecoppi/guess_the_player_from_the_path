"""Adapter contract: abstract base, result types, and structured errors.

Defines the source-neutral interface that every player data source must
implement, plus the data structures that carry results and failures through
the pipeline.

Design principles:
- One failing source must NOT corrupt data obtained from another source.
- Adapters expose structured failures for upstream retry/review decisions.
- No silent swallowing of HTTP or parsing errors.
- Raw source payloads are preserved for downstream normalization (#26)
  and provenance (#27).
"""
from __future__ import annotations

import abc
import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional, TypedDict


class AdapterErrorType(str, Enum):
    """Categorizzazione strutturata degli errori dell'adapter."""

    TRANSPORT = "transport"        # HTTP / network-level failure
    PARSE = "parse"                # Source returned data but parser failed
    NOT_FOUND = "not_found"        # Source record does not exist
    TIMEOUT = "timeout"            # Request timed out
    RATE_LIMIT = "rate_limit"      # 429 or equivalent throttling
    UNKNOWN = "unknown"            # Catch-all for unexpected errors


@dataclass
class AdapterError:
    """Structured failure from an adapter, suitable for logging and retry decisions.

    Attributes:
        error_type: Categorised cause (transport, parse, not_found, ...).
        message: Human-readable description.
        source_name: Which adapter produced this error.
        details: Free-form key/value metadata (HTTP status, URL, stack trace, ...).
        retryable: Hint for orchestration — True means a retry *might* succeed.
    """

    error_type: AdapterErrorType
    message: str
    source_name: str
    details: dict[str, Any] = field(default_factory=dict)
    retryable: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_type": self.error_type.value,
            "message": self.message,
            "source_name": self.source_name,
            "details": copy.deepcopy(self.details),
            "retryable": self.retryable,
        }


class CareerEntry(TypedDict, total=False):
    """A single career stop as extracted by a source adapter.

    All fields are optional (total=False) because different sources provide
    different subsets.  The adapter should populate whatever the source gives
    and leave the rest absent — downstream normalization (#26) handles gaps.
    """

    team: str
    country: str
    league: str
    start_year: Optional[int]
    end_year: Optional[int]
    apps: Optional[int]
    goals: Optional[int]
    loan: bool
    link: Optional[str]   # Wiki link target for club resolution


@dataclass
class AdapterResult:
    """Source-neutral result container returned by every adapter.

    Success is defined by ``success=True`` AND at least ``player_name`` being
    populated.  An adapter may still succeed with partial data (some fields
    ``None``) — the pipeline decides later whether partial data is acceptable.

    Attributes:
        source_name:    Canonical name of the source (e.g. "wikipedia", "wikidata").
        source_id:      Identifier used to query the source (page title, QID, ...).
        success:        True when usable data was extracted; False on complete failure.
        player_name:    Primary display name.
        aliases:        Alternative known names (lowercase, deduplicated).
        birth_year:     Year of birth, if found.
        birth_place:    Place of birth as raw source string, if available.
        nationality:    Nationality string *as the source reported it* (no normalisation).
        nationality_raw: Raw nationality adjective/code for downstream mapping.
        position:       Playing position *as the source reported it*.
        career:         Ordered list of career stops.
        source_metadata: Adapter-specific metadata (retrieved_at, url, revision, ...).
        raw_payload:    Full source-specific data preserved for provenance (#27).
        errors:         Non-fatal errors encountered during fetch/parse.
    """

    source_name: str
    source_id: str
    success: bool = False

    player_name: Optional[str] = None
    aliases: list[str] = field(default_factory=list)
    birth_year: Optional[int] = None
    birth_place: Optional[str] = None
    nationality: Optional[str] = None
    nationality_raw: Optional[str] = None
    position: Optional[str] = None
    career: list[CareerEntry] = field(default_factory=list)

    source_metadata: dict[str, Any] = field(default_factory=dict)
    raw_payload: dict[str, Any] = field(default_factory=dict)
    errors: list[AdapterError] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_name": self.source_name,
            "source_id": self.source_id,
            "success": self.success,
            "player_name": self.player_name,
            "aliases": list(self.aliases),
            "birth_year": self.birth_year,
            "birth_place": self.birth_place,
            "nationality": self.nationality,
            "nationality_raw": self.nationality_raw,
            "position": self.position,
            "career": [dict(c) for c in self.career],
            "source_metadata": copy.deepcopy(self.source_metadata),
            "raw_payload": copy.deepcopy(self.raw_payload),
            "errors": [e.to_dict() for e in self.errors],
        }


class PlayerSourceAdapter(abc.ABC):
    """Abstract contract that every player data source must implement.

    Concrete adapters are responsible for:
    1. Fetching data from their source (Wikipedia, Wikidata, ...);
    2. Parsing it into a source-neutral ``AdapterResult``;
    3. Wrapping ALL errors (network, parse, not-found) into ``AdapterError``
       instances rather than raising unstructured exceptions.
    """

    @property
    @abc.abstractmethod
    def source_name(self) -> str:
        """Canonical name used as the adapter's source identifier."""
        ...

    @abc.abstractmethod
    def fetch_player(self, identifier: str) -> AdapterResult:
        """Fetch and parse player data for the given source-specific identifier.

        Must NOT raise on recoverable errors — wrap them in ``AdapterResult.errors``
        and set ``success=False``.

        Args:
            identifier: Source-specific ID (e.g. Wikipedia page title, Wikidata QID).

        Returns:
            An ``AdapterResult`` with ``success=True`` on extractable data, or
            ``success=False`` with structured errors.
        """
        ...

    @abc.abstractmethod
    def search_player(self, query: str, limit: int = 5) -> list[str]:
        """Search for player identifiers matching a free-text query.

        Returns up to ``limit`` source-specific identifiers.  On error returns
        an empty list rather than raising (search is best-effort).

        Args:
            query: Free-text search query (player name, nickname, ...).
            limit: Maximum number of identifiers to return.

        Returns:
            List of source-specific identifiers found.
        """
        ...

    @staticmethod
    def _now_iso() -> str:
        """UTC timestamp in ISO-8601 format."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
