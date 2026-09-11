"""Candidate Player Core — modello di dominio, stati del ciclo di vita e transizioni.

Fornisce il modello e le regole fondamentali per la pipeline di ingestione dei calciatori:
- Lifecycle states finiti ed espliciti (DISCOVERED -> ... -> APPROVED / REJECTED);
- Macchina a stati rigida con eccezione dedicata per transizioni non consentite;
- Generazione deterministica dell'identificativo del candidato;
- Tracciamento della cronologia delle transizioni (audit trail);
- Tracciamento strutturato degli errori e dei tentativi di retry;
- Separazione totale e rigorosa dal dataset di produzione data/players.json.
"""
from __future__ import annotations

import copy
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


def _now_utc_iso() -> str:
    """Restituisce il timestamp UTC corrente in formato ISO-8601 YYYY-MM-DDTHH:MM:SSZ."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clean_slug(text: str) -> str:
    """Normalizza una stringa in uno slug minuscolo, senza accenti e con underscore."""
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", str(text).strip().lower())
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    cleaned = re.sub(r"[^a-z0-9]+", "_", without_accents)
    return cleaned.strip("_")


def make_candidate_id(source: str, source_id: str) -> str:
    """Genera un identificatore deterministico e URL-safe per un candidato da fonte esterna.

    Esempio:
        make_candidate_id("wikipedia", "Francesco Totti") -> "cand_wikipedia_francesco_totti"
        make_candidate_id("wikidata", "Q1853") -> "cand_wikidata_q1853"
    """
    clean_src = _clean_slug(source)
    clean_id = _clean_slug(source_id)
    if not clean_src or not clean_id:
        raise ValueError("source e source_id devono essere stringhe valide e non vuote")
    return f"cand_{clean_src}_{clean_id}"


def make_candidate_id_from_name(full_name: str, birth_year: Optional[int] = None) -> str:
    """Genera un identificatore deterministico basato su nome e anno di nascita opzionale.

    Esempio:
        make_candidate_id_from_name("Lionel Messi", 1987) -> "cand_lionel_messi_1987"
        make_candidate_id_from_name("Pelé") -> "cand_pele"
    """
    clean_name = _clean_slug(full_name)
    if not clean_name:
        raise ValueError("full_name deve essere una stringa valida e non vuota")
    if birth_year is not None:
        return f"cand_{clean_name}_{birth_year}"
    return f"cand_{clean_name}"


class CandidateState(str, Enum):
    """Stati del ciclo di vita di un candidato calciatore nella pipeline."""

    DISCOVERED = "DISCOVERED"
    FETCHED = "FETCHED"
    NORMALIZED = "NORMALIZED"
    VALIDATED = "VALIDATED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    READY = "READY"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


# Grafo esplicito delle transizioni consentite tra gli stati.
ALLOWED_TRANSITIONS: dict[CandidateState, set[CandidateState]] = {
    CandidateState.DISCOVERED: {
        CandidateState.FETCHED,
        CandidateState.REJECTED,
    },
    CandidateState.FETCHED: {
        CandidateState.NORMALIZED,
        CandidateState.REVIEW_REQUIRED,
        CandidateState.REJECTED,
    },
    CandidateState.NORMALIZED: {
        CandidateState.VALIDATED,
        CandidateState.REVIEW_REQUIRED,
        CandidateState.REJECTED,
    },
    CandidateState.VALIDATED: {
        CandidateState.READY,
        CandidateState.REVIEW_REQUIRED,
        CandidateState.APPROVED,
        CandidateState.REJECTED,
    },
    CandidateState.REVIEW_REQUIRED: {
        CandidateState.READY,
        CandidateState.APPROVED,
        CandidateState.REJECTED,
        CandidateState.FETCHED,
        CandidateState.NORMALIZED,
    },
    CandidateState.READY: {
        CandidateState.APPROVED,
        CandidateState.REJECTED,
        CandidateState.REVIEW_REQUIRED,
    },
    # APPROVED e REJECTED sono deliberatamente considerati stati terminali:
    # una volta che una decisione finale e' stata presa, il record e' archiviato
    # e non puo' essere reimmesso in transizione attiva senza un nuovo ciclo di ingestion.
    CandidateState.APPROVED: set(),
    CandidateState.REJECTED: set(),
}


class CandidateCoreError(Exception):
    """Eccezione base per errori del modulo Candidate Player Core."""


class InvalidStateTransitionError(CandidateCoreError):
    """Sollevata quando si tenta una transizione di stato non consentita."""

    def __init__(
        self,
        candidate_id: str,
        current_state: CandidateState,
        target_state: CandidateState,
        allowed_states: set[CandidateState],
    ) -> None:
        self.candidate_id = candidate_id
        self.current_state = current_state
        self.target_state = target_state
        self.allowed_states = allowed_states
        allowed_str = (
            ", ".join(s.value for s in sorted(allowed_states, key=lambda s: s.value))
            if allowed_states
            else "nessuna (stato terminale)"
        )
        super().__init__(
            f"Transizione non valida per il candidato '{candidate_id}': "
            f"impossibile passare da '{current_state.value}' a '{target_state.value}'. "
            f"Transizioni consentite: [{allowed_str}]."
        )


@dataclass
class StateTransitionRecord:
    """Registrazione immutabile di una transizione di stato per l'audit trail."""

    from_state: CandidateState
    to_state: CandidateState
    timestamp: str
    reason: Optional[str] = None
    actor: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_state": self.from_state.value,
            "to_state": self.to_state.value,
            "timestamp": self.timestamp,
            "reason": self.reason,
            "actor": self.actor,
            "metadata": copy.deepcopy(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StateTransitionRecord:
        return cls(
            from_state=CandidateState(data["from_state"]),
            to_state=CandidateState(data["to_state"]),
            timestamp=str(data["timestamp"]),
            reason=data.get("reason"),
            actor=data.get("actor"),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class CandidateError:
    """Struttura per memorizzare informazioni dettagliate su fallimenti e warning."""

    error_type: str
    message: str
    timestamp: str
    state: CandidateState
    details: dict[str, Any] = field(default_factory=dict)
    retryable: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_type": self.error_type,
            "message": self.message,
            "timestamp": self.timestamp,
            "state": self.state.value,
            "details": copy.deepcopy(self.details),
            "retryable": self.retryable,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CandidateError:
        return cls(
            error_type=str(data["error_type"]),
            message=str(data["message"]),
            timestamp=str(data["timestamp"]),
            state=CandidateState(data["state"]),
            details=dict(data.get("details", {})),
            retryable=bool(data.get("retryable", True)),
        )


@dataclass
class CandidatePlayer:
    """Modello di dominio per un calciatore candidato nella pipeline di ingestione.

    Isolato dal dataset di produzione, mantiene la storia delle transizioni, lo stato di
    avanzamento, i metadati di qualità/provenienza e i dettagli sugli errori/retry.
    """

    candidate_id: str
    source: str
    source_id: str
    status: CandidateState = CandidateState.DISCOVERED
    created_at: str = field(default_factory=_now_utc_iso)
    updated_at: str = field(default_factory=_now_utc_iso)
    last_transition_at: Optional[str] = None

    # Dati anagrafici e carriera (popolati progressivamente tra FETCHED e NORMALIZED)
    full_name: Optional[str] = None
    aliases: list[str] = field(default_factory=list)
    nationality: Optional[str] = None
    position: Optional[str] = None
    birth_year: Optional[int] = None
    popularity: Optional[int] = None
    career: list[dict[str, Any]] = field(default_factory=list)
    raw_data: dict[str, Any] = field(default_factory=dict)

    # Indicatori di qualità e validazione (agganci per #26 e #27)
    validation_warnings: list[str] = field(default_factory=list)
    validation_errors: list[str] = field(default_factory=list)
    confidence_score: Optional[float] = None

    # Gestione retry ed errori
    retry_count: int = 0
    max_retries: int = 3
    errors: list[CandidateError] = field(default_factory=list)
    last_error: Optional[CandidateError] = None

    # Tracciamento e audit trail
    state_history: list[StateTransitionRecord] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.status, str):
            self.status = CandidateState(self.status)
        if not self.candidate_id:
            raise ValueError("candidate_id non puo' essere vuoto")
        if not self.source or not self.source_id:
            raise ValueError("source e source_id devono essere valorizzati")
        if not self.created_at:
            self.created_at = _now_utc_iso()
        if not self.updated_at:
            self.updated_at = self.created_at

    def is_terminal(self) -> bool:
        """Indica se lo stato corrente e' terminale (APPROVED o REJECTED)."""
        return self.status in (CandidateState.APPROVED, CandidateState.REJECTED)

    def can_transition_to(self, target: CandidateState | str) -> bool:
        """Verifica se la transizione verso target e' lecita senza eseguirla."""
        target_state = target if isinstance(target, CandidateState) else CandidateState(target)
        allowed = ALLOWED_TRANSITIONS.get(self.status, set())
        return target_state in allowed

    def transition_to(
        self,
        target: CandidateState | str,
        reason: Optional[str] = None,
        actor: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> StateTransitionRecord:
        """Esegue la transizione verso il nuovo stato, aggiornando timestamp e cronologia.

        Solleva InvalidStateTransitionError se la transizione non e' consentita dal grafo.
        """
        target_state = target if isinstance(target, CandidateState) else CandidateState(target)
        allowed = ALLOWED_TRANSITIONS.get(self.status, set())

        if target_state not in allowed:
            raise InvalidStateTransitionError(
                candidate_id=self.candidate_id,
                current_state=self.status,
                target_state=target_state,
                allowed_states=allowed,
            )

        now = _now_utc_iso()
        record = StateTransitionRecord(
            from_state=self.status,
            to_state=target_state,
            timestamp=now,
            reason=reason,
            actor=actor,
            metadata=dict(metadata or {}),
        )

        self.state_history.append(record)
        self.status = target_state
        self.last_transition_at = now
        self.updated_at = now
        return record

    def record_error(
        self,
        error_type: str,
        message: str,
        details: Optional[dict[str, Any]] = None,
        retryable: bool = True,
        increment_retry_count: bool = True,
    ) -> CandidateError:
        """Registra un errore strutturato e aggiorna lo stato dei tentativi."""
        now = _now_utc_iso()
        err = CandidateError(
            error_type=error_type,
            message=message,
            timestamp=now,
            state=self.status,
            details=dict(details or {}),
            retryable=retryable,
        )
        self.errors.append(err)
        self.last_error = err
        if retryable and increment_retry_count:
            self.retry_count += 1
        self.updated_at = now
        return err

    def increment_retry(self) -> int:
        """Incrementa il conteggio dei tentativi e aggiorna updated_at."""
        self.retry_count += 1
        self.updated_at = _now_utc_iso()
        return self.retry_count

    def reset_retries(self) -> None:
        """Azzera il contatore dei tentativi."""
        self.retry_count = 0
        self.updated_at = _now_utc_iso()

    def can_retry(self) -> bool:
        """Indica se e' possibile effettuare un ulteriore tentativo di retry."""
        return self.retry_count < self.max_retries

    def to_dict(self) -> dict[str, Any]:
        """Serializza il candidato in un dizionario compatibile con JSON."""
        return {
            "candidate_id": self.candidate_id,
            "source": self.source,
            "source_id": self.source_id,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_transition_at": self.last_transition_at,
            "full_name": self.full_name,
            "aliases": list(self.aliases),
            "nationality": self.nationality,
            "position": self.position,
            "birth_year": self.birth_year,
            "popularity": self.popularity,
            "career": copy.deepcopy(self.career),
            "raw_data": copy.deepcopy(self.raw_data),
            "validation_warnings": list(self.validation_warnings),
            "validation_errors": list(self.validation_errors),
            "confidence_score": self.confidence_score,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "errors": [e.to_dict() for e in self.errors],
            "last_error": self.last_error.to_dict() if self.last_error else None,
            "state_history": [r.to_dict() for r in self.state_history],
            "metadata": copy.deepcopy(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CandidatePlayer:
        """Ricostruisce un CandidatePlayer da una rappresentazione a dizionario."""
        candidate = cls(
            candidate_id=str(data["candidate_id"]),
            source=str(data["source"]),
            source_id=str(data["source_id"]),
            status=CandidateState(data.get("status", CandidateState.DISCOVERED.value)),
            created_at=str(data.get("created_at") or _now_utc_iso()),
            updated_at=str(data.get("updated_at") or _now_utc_iso()),
            last_transition_at=data.get("last_transition_at"),
            full_name=data.get("full_name"),
            aliases=list(data.get("aliases") or []),
            nationality=data.get("nationality"),
            position=data.get("position"),
            birth_year=data.get("birth_year"),
            popularity=data.get("popularity"),
            career=list(data.get("career") or []),
            raw_data=dict(data.get("raw_data") or {}),
            validation_warnings=list(data.get("validation_warnings") or []),
            validation_errors=list(data.get("validation_errors") or []),
            confidence_score=data.get("confidence_score"),
            retry_count=int(data.get("retry_count", 0)),
            max_retries=int(data.get("max_retries", 3)),
            errors=[CandidateError.from_dict(e) for e in (data.get("errors") or [])],
            last_error=CandidateError.from_dict(data["last_error"]) if data.get("last_error") else None,
            state_history=[StateTransitionRecord.from_dict(r) for r in (data.get("state_history") or [])],
            metadata=dict(data.get("metadata") or {}),
        )
        return candidate
