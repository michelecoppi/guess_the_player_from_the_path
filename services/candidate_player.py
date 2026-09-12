"""Candidate Player Core — modello di dominio, stati del ciclo di vita e transizioni.

Fornisce il modello e le regole fondamentali per la pipeline di ingestione dei calciatori:
- Lifecycle states finiti ed espliciti (DISCOVERED -> ... -> APPROVED / REJECTED);
- Macchina a stati rigida con eccezione dedicata per transizioni non consentite;
- Generazione deterministica dell'identificativo del candidato, immune a collisioni;
- Tracciamento della cronologia delle transizioni (audit trail);
- Tracciamento strutturato degli errori e dei tentativi di retry;
- Separazione totale e rigorosa dal dataset di produzione data/players.json.
"""
from __future__ import annotations

import copy
import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from services.candidate_provenance import CandidateProvenance


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
    """Genera un identificatore deterministico, collision-safe e URL/filesystem-safe per un candidato.

    Combina uno slug leggibile con un hash crittografico stabile (SHA-256 a 8 caratteri esadecimali)
    calcolato sui dati grezzi di source e source_id. Questo previene collisioni silenziose tra
    identificatori esterni distinti che collasserebbero allo stesso slug (es. 'A-B', 'A/B', 'A_B').

    Esempio:
        make_candidate_id("wikipedia", "Francesco Totti") -> "cand_wikipedia_francesco_totti_..."
        make_candidate_id("wikidata", "Q1853") -> "cand_wikidata_q1853_..."
    """
    clean_src = _clean_slug(source)
    clean_id = _clean_slug(source_id)
    if not clean_src or not str(source_id).strip():
        raise ValueError("source e source_id devono essere stringhe valide e non vuote")

    raw_token = f"{source.strip()}:{source_id.strip()}".encode("utf-8")
    hash_suffix = hashlib.sha256(raw_token).hexdigest()[:8]

    slug_part = clean_id[:40].rstrip("_") if clean_id else "item"
    return f"cand_{clean_src}_{slug_part}_{hash_suffix}"


def make_candidate_id_from_name(full_name: str, birth_year: Optional[int] = None) -> str:
    """Genera un identificatore deterministico e collision-safe basato su nome e anno di nascita.

    Esempio:
        make_candidate_id_from_name("Lionel Messi", 1987) -> "cand_lionel_messi_1987_..."
        make_candidate_id_from_name("Pelé") -> "cand_pele_..."
    """
    clean_name = _clean_slug(full_name)
    if not clean_name:
        raise ValueError("full_name deve essere una stringa valida e non vuota")

    raw_token = f"{full_name.strip()}:{birth_year if birth_year is not None else ''}".encode("utf-8")
    hash_suffix = hashlib.sha256(raw_token).hexdigest()[:8]

    slug_part = clean_name[:40].rstrip("_")
    if birth_year is not None:
        return f"cand_{slug_part}_{birth_year}_{hash_suffix}"
    return f"cand_{slug_part}_{hash_suffix}"


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


@dataclass(init=False, repr=True)
class CandidatePlayer:
    """Modello di dominio per un calciatore candidato nella pipeline di ingestione.

    Isolato dal dataset di produzione, mantiene la storia delle transizioni, lo stato di
    avanzamento, i metadati di qualità/provenienza e i dettagli sugli errori/retry.

    Lo stato del ciclo di vita (`status`) è protetto da modifiche dirette arbitrarie:
    solo l'API di transizione `transition_to()` o il meccanismo di deserializzazione
    possono impostare o far avanzare lo stato.
    """

    candidate_id: str
    source: str
    source_id: str
    _status: CandidateState
    created_at: str
    updated_at: str
    last_transition_at: Optional[str]

    # Dati anagrafici e carriera (popolati progressivamente tra FETCHED e NORMALIZED)
    full_name: Optional[str]
    aliases: list[str]
    nationality: Optional[str]
    position: Optional[str]
    birth_year: Optional[int]
    popularity: Optional[int]
    career: list[dict[str, Any]]
    raw_data: dict[str, Any]

    # Indicatori di qualità e validazione (agganci per #26 e #27)
    validation_warnings: list[str]
    validation_errors: list[str]
    confidence_score: Optional[float]
    provenance: CandidateProvenance

    # Gestione retry ed errori
    retry_count: int
    max_retries: int
    errors: list[CandidateError]
    last_error: Optional[CandidateError]

    # Tracciamento e audit trail
    state_history: list[StateTransitionRecord]
    metadata: dict[str, Any]

    def __init__(
        self,
        candidate_id: str,
        source: str,
        source_id: str,
        *,
        _status: CandidateState = CandidateState.DISCOVERED,
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None,
        last_transition_at: Optional[str] = None,
        full_name: Optional[str] = None,
        aliases: Optional[list[str]] = None,
        nationality: Optional[str] = None,
        position: Optional[str] = None,
        birth_year: Optional[int] = None,
        popularity: Optional[int] = None,
        career: Optional[list[dict[str, Any]]] = None,
        raw_data: Optional[dict[str, Any]] = None,
        validation_warnings: Optional[list[str]] = None,
        validation_errors: Optional[list[str]] = None,
        confidence_score: Optional[float] = None,
        provenance: Optional[CandidateProvenance] = None,
        retry_count: int = 0,
        max_retries: int = 3,
        errors: Optional[list[CandidateError]] = None,
        last_error: Optional[CandidateError] = None,
        state_history: Optional[list[StateTransitionRecord]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        if not candidate_id:
            raise ValueError("candidate_id non puo' essere vuoto")
        if not source or not source_id:
            raise ValueError("source e source_id devono essere valorizzati")

        self.candidate_id = candidate_id
        self.source = source
        self.source_id = source_id

        if isinstance(_status, str):
            _status = CandidateState(_status)
        self._status = _status

        now = _now_utc_iso()
        self.created_at = created_at or now
        self.updated_at = updated_at or self.created_at
        self.last_transition_at = last_transition_at

        self.full_name = full_name
        self.aliases = list(aliases) if aliases is not None else []
        self.nationality = nationality
        self.position = position
        self.birth_year = birth_year
        self.popularity = popularity
        self.career = list(career) if career is not None else []
        self.raw_data = dict(raw_data) if raw_data is not None else {}

        self.validation_warnings = list(validation_warnings) if validation_warnings is not None else []
        self.validation_errors = list(validation_errors) if validation_errors is not None else []
        self.confidence_score = confidence_score
        self.provenance = provenance if provenance is not None else CandidateProvenance()


        self.retry_count = int(retry_count)
        self.max_retries = int(max_retries)
        self.errors = list(errors) if errors is not None else []
        self.last_error = last_error

        self.state_history = list(state_history) if state_history is not None else []
        self.metadata = dict(metadata) if metadata is not None else {}

    @property
    def status(self) -> CandidateState:
        """Stato corrente del candidato nel ciclo di vita (in sola lettura)."""
        return self._status

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "status":
            raise AttributeError(
                "Lo stato del candidato non puo' essere modificato direttamente: "
                "utilizzare candidate.transition_to() per eseguire una transizione validata."
            )
        super().__setattr__(name, value)

    def is_terminal(self) -> bool:
        """Indica se lo stato corrente e' terminale (APPROVED o REJECTED)."""
        return self._status in (CandidateState.APPROVED, CandidateState.REJECTED)

    def can_transition_to(self, target: CandidateState | str) -> bool:
        """Verifica se la transizione verso target e' lecita senza eseguirla."""
        target_state = target if isinstance(target, CandidateState) else CandidateState(target)
        allowed = ALLOWED_TRANSITIONS.get(self._status, set())
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
        allowed = ALLOWED_TRANSITIONS.get(self._status, set())

        if target_state not in allowed:
            raise InvalidStateTransitionError(
                candidate_id=self.candidate_id,
                current_state=self._status,
                target_state=target_state,
                allowed_states=allowed,
            )

        now = _now_utc_iso()
        record = StateTransitionRecord(
            from_state=self._status,
            to_state=target_state,
            timestamp=now,
            reason=reason,
            actor=actor,
            metadata=dict(metadata or {}),
        )

        self.state_history.append(record)
        self._status = target_state
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
            state=self._status,
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
            "status": self._status.value,
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
            "provenance": self.provenance.to_dict(),
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
        prov_raw = data.get("provenance")
        provenance = CandidateProvenance.from_dict(prov_raw) if prov_raw else CandidateProvenance()

        candidate = cls(
            candidate_id=str(data["candidate_id"]),
            source=str(data["source"]),
            source_id=str(data["source_id"]),
            _status=CandidateState(data.get("status", CandidateState.DISCOVERED.value)),
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
            provenance=provenance,
            retry_count=int(data.get("retry_count", 0)),
            max_retries=int(data.get("max_retries", 3)),
            errors=[CandidateError.from_dict(e) for e in (data.get("errors") or [])],
            last_error=CandidateError.from_dict(data["last_error"]) if data.get("last_error") else None,
            state_history=[StateTransitionRecord.from_dict(r) for r in (data.get("state_history") or [])],
            metadata=dict(data.get("metadata") or {}),
        )
        return candidate

    def record_observation(
        self,
        field_path: str,
        source: str,
        source_id: str,
        raw_value: Any,
        **kwargs: Any,
    ) -> Any:
        """Helper per registrare un'osservazione di fonte sulla provenienza del candidato."""
        return self.provenance.record_observation(
            field_path=field_path,
            source=source,
            source_id=source_id,
            raw_value=raw_value,
            **kwargs,
        )

    def get_provenance_for_path(self, field_path: str) -> Any:
        """Helper per accedere alla provenienza di un determinato percorso campo."""
        return self.provenance.get_provenance_for_path(field_path)

    def record_normalization(
        self,
        field_path: str,
        raw_value: Any,
        normalized_value: Any,
        **kwargs: Any,
    ) -> Any:
        """Helper per registrare una normalizzazione sulla provenienza del candidato."""
        return self.provenance.record_normalization(
            field_path=field_path,
            raw_value=raw_value,
            normalized_value=normalized_value,
            **kwargs,
        )

