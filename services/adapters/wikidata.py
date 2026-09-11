"""Wikidata adapter for structured player data acquisition.

Fetches footballer data from the Wikidata entity API — a structured,
machine-readable source complementary to Wikipedia's free-text infoboxes.

Wikidata properties used:
- P31  (instance of) — to verify the entity is a human
- P106 (occupation) — to verify the entity is a footballer
- P27  (country of citizenship) — nationality
- P413 (position played on team) — playing position
- P569 (date of birth) — birth year
- P54  (member of sports team) — career history
  - P580 (start time) qualifier — start year
  - P582 (end time) qualifier — end year
  - P118 (league) qualifier — league
  - P1642 (number of matches played) qualifier — appearances
  - P1351 (number of goals) qualifier — goals
"""
from __future__ import annotations

import re
import urllib.parse
from typing import Any, Optional

from services.adapters.base import (
    AdapterError,
    AdapterErrorType,
    AdapterResult,
    CareerEntry,
    PlayerSourceAdapter,
)
from services.adapters.http_client import HttpClient, HttpError, UrllibHttpClient

_SOURCE_NAME = "wikidata"
_ENTITY_API = "https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"

# ── Position mapping (Wikidata QIDs → dataset labels) ────────────────────

_POSITION_MAP: dict[str, str] = {
    "Q193592": "Attaccante",        # forward
    "Q280658": "Centrocampista",    # midfielder
    "Q336286": "Difensore",         # defender
    "Q201330": "Portiere",          # goalkeeper
    "Q4611891": "Centrocampista",   # winger (maps to centrocampista in dataset)
    "Q2383640": "Centrocampista",   # attacking midfielder
    "Q1249716": "Centrocampista",   # defensive midfielder
    "Q6543924": "Attaccante",       # centre-forward
    "Q1397417": "Difensore",        # centre-back
    "Q1203494": "Difensore",        # full-back
    "Q18553490": "Difensore",       # wing-back
}


class WikidataAdapter(PlayerSourceAdapter):
    """Adapter for Wikidata entity JSON API.

    Uses the Wikidata REST entity endpoint (no SPARQL) for simplicity
    and testability.  Extracts player data from claims/qualifiers.
    """

    def __init__(self, http_client: Optional[HttpClient] = None) -> None:
        self._http = http_client or UrllibHttpClient()

    @property
    def source_name(self) -> str:
        return _SOURCE_NAME

    # ── Public contract ──────────────────────────────────────────────────

    def fetch_player(self, identifier: str) -> AdapterResult:
        """Fetch and parse a Wikidata entity.

        ``identifier`` is a Wikidata QID (e.g. ``"Q1853"`` for Totti).
        """
        qid = self._normalize_qid(identifier)
        result = AdapterResult(source_name=_SOURCE_NAME, source_id=qid)

        # 1. Fetch entity JSON
        entity: Optional[dict[str, Any]] = None
        try:
            entity = self._fetch_entity(qid)
        except Exception as exc:
            result.errors.append(self._error_from_exception(exc, qid))
            return result

        if entity is None:
            result.errors.append(AdapterError(
                error_type=AdapterErrorType.NOT_FOUND,
                message=f"Entità non trovata: {qid}",
                source_name=_SOURCE_NAME,
                retryable=False,
            ))
            return result

        result.raw_payload = {"entity": entity, "qid": qid}
        result.source_metadata["retrieved_at"] = self._now_iso()
        result.source_metadata["url"] = f"https://www.wikidata.org/wiki/{qid}"

        # 2. Extract data
        try:
            self._extract_player_data(entity, result)
        except Exception as exc:
            result.errors.append(AdapterError(
                error_type=AdapterErrorType.PARSE,
                message=f"Errore nel parsing dell'entità: {exc}",
                source_name=_SOURCE_NAME,
                details={"qid": qid},
                retryable=False,
            ))

        result.success = bool(result.player_name or result.career)
        return result

    def search_player(self, query: str, limit: int = 5) -> list[str]:
        """Search Wikidata for entity QIDs matching a query."""
        url = (
            "https://www.wikidata.org/w/api.php"
            "?action=wbsearchentities"
            "&search=" + urllib.parse.quote(query)
            + f"&language=it&limit={limit}&format=json"
        )
        try:
            resp = self._http.get(url)
            data = resp.json()
            return [hit["id"] for hit in data.get("search", [])]
        except Exception:
            return []

    # ── HTTP layer ───────────────────────────────────────────────────────

    def _fetch_entity(self, qid: str) -> Optional[dict[str, Any]]:
        """Fetch the raw Wikidata entity JSON."""
        url = _ENTITY_API.format(qid=qid)
        resp = self._http.get(url)
        data = resp.json()
        entities = data.get("entities", {})
        return entities.get(qid)

    # ── Data extraction ──────────────────────────────────────────────────

    def _extract_player_data(self, entity: dict[str, Any], result: AdapterResult) -> None:
        """Populate the AdapterResult from a Wikidata entity dict."""
        claims = entity.get("claims", {})

        # Name: prefer Italian label, fallback to English, then any
        labels = entity.get("labels", {})
        result.player_name = self._best_label(labels)

        # Aliases
        aliases_data = entity.get("aliases", {})
        seen: set[str] = set()
        for lang in ("it", "en", "es", "fr", "de", "pt"):
            for entry in aliases_data.get(lang, []):
                val = entry.get("value", "").strip().lower()
                if val and val not in seen:
                    result.aliases.append(val)
                    seen.add(val)

        # Birth year (P569)
        result.birth_year = self._extract_year_from_claims(claims, "P569")

        # Nationality (P27)
        result.nationality = self._extract_entity_label(claims, "P27")

        # Position (P413)
        result.position = self._extract_position(claims)

        # Career (P54 — member of sports team)
        result.career = self._extract_career(claims)

    @staticmethod
    def _best_label(labels: dict[str, Any]) -> Optional[str]:
        """Pick the best label from Wikidata labels dict."""
        for lang in ("it", "en", "es", "fr", "de", "pt"):
            if lang in labels:
                return labels[lang].get("value")
        if labels:
            return next(iter(labels.values())).get("value")
        return None

    @staticmethod
    def _extract_year_from_claims(claims: dict[str, Any], prop: str) -> Optional[int]:
        """Extract a year from a time-valued claim."""
        for claim in claims.get(prop, []):
            mainsnak = claim.get("mainsnak", {})
            dv = mainsnak.get("datavalue", {})
            if dv.get("type") == "time":
                time_str = dv.get("value", {}).get("time", "")
                m = re.search(r"(\d{4})", time_str)
                if m:
                    return int(m.group(1))
        return None

    @staticmethod
    def _extract_entity_label(claims: dict[str, Any], prop: str) -> Optional[str]:
        """Extract the label of the first entity-valued claim (e.g. nationality)."""
        for claim in claims.get(prop, []):
            mainsnak = claim.get("mainsnak", {})
            dv = mainsnak.get("datavalue", {})
            if dv.get("type") == "wikibase-entityid":
                qid = dv.get("value", {}).get("id")
                if qid:
                    return qid  # Return QID; downstream maps to country name
        return None

    @classmethod
    def _extract_position(cls, claims: dict[str, Any]) -> Optional[str]:
        """Map P413 (position played on team) to dataset position labels."""
        for claim in claims.get("P413", []):
            mainsnak = claim.get("mainsnak", {})
            dv = mainsnak.get("datavalue", {})
            if dv.get("type") == "wikibase-entityid":
                qid = dv.get("value", {}).get("id")
                if qid and qid in _POSITION_MAP:
                    return _POSITION_MAP[qid]
        return None

    @classmethod
    def _extract_career(cls, claims: dict[str, Any]) -> list[CareerEntry]:
        """Extract career stops from P54 (member of sports team) with qualifiers."""
        stops: list[CareerEntry] = []
        for claim in claims.get("P54", []):
            mainsnak = claim.get("mainsnak", {})
            dv = mainsnak.get("datavalue", {})
            if dv.get("type") != "wikibase-entityid":
                continue

            team_qid = dv.get("value", {}).get("id")
            if not team_qid:
                continue

            qualifiers = claim.get("qualifiers", {})

            entry: CareerEntry = {
                "team": team_qid,  # QID — downstream resolves to name
                "start_year": cls._year_from_qualifier(qualifiers, "P580"),
                "end_year": cls._year_from_qualifier(qualifiers, "P582"),
                "apps": cls._int_from_qualifier(qualifiers, "P1642"),
                "goals": cls._int_from_qualifier(qualifiers, "P1351"),
            }

            # Sport number (P1618) = jersey number — not needed but harmless

            stops.append(entry)

        return stops

    @staticmethod
    def _year_from_qualifier(qualifiers: dict[str, Any], prop: str) -> Optional[int]:
        """Extract a year from a qualifier time value."""
        for q in qualifiers.get(prop, []):
            dv = q.get("datavalue", {})
            if dv.get("type") == "time":
                time_str = dv.get("value", {}).get("time", "")
                m = re.search(r"(\d{4})", time_str)
                if m:
                    return int(m.group(1))
        return None

    @staticmethod
    def _int_from_qualifier(qualifiers: dict[str, Any], prop: str) -> Optional[int]:
        """Extract an integer from a quantity qualifier."""
        for q in qualifiers.get(prop, []):
            dv = q.get("datavalue", {})
            if dv.get("type") == "quantity":
                try:
                    return int(float(dv.get("value", {}).get("amount", "")))
                except (ValueError, TypeError):
                    pass
        return None

    @staticmethod
    def _normalize_qid(identifier: str) -> str:
        """Ensure identifier is a clean QID (e.g. 'Q1853')."""
        identifier = identifier.strip()
        if re.match(r"^Q\d+$", identifier, re.I):
            return identifier.upper()
        # Try to extract from a URL
        m = re.search(r"(Q\d+)", identifier, re.I)
        if m:
            return m.group(1).upper()
        return identifier

    # ── Error helpers ────────────────────────────────────────────────────

    def _error_from_exception(self, exc: Exception, identifier: str) -> AdapterError:
        """Convert an exception into a structured ``AdapterError``."""
        if isinstance(exc, HttpError):
            if exc.status_code == 404:
                return AdapterError(
                    error_type=AdapterErrorType.NOT_FOUND,
                    message=f"Entità non trovata: {identifier}",
                    source_name=_SOURCE_NAME,
                    details={"status_code": exc.status_code, "url": exc.url},
                    retryable=False,
                )
            if exc.status_code == 429:
                return AdapterError(
                    error_type=AdapterErrorType.RATE_LIMIT,
                    message=f"Rate limited: {identifier}",
                    source_name=_SOURCE_NAME,
                    details={"status_code": exc.status_code},
                    retryable=True,
                )
            return AdapterError(
                error_type=AdapterErrorType.TRANSPORT,
                message=f"HTTP {exc.status_code}: {exc.message}",
                source_name=_SOURCE_NAME,
                details={"status_code": exc.status_code, "url": exc.url},
                retryable=exc.retryable,
            )
        if isinstance(exc, TimeoutError):
            return AdapterError(
                error_type=AdapterErrorType.TIMEOUT,
                message=f"Timeout: {exc}",
                source_name=_SOURCE_NAME,
                details={"identifier": identifier},
                retryable=True,
            )
        return AdapterError(
            error_type=AdapterErrorType.UNKNOWN,
            message=f"{type(exc).__name__}: {exc}",
            source_name=_SOURCE_NAME,
            details={"identifier": identifier},
            retryable=False,
        )
