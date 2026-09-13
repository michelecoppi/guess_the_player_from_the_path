"""Candidate Player Review Queue and Approval Service (#15).

Provides the complete domain and service layer for human review and production promotion:
- Reviewable states: REVIEW_REQUIRED, READY, VALIDATED;
- Optimistic concurrency protection using candidate revision tokens;
- Structured review projection including findings, warnings, duplicate suggestions, and career timeline;
- Admin authorization enforcement using repository standard ADMIN_TELEGRAM_IDS;
- Safe production dataset promotion with pre-write snapshot backup, atomic write, and rollback recovery;
- Typed allow-list for edits before approval with automatic re-normalization and re-validation;
- Merge with existing production player without duplicate creation;
- Explicit source-wrong decision preserving evidence and provenance;
- Ingestion retry via existing pipeline and FSM-compliant transitions;
- Idempotency across approve, reject, merge, and retry operations.
"""
from __future__ import annotations

import copy
import json
import logging
import os
import re
import shutil
import tempfile
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from services.candidate_finding import FindingCode
from services.candidate_normalization import clean_text, normalize_candidate
from services.candidate_player import (
    CandidatePlayer,
    CandidateState,
)
from services.candidate_validation import (
    validate_candidate,
)
from services.career_order import order_career
from services.matching import normalize as match_normalize
from services.matching import similarity
from services.player_pool import (
    _PLAYERS_PATH,
    reload_dataset,
    validate_dataset,
    validate_player,
)
from services.repos.candidates import (
    CandidatePlayerRepository,
    FileCandidatePlayerRepository,
)

logger = logging.getLogger(__name__)

# Fallback/default for admin IDs
try:
    from config import ADMIN_TELEGRAM_IDS as CONFIG_ADMIN_TELEGRAM_IDS
except Exception:
    CONFIG_ADMIN_TELEGRAM_IDS = []


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
    """Proiezione strutturata di contesto per la revisione umana."""
    candidate_id: str
    status: CandidateState
    revision: int
    full_name: Optional[str]
    normalized_name: Optional[str]
    aliases: list[str]
    nationality: Optional[str]
    position: Optional[str]
    birth_year: Optional[int]
    popularity: Optional[int]
    career: list[dict[str, Any]]
    source: str
    source_id: str
    confidence_score: Optional[float]
    validation_warnings: list[str]
    validation_errors: list[str]
    normalization_findings: list[dict[str, Any]]
    validation_findings: list[dict[str, Any]]
    unknown_clubs: list[str]
    ambiguous_aliases: list[str]
    has_source_conflicts: bool
    possible_duplicates: list[PossibleDuplicateMatch]
    created_at: str
    updated_at: str
    last_transition_at: Optional[str]
    state_history: list[dict[str, Any]]
    review_history: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "status": self.status.value,
            "revision": self.revision,
            "full_name": self.full_name,
            "normalized_name": self.normalized_name,
            "aliases": list(self.aliases),
            "nationality": self.nationality,
            "position": self.position,
            "birth_year": self.birth_year,
            "popularity": self.popularity,
            "career": copy.deepcopy(self.career),
            "source": self.source,
            "source_id": self.source_id,
            "confidence_score": self.confidence_score,
            "validation_warnings": list(self.validation_warnings),
            "validation_errors": list(self.validation_errors),
            "normalization_findings": copy.deepcopy(self.normalization_findings),
            "validation_findings": copy.deepcopy(self.validation_findings),
            "unknown_clubs": list(self.unknown_clubs),
            "ambiguous_aliases": list(self.ambiguous_aliases),
            "has_source_conflicts": self.has_source_conflicts,
            "possible_duplicates": [d.to_dict() for d in self.possible_duplicates],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_transition_at": self.last_transition_at,
            "state_history": copy.deepcopy(self.state_history),
            "review_history": copy.deepcopy(self.review_history),
        }


@dataclass
class ReviewResult:
    """Risultato tipizzato restituito da tutte le operazioni di revisione."""
    success: bool
    status: ReviewStatus
    candidate_id: str
    message: str
    promoted_player_id: Optional[str] = None
    candidate: Optional[CandidatePlayer] = None
    projection: Optional[ReviewCandidateProjection] = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReviewQueuePage:
    """Pagina paginata della Review Queue."""
    items: list[ReviewCandidateProjection]
    total: int
    limit: int
    offset: int


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class CandidateReviewError(Exception):
    """Errore base del servizio di review."""
    def __init__(self, message: str, status: ReviewStatus = ReviewStatus.VALIDATION_FAILED) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


class ReviewAuthError(CandidateReviewError):
    """Mancata autenticazione."""
    def __init__(self, message: str = "Autenticazione richiesta") -> None:
        super().__init__(message, status=ReviewStatus.UNAUTHORIZED)


class ReviewForbiddenError(CandidateReviewError):
    """Utente non autorizzato."""
    def __init__(self, message: str = "Permesso negato") -> None:
        super().__init__(message, status=ReviewStatus.FORBIDDEN)


class StaleRevisionError(CandidateReviewError):
    """Revisione richiesta non coincidente (conflitto di concorrenza)."""
    def __init__(self, candidate_id: str, current_rev: int, expected_rev: int) -> None:
        super().__init__(
            f"Conflitto di revisione per '{candidate_id}': attesa {expected_rev}, attuale {current_rev}",
            status=ReviewStatus.STALE_REVISION,
        )
        self.current_rev = current_rev
        self.expected_rev = expected_rev


# ---------------------------------------------------------------------------
# Constants & Allow-lists
# ---------------------------------------------------------------------------

REVIEWABLE_STATES = {
    CandidateState.REVIEW_REQUIRED,
    CandidateState.READY,
    CandidateState.VALIDATED,
}

EDITABLE_CANDIDATE_FIELDS = {
    "full_name",
    "aliases",
    "nationality",
    "position",
    "birth_year",
    "popularity",
    "career",
}

ALLOWED_CAREER_ENTRY_KEYS = {
    "team",
    "country",
    "league",
    "start_year",
    "end_year",
    "loan",
    "apps",
    "goals",
    "_stop_id",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_production_player_id(
    full_name: str,
    existing_ids: set[str],
    birth_year: Optional[int] = None,
) -> str:
    """Genera un identificativo deterministico e collision-safe per data/players.json."""
    if not full_name or not str(full_name).strip():
        raise ValueError("full_name non puo' essere vuoto")

    decomposed = unicodedata.normalize("NFKD", str(full_name).strip().lower())
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    cleaned = re.sub(r"[^a-z0-9]+", "_", without_accents).strip("_")
    slug = cleaned[:40].rstrip("_") or "player"

    # Se non c'è collisione, usa lo slug pulito
    if slug not in existing_ids:
        return slug

    # Se c'è collisione e abbiamo un birth_year, prova con l'anno
    if birth_year is not None:
        with_year = f"{slug}_{birth_year}"
        if with_year not in existing_ids:
            return with_year

    # Altrimenti sequenziale
    counter = 2
    while f"{slug}_{counter}" in existing_ids:
        counter += 1
    return f"{slug}_{counter}"


def find_possible_duplicates(
    candidate: CandidatePlayer,
    production_players: list[dict[str, Any]],
) -> list[PossibleDuplicateMatch]:
    """Individua potenziali duplicati già presenti nel dataset di produzione."""
    if not candidate.full_name:
        return []

    matches: list[PossibleDuplicateMatch] = []
    cand_name_norm = match_normalize(candidate.full_name)
    cand_aliases_norm = {match_normalize(a) for a in candidate.aliases if a and a.strip()}
    cand_birth = candidate.birth_year
    cand_nat = clean_text(candidate.nationality or "").lower()
    cand_clubs = {
        clean_text(stop.get("team", "")).lower()
        for stop in candidate.career
        if stop.get("team")
    }

    for p in production_players:
        pid = p.get("id", "")
        pname = p.get("full_name", "")
        pname_norm = match_normalize(pname)
        p_aliases_norm = {match_normalize(a) for a in p.get("aliases", []) if a}
        p_birth = p.get("birth_year")
        p_nat = clean_text(p.get("nationality", "")).lower()
        p_clubs = {
            clean_text(stop.get("team", "")).lower()
            for stop in p.get("career", [])
            if stop.get("team")
        }

        reasons = []
        score = 0.0

        # 1. Match esatto sul nome normalizzato
        if cand_name_norm == pname_norm:
            score = max(score, 1.0)
            reasons.append("Nome normalizzato identico")
        elif cand_name_norm in p_aliases_norm:
            score = max(score, 0.95)
            reasons.append("Il nome coincide con un alias esistente")
        elif cand_aliases_norm and cand_aliases_norm.intersection(p_aliases_norm):
            common = sorted(cand_aliases_norm.intersection(p_aliases_norm))
            score = max(score, 0.90)
            reasons.append(f"Condivide alias: {common[0]}")

        # 2. Somiglianza fuzzy sul nome
        sim = similarity(cand_name_norm, pname_norm)
        if sim >= 0.85:
            birth_match = (cand_birth is not None and cand_birth == p_birth)
            nat_match = (cand_nat and cand_nat == p_nat)
            if birth_match and nat_match:
                score = max(score, 0.92)
                reasons.append(f"Nome molto simile ({int(sim*100)}%), stessa nazionalità e anno di nascita")
            elif birth_match or nat_match:
                score = max(score, 0.85)
                reasons.append(f"Nome molto simile ({int(sim*100)}%) con riscontro anagrafico")
            else:
                score = max(score, round(sim * 0.85, 2))
                reasons.append(f"Nome simile ({int(sim*100)}%)")

        # 3. Sovrapposizione club in carriera
        shared_clubs = cand_clubs.intersection(p_clubs) - {"", "?"}
        if len(shared_clubs) >= 2:
            career_score = min(0.85, 0.60 + len(shared_clubs) * 0.08)
            if career_score > score:
                score = career_score
            sample_clubs = ", ".join(sorted(shared_clubs)[:3])
            reasons.append(f"Carriera sovrapposta in {len(shared_clubs)} club ({sample_clubs})")

        if score >= 0.70 and reasons:
            matches.append(
                PossibleDuplicateMatch(
                    player_id=pid,
                    player_name=pname,
                    confidence=min(1.0, score),
                    match_reasons=reasons,
                )
            )

    matches.sort(key=lambda m: m.confidence, reverse=True)
    return matches[:5]


def build_review_projection(
    candidate: CandidatePlayer,
    production_players: list[dict[str, Any]],
) -> ReviewCandidateProjection:
    """Costruisce una proiezione sicura e completa per la Review Queue."""
    norm_name = clean_text(candidate.full_name) if candidate.full_name else None

    # Estrazione findings strutturati
    norm_findings = list(candidate.metadata.get("normalization_findings", []))
    val_findings = list(candidate.metadata.get("validation_findings", []))

    # Analisi club sconosciuti e alias ambigui dai findings
    unknown_clubs: list[str] = []
    ambiguous_aliases: list[str] = []

    for f in norm_findings + val_findings:
        code = f.get("code")
        val = f.get("input_value")
        if code in (FindingCode.CLUB_MISSING_COUNTRY, FindingCode.CLUB_MISSING_LEAGUE, FindingCode.CLUB_UNRESOLVED_QID):
            if val and str(val) not in unknown_clubs:
                unknown_clubs.append(str(val))
        elif code in (FindingCode.PLAYER_ALIAS_AMBIGUOUS, FindingCode.CLUB_AMBIGUOUS_ALIAS):
            if val and str(val) not in ambiguous_aliases:
                ambiguous_aliases.append(str(val))

    has_source_conflicts = bool(
        candidate.metadata.get("has_source_conflicts")
        or (hasattr(candidate, "provenance") and candidate.provenance and candidate.provenance.has_conflicts())
    )

    possible_dups = find_possible_duplicates(candidate, production_players)

    review_history = list(candidate.metadata.get("review_events", []))

    return ReviewCandidateProjection(
        candidate_id=candidate.candidate_id,
        status=candidate.status,
        revision=candidate.revision,
        full_name=candidate.full_name,
        normalized_name=norm_name,
        aliases=list(candidate.aliases),
        nationality=candidate.nationality,
        position=candidate.position,
        birth_year=candidate.birth_year,
        popularity=candidate.popularity,
        career=copy.deepcopy(candidate.career),
        source=candidate.source,
        source_id=candidate.source_id,
        confidence_score=candidate.confidence_score,
        validation_warnings=list(candidate.validation_warnings),
        validation_errors=list(candidate.validation_errors),
        normalization_findings=norm_findings,
        validation_findings=val_findings,
        unknown_clubs=unknown_clubs,
        ambiguous_aliases=ambiguous_aliases,
        has_source_conflicts=has_source_conflicts,
        possible_duplicates=possible_dups,
        created_at=candidate.created_at,
        updated_at=candidate.updated_at,
        last_transition_at=candidate.last_transition_at,
        state_history=[r.to_dict() for r in candidate.state_history],
        review_history=review_history,
    )


# ---------------------------------------------------------------------------
# CandidateReviewService
# ---------------------------------------------------------------------------

class CandidateReviewService:
    """Servizio per la gestione e approvazione dei Candidate Players."""

    def __init__(
        self,
        candidate_repo: Optional[CandidatePlayerRepository] = None,
        players_path: Optional[Path | str] = None,
        backup_dir: Optional[Path | str] = None,
        admin_ids: Optional[list[int]] = None,
        current_year_provider: Optional[Callable[[], int]] = None,
    ) -> None:
        self._repo = candidate_repo if candidate_repo is not None else FileCandidatePlayerRepository()
        self._players_path = Path(players_path).resolve() if players_path else Path(_PLAYERS_PATH).resolve()

        base_dir = Path(__file__).resolve().parents[1]
        self._backup_dir = Path(backup_dir).resolve() if backup_dir else (base_dir / "backup").resolve()
        self._backup_dir.mkdir(parents=True, exist_ok=True)

        if admin_ids is not None:
            self._admin_ids = list(admin_ids)
        else:
            self._admin_ids = list(CONFIG_ADMIN_TELEGRAM_IDS)

        self._current_year_provider = current_year_provider

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
        """Carica in modo sicuro l'elenco dei giocatori dal dataset di produzione."""
        if not self._players_path.is_file():
            return []
        with open(self._players_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return list(data.get("players", []))

    def _backup_production_dataset(self) -> str:
        """Crea una copia di backup prima di qualunque mutazione a data/players.json."""
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        dest = self._backup_dir / f"players-review-{stamp}.json"
        if self._players_path.is_file():
            shutil.copy2(self._players_path, dest)
        return str(dest)

    def _atomic_write_production_dataset(self, players: list[dict[str, Any]]) -> None:
        """Scrittura atomica sicura del dataset di produzione."""
        # Legge commento o struttura esistente
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

        # Svuota cache memoria
        reload_dataset()

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
            candidates = [
                c for c in candidates
                if (c.full_name and query in clean_text(c.full_name).lower())
                or query in c.candidate_id.lower()
                or any(query in clean_text(a).lower() for a in c.aliases)
            ]

        # Ordinamento
        if sort_by == "oldest":
            candidates.sort(key=lambda c: c.created_at)
        else:  # newest
            candidates.sort(key=lambda c: c.created_at, reverse=True)

        total = len(candidates)
        sliced = candidates[offset : offset + limit]

        projections = [build_review_projection(c, prod_players) for c in sliced]
        return ReviewQueuePage(items=projections, total=total, limit=limit, offset=offset)

    def get_candidate_detail(
        self,
        admin: AdminIdentity,
        candidate_id: str,
    ) -> ReviewCandidateProjection:
        """Recupera la proiezione di dettaglio di un singolo candidato."""
        self._verify_auth(admin)
        candidate = self._repo.get_by_id(candidate_id)
        if not candidate:
            raise CandidateReviewError(f"Candidato '{candidate_id}' non trovato.", status=ReviewStatus.NOT_FOUND)

        prod_players = self._load_production_players()
        return build_review_projection(candidate, prod_players)

    # -----------------------------------------------------------------------
    # Mutazioni: Approve, Edit, Reject, Merge, Source Wrong, Retry
    # -----------------------------------------------------------------------

    def approve(
        self,
        admin: AdminIdentity,
        candidate_id: str,
        expected_revision: int,
        player_id_override: Optional[str] = None,
        force_allow_warnings: bool = True,
    ) -> ReviewResult:
        """Approva un candidato e lo promuove nel dataset di produzione."""
        self._verify_auth(admin)
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

        # Verifica warning se force_allow_warnings=False
        if not force_allow_warnings and candidate.validation_warnings:
            return ReviewResult(
                success=False,
                status=ReviewStatus.VALIDATION_FAILED,
                candidate_id=candidate_id,
                message=f"Approvazione rifiutata: presenti {len(candidate.validation_warnings)} warning.",
                warnings=list(candidate.validation_warnings),
            )

        # Carica il dataset di produzione
        prod_players = self._load_production_players()
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

        # Esecuzione promozione sicura con backup e rollback garantito
        backup_file = self._backup_production_dataset()
        try:
            self._atomic_write_production_dataset(simulated_dataset)
        except Exception as err:
            logger.exception("Scrittura del dataset di produzione fallita")
            return ReviewResult(
                success=False,
                status=ReviewStatus.PERSISTENCE_FAILURE,
                candidate_id=candidate_id,
                message=f"Errore durante la scrittura di data/players.json: {err}",
            )

        # Aggiornamento Candidate Player e salvataggio
        try:
            candidate.metadata["promoted_player_id"] = target_id
            candidate.metadata["promoted_at"] = _now_utc_iso()
            candidate.metadata["promoted_by"] = admin.user_id
            candidate.metadata["backup_snapshot"] = backup_file

            audit_event = {
                "action": ReviewAction.APPROVE.value,
                "actor": admin.user_id,
                "timestamp": _now_utc_iso(),
                "promoted_player_id": target_id,
                "backup": backup_file,
            }
            candidate.metadata.setdefault("review_events", []).append(audit_event)

            candidate.transition_to(
                CandidateState.APPROVED,
                reason=f"Approvato e promosso nel dataset di produzione con ID '{target_id}'",
                actor=f"admin:{admin.user_id}",
                metadata={"promoted_player_id": target_id, "backup": backup_file},
            )
            self._repo.save(candidate)
        except Exception as err:
            # Ripristino da backup per garantire atomicità tra candidato e produzione
            logger.error("Salvataggio candidato fallito dopo scrittura produzione. Eseguo rollback.")
            try:
                if os.path.exists(backup_file):
                    shutil.copy2(backup_file, self._players_path)
                    reload_dataset()
            except Exception as rollback_err:
                logger.critical(f"Rollback del dataset fallito: {rollback_err}")

            return ReviewResult(
                success=False,
                status=ReviewStatus.PERSISTENCE_FAILURE,
                candidate_id=candidate_id,
                message=f"Salvataggio stato candidato fallito (dataset ripristinato da backup): {err}",
            )

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

        if candidate.is_terminal():
            return ReviewResult(
                success=False,
                status=ReviewStatus.INVALID_STATE,
                candidate_id=candidate_id,
                message=f"Impossibile modificare il candidato '{candidate_id}' in stato terminale '{candidate.status.value}'.",
            )

        if candidate.revision != expected_revision:
            return ReviewResult(
                success=False,
                status=ReviewStatus.STALE_REVISION,
                candidate_id=candidate_id,
                message=f"Conflitto di revisione per '{candidate_id}': attesa {expected_revision}, attuale {candidate.revision}.",
            )

        # Controllo allow-list campi
        disallowed_fields = set(updates.keys()) - EDITABLE_CANDIDATE_FIELDS
        if disallowed_fields:
            return ReviewResult(
                success=False,
                status=ReviewStatus.FORBIDDEN_FIELD,
                candidate_id=candidate_id,
                message=f"Campi non modificabili: {sorted(disallowed_fields)}.",
                errors=[f"Campo '{f}' non consentito nell'allow-list" for f in sorted(disallowed_fields)],
            )

        changed_summary: dict[str, Any] = {}

        # Applicazione campi autorizzati
        if "full_name" in updates:
            changed_summary["full_name"] = {"before": candidate.full_name, "after": updates["full_name"]}
            candidate.full_name = str(updates["full_name"]).strip() if updates["full_name"] is not None else None

        if "aliases" in updates:
            changed_summary["aliases"] = {"before": candidate.aliases, "after": updates["aliases"]}
            candidate.aliases = [str(a).strip() for a in (updates["aliases"] or []) if str(a).strip()]

        if "nationality" in updates:
            changed_summary["nationality"] = {"before": candidate.nationality, "after": updates["nationality"]}
            candidate.nationality = str(updates["nationality"]).strip() if updates["nationality"] is not None else None

        if "position" in updates:
            changed_summary["position"] = {"before": candidate.position, "after": updates["position"]}
            candidate.position = str(updates["position"]).strip() if updates["position"] is not None else None

        if "birth_year" in updates:
            changed_summary["birth_year"] = {"before": candidate.birth_year, "after": updates["birth_year"]}
            by = updates["birth_year"]
            candidate.birth_year = int(by) if by is not None and str(by).strip() != "" else None

        if "popularity" in updates:
            changed_summary["popularity"] = {"before": candidate.popularity, "after": updates["popularity"]}
            pop = updates["popularity"]
            candidate.popularity = int(pop) if pop is not None else None

        if "career" in updates:
            raw_career = updates["career"] or []
            sanitized_career: list[dict[str, Any]] = []
            for stop in raw_career:
                if not isinstance(stop, dict):
                    continue
                clean_stop = {k: stop[k] for k in ALLOWED_CAREER_ENTRY_KEYS if k in stop}
                sanitized_career.append(clean_stop)
            changed_summary["career"] = {"stops_count": len(sanitized_career)}
            candidate.career = sanitized_career

        # Re-normalizzazione e re-validazione
        normalize_candidate(candidate, actor=f"admin:{admin.user_id}:edit")
        validate_candidate(
            candidate,
            current_year_provider=self._current_year_provider,
            actor=f"admin:{admin.user_id}:edit",
        )

        candidate.bump_revision()

        audit_event = {
            "action": ReviewAction.EDIT.value,
            "actor": admin.user_id,
            "timestamp": _now_utc_iso(),
            "reason": reason,
            "changed_fields": changed_summary,
            "revision": candidate.revision,
        }
        candidate.metadata.setdefault("review_events", []).append(audit_event)

        self._repo.save(candidate)
        prod_players = self._load_production_players()
        projection = build_review_projection(candidate, prod_players)

        return ReviewResult(
            success=True,
            status=ReviewStatus.SUCCESS,
            candidate_id=candidate_id,
            message="Modifiche applicate con successo.",
            candidate=candidate,
            projection=projection,
            warnings=list(candidate.validation_warnings),
            errors=list(candidate.validation_errors),
        )

    def reject(
        self,
        admin: AdminIdentity,
        candidate_id: str,
        expected_revision: int,
        reason: str,
    ) -> ReviewResult:
        """Rifiuta un candidato preservando cronologia e dati."""
        self._verify_auth(admin)
        candidate = self._repo.get_by_id(candidate_id)
        if not candidate:
            return ReviewResult(
                success=False,
                status=ReviewStatus.NOT_FOUND,
                candidate_id=candidate_id,
                message=f"Candidato '{candidate_id}' non trovato.",
            )

        # Idempotenza
        if candidate.status == CandidateState.REJECTED:
            return ReviewResult(
                success=True,
                status=ReviewStatus.ALREADY_PROCESSED,
                candidate_id=candidate_id,
                message=f"Il candidato '{candidate_id}' è già stato rifiutato.",
                candidate=candidate,
            )

        if candidate.is_terminal():
            return ReviewResult(
                success=False,
                status=ReviewStatus.INVALID_STATE,
                candidate_id=candidate_id,
                message=f"Impossibile rifiutare un candidato nello stato terminale '{candidate.status.value}'.",
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
            reason=reason or "Candidato rifiutato in fase di revisione",
            actor=f"admin:{admin.user_id}",
            metadata={"decision": "REJECTED"},
        )
        self._repo.save(candidate)

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

    def merge(
        self,
        admin: AdminIdentity,
        candidate_id: str,
        expected_revision: int,
        target_player_id: str,
        reason: str,
    ) -> ReviewResult:
        """Associa il candidato a un giocatore già esistente senza creare duplicati in produzione."""
        self._verify_auth(admin)
        candidate = self._repo.get_by_id(candidate_id)
        if not candidate:
            return ReviewResult(
                success=False,
                status=ReviewStatus.NOT_FOUND,
                candidate_id=candidate_id,
                message=f"Candidato '{candidate_id}' non trovato.",
            )

        # Idempotenza
        if (
            candidate.status == CandidateState.APPROVED
            and candidate.metadata.get("review_decision") == "MERGED"
            and candidate.metadata.get("merged_into_player_id") == target_player_id
        ):
            return ReviewResult(
                success=True,
                status=ReviewStatus.ALREADY_PROCESSED,
                candidate_id=candidate_id,
                message=f"Il candidato è già stato unito al giocatore esistente '{target_player_id}'.",
                promoted_player_id=target_player_id,
                candidate=candidate,
            )

        if candidate.is_terminal():
            return ReviewResult(
                success=False,
                status=ReviewStatus.INVALID_STATE,
                candidate_id=candidate_id,
                message=f"Impossibile unire un candidato in stato terminale '{candidate.status.value}'.",
            )

        if candidate.revision != expected_revision:
            return ReviewResult(
                success=False,
                status=ReviewStatus.STALE_REVISION,
                candidate_id=candidate_id,
                message=f"Conflitto di revisione per '{candidate_id}': attesa {expected_revision}, attuale {candidate.revision}.",
            )

        # Verifica esistenza target in produzione
        prod_players = self._load_production_players()
        existing_targets = {p.get("id"): p for p in prod_players if p.get("id")}
        if target_player_id not in existing_targets:
            return ReviewResult(
                success=False,
                status=ReviewStatus.INVALID_MERGE_TARGET,
                candidate_id=candidate_id,
                message=f"Il giocatore target '{target_player_id}' non esiste nel dataset di produzione.",
            )

        candidate.metadata["review_decision"] = "MERGED"
        candidate.metadata["merged_into_player_id"] = target_player_id
        candidate.metadata["merged_at"] = _now_utc_iso()
        candidate.metadata["merged_by"] = admin.user_id

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
        self._repo.save(candidate)

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

    def mark_source_wrong(
        self,
        admin: AdminIdentity,
        candidate_id: str,
        expected_revision: int,
        source: str,
        reason: str,
    ) -> ReviewResult:
        """Segnala la fonte come errata o inaffidabile preservando l'evidenza."""
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
                message=f"Impossibile marcare fonte errata su un candidato in stato terminale '{candidate.status.value}'.",
            )

        if candidate.revision != expected_revision:
            return ReviewResult(
                success=False,
                status=ReviewStatus.STALE_REVISION,
                candidate_id=candidate_id,
                message=f"Conflitto di revisione per '{candidate_id}': attesa {expected_revision}, attuale {candidate.revision}.",
            )

        candidate.metadata["source_unreliable"] = True
        candidate.metadata["unreliable_source_key"] = source
        candidate.metadata["unreliable_source_reason"] = reason

        audit_event = {
            "action": ReviewAction.SOURCE_WRONG.value,
            "actor": admin.user_id,
            "timestamp": _now_utc_iso(),
            "source": source,
            "reason": reason,
        }
        candidate.metadata.setdefault("review_events", []).append(audit_event)

        candidate.transition_to(
            CandidateState.REJECTED,
            reason=f"Fonte '{source}' segnalata come non attendibile: {reason}",
            actor=f"admin:{admin.user_id}",
            metadata={"decision": "SOURCE_WRONG", "source": source},
        )
        self._repo.save(candidate)

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

    def retry_ingestion(
        self,
        admin: AdminIdentity,
        candidate_id: str,
        expected_revision: int,
        adapter_fetcher: Optional[Callable[[str, str], Any]] = None,
    ) -> ReviewResult:
        """Ritenta l'ingestione tramite la pipeline esistente."""
        self._verify_auth(admin)
        candidate = self._repo.get_by_id(candidate_id)
        if not candidate:
            return ReviewResult(
                success=False,
                status=ReviewStatus.NOT_FOUND,
                candidate_id=candidate_id,
                message=f"Candidato '{candidate_id}' non trovato.",
            )

        # Se già terminale, la FSM vieta categoricamente di rientrare in pipeline attiva
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

        # Transizione consentita verso FETCHED tramite FSM
        # Grafo FSM:
        # VALIDATED -> REVIEW_REQUIRED -> FETCHED
        # READY -> REVIEW_REQUIRED -> FETCHED
        # REVIEW_REQUIRED -> FETCHED
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

        # Se fornita una funzione o adapter per rifare fetch
        if adapter_fetcher is not None:
            try:
                adapter_result = adapter_fetcher(candidate.source, candidate.source_id)
                if adapter_result:
                    from services.adapters.candidate_integration import populate_candidate_from_result
                    populate_candidate_from_result(candidate, adapter_result)
                    if getattr(adapter_result, "player_name", None):
                        candidate.full_name = adapter_result.player_name
            except Exception as err:
                return ReviewResult(
                    success=False,
                    status=ReviewStatus.SOURCE_ERROR,
                    candidate_id=candidate_id,
                    message=f"Errore durante l'acquisizione della fonte: {err}",
                )

        # Pipeline standard: normalizzazione deterministica -> validazione
        normalize_candidate(candidate, actor=f"admin:{admin.user_id}:retry")
        validate_candidate(
            candidate,
            current_year_provider=self._current_year_provider,
            actor=f"admin:{admin.user_id}:retry",
        )

        audit_event = {
            "action": ReviewAction.RETRY.value,
            "actor": admin.user_id,
            "timestamp": _now_utc_iso(),
            "resulting_state": candidate.status.value,
            "revision": candidate.revision,
        }
        candidate.metadata.setdefault("review_events", []).append(audit_event)

        self._repo.save(candidate)
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
