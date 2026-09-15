"""Candidate Player Review Queue and Approval Service (#15).

Provides the complete domain and service layer for human review and production promotion:
- Reviewable states: REVIEW_REQUIRED, READY, VALIDATED;
- Real optimistic concurrency protection using candidate revision tokens (CAS save_if_revision);
- Process-safe and thread-safe serialization for production dataset mutations and rollback;
- Structured review projection including findings, warnings, duplicate suggestions, and career timeline;
- Admin authorization enforcement using repository standard ADMIN_TELEGRAM_IDS;
- Fail-closed validation for missing or corrupt production datasets;
- Safe production dataset promotion with collision-safe snapshot backup, atomic write, and rollback recovery;
- Typed allow-list for edits before approval with automatic re-normalization and re-validation;
- Merge with existing production player without duplicate creation;
- Explicit source-wrong decision preserving evidence and provenance without terminal locking;
- Review-aware provenance conflict evaluation: observations from explicitly rejected sources are
  excluded from blocking-conflict computation while remaining fully auditable in provenance;
- Explicit source selection in retry_ingestion(): retrying an unreliable source without an
  alternative returns SOURCE_ERROR; legitimate conflicts among still-trusted sources remain blocking;
- Ingestion retry via existing adapters and pipeline with per-entity source identity;
- Idempotency across approve, reject, merge, and retry operations;
- Leak-free sanitized error handling and projection DTOs.
"""
from __future__ import annotations

import copy
import functools
import json
import logging
import os
import re
import shutil
import tempfile
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Optional

from services import observability
from services.adapters.candidate_integration import populate_candidate_from_result
from services.candidate_normalization import clean_text, normalize_candidate
from services.candidate_player import (
    CandidatePlayer,
    CandidateState,
)
from services.candidate_validation import (
    validate_candidate,
)
from services.career_order import order_career
from services.matching import similarity
from services.player_pool import (
    reload_dataset,
    validate_dataset,
    validate_player,
)
from services.repos.candidates import (
    CandidatePlayerRepository,
)
from services.repos.file_lock import ProcessFileLock

# Fallback/default for admin IDs
try:
    from config import ADMIN_TELEGRAM_IDS as CONFIG_ADMIN_TELEGRAM_IDS
except Exception:
    CONFIG_ADMIN_TELEGRAM_IDS = []


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


REVIEWABLE_STATES = frozenset({
    CandidateState.VALIDATED,
    CandidateState.REVIEW_REQUIRED,
    CandidateState.READY,
})


# ---------------------------------------------------------------------------
# Enums and Value Objects
# ---------------------------------------------------------------------------

class ReviewAction(str, Enum):
    APPROVE = "APPROVE"
    EDIT = "EDIT"
    REJECT = "REJECT"
    MERGE = "MERGE"
    SOURCE_WRONG = "SOURCE_WRONG"
    RETRY = "RETRY"


class ReviewStatus(str, Enum):
    SUCCESS = "success"
    NOT_FOUND = "not_found"
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    INVALID_STATE = "invalid_state"
    STALE_REVISION = "stale_revision"
    VALIDATION_FAILED = "validation_failed"
    UNRESOLVED_CONFLICT = "unresolved_conflict"
    DUPLICATE_PLAYER = "duplicate_player"
    INVALID_MERGE_TARGET = "invalid_merge_target"
    ALREADY_PROCESSED = "already_processed"
    PERSISTENCE_FAILURE = "persistence_failure"
    FORBIDDEN_FIELD = "forbidden_field"
    SOURCE_ERROR = "source_error"


@dataclass
class AdminIdentity:
    """Identità verificata dell'amministratore che esegue l'azione di review."""

    user_id: int
    username: Optional[str] = None


@dataclass
class PossibleDuplicateMatch:
    """Suggerimento di possibile duplicato presente nel dataset di produzione."""

    player_id: str
    player_name: str
    confidence: float
    match_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "player_id": self.player_id,
            "player_name": self.player_name,
            "confidence": round(self.confidence, 2),
            "match_reasons": list(self.match_reasons),
        }


@dataclass
class ReviewCandidateProjection:
    """Proiezione di un candidato per la consultazione da parte dell'interfaccia review (#15)."""

    candidate_id: str
    full_name: Optional[str]
    birth_year: Optional[int]
    nationality: Optional[str]
    position: Optional[str]
    aliases: list[str]
    career: list[dict[str, Any]]
    status: str
    revision: int
    source: str
    source_id: str
    created_at: str
    updated_at: str
    is_one_club_man: bool
    is_retired: bool
    popularity: int
    validation_errors: list[str]
    validation_warnings: list[str]
    findings: list[dict[str, Any]]
    field_observations: dict[str, list[dict[str, Any]]]
    has_source_conflicts: bool
    possible_duplicates: list[PossibleDuplicateMatch]
    review_history: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "full_name": self.full_name,
            "birth_year": self.birth_year,
            "nationality": self.nationality,
            "position": self.position,
            "aliases": list(self.aliases),
            "career": copy.deepcopy(self.career),
            "status": self.status,
            "revision": self.revision,
            "source": self.source,
            "source_id": self.source_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "is_one_club_man": self.is_one_club_man,
            "is_retired": self.is_retired,
            "popularity": self.popularity,
            "validation_errors": list(self.validation_errors),
            "validation_warnings": list(self.validation_warnings),
            "findings": copy.deepcopy(self.findings),
            "field_observations": copy.deepcopy(self.field_observations),
            "has_source_conflicts": self.has_source_conflicts,
            "possible_duplicates": [d.to_dict() for d in self.possible_duplicates],
            "review_history": copy.deepcopy(self.review_history),
        }


@dataclass
class ReviewResult:
    """Esito strutturato e sicuro di un'operazione del servizio di review."""

    success: bool
    status: ReviewStatus
    candidate_id: Optional[str] = None
    message: str = ""
    promoted_player_id: Optional[str] = None
    candidate: Optional[CandidatePlayer] = None
    projection: Optional[ReviewCandidateProjection] = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "success": self.success,
            "status": self.status.value,
            "message": self.message,
        }
        if self.candidate_id:
            d["candidate_id"] = self.candidate_id
        if self.promoted_player_id:
            d["promoted_player_id"] = self.promoted_player_id
        if self.errors:
            d["errors"] = list(self.errors)
        if self.warnings:
            d["warnings"] = list(self.warnings)
        if self.conflicts:
            d["conflicts"] = list(self.conflicts)
        if self.projection:
            d["projection"] = self.projection.to_dict()
        return d


@dataclass
class ReviewQueuePage:
    """Pagina di risultati per la coda dei candidati da revisionare."""

    items: list[ReviewCandidateProjection]
    total: int
    offset: int
    limit: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": [item.to_dict() for item in self.items],
            "total": self.total,
            "offset": self.offset,
            "limit": self.limit,
        }


class ReviewAuthError(Exception):
    """Eccezione sollevata quando l'operatore non è autenticato."""


class ReviewForbiddenError(Exception):
    """Eccezione sollevata quando l'operatore non ha i privilegi di amministratore."""


class StaleRevisionError(Exception):
    """Eccezione sollevata in caso di conflitto di concorrenza ottimistica."""


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

def _observed_review(action: str) -> Callable[[Callable[..., "ReviewResult"]], Callable[..., "ReviewResult"]]:
    """Un record strutturato per ogni azione di review: esito, durata, candidato.

    Osserva e basta: argomenti, risultato ed eccezioni passano invariati. I guasti veri
    (scrittura del dataset, fonte esterna) hanno gia' il loro evento ERROR nel punto in cui
    succedono; qui un esito negativo e' al piu' un WARNING, per non contarli due volte.
    Non registra mai il candidato, i dati della fonte o i percorsi."""
    def decorate(method: Callable[..., "ReviewResult"]) -> Callable[..., "ReviewResult"]:
        @functools.wraps(method)
        def wrapper(self: Any, *args: Any, **kwargs: Any) -> "ReviewResult":
            admin = args[0] if args else kwargs.get("admin")
            candidate_id = args[1] if len(args) > 1 else kwargs.get("candidate_id")
            started = perf_counter()
            with observability.bind(
                component="ingestion", operation=action,
                candidate_id=candidate_id if isinstance(candidate_id, str) else None,
                actor_ref=observability.user_ref(getattr(admin, "user_id", None)),
            ):
                try:
                    result = method(self, *args, **kwargs)
                except (ReviewAuthError, ReviewForbiddenError, StaleRevisionError) as exc:
                    observability.log_event("candidate.review.denied", logging.WARNING, error_type=type(exc).__name__)
                    raise
                except Exception as exc:
                    observability.log_event("candidate.review.failed", logging.ERROR, exc_info=exc,
                                            error_type=type(exc).__name__)
                    raise
                status = getattr(result.status, "value", str(result.status))
                if result.success and action == "approve":
                    event = "candidate.approved"
                elif result.status == ReviewStatus.VALIDATION_FAILED:
                    event = "candidate.validation.failed"
                else:
                    event = "candidate.review.completed"
                observability.log_event(
                    event, logging.INFO if result.success else logging.WARNING, status=status,
                    success=result.success, error_count=len(result.errors or []),
                    duration_ms=round((perf_counter() - started) * 1000, 1),
                )
            return result
        return wrapper
    return decorate


def _normalize_name_for_comparison(name: str) -> str:
    """Normalizza un nome rimuovendo accenti, punteggiatura e spazi doppi."""
    if not name:
        return ""
    norm = unicodedata.normalize("NFKD", name)
    clean = "".join(c for c in norm if not unicodedata.combining(c))
    clean = re.sub(r"[^\w\s]", "", clean).strip().lower()
    return re.sub(r"\s+", " ", clean)


def _is_source_observation_rejected(
    source: str,
    source_id: str,
    unreliable_entries: list[dict[str, Any]],
) -> bool:
    """Returns True if the (source, source_id) pair matches any explicitly rejected entry.

    Identity matching prefers (source, source_id) when source_id was stored; falls back to
    source-name-only matching when source_id was not captured (legacy records).

    This is intentionally per-entity: marking one vandalized Wikipedia page as wrong
    does NOT globally distrust all Wikipedia observations.
    """
    for entry in unreliable_entries:
        if entry.get("source") != source:
            continue
        stored_sid = entry.get("source_id")
        if stored_sid is None:
            # Legacy SOURCE_WRONG without source_id: match on source name only (conservative)
            return True
        if stored_sid == source_id:
            return True
    return False


def _field_has_conflict_excluding_rejected(
    fp: Any,
    unreliable_entries: list[dict[str, Any]],
) -> bool:
    """Checks if a FieldProvenance has a conflict among still-trusted source observations.

    Observations whose (source, source_id) appears in unreliable_entries are excluded from
    the conflict computation.  All observations remain present in provenance (auditable).

    This intentionally does NOT mutate the FieldProvenance object.
    """
    if not hasattr(fp, "observations"):
        return False

    trusted_obs = [
        obs for obs in fp.observations
        if not _is_source_observation_rejected(obs.source, obs.source_id, unreliable_entries)
    ]

    # Need at least 2 observations from distinct trusted sources to have a conflict
    trusted_sources = {obs.source for obs in trusted_obs}
    if len(trusted_sources) < 2:
        return False

    def _effective_val(obs: Any) -> Any:
        val = obs.normalized_value if obs.normalized_value is not None else obs.raw_value
        if isinstance(val, str):
            return val.strip().lower()
        return val

    # Group by source (last observation per source wins, consistent with FieldProvenance.has_conflict)
    by_source: dict[str, Any] = {}
    for obs in trusted_obs:
        by_source[obs.source] = _effective_val(obs)

    unique_effective = set(by_source.values())
    return len(unique_effective) > 1


def get_candidate_provenance_conflicts(candidate: CandidatePlayer) -> list[str]:
    """Rileva i percorsi campo in cui sussiste una reale discordanza irrisolta tra fonti ancora attendibili.

    Le osservazioni provenienti da fonti esplicitamente rifiutate tramite SOURCE_WRONG sono escluse
    dal computo dei conflitti bloccanti, ma rimangono intatte e consultabili nella provenienza.

    Semantic contract:
    - All observations remain in provenance.fields (fully auditable).
    - SOURCE_WRONG decisions are visible in candidate.metadata["unreliable_sources"].
    - Only observations from explicitly rejected (source, source_id) pairs are excluded.
    - Legitimate conflicts among still-trusted sources remain blocking (fail-closed).
    - Marking one source wrong does NOT silently declare every future observation from that
      provider globally untrusted — identity is matched per (source, source_id) when available.
    """
    if not candidate.provenance:
        return []
    unreliable_entries: list[dict[str, Any]] = candidate.metadata.get("unreliable_sources", [])
    conflicts: list[str] = []
    fields_dict = (
        getattr(candidate.provenance, "fields", {})
        if not isinstance(candidate.provenance, dict)
        else candidate.provenance
    )
    for path, fp in fields_dict.items():
        if _field_has_conflict_excluding_rejected(fp, unreliable_entries):
            conflicts.append(path)
    return conflicts


def find_possible_duplicates(
    candidate: CandidatePlayer,
    production_players: list[dict[str, Any]],
) -> list[PossibleDuplicateMatch]:
    """Individua potenziali duplicati già esistenti nel dataset di produzione."""
    matches: list[PossibleDuplicateMatch] = []
    c_name = _normalize_name_for_comparison(candidate.full_name or "")
    if not c_name:
        return matches

    c_aliases = {_normalize_name_for_comparison(a) for a in candidate.aliases if a}
    c_year = candidate.birth_year
    c_teams = {clean_text(stop.get("team", "")).lower() for stop in candidate.career if stop.get("team")}

    for player in production_players:
        pid = player.get("id", "")
        p_name = _normalize_name_for_comparison(player.get("full_name", ""))
        p_aliases = {_normalize_name_for_comparison(a) for a in player.get("aliases", []) if a}
        p_year = player.get("birth_year")
        p_teams = {clean_text(stop.get("team", "")).lower() for stop in player.get("career", []) if stop.get("team")}

        reasons: list[str] = []
        score = 0.0

        # 1. Match identico del nome normalizzato
        if c_name and p_name and c_name == p_name:
            reasons.append("Nome completo identico")
            score = max(score, 0.95)

        # 2. Match di alias
        common_aliases = c_aliases.intersection(p_aliases)
        if common_aliases:
            reasons.append(f"Alias condiviso ({', '.join(sorted(common_aliases))})")
            score = max(score, 0.85)

        # 3. Match nome candidato coincide con alias produzione (o viceversa)
        if c_name in p_aliases:
            reasons.append(f"Nome candidato coincide con alias esistente '{c_name}'")
            score = max(score, 0.85)
        if p_name in c_aliases:
            reasons.append(f"Nome produzione coincide con alias candidato '{p_name}'")
            score = max(score, 0.85)

        # 4. Somiglianza fuzzy sul nome (Levenshtein)
        sim = similarity(c_name, p_name)
        if sim >= 0.85 and score < 0.85:
            reasons.append(f"Somiglianza testuale elevata ({int(sim * 100)}%)")
            score = max(score, sim * 0.9)

        # 5. Coincidenza anno di nascita
        if c_year and p_year and c_year == p_year:
            if reasons:
                reasons.append(f"Stesso anno di nascita ({c_year})")
                score = min(1.0, score + 0.1)

        # 6. Squadre di carriera in comune
        common_teams = c_teams.intersection(p_teams)
        if common_teams:
            if reasons:
                reasons.append(f"Club in comune ({', '.join(sorted(common_teams))})")
                score = min(1.0, score + 0.05)
            elif len(common_teams) >= 2:
                reasons.append(f"2+ club condivisi ({', '.join(sorted(common_teams))})")
                score = max(score, 0.70)

        if score >= 0.70:
            matches.append(
                PossibleDuplicateMatch(
                    player_id=pid,
                    player_name=player.get("full_name", pid),
                    confidence=score,
                    match_reasons=reasons,
                )
            )

    matches.sort(key=lambda m: m.confidence, reverse=True)
    return matches


def make_production_player_id(
    candidate_name: str,
    existing_ids: set[str],
    birth_year: Optional[int] = None,
) -> str:
    """Genera un identificatore canonico deterministico e privo di collisioni per data/players.json."""
    norm = unicodedata.normalize("NFKD", candidate_name)
    clean = "".join(c for c in norm if not unicodedata.combining(c))
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", clean).strip("_").lower()
    if not slug:
        slug = f"player_{birth_year}" if birth_year else "player"

    candidate_id = slug
    if candidate_id not in existing_ids:
        return candidate_id

    # Se collidere, tenta con l'anno di nascita se disponibile
    if birth_year:
        year_slug = f"{slug}_{birth_year}"
        if year_slug not in existing_ids:
            return year_slug

    # Altrimenti aggiunge un suffisso numerico progressivo deterministico
    counter = 2
    while True:
        numbered = f"{slug}_{counter}"
        if numbered not in existing_ids:
            return numbered
        counter += 1


def _sanitize_audit_event(event: dict[str, Any]) -> dict[str, Any]:
    """Rimuove dettagli sensibili o percorsi assoluti da un evento di audit."""
    sanitized = copy.deepcopy(event)
    for key in ("backup", "snapshot", "backup_snapshot"):
        if key in sanitized and isinstance(sanitized[key], str):
            sanitized[key] = Path(sanitized[key]).name
    return sanitized


def build_review_projection(
    candidate: CandidatePlayer,
    production_players: list[dict[str, Any]],
) -> ReviewCandidateProjection:
    """Costruisce una vista strutturata, sicura e priva di dati grezzi non sanitizzati."""
    field_observations: dict[str, list[dict[str, Any]]] = {}

    if candidate.provenance:
        fields_dict = getattr(candidate.provenance, "fields", {}) if not isinstance(candidate.provenance, dict) else candidate.provenance
        for path, fp in fields_dict.items():
            obs_list = []
            for obs in fp.observations:
                obs_dict = {
                    "source": obs.source,
                    "source_id": obs.source_id,
                    "confidence": obs.confidence,
                    "confidence_level": obs.confidence_level,
                    "retrieved_at": obs.retrieved_at,
                    "raw_value": str(obs.raw_value) if obs.raw_value is not None else None,
                }
                obs_list.append(obs_dict)
            field_observations[path] = obs_list

    # Review-aware conflict policy: only unresolved BLOCKING conflicts among trusted sources
    has_conflicts = bool(get_candidate_provenance_conflicts(candidate))

    raw_findings = candidate.metadata.get("validation_findings", [])
    findings_list: list[dict[str, Any]] = copy.deepcopy(raw_findings) if isinstance(raw_findings, list) else []

    duplicates = find_possible_duplicates(candidate, production_players)

    sanitized_history = []
    for ev in candidate.metadata.get("review_events", []):
        if isinstance(ev, dict):
            sanitized_history.append(_sanitize_audit_event(ev))

    return ReviewCandidateProjection(
        candidate_id=candidate.candidate_id,
        full_name=candidate.full_name,
        birth_year=candidate.birth_year,
        nationality=candidate.nationality,
        position=candidate.position,
        aliases=list(candidate.aliases),
        career=copy.deepcopy(candidate.career),
        status=candidate.status.value,
        revision=candidate.revision,
        source=candidate.source,
        source_id=candidate.source_id,
        created_at=candidate.created_at,
        updated_at=candidate.updated_at,
        is_one_club_man=bool(candidate.metadata.get("is_one_club_man", False)),
        is_retired=bool(candidate.metadata.get("is_retired", False)),
        popularity=candidate.popularity if candidate.popularity in (1, 2, 3, 4, 5) else 3,
        validation_errors=list(candidate.validation_errors),
        validation_warnings=list(candidate.validation_warnings),
        findings=findings_list,
        field_observations=field_observations,
        has_source_conflicts=has_conflicts,
        possible_duplicates=duplicates,
        review_history=sanitized_history,
    )


def _default_adapter_resolver(source: str, source_id: str) -> Optional[Any]:
    """Risolutore di adapter standard per la pipeline di acquisizione."""
    src = str(source).strip().lower()
    if src == "wikipedia":
        from services.adapters.wikipedia import WikipediaAdapter

        return WikipediaAdapter().fetch_player(source_id)
    elif src == "wikidata":
        from services.adapters.wikidata import WikidataAdapter

        return WikidataAdapter().fetch_player(source_id)
    return None


# ---------------------------------------------------------------------------
# CandidateReviewService
# ---------------------------------------------------------------------------

class CandidateReviewService:
    """Servizio per la coda di revisione umana e la promozione controllata a produzione (#15)."""

    def __init__(
        self,
        repo: Optional[CandidatePlayerRepository] = None,
        *,
        candidate_repo: Optional[CandidatePlayerRepository] = None,
        players_path: Optional[Path | str] = None,
        backup_dir: Optional[Path | str] = None,
        admin_ids: Optional[list[int]] = None,
        current_year_provider: Optional[Callable[[], int]] = None,
        adapter_resolver: Optional[Callable[[str, str], Any]] = None,
    ) -> None:
        effective_repo = candidate_repo if candidate_repo is not None else repo
        if effective_repo is None:
            raise ValueError("Candidate repository must be provided")
        self._repo = effective_repo
        base_dir = Path(__file__).resolve().parents[1]

        self._players_path = Path(players_path).resolve() if players_path else (base_dir / "data" / "players.json").resolve()
        self._production_lock_path = self._players_path.with_suffix(".lock")
        self._backup_dir = Path(backup_dir).resolve() if backup_dir else (base_dir / "backup").resolve()
        self._backup_dir.mkdir(parents=True, exist_ok=True)

        # Prevenzione path traversal sulla directory backup
        if ".." in str(self._backup_dir):
            raise ValueError(f"Percorso backup non sicuro: {self._backup_dir}")

        if admin_ids is not None:
            self._admin_ids = list(admin_ids)
        else:
            self._admin_ids = list(CONFIG_ADMIN_TELEGRAM_IDS)

        self._current_year_provider = current_year_provider
        self._adapter_resolver = adapter_resolver or _default_adapter_resolver

    def _verify_auth(self, admin: Optional[AdminIdentity]) -> AdminIdentity:
        """Verifica che l'amministratore sia valido e autorizzato."""
        if admin is None or not isinstance(admin, AdminIdentity):
            raise ReviewAuthError("Autenticazione richiesta: credenziali admin non fornite.")
        if not isinstance(admin.user_id, int):
            raise ReviewAuthError("Identità admin non valida: user_id deve essere un intero.")
        if admin.user_id not in self._admin_ids:
            raise ReviewForbiddenError(f"Accesso negato: l'utente {admin.user_id} non è un amministratore autorizzato.")
        return admin

    def _load_production_players(self) -> list[dict[str, Any]]:
        """Carica in modalità non bloccante l'elenco dei giocatori per proiezioni di sola lettura."""
        if not self._players_path.is_file():
            return []
        try:
            with open(self._players_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return list(data.get("players", []))
        except Exception:
            return []

    def _load_production_players_strict(self) -> tuple[Optional[list[dict[str, Any]]], Optional[str]]:
        """Carica il dataset di produzione con semantica FAIL-CLOSED per mutazioni."""
        if not self._players_path.is_file():
            observability.log_event("candidate.dataset.unreadable", logging.ERROR, reason="missing")
            return None, "Dataset di produzione mancante o non accessibile."
        try:
            with open(self._players_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as err:
            observability.log_event("candidate.dataset.unreadable", logging.ERROR, exc_info=err, reason="invalid_json")
            return None, "Dataset di produzione non valido o corrotto."

        if not isinstance(data, dict) or "players" not in data or not isinstance(data["players"], list):
            observability.log_event("candidate.dataset.unreadable", logging.ERROR, reason="invalid_structure")
            return None, "Struttura del dataset di produzione inattesa o non conforme."

        return list(data["players"]), None

    def _backup_production_dataset(self, candidate_id: str) -> tuple[str, Path]:
        """Crea una copia di backup con identificatore univoco e sicuro (collision-free)."""
        self._backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
        clean_cid = re.sub(r"[^a-zA-Z0-9]+", "_", str(candidate_id)).strip("_")[:20] or "cand"
        random_suffix = uuid.uuid4().hex[:8]
        filename = f"players-review-{stamp}_{clean_cid}_{random_suffix}.json"
        dest = self._backup_dir / filename

        if self._players_path.is_file():
            shutil.copy2(str(self._players_path), str(dest))
        return filename, dest

    def _atomic_write_production_dataset(self, players: list[dict[str, Any]]) -> None:
        """Scrittura atomica sicura del dataset di produzione con fsync e replace."""
        comment = (
            "Dataset locale curato di carriere calcistiche. 'verified': true = dati controllati e pronti "
            "per la selezione automatica."
        )
        if self._players_path.is_file():
            try:
                with open(self._players_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                    comment = existing.get("_comment", comment)
            except Exception:
                pass

        payload = {
            "_comment": comment,
            "players": players,
        }

        parent_dir = self._players_path.parent
        parent_dir.mkdir(parents=True, exist_ok=True)

        handle, tmp_path_str = tempfile.mkstemp(dir=str(parent_dir), prefix=".tmp_players_", suffix=".json")
        try:
            with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path_str, str(self._players_path))
        except Exception:
            if os.path.exists(tmp_path_str):
                try:
                    os.remove(tmp_path_str)
                except OSError:
                    pass
            raise

    # -----------------------------------------------------------------------
    # Query: list and get
    # -----------------------------------------------------------------------

    def list_queue(
        self,
        admin: AdminIdentity,
        state: Optional[CandidateState | str] = None,
        has_warnings: Optional[bool] = None,
        source: Optional[str] = None,
        search: Optional[str] = None,
        sort_by: str = "newest",
        limit: int = 50,
        offset: int = 0,
    ) -> ReviewQueuePage:
        """Elenca i candidati in coda di revisione con supporto a filtri e paginazione."""
        self._verify_auth(admin)

        limit = max(1, min(100, int(limit)))
        offset = max(0, int(offset))

        all_candidates = self._repo.list_all()
        prod_players = self._load_production_players()

        # Filtro stati: solo stati da revisione consentiti (esclude terminali APPROVED e REJECTED)
        candidates = [c for c in all_candidates if c.status in REVIEWABLE_STATES]

        if state is not None:
            st = state if isinstance(state, CandidateState) else CandidateState(state)
            candidates = [c for c in candidates if c.status == st]

        if has_warnings is not None:
            if has_warnings:
                candidates = [c for c in candidates if len(c.validation_warnings) > 0 or len(c.validation_errors) > 0]
            else:
                candidates = [c for c in candidates if len(c.validation_warnings) == 0 and len(c.validation_errors) == 0]

        if source is not None and str(source).strip():
            src_clean = str(source).strip().lower()
            candidates = [c for c in candidates if c.source.lower() == src_clean]

        if search is not None and str(search).strip():
            query = clean_text(str(search)).lower()
            filtered = []
            for c in candidates:
                c_name = (c.full_name or "").lower()
                c_aliases = " ".join(c.aliases).lower()
                c_teams = " ".join(stop.get("team", "") for stop in c.career).lower()
                if query in c_name or query in c_aliases or query in c_teams or query in c.candidate_id.lower():
                    filtered.append(c)
            candidates = filtered

        # Ordinamento
        if sort_by == "oldest":
            candidates.sort(key=lambda c: c.created_at)
        elif sort_by == "urgency":
            candidates.sort(
                key=lambda c: (
                    0 if c.validation_errors else (1 if c.validation_warnings else 2),
                    c.created_at,
                )
            )
        else:  # newest
            candidates.sort(key=lambda c: c.created_at, reverse=True)

        total = len(candidates)
        sliced = candidates[offset : offset + limit]

        items = [build_review_projection(c, prod_players) for c in sliced]
        return ReviewQueuePage(items=items, total=total, offset=offset, limit=limit)

    def get_candidate_detail(
        self,
        admin: AdminIdentity,
        candidate_id: str,
    ) -> Optional[ReviewCandidateProjection]:
        """Recupera la proiezione dettagliata di un candidato per la revisione."""
        self._verify_auth(admin)
        candidate = self._repo.get_by_id(candidate_id)
        if not candidate:
            return None

        prod_players = self._load_production_players()
        return build_review_projection(candidate, prod_players)

    def list_merge_targets(self, admin: AdminIdentity) -> list[dict[str, Any]]:
        """Elenco minimale e di sola lettura dei giocatori di produzione utilizzabile come
        target di merge dalla UI di revisione: solo i campi utili al reviewer per scegliere
        (id, nome, anno di nascita, nazionalità), mai il record di produzione completo né il
        dataset grezzo. Il merge vero e proprio passa sempre e solo da ``merge_candidate``.
        """
        self._verify_auth(admin)
        prod_players = self._load_production_players()
        targets = [
            {
                "player_id": p.get("id"),
                "full_name": p.get("full_name"),
                "birth_year": p.get("birth_year"),
                "nationality": p.get("nationality"),
            }
            for p in prod_players
            if p.get("id")
        ]
        targets.sort(key=lambda t: (t["full_name"] or "", t["player_id"]))
        return targets

    # -----------------------------------------------------------------------
    # Mutazioni: approve, edit, reject, merge, mark_source_wrong, retry
    # -----------------------------------------------------------------------

    @_observed_review("approve")
    def approve_candidate(
        self,
        admin: AdminIdentity,
        candidate_id: str,
        expected_revision: int,
        *,
        allow_warnings: bool = False,
        force_allow_warnings: Optional[bool] = None,
        player_id_override: Optional[str] = None,
    ) -> ReviewResult:
        """Approva un candidato e lo promuove nel dataset di produzione con sezione critica protetta."""
        self._verify_auth(admin)

        effective_allow_warnings = force_allow_warnings if force_allow_warnings is not None else allow_warnings

        # Sezione critica serializzata per mutazioni su players.json
        with ProcessFileLock(self._production_lock_path):
            candidate = self._repo.get_by_id(candidate_id)
            if not candidate:
                return ReviewResult(
                    success=False,
                    status=ReviewStatus.NOT_FOUND,
                    candidate_id=candidate_id,
                    message=f"Candidato '{candidate_id}' non trovato.",
                )

            # Idempotenza: se già APPROVED, ritorna successo sicuro
            if candidate.status == CandidateState.APPROVED:
                promoted_id = candidate.metadata.get("promoted_player_id", "")
                return ReviewResult(
                    success=True,
                    status=ReviewStatus.ALREADY_PROCESSED,
                    candidate_id=candidate_id,
                    message=f"Il candidato '{candidate_id}' è già stato approvato (player_id: '{promoted_id}').",
                    promoted_player_id=promoted_id,
                    candidate=candidate,
                )

            # Controllo concorrenza ottimistica
            if candidate.revision != expected_revision:
                return ReviewResult(
                    success=False,
                    status=ReviewStatus.STALE_REVISION,
                    candidate_id=candidate_id,
                    message=(
                        f"Conflitto di revisione per '{candidate_id}': attesa {expected_revision}, "
                        f"ma il record è stato aggiornato alla revisione {candidate.revision}."
                    ),
                )

            # Controllo stato autorizzato
            if candidate.status not in REVIEWABLE_STATES:
                return ReviewResult(
                    success=False,
                    status=ReviewStatus.INVALID_STATE,
                    candidate_id=candidate_id,
                    message=(
                        f"Impossibile approvare il candidato '{candidate_id}' nello stato "
                        f"'{candidate.status.value}'. Stati ammessi: {[s.value for s in REVIEWABLE_STATES]}."
                    ),
                )

            # Riesegue normalizzazione e validazione a fresco
            normalize_candidate(candidate, actor=f"admin:{admin.user_id}:approve")
            validate_candidate(
                candidate,
                current_year_provider=self._current_year_provider,
                actor=f"admin:{admin.user_id}:approve",
            )

            # Verifica assenza di errori bloccanti
            if candidate.validation_errors:
                return ReviewResult(
                    success=False,
                    status=ReviewStatus.UNRESOLVED_CONFLICT,
                    candidate_id=candidate_id,
                    message=f"Impossibile approvare: presenti {len(candidate.validation_errors)} errori bloccanti.",
                    errors=list(candidate.validation_errors),
                    warnings=list(candidate.validation_warnings),
                )

            # Verifica assenza di conflitti di provenienza irrisolti
            provenance_conflicts = get_candidate_provenance_conflicts(candidate)
            if provenance_conflicts:
                return ReviewResult(
                    success=False,
                    status=ReviewStatus.UNRESOLVED_CONFLICT,
                    candidate_id=candidate_id,
                    message=(
                        f"Impossibile approvare: presenti conflitti irrisolti tra fonti nei campi: "
                        f"{', '.join(provenance_conflicts)}."
                    ),
                    conflicts=provenance_conflicts,
                    warnings=list(candidate.validation_warnings),
                )

            # Verifica warning con accettazione esplicita
            if not effective_allow_warnings and candidate.validation_warnings:
                return ReviewResult(
                    success=False,
                    status=ReviewStatus.VALIDATION_FAILED,
                    candidate_id=candidate_id,
                    message=f"Approvazione rifiutata: presenti {len(candidate.validation_warnings)} warning non confermati.",
                    warnings=list(candidate.validation_warnings),
                )

            # Carica il dataset di produzione con FAIL-CLOSED
            prod_players, load_err = self._load_production_players_strict()
            if prod_players is None:
                return ReviewResult(
                    success=False,
                    status=ReviewStatus.PERSISTENCE_FAILURE,
                    candidate_id=candidate_id,
                    message=load_err or "Dataset di produzione non accessibile.",
                )

            existing_ids = {p["id"] for p in prod_players if "id" in p}

            # Determinazione player_id
            if player_id_override:
                target_id = str(player_id_override).strip().lower().replace(" ", "_")
                if target_id in existing_ids:
                    return ReviewResult(
                        success=False,
                        status=ReviewStatus.DUPLICATE_PLAYER,
                        candidate_id=candidate_id,
                        message=f"L'id giocatore '{target_id}' esiste già nel dataset di produzione.",
                    )
            else:
                target_id = make_production_player_id(
                    candidate.full_name or "player",
                    existing_ids,
                    birth_year=candidate.birth_year,
                )

            # Costruisce la scheda Player canonica
            clean_career = []
            for stop in candidate.career:
                entry = {
                    k: stop[k]
                    for k in ("team", "country", "league", "start_year", "end_year", "loan", "apps", "goals")
                    if k in stop and stop[k] is not None
                }
                clean_career.append(entry)
            clean_career = order_career(clean_career)

            new_player: dict[str, Any] = {
                "id": target_id,
                "full_name": candidate.full_name,
                "aliases": list(candidate.aliases),
                "nationality": candidate.nationality,
                "position": candidate.position,
                "birth_year": candidate.birth_year,
                "popularity": candidate.popularity if candidate.popularity in (1, 2, 3, 4, 5) else 3,
                "verified": True,
                "career": clean_career,
            }

            # Controlli invarianti sul nuovo giocatore e sul dataset complessivo
            player_problems = validate_player(new_player)
            if player_problems:
                return ReviewResult(
                    success=False,
                    status=ReviewStatus.VALIDATION_FAILED,
                    candidate_id=candidate_id,
                    message=f"La scheda canonica generata non rispetta le regole di validazione: {player_problems[0]}",
                    errors=player_problems,
                )

            simulated_dataset = prod_players + [new_player]
            dataset_problems = validate_dataset(simulated_dataset)
            if dataset_problems:
                return ReviewResult(
                    success=False,
                    status=ReviewStatus.VALIDATION_FAILED,
                    candidate_id=candidate_id,
                    message=f"L'inserimento creerebbe un'incoerenza nel dataset globale: {dataset_problems[0]}",
                    errors=dataset_problems,
                )

            # Creazione snapshot di backup con identificatore univoco
            snapshot_name, snapshot_dest = self._backup_production_dataset(candidate.candidate_id)

            # Scrittura atomica del nuovo dataset di produzione
            try:
                self._atomic_write_production_dataset(simulated_dataset)
            except Exception as err:
                observability.log_event("candidate.approval.persistence_failed", logging.ERROR, exc_info=err,
                                        stage="production_write", error_type=type(err).__name__)
                return ReviewResult(
                    success=False,
                    status=ReviewStatus.PERSISTENCE_FAILURE,
                    candidate_id=candidate_id,
                    message="Errore durante la scrittura del file di produzione.",
                )

            # Aggiornamento Candidate Player e salvataggio condizionale (CAS)
            candidate.metadata["promoted_player_id"] = target_id
            candidate.metadata["promoted_at"] = _now_utc_iso()
            candidate.metadata["promoted_by"] = admin.user_id
            candidate.metadata["backup_snapshot_id"] = snapshot_name

            audit_event = {
                "action": ReviewAction.APPROVE.value,
                "actor": admin.user_id,
                "timestamp": _now_utc_iso(),
                "promoted_player_id": target_id,
                "backup_snapshot": snapshot_name,
            }
            candidate.metadata.setdefault("review_events", []).append(audit_event)

            candidate.transition_to(
                CandidateState.APPROVED,
                reason=f"Approvato e promosso nel dataset di produzione con ID '{target_id}'",
                actor=f"admin:{admin.user_id}",
                metadata={"promoted_player_id": target_id, "backup_snapshot": snapshot_name},
            )

            # Salvataggio CAS: verifica atomicamente la revisione originale persistita
            try:
                saved = self._repo.save_if_revision(candidate, expected_persisted_revision=expected_revision)
            except Exception as save_err:
                observability.log_event("candidate.approval.persistence_failed", logging.ERROR, exc_info=save_err,
                                        stage="candidate_save", error_type=type(save_err).__name__)
                saved = False
                save_exc = True
            else:
                save_exc = False

            if not saved:
                # Ripristino da backup per garantire atomicità: mantenuto all'interno del lock di produzione
                observability.log_event("candidate.approval.rolled_back", logging.WARNING,
                                        reason="save_failed" if save_exc else "stale_revision")
                try:
                    if snapshot_dest.is_file():
                        shutil.copy2(str(snapshot_dest), str(self._players_path))
                except Exception as rollback_err:
                    observability.log_event("candidate.approval.rollback_failed", logging.CRITICAL,
                                            exc_info=rollback_err, error_type=type(rollback_err).__name__)

                status = ReviewStatus.PERSISTENCE_FAILURE if save_exc else ReviewStatus.STALE_REVISION
                return ReviewResult(
                    success=False,
                    status=status,
                    candidate_id=candidate_id,
                    message="Salvataggio del candidato fallito: modifiche al dataset annullate.",
                )

            # Ricarica dataset in memoria
            reload_dataset()

        projection = build_review_projection(candidate, simulated_dataset)
        return ReviewResult(
            success=True,
            status=ReviewStatus.SUCCESS,
            candidate_id=candidate_id,
            message=f"Candidato approvato e promosso con successo come '{target_id}'.",
            promoted_player_id=target_id,
            candidate=candidate,
            projection=projection,
        )

    @_observed_review("edit")
    def edit(
        self,
        admin: AdminIdentity,
        candidate_id: str,
        expected_revision: int,
        updates: dict[str, Any],
        reason: Optional[str] = None,
    ) -> ReviewResult:
        """Modifica i campi proposti di un candidato prima dell'approvazione."""
        self._verify_auth(admin)
        candidate = self._repo.get_by_id(candidate_id)
        if not candidate:
            return ReviewResult(
                success=False,
                status=ReviewStatus.NOT_FOUND,
                candidate_id=candidate_id,
                message=f"Candidato '{candidate_id}' non trovato.",
            )

        if candidate.status not in REVIEWABLE_STATES:
            return ReviewResult(
                success=False,
                status=ReviewStatus.INVALID_STATE,
                candidate_id=candidate_id,
                message=f"Impossibile modificare il candidato nello stato '{candidate.status.value}'. Stati ammessi: {[s.value for s in REVIEWABLE_STATES]}.",
            )

        if candidate.revision != expected_revision:
            return ReviewResult(
                success=False,
                status=ReviewStatus.STALE_REVISION,
                candidate_id=candidate_id,
                message=f"Conflitto di revisione per '{candidate_id}': attesa {expected_revision}, attuale {candidate.revision}.",
            )

        ALLOWED_FIELDS = {
            "full_name",
            "birth_year",
            "nationality",
            "position",
            "aliases",
            "career",
            "is_one_club_man",
            "is_retired",
            "popularity",
        }

        forbidden = [k for k in updates.keys() if k not in ALLOWED_FIELDS]
        if forbidden:
            return ReviewResult(
                success=False,
                status=ReviewStatus.FORBIDDEN_FIELD,
                candidate_id=candidate_id,
                message=f"Campi non modificabili: {forbidden}. Campi ammessi: {sorted(ALLOWED_FIELDS)}",
                errors=forbidden,
            )

        # Traccia le modifiche nell'audit trail
        audit_event = {
            "action": ReviewAction.EDIT.value,
            "actor": admin.user_id,
            "timestamp": _now_utc_iso(),
            "reason": reason or "Modifica manuale pre-approvazione",
            "fields_modified": list(updates.keys()),
        }

        for k, v in updates.items():
            if k == "career":
                clean_stops = []
                for stop in v:
                    clean_stops.append(dict(stop))
                setattr(candidate, k, clean_stops)
            else:
                setattr(candidate, k, v)

        candidate.bump_revision()
        candidate.metadata.setdefault("review_events", []).append(audit_event)

        # Riesegue normalizzazione deterministica e validazione carriere
        normalize_candidate(candidate, actor=f"admin:{admin.user_id}:edit")
        validate_candidate(
            candidate,
            current_year_provider=self._current_year_provider,
            actor=f"admin:{admin.user_id}:edit",
        )

        saved = self._repo.save_if_revision(candidate, expected_persisted_revision=expected_revision)
        if not saved:
            return ReviewResult(
                success=False,
                status=ReviewStatus.STALE_REVISION,
                candidate_id=candidate_id,
                message=f"Conflitto di revisione per '{candidate_id}': il record è stato aggiornato contemporaneamente.",
            )

        prod_players = self._load_production_players()
        projection = build_review_projection(candidate, prod_players)

        return ReviewResult(
            success=True,
            status=ReviewStatus.SUCCESS,
            candidate_id=candidate_id,
            message="Modifiche applicate e validate con successo.",
            candidate=candidate,
            projection=projection,
            errors=list(candidate.validation_errors),
            warnings=list(candidate.validation_warnings),
        )

    def edit_and_approve(
        self,
        admin: AdminIdentity,
        candidate_id: str,
        expected_revision: int,
        updates: dict[str, Any],
        *,
        allow_warnings: bool = False,
        force_allow_warnings: Optional[bool] = None,
        player_id_override: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> ReviewResult:
        """Modifica e approva in sequenza garantendo la consistenza transazionale."""
        edit_res = self.edit(admin, candidate_id, expected_revision, updates, reason=reason)
        if not edit_res.success or not edit_res.candidate:
            return edit_res

        return self.approve_candidate(
            admin,
            candidate_id,
            expected_revision=edit_res.candidate.revision,
            allow_warnings=allow_warnings,
            force_allow_warnings=force_allow_warnings,
            player_id_override=player_id_override,
        )

    @_observed_review("reject")
    def reject_candidate(
        self,
        admin: AdminIdentity,
        candidate_id: str,
        expected_revision: int,
        reason: str,
    ) -> ReviewResult:
        """Rifiuta un candidato registrando motivazione e audit trail."""
        self._verify_auth(admin)
        candidate = self._repo.get_by_id(candidate_id)
        if not candidate:
            return ReviewResult(
                success=False,
                status=ReviewStatus.NOT_FOUND,
                candidate_id=candidate_id,
                message=f"Candidato '{candidate_id}' non trovato.",
            )

        if candidate.status == CandidateState.REJECTED:
            return ReviewResult(
                success=True,
                status=ReviewStatus.ALREADY_PROCESSED,
                candidate_id=candidate_id,
                message=f"Il candidato '{candidate_id}' è già stato rifiutato.",
                candidate=candidate,
            )

        if candidate.status not in REVIEWABLE_STATES:
            return ReviewResult(
                success=False,
                status=ReviewStatus.INVALID_STATE,
                candidate_id=candidate_id,
                message=f"Impossibile rifiutare il candidato nello stato '{candidate.status.value}'. Stati ammessi: {[s.value for s in REVIEWABLE_STATES]}.",
            )

        if candidate.revision != expected_revision:
            return ReviewResult(
                success=False,
                status=ReviewStatus.STALE_REVISION,
                candidate_id=candidate_id,
                message=f"Conflitto di revisione per '{candidate_id}': attesa {expected_revision}, attuale {candidate.revision}.",
            )

        audit_event = {
            "action": ReviewAction.REJECT.value,
            "actor": admin.user_id,
            "timestamp": _now_utc_iso(),
            "reason": reason,
        }
        candidate.metadata.setdefault("review_events", []).append(audit_event)

        candidate.transition_to(
            CandidateState.REJECTED,
            reason=reason,
            actor=f"admin:{admin.user_id}",
            metadata={"decision": "REJECTED"},
        )

        saved = self._repo.save_if_revision(candidate, expected_persisted_revision=expected_revision)
        if not saved:
            return ReviewResult(
                success=False,
                status=ReviewStatus.STALE_REVISION,
                candidate_id=candidate_id,
                message=f"Conflitto di revisione per '{candidate_id}': il record è stato aggiornato contemporaneamente.",
            )

        prod_players = self._load_production_players()
        projection = build_review_projection(candidate, prod_players)

        return ReviewResult(
            success=True,
            status=ReviewStatus.SUCCESS,
            candidate_id=candidate_id,
            message="Candidato rifiutato con successo.",
            candidate=candidate,
            projection=projection,
        )

    @_observed_review("merge")
    def merge_candidate(
        self,
        admin: AdminIdentity,
        candidate_id: str,
        expected_revision: int,
        target_player_id: str,
        reason: str,
    ) -> ReviewResult:
        """Associa il candidato a un giocatore già esistente a produzione."""
        self._verify_auth(admin)
        candidate = self._repo.get_by_id(candidate_id)
        if not candidate:
            return ReviewResult(
                success=False,
                status=ReviewStatus.NOT_FOUND,
                candidate_id=candidate_id,
                message=f"Candidato '{candidate_id}' non trovato.",
            )

        if candidate.status == CandidateState.APPROVED and candidate.metadata.get("promoted_player_id") == target_player_id:
            return ReviewResult(
                success=True,
                status=ReviewStatus.ALREADY_PROCESSED,
                candidate_id=candidate_id,
                message=f"Il candidato è già associato a '{target_player_id}'.",
                promoted_player_id=target_player_id,
                candidate=candidate,
            )

        if candidate.status not in REVIEWABLE_STATES:
            return ReviewResult(
                success=False,
                status=ReviewStatus.INVALID_STATE,
                candidate_id=candidate_id,
                message=f"Impossibile effettuare il merge del candidato nello stato '{candidate.status.value}'. Stati ammessi: {[s.value for s in REVIEWABLE_STATES]}.",
            )

        if candidate.revision != expected_revision:
            return ReviewResult(
                success=False,
                status=ReviewStatus.STALE_REVISION,
                candidate_id=candidate_id,
                message=f"Conflitto di revisione per '{candidate_id}': attesa {expected_revision}, attuale {candidate.revision}.",
            )

        prod_players = self._load_production_players()
        existing_ids = {p["id"] for p in prod_players if "id" in p}
        if target_player_id not in existing_ids:
            return ReviewResult(
                success=False,
                status=ReviewStatus.INVALID_MERGE_TARGET,
                candidate_id=candidate_id,
                message=f"Il giocatore target '{target_player_id}' non esiste nel dataset di produzione.",
            )

        candidate.metadata["promoted_player_id"] = target_player_id
        candidate.metadata["merge_target"] = target_player_id
        candidate.metadata["merged_into_player_id"] = target_player_id
        candidate.metadata["merge_reason"] = reason
        candidate.metadata["review_decision"] = "MERGED"

        audit_event = {
            "action": ReviewAction.MERGE.value,
            "actor": admin.user_id,
            "timestamp": _now_utc_iso(),
            "target_player_id": target_player_id,
            "reason": reason,
        }
        candidate.metadata.setdefault("review_events", []).append(audit_event)

        candidate.transition_to(
            CandidateState.APPROVED,
            reason=f"Unito al giocatore esistente '{target_player_id}': {reason}",
            actor=f"admin:{admin.user_id}",
            metadata={"decision": "MERGED", "target_player_id": target_player_id},
        )

        saved = self._repo.save_if_revision(candidate, expected_persisted_revision=expected_revision)
        if not saved:
            return ReviewResult(
                success=False,
                status=ReviewStatus.STALE_REVISION,
                candidate_id=candidate_id,
                message=f"Conflitto di revisione per '{candidate_id}': il record è stato aggiornato contemporaneamente.",
            )

        projection = build_review_projection(candidate, prod_players)
        return ReviewResult(
            success=True,
            status=ReviewStatus.SUCCESS,
            candidate_id=candidate_id,
            message=f"Candidato associato con successo a '{target_player_id}'.",
            promoted_player_id=target_player_id,
            candidate=candidate,
            projection=projection,
        )

    @_observed_review("mark_source_wrong")
    def mark_source_wrong(
        self,
        admin: AdminIdentity,
        candidate_id: str,
        expected_revision: int,
        source: str,
        reason: str,
        source_id: Optional[str] = None,
    ) -> ReviewResult:
        """Segnala la fonte come errata preservando evidenza e provenienza, consentendo futuro recupero.

        Args:
            source: Nome canonico della fonte (es. 'wikipedia', 'wikidata').
            reason: Motivazione leggibile della decisione.
            source_id: Identificativo specifico dell'entità rifiutata (es. titolo pagina Wikipedia,
                QID Wikidata).  Quando fornito, il rifiuto è limitato a quella specifica entità:
                marcare errata una pagina Wikipedia vandalisata NON dichiara globalmente tutte le
                osservazioni Wikipedia come non attendibili.  Se None, il rifiuto si applica a
                tutte le osservazioni della fonte per questo candidato.
        """
        self._verify_auth(admin)
        candidate = self._repo.get_by_id(candidate_id)
        if not candidate:
            return ReviewResult(
                success=False,
                status=ReviewStatus.NOT_FOUND,
                candidate_id=candidate_id,
                message=f"Candidato '{candidate_id}' non trovato.",
            )

        if candidate.status not in REVIEWABLE_STATES:
            return ReviewResult(
                success=False,
                status=ReviewStatus.INVALID_STATE,
                candidate_id=candidate_id,
                message=f"Impossibile marcare fonte errata su un candidato in stato '{candidate.status.value}'. Stati ammessi: {[s.value for s in REVIEWABLE_STATES]}.",
            )

        if candidate.revision != expected_revision:
            return ReviewResult(
                success=False,
                status=ReviewStatus.STALE_REVISION,
                candidate_id=candidate_id,
                message=f"Conflitto di revisione per '{candidate_id}': attesa {expected_revision}, attuale {candidate.revision}.",
            )

        candidate.metadata["source_unreliable"] = True
        unreliable_entry: dict[str, Any] = {
            "source": source,
            "reason": reason,
            "marked_at": _now_utc_iso(),
            "marked_by": admin.user_id,
        }
        # Store source_id for per-entity disambiguation (see _is_source_observation_rejected)
        if source_id is not None:
            unreliable_entry["source_id"] = source_id
        candidate.metadata.setdefault("unreliable_sources", []).append(unreliable_entry)

        audit_event: dict[str, Any] = {
            "action": ReviewAction.SOURCE_WRONG.value,
            "actor": admin.user_id,
            "timestamp": _now_utc_iso(),
            "source": source,
            "reason": reason,
        }
        if source_id is not None:
            audit_event["source_id"] = source_id
        candidate.metadata.setdefault("review_events", []).append(audit_event)

        # Mantiene il candidato in REVIEW_REQUIRED (stato non terminale) per consentire futuro retry/edit
        if candidate.status != CandidateState.REVIEW_REQUIRED:
            candidate.transition_to(
                CandidateState.REVIEW_REQUIRED,
                reason=f"Fonte '{source}' segnalata come non attendibile: {reason}",
                actor=f"admin:{admin.user_id}",
                metadata={"decision": "SOURCE_WRONG", "source": source},
            )
        else:
            candidate.bump_revision()

        saved = self._repo.save_if_revision(candidate, expected_persisted_revision=expected_revision)
        if not saved:
            return ReviewResult(
                success=False,
                status=ReviewStatus.STALE_REVISION,
                candidate_id=candidate_id,
                message=f"Conflitto di revisione per '{candidate_id}': il record è stato aggiornato contemporaneamente.",
            )

        prod_players = self._load_production_players()
        projection = build_review_projection(candidate, prod_players)

        return ReviewResult(
            success=True,
            status=ReviewStatus.SUCCESS,
            candidate_id=candidate_id,
            message=f"Fonte '{source}' marcata come errata.",
            candidate=candidate,
            projection=projection,
        )

    @_observed_review("retry_ingestion")
    def retry_ingestion(
        self,
        admin: AdminIdentity,
        candidate_id: str,
        expected_revision: int,
        *,
        retry_source: Optional[str] = None,
        retry_source_id: Optional[str] = None,
        adapter_fetcher: Optional[Callable[[str, str], Any]] = None,
    ) -> ReviewResult:
        """Ritenta l'ingestione tramite la pipeline esistente, con supporto per selezione esplicita della fonte.

        Args:
            retry_source: Nome canonico della fonte alternativa (es. 'wikidata', 'wikipedia').
                Se None, la fonte corrente del candidato viene usata SE non è marcata come
                non attendibile. Se la fonte corrente è in unreliable_sources, è obbligatorio
                fornire retry_source — la chiamata restituisce SOURCE_ERROR senza invocare alcun
                adapter.
            retry_source_id: Identificativo dell'entità nella fonte alternativa (es. QID Wikidata).
                Se retry_source è fornito e retry_source_id è None, viene usato il source_id
                corrente del candidato come fallback (compatibilità per fonti con stesso ID).
            adapter_fetcher: Callable di test per iniettare un adapter personalizzato.
                In produzione, usare retry_source/retry_source_id invece di questo parametro.
                La firma è (source: str, source_id: str) -> AdapterResult.

        Contract:
            - Se retry_source è None e la fonte corrente è in unreliable_sources →
              SOURCE_ERROR (selezione fonte richiesta, nessun adapter invocato).
            - Se retry_source è fornito → l'adapter per retry_source è risolto e invocato.
            - CAS su expected_revision garantisce l'isolamento da operazioni concorrenti.
        """
        self._verify_auth(admin)
        candidate = self._repo.get_by_id(candidate_id)
        if not candidate:
            return ReviewResult(
                success=False,
                status=ReviewStatus.NOT_FOUND,
                candidate_id=candidate_id,
                message=f"Candidato '{candidate_id}' non trovato.",
            )

        if candidate.is_terminal():
            return ReviewResult(
                success=False,
                status=ReviewStatus.INVALID_STATE,
                candidate_id=candidate_id,
                message=f"Impossibile ritentare l'ingestione: il candidato è in stato terminale '{candidate.status.value}'.",
            )

        if candidate.revision != expected_revision:
            return ReviewResult(
                success=False,
                status=ReviewStatus.STALE_REVISION,
                candidate_id=candidate_id,
                message=f"Conflitto di revisione per '{candidate_id}': attesa {expected_revision}, attuale {candidate.revision}.",
            )

        # --- Source selection logic ---
        # Determine the effective source and source_id for this retry attempt.
        # If adapter_fetcher is provided (test seam), the source routing below is bypassed entirely
        # and the caller is responsible for the fetch.
        unreliable_entries: list[dict[str, Any]] = candidate.metadata.get("unreliable_sources", [])

        if adapter_fetcher is None:
            # Production path: use the real resolver.
            if retry_source is not None:
                # Explicit override: caller selects a different source.
                effective_source = str(retry_source).strip().lower()
                effective_source_id = (
                    str(retry_source_id).strip() if retry_source_id is not None
                    else candidate.source_id
                )
            else:
                # No override supplied: fall back to the candidate's current source.
                # Fail-closed if that source is already marked unreliable.
                if _is_source_observation_rejected(
                    candidate.source,
                    candidate.source_id,
                    unreliable_entries,
                ):
                    return ReviewResult(
                        success=False,
                        status=ReviewStatus.SOURCE_ERROR,
                        candidate_id=candidate_id,
                        message=(
                            f"La fonte corrente '{candidate.source}' è marcata come non attendibile. "
                            "Specificare una fonte alternativa tramite retry_source e retry_source_id."
                        ),
                    )
                effective_source = candidate.source
                effective_source_id = candidate.source_id

            # Resolve and call the real adapter.
            try:
                adapter_result = self._adapter_resolver(effective_source, effective_source_id)
            except Exception as err:
                observability.log_event("candidate.ingestion.source_failed", logging.ERROR, exc_info=err,
                                        source=effective_source, error_type=type(err).__name__)
                return ReviewResult(
                    success=False,
                    status=ReviewStatus.SOURCE_ERROR,
                    candidate_id=candidate_id,
                    message="Errore durante l'acquisizione della fonte esterna.",
                )
        else:
            # Test seam path: caller provides a fully custom fetcher.
            # The source used is whatever the fetcher returns — we pass the candidate's current
            # source/source_id so the fetcher has context, but it may return any source.
            effective_source = retry_source or candidate.source
            effective_source_id = retry_source_id or candidate.source_id
            try:
                adapter_result = adapter_fetcher(effective_source, effective_source_id)
            except Exception as err:
                observability.log_event("candidate.ingestion.source_failed", logging.ERROR, exc_info=err,
                                        source=effective_source, error_type=type(err).__name__)
                return ReviewResult(
                    success=False,
                    status=ReviewStatus.SOURCE_ERROR,
                    candidate_id=candidate_id,
                    message="Errore durante l'acquisizione della fonte esterna.",
                )

        if adapter_result is None:
            return ReviewResult(
                success=False,
                status=ReviewStatus.SOURCE_ERROR,
                candidate_id=candidate_id,
                message=f"Nessun adapter compatibile o disponibile per la fonte '{effective_source}'.",
            )

        if not getattr(adapter_result, "success", True):
            return ReviewResult(
                success=False,
                status=ReviewStatus.SOURCE_ERROR,
                candidate_id=candidate_id,
                message="Acquisizione fallita dalla fonte esterna.",
            )

        # --- State machine transitions ---
        # Transizione consentita verso FETCHED tramite FSM
        if candidate.status in (CandidateState.READY, CandidateState.VALIDATED):
            candidate.transition_to(
                CandidateState.REVIEW_REQUIRED,
                reason="Re-indirizzamento a review prima del retry",
                actor=f"admin:{admin.user_id}",
            )

        if candidate.status == CandidateState.REVIEW_REQUIRED:
            candidate.transition_to(
                CandidateState.FETCHED,
                reason="Richiesto retry di ingestione",
                actor=f"admin:{admin.user_id}",
            )

        # --- Populate and re-normalize ---
        # On a retry, we perform a full re-ingestion from the chosen source.
        # The career list is reset so that only the new source's data drives the
        # candidate's career field.  Historical observations from prior sources
        # remain intact in candidate.provenance.fields for full auditability.
        candidate.career = []
        populate_candidate_from_result(candidate, adapter_result)
        if getattr(adapter_result, "player_name", None):
            candidate.full_name = adapter_result.player_name

        normalize_candidate(candidate, actor=f"admin:{admin.user_id}:retry")
        validate_candidate(
            candidate,
            current_year_provider=self._current_year_provider,
            actor=f"admin:{admin.user_id}:retry",
        )

        # Update active source identity to the successful source (#15 consistency fix)
        res_source = getattr(adapter_result, "source_name", None) or effective_source
        res_source_id = getattr(adapter_result, "source_id", None) or effective_source_id
        candidate.source = str(res_source).strip().lower()
        candidate.source_id = str(res_source_id).strip()

        audit_event: dict[str, Any] = {
            "action": ReviewAction.RETRY.value,
            "actor": admin.user_id,
            "timestamp": _now_utc_iso(),
            "retry_source": candidate.source,
            "retry_source_id": candidate.source_id,
            "resulting_state": candidate.status.value,
            "revision": candidate.revision,
        }
        candidate.metadata.setdefault("review_events", []).append(audit_event)
        # Track which source was used for the latest retry for easy inspection
        candidate.metadata["last_retry_source"] = candidate.source
        candidate.metadata["last_retry_source_id"] = candidate.source_id

        saved = self._repo.save_if_revision(candidate, expected_persisted_revision=expected_revision)
        if not saved:
            return ReviewResult(
                success=False,
                status=ReviewStatus.STALE_REVISION,
                candidate_id=candidate_id,
                message=f"Conflitto di revisione per '{candidate_id}': il record è stato aggiornato contemporaneamente.",
            )

        prod_players = self._load_production_players()
        projection = build_review_projection(candidate, prod_players)

        return ReviewResult(
            success=True,
            status=ReviewStatus.SUCCESS,
            candidate_id=candidate_id,
            message=f"Retry di ingestione completato. Nuovo stato: '{candidate.status.value}'.",
            candidate=candidate,
            projection=projection,
        )

    # Alias per compatibilità di interfaccia
    approve = approve_candidate
    reject = reject_candidate
    merge = merge_candidate
