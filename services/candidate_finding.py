"""Structured findings model for Candidate Player normalization and validation.

Defines the finding severity, structured container, and stable code taxonomy
used to communicate data quality issues, warnings, and blocking errors
throughout the Candidate Player lifecycle (#26).
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class FindingSeverity(str, Enum):
    """Livelli di severità per i rilievi di normalizzazione e validazione."""

    WARNING = "warning"  # Sospetto o discrepanza non bloccante; il candidato può essere VALIDATED
    ERROR = "error"      # Errore bloccante o ambiguità critica; richiede revisione umana (REVIEW_REQUIRED)


# Codici stabili per i rilievi (usati nei test e nella Review Queue #15)
class FindingCode:
    # Player-level codes
    PLAYER_NAME_EMPTY = "PLAYER_NAME_EMPTY"
    PLAYER_NAME_MALFORMED = "PLAYER_NAME_MALFORMED"
    PLAYER_NATIONALITY_MISSING = "PLAYER_NATIONALITY_MISSING"
    PLAYER_POSITION_MISSING = "PLAYER_POSITION_MISSING"
    PLAYER_BIRTH_YEAR_IMPLAUSIBLE = "PLAYER_BIRTH_YEAR_IMPLAUSIBLE"
    PLAYER_ALIAS_MALFORMED = "PLAYER_ALIAS_MALFORMED"
    PLAYER_ALIAS_AMBIGUOUS = "PLAYER_ALIAS_AMBIGUOUS"

    # Career-level codes
    CAREER_EMPTY = "CAREER_EMPTY"
    CAREER_TOO_SHORT = "CAREER_TOO_SHORT"
    CAREER_ONE_CLUB_MISMATCH = "CAREER_ONE_CLUB_MISMATCH"
    CAREER_DUPLICATE_STOP = "CAREER_DUPLICATE_STOP"
    CAREER_INVALID_RANGE = "CAREER_INVALID_RANGE"
    CAREER_FUTURE_YEAR = "CAREER_FUTURE_YEAR"
    CAREER_OVERLAP = "CAREER_OVERLAP"
    CAREER_ORPHAN_LOAN = "CAREER_ORPHAN_LOAN"
    CAREER_ORDER = "CAREER_ORDER"
    CAREER_APPS_GOALS_INVALID = "CAREER_APPS_GOALS_INVALID"

    # Club & stop-level codes
    CLUB_NAME_MISSING = "CLUB_NAME_MISSING"
    CLUB_NAME_MALFORMED = "CLUB_NAME_MALFORMED"
    CLUB_UNRESOLVED_QID = "CLUB_UNRESOLVED_QID"
    CLUB_MISSING_COUNTRY = "CLUB_MISSING_COUNTRY"
    CLUB_MISSING_LEAGUE = "CLUB_MISSING_LEAGUE"
    CLUB_COUNTRY_MISMATCH = "CLUB_COUNTRY_MISMATCH"
    CLUB_AMBIGUOUS_ALIAS = "CLUB_AMBIGUOUS_ALIAS"
    CLUB_NORMALIZED = "CLUB_NORMALIZED"
    LEAGUE_NORMALIZED = "LEAGUE_NORMALIZED"
    COUNTRY_NORMALIZED = "COUNTRY_NORMALIZED"
    NUMERIC_STANDARDIZED = "NUMERIC_STANDARDIZED"
    LOAN_STANDARDIZED = "LOAN_STANDARDIZED"


@dataclass
class CandidateFinding:
    """Rilievo strutturato emesso dai servizi di normalizzazione e validazione.

    Attributes:
        code: Codice stabile del rilievo (es. CAREER_DUPLICATE_STOP, CLUB_MISSING_LEAGUE).
        severity: Livello di gravità (WARNING o ERROR).
        message: Descrizione comprensibile e azionabile del problema.
        field_path: Percorso del campo interessato (es. 'full_name', 'career[0].start_year').
        input_value: Valore grezzo o problematico rilevato.
        context: Dizionario con metadati contestuali (es. conflicting player ID, suggerimenti).
        requires_review: Indica se questo rilievo forza lo stato in REVIEW_REQUIRED.
    """

    code: str
    severity: FindingSeverity
    message: str
    field_path: str
    input_value: Optional[Any] = None
    context: dict[str, Any] = field(default_factory=dict)
    requires_review: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.severity, str):
            self.severity = FindingSeverity(self.severity)
        # Di default, ogni errore bloccante richiede revisione umana
        if self.severity == FindingSeverity.ERROR:
            self.requires_review = True

    def to_dict(self) -> dict[str, Any]:
        """Serializza il rilievo in un dizionario compatibile con JSON."""
        return {
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
            "field_path": self.field_path,
            "input_value": copy.deepcopy(self.input_value),
            "context": copy.deepcopy(self.context),
            "requires_review": self.requires_review,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CandidateFinding:
        """Ricostruisce un CandidateFinding da dizionario."""
        return cls(
            code=str(data["code"]),
            severity=FindingSeverity(data["severity"]),
            message=str(data["message"]),
            field_path=str(data["field_path"]),
            input_value=data.get("input_value"),
            context=dict(data.get("context", {})),
            requires_review=bool(data.get("requires_review", False)),
        )
