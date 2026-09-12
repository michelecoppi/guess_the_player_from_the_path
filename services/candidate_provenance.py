"""Candidate Player Provenance — modello di dominio per la tracciabilità granulare dei dati.

Fornisce la rappresentazione interna, immutabile e verificabile dell'origine di ciascun dato
importato per un Candidate Player (#27):
- Provenance a livello di singolo campo (field-level lineage: 'full_name', 'career[0].team', ecc.);
- Supporto a osservazioni multi-source (es. Wikipedia + Wikidata per la stessa entità);
- Conservazione dei conflitti e delle discordanze tra fonti senza sovrascritture silenziose;
- Tracciabilità delle trasformazioni di normalizzazione (raw_value -> normalized_value);
- Identità stabile delle tappe di carriera (_stop_id) immune al riordinamento canonico;
- Modello di confidenza spiegabile e deterministico (ConfidenceLevel);
- Timestamp UTC timezone-aware immutabili basati sull'operazione di recupero;
- Nessun appesantimento né modifica del payload pubblico di produzione data/players.json.
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


def now_utc_iso() -> str:
    """Restituisce il timestamp UTC corrente in formato ISO-8601 (YYYY-MM-DDTHH:MM:SSZ)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ConfidenceLevel(str, Enum):
    """Livelli di confidenza spiegabili per osservazioni da fonte o dati derivati.

    Regole semantiche:
    - EXACT_STRUCTURED (1.00): Dato estratto da proprietà/statement strutturato diretto
      (es. Wikidata claim P569 data di nascita, P27 cittadinanza, P54 membership con qualificatori).
    - PARSED_CLAIM (0.90): Dato estratto da template/infobox semi-strutturato ad alta affidabilità
      (es. parametri del template {{Bio}} o {{Sportivo}} di Wikipedia).
    - PARSER_DERIVED (0.75): Dato estratto tramite euristica testuale, espressione regolare o
      target di wikilink (es. parsing del testo libero delle tappe di carriera).
    - INFERRED_NORMALIZED (0.60): Dato arricchito o trasformato tramite tabella canonica, alias
      o vocabolario controllato di repository (es. 'PSG' -> 'Paris Saint-Germain').
    - AMBIGUOUS (0.30): Dato dubbio, in conflitto o ambiguo che richiede revisione umana (#15).
    """

    EXACT_STRUCTURED = "exact_structured"
    PARSED_CLAIM = "parsed_claim"
    PARSER_DERIVED = "parser_derived"
    INFERRED_NORMALIZED = "inferred_normalized"
    AMBIGUOUS = "ambiguous"


_CONFIDENCE_SCORE_MAP: dict[ConfidenceLevel, float] = {
    ConfidenceLevel.EXACT_STRUCTURED: 1.0,
    ConfidenceLevel.PARSED_CLAIM: 0.9,
    ConfidenceLevel.PARSER_DERIVED: 0.75,
    ConfidenceLevel.INFERRED_NORMALIZED: 0.6,
    ConfidenceLevel.AMBIGUOUS: 0.3,
}


def score_for_confidence_level(level: ConfidenceLevel | str) -> float:
    """Restituisce il punteggio numerico deterministico per il livello di confidenza."""
    enum_val = level if isinstance(level, ConfidenceLevel) else ConfidenceLevel(str(level))
    return _CONFIDENCE_SCORE_MAP.get(enum_val, 0.5)


def make_career_stop_id(source: str, index: int, hint: Optional[Any] = None) -> str:
    """Genera un identificatore interno univoco e stabile per una tappa di carriera."""

    clean_src = re.sub(r"[^a-z0-9]+", "_", str(source).strip().lower()).strip("_") or "src"
    if hint:
        clean_hint = re.sub(r"[^a-z0-9]+", "_", str(hint).strip().lower()).strip("_")[:20]
        return f"{clean_src}_stop_{clean_hint}_{index}"
    return f"{clean_src}_stop_{index}"


@dataclass
class SourceObservation:
    """Singola osservazione di un valore rilevata da una specifica fonte esterna.

    Attributes:
        source: Nome canonico della fonte (es. 'wikipedia', 'wikidata').
        source_id: Identificativo univoco per la fonte (es. 'Francesco_Totti', 'Q1853').
        retrieved_at: Timestamp UTC di recupero effettivo (ISO-8601).
        confidence: Punteggio spiegabile (0.0 - 1.0).
        confidence_level: Livello semantico di confidenza (ConfidenceLevel).
        raw_value: Valore grezzo originale come restituito dalla sorgente.
        normalized_value: Eventuale valore normalizzato a livello di adapter/fonte.
        source_url: URL canonico della risorsa sorgente.
        metadata: Metadati specifici della fonte (revisione, claim ID, property ID).
        adapter_version: Identificativo della versione o parser dell'adapter.
    """

    source: str
    source_id: str
    retrieved_at: str
    confidence: float
    confidence_level: str
    raw_value: Any
    normalized_value: Optional[Any] = None
    source_url: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    adapter_version: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.source or not str(self.source).strip():
            raise ValueError("source non puo' essere vuoto")
        if not self.source_id or not str(self.source_id).strip():
            raise ValueError("source_id non puo' essere vuoto")
        if not self.retrieved_at:
            self.retrieved_at = now_utc_iso()
        if not self.confidence_level:
            self.confidence_level = ConfidenceLevel.PARSED_CLAIM.value
        if self.confidence is None:
            self.confidence = score_for_confidence_level(self.confidence_level)

    def to_dict(self) -> dict[str, Any]:
        """Serializza l'osservazione in un dizionario compatibile con JSON."""
        return {
            "source": self.source,
            "source_id": self.source_id,
            "retrieved_at": self.retrieved_at,
            "confidence": round(float(self.confidence), 2),
            "confidence_level": self.confidence_level,
            "raw_value": copy.deepcopy(self.raw_value),
            "normalized_value": copy.deepcopy(self.normalized_value),
            "source_url": self.source_url,
            "metadata": copy.deepcopy(self.metadata),
            "adapter_version": self.adapter_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SourceObservation:
        """Ricostruisce una SourceObservation da dizionario."""
        return cls(
            source=str(data["source"]),
            source_id=str(data["source_id"]),
            retrieved_at=str(data.get("retrieved_at") or now_utc_iso()),
            confidence=float(data.get("confidence", 0.9)),
            confidence_level=str(data.get("confidence_level", ConfidenceLevel.PARSED_CLAIM.value)),
            raw_value=copy.deepcopy(data.get("raw_value")),
            normalized_value=copy.deepcopy(data.get("normalized_value")),
            source_url=data.get("source_url"),
            metadata=dict(data.get("metadata", {})),
            adapter_version=data.get("adapter_version"),
        )


@dataclass
class NormalizationRecord:
    """Registrazione di una trasformazione applicata da un servizio di normalizzazione (#26).

    Attributes:
        raw_value: Valore antecedente alla trasformazione.
        normalized_value: Valore risultante standardizzato.
        finding_code: Codice del rilievo associato (es. CLUB_NORMALIZED, LEAGUE_NORMALIZED).
        rule: Identificativo della regola o dizionario applicato.
        timestamp: Timestamp UTC dell'operazione.
    """

    raw_value: Any
    normalized_value: Any
    finding_code: Optional[str] = None
    rule: Optional[str] = None
    timestamp: str = field(default_factory=now_utc_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_value": copy.deepcopy(self.raw_value),
            "normalized_value": copy.deepcopy(self.normalized_value),
            "finding_code": self.finding_code,
            "rule": self.rule,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NormalizationRecord:
        return cls(
            raw_value=copy.deepcopy(data.get("raw_value")),
            normalized_value=copy.deepcopy(data.get("normalized_value")),
            finding_code=data.get("finding_code"),
            rule=data.get("rule"),
            timestamp=str(data.get("timestamp") or now_utc_iso()),
        )


@dataclass
class FieldProvenance:
    """Contenitore della provenienza per uno specifico percorso campo di CandidatePlayer.

    Raccoglie le osservazioni da fonti multiple, i valori correnti e normalizzati,
    e la cronologia delle trasformazioni subite.

    Attributes:
        field_path: Percorso stabile del campo (es. 'full_name', 'career[0].team').
        stop_id: Identificatore univoco e stabile della tappa di carriera, se applicabile.
        current_value: Valore attivo al momento sul candidato.
        normalized_value: Valore standardizzato consolidato.
        observations: Elenco delle osservazioni raccolte da tutte le fonti partecipanti.
        transformations: Elenco dei passi di normalizzazione eseguiti.
    """

    field_path: str
    stop_id: Optional[str] = None
    current_value: Optional[Any] = None
    normalized_value: Optional[Any] = None
    observations: list[SourceObservation] = field(default_factory=list)
    transformations: list[NormalizationRecord] = field(default_factory=list)

    def add_observation(self, observation: SourceObservation) -> None:
        """Aggiunge un'osservazione; aggiorna un'osservazione esistente dalla stessa sorgente se identica."""
        # Se esiste già un'osservazione della stessa sorgente con la stessa source_id, la sostituisce o la aggiorna
        for i, existing in enumerate(self.observations):
            if existing.source == observation.source and existing.source_id == observation.source_id:
                self.observations[i] = observation
                return
        self.observations.append(observation)

    def add_transformation(self, record: NormalizationRecord) -> None:
        """Aggiunge una trasformazione alla cronologia di normalizzazione del campo."""
        self.transformations.append(record)
        self.normalized_value = record.normalized_value

    def has_multiple_sources(self) -> bool:
        """Indica se il campo e' supportato da almeno due fonti distinte."""
        unique_sources = {obs.source for obs in self.observations}
        return len(unique_sources) > 1

    def has_conflict(self) -> bool:
        """Rileva se vi e' un disaccordo non risolto tra fonti distinte.

        Un conflitto esiste quando due o piu' fonti distinte forniscono valori che differiscono
        sia nella forma grezza sia dopo l'eventuale normalizzazione di fonte.
        """
        if not self.has_multiple_sources():
            return False

        # Consideriamo il valore normalizzato della fonte se disponibile, altrimenti il valore grezzo
        def _effective_val(obs: SourceObservation) -> Any:
            val = obs.normalized_value if obs.normalized_value is not None else obs.raw_value
            if isinstance(val, str):
                return val.strip().lower()
            return val

        by_source: dict[str, Any] = {}
        for obs in self.observations:
            by_source[obs.source] = _effective_val(obs)

        unique_effective = set(by_source.values())
        return len(unique_effective) > 1

    def supporting_sources(self, value: Any = None) -> list[str]:
        """Restituisce l'elenco delle fonti che concordano con il valore specificato (o corrente)."""
        target = value if value is not None else (self.normalized_value if self.normalized_value is not None else self.current_value)

        def _matches(obs: SourceObservation) -> bool:
            if target is None:
                return False
            norm_target = str(target).strip().lower() if isinstance(target, str) else target

            raw = str(obs.raw_value).strip().lower() if isinstance(obs.raw_value, str) else obs.raw_value
            norm = str(obs.normalized_value).strip().lower() if isinstance(obs.normalized_value, str) else obs.normalized_value

            return raw == norm_target or norm == norm_target

        return [obs.source for obs in self.observations if _matches(obs)]

    def conflicting_sources(self, value: Any = None) -> list[str]:
        """Restituisce l'elenco delle fonti che discordano con il valore specificato (o corrente)."""
        supporting = set(self.supporting_sources(value))
        all_sources = [obs.source for obs in self.observations]
        return [s for s in all_sources if s not in supporting]

    def get_observation(self, source: str) -> Optional[SourceObservation]:
        """Recupera l'osservazione associata a una determinata fonte."""
        for obs in self.observations:
            if obs.source == source:
                return obs
        return None

    def to_dict(self) -> dict[str, Any]:
        """Serializza FieldProvenance in dizionario compatibile con JSON."""
        return {
            "field_path": self.field_path,
            "stop_id": self.stop_id,
            "current_value": copy.deepcopy(self.current_value),
            "normalized_value": copy.deepcopy(self.normalized_value),
            "observations": [obs.to_dict() for obs in self.observations],
            "transformations": [tr.to_dict() for tr in self.transformations],
            "has_conflict": self.has_conflict(),
            "supporting_sources": self.supporting_sources(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FieldProvenance:
        """Ricostruisce un FieldProvenance da dizionario."""
        return cls(
            field_path=str(data["field_path"]),
            stop_id=data.get("stop_id"),
            current_value=copy.deepcopy(data.get("current_value")),
            normalized_value=copy.deepcopy(data.get("normalized_value")),
            observations=[SourceObservation.from_dict(o) for o in data.get("observations", [])],
            transformations=[NormalizationRecord.from_dict(t) for t in data.get("transformations", [])],
        )


@dataclass
class CandidateProvenance:
    """Contenitore di primo livello della provenienza per un CandidatePlayer.

    Organizza i campi indicizzati (`fields`), mappa le tappe di carriera in modo stabile
    (`stop_id`), e fornisce API strutturate per interrogazioni, rilevamento conflitti
    e allineamento degli indici dopo riordini.
    """

    fields: dict[str, FieldProvenance] = field(default_factory=dict)

    def record_observation(
        self,
        field_path: str,
        source: str,
        source_id: str,
        raw_value: Any,
        *,
        retrieved_at: Optional[str] = None,
        confidence: Optional[float] = None,
        confidence_level: Optional[ConfidenceLevel | str] = None,
        normalized_value: Optional[Any] = None,
        source_url: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        adapter_version: Optional[str] = None,
        stop_id: Optional[str] = None,
    ) -> SourceObservation:
        """Registra un'osservazione di una fonte per un determinato percorso di campo."""
        if not field_path:
            raise ValueError("field_path non puo' essere vuoto")

        c_level = (
            confidence_level.value
            if isinstance(confidence_level, ConfidenceLevel)
            else (str(confidence_level) if confidence_level else ConfidenceLevel.PARSED_CLAIM.value)
        )
        c_score = confidence if confidence is not None else score_for_confidence_level(c_level)

        obs = SourceObservation(
            source=source,
            source_id=source_id,
            retrieved_at=retrieved_at or now_utc_iso(),
            confidence=c_score,
            confidence_level=c_level,
            raw_value=raw_value,
            normalized_value=normalized_value,
            source_url=source_url,
            metadata=dict(metadata or {}),
            adapter_version=adapter_version,
        )

        fp = self.fields.get(field_path)
        if fp is None:
            fp = FieldProvenance(
                field_path=field_path,
                stop_id=stop_id,
                current_value=raw_value,
                normalized_value=normalized_value,
            )
            self.fields[field_path] = fp
        else:
            if stop_id and not fp.stop_id:
                fp.stop_id = stop_id
            if fp.current_value is None:
                fp.current_value = raw_value
            if normalized_value is not None:
                fp.normalized_value = normalized_value

        fp.add_observation(obs)
        return obs

    def get_provenance_for_path(self, field_path: str) -> Optional[FieldProvenance]:
        """Restituisce il record di provenienza per un determinato percorso campo, o None."""
        return self.fields.get(field_path)

    def get_provenance_for_stop(self, stop_id: str, field_name: str) -> Optional[FieldProvenance]:
        """Trova la provenienza di un attributo di una tappa di carriera tramite il suo stop_id stabile."""
        for fp in self.fields.values():
            if fp.stop_id == stop_id and fp.field_path.endswith(f".{field_name}"):
                return fp
        return None

    def get_source_observations(self, field_path: str) -> list[SourceObservation]:
        """Restituisce tutte le osservazioni registrate per un percorso campo."""
        fp = self.fields.get(field_path)
        return list(fp.observations) if fp else []

    def record_normalization(
        self,
        field_path: str,
        raw_value: Any,
        normalized_value: Any,
        *,
        finding_code: Optional[str] = None,
        rule: Optional[str] = None,
        stop_id: Optional[str] = None,
    ) -> NormalizationRecord:
        """Registra una modifica di normalizzazione su un determinato campo."""
        rec = NormalizationRecord(
            raw_value=raw_value,
            normalized_value=normalized_value,
            finding_code=finding_code,
            rule=rule,
            timestamp=now_utc_iso(),
        )
        fp = self.fields.get(field_path)
        if fp is None:
            fp = FieldProvenance(
                field_path=field_path,
                stop_id=stop_id,
                current_value=normalized_value,
                normalized_value=normalized_value,
            )
            self.fields[field_path] = fp
        else:
            fp.current_value = normalized_value
            fp.normalized_value = normalized_value
            if stop_id and not fp.stop_id:
                fp.stop_id = stop_id

        fp.add_transformation(rec)
        return rec

    def reindex_career_paths(self, career: list[dict[str, Any]]) -> None:
        """Riallinea i percorsi `career[i].prop` in base al nuovo ordine delle tappe di carriera.

        Usa la chiave `_stop_id` presente in ogni dizionario di tappa per mappare l'identità
        originale alla nuova posizione array `i`. Garantisce che dopo `order_career`
        i riferimenti puntino esattamente alla tappa corretta senza alterare le osservazioni.
        """
        if not career:
            return

        # Crea mappa stop_id -> nuovo indice posizionale
        stop_to_new_idx: dict[str, int] = {}
        for new_idx, stop in enumerate(career):
            sid = stop.get("_stop_id")
            if sid:
                stop_to_new_idx[sid] = new_idx

        new_fields: dict[str, FieldProvenance] = {}
        career_path_regex = re.compile(r"^career\[(?:\d+|[a-zA-Z0-9_-]+)\]\.([a-zA-Z0-9_]+)$")

        for key, fp in self.fields.items():
            match = career_path_regex.match(key)
            if match and fp.stop_id and fp.stop_id in stop_to_new_idx:
                prop_name = match.group(1)
                new_idx = stop_to_new_idx[fp.stop_id]
                new_path = f"career[{new_idx}].{prop_name}"
                fp.field_path = new_path
                new_fields[new_path] = fp
            else:
                new_fields[key] = fp

        self.fields = new_fields

    def has_conflicts(self) -> bool:
        """Verifica se esiste almeno un campo con conflitti non risolti tra fonti."""
        return any(fp.has_conflict() for fp in self.fields.values())

    def get_conflicts(self) -> dict[str, FieldProvenance]:
        """Restituisce tutti i campi che presentano conflitti tra fonti diverse."""
        return {k: fp for k, fp in self.fields.items() if fp.has_conflict()}

    def to_dict(self) -> dict[str, Any]:
        """Serializza l'intera provenienza in formato dizionario compatibile con JSON."""
        return {
            "fields": {k: fp.to_dict() for k, fp in sorted(self.fields.items())},
            "has_conflicts": self.has_conflicts(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CandidateProvenance:
        """Ricostruisce un CandidateProvenance da dizionario."""
        fields_data = data.get("fields", {})
        fields = {k: FieldProvenance.from_dict(v) for k, v in fields_data.items()}
        return cls(fields=fields)
