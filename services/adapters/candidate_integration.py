"""Glue layer between source adapters and Candidate Player Core.

Provides functions to:
1. Populate a CandidatePlayer from a successful AdapterResult;
2. Merge multiple adapter results (Wikipedia, Wikidata, etc.) preserving field-level provenance (#27);
3. Record structured adapter failures into the candidate error log;
4. Transition the candidate from DISCOVERED to FETCHED on successful acquisition.

Does NOT perform normalization, validation, review assignment, or production promotion.
Those responsibilities belong to #26 and #15.
"""
from __future__ import annotations

import copy
from typing import Any, Optional

from services.adapters.base import AdapterError, AdapterResult
from services.candidate_player import (
    CandidatePlayer,
    CandidateState,
)
from services.candidate_provenance import (
    ConfidenceLevel,
    make_career_stop_id,
    now_utc_iso,
)


def _determine_confidence_level(source_name: str, phase: str = "default") -> ConfidenceLevel:
    """Restituisce il livello di confidenza appropriato in base alla fonte e alla modalità di estrazione."""
    src = source_name.lower()
    if "wikidata" in src:
        # Wikidata e' un database di grafi strutturato
        return ConfidenceLevel.EXACT_STRUCTURED
    elif "wikipedia" in src:
        # Wikipedia e' semi-strutturata (template bio/infobox)
        return ConfidenceLevel.PARSED_CLAIM
    return ConfidenceLevel.PARSED_CLAIM


def _find_matching_career_stop(
    existing_career: list[dict[str, Any]],
    incoming_stop: dict[str, Any],
    excluded_indices: Optional[set[int]] = None,
) -> Optional[int]:
    """Cerca una tappa di carriera esistente compatibile con una nuova tappa in arrivo.

    Criteri di matching deterministico:
    1. Identita' esatta del club (cleaned) oppure identita' canonica normalizzata dal livello sicuro di normalizzazione.
       Non usa MAI sottostringhe (in/contains) per evitare fusioni errate (es. Inter vs Inter Miami, Real vs Real Madrid).
       Gli alias ambigui non sono mai match autoritativi.
    2. Compatibilita' temporale (anni coincidenti o entro +-1 anno).
    """
    in_raw = incoming_stop.get("team")
    if not in_raw or not str(in_raw).strip():
        return None

    from services.candidate_normalization import (
        FindingCode,
        FindingSeverity,
        clean_text,
        normalize_club_name,
    )

    in_clean = clean_text(str(in_raw)).lower()
    in_start = incoming_stop.get("start_year")
    in_end = incoming_stop.get("end_year")

    norm_in = ""
    try:
        norm_in_res, findings_in = normalize_club_name(in_raw, incoming_stop.get("country"))
        is_ambig_in = any(f.code == FindingCode.CLUB_AMBIGUOUS_ALIAS for f in findings_in)
        has_err_in = any(f.severity == FindingSeverity.ERROR for f in findings_in)
        if norm_in_res and not is_ambig_in and not has_err_in:
            norm_in = clean_text(norm_in_res).lower()
    except Exception:
        pass

    for idx, existing in enumerate(existing_career):
        if excluded_indices and idx in excluded_indices:
            continue

        ex_raw = existing.get("team")
        if not ex_raw or not str(ex_raw).strip():
            continue

        ex_clean = clean_text(str(ex_raw)).lower()
        ex_start = existing.get("start_year")
        ex_end = existing.get("end_year")

        norm_ex = ""
        try:
            norm_ex_res, findings_ex = normalize_club_name(ex_raw, existing.get("country"))
            is_ambig_ex = any(f.code == FindingCode.CLUB_AMBIGUOUS_ALIAS for f in findings_ex)
            has_err_ex = any(f.severity == FindingSeverity.ERROR for f in findings_ex)
            if norm_ex_res and not is_ambig_ex and not has_err_ex:
                norm_ex = clean_text(norm_ex_res).lower()
        except Exception:
            pass

        # Verifica equivalenza deterministica:
        # - Identita' esatta pulita (in_clean == ex_clean)
        # - Oppure identita' canonica normalizzata esatta (norm_in == norm_ex)
        # Sottostringhe / contenimento parziale tassativamente vietati!
        team_match = (
            in_clean == ex_clean
            or bool(norm_in and norm_ex and norm_in == norm_ex)
        )
        if not team_match:
            continue

        # Compatibilita' temporale: coincidenti o entro +-1 anno
        def _safe_year(val: Any) -> Optional[int]:
            if val is None or isinstance(val, bool):
                return None
            if isinstance(val, int):
                return val
            try:
                return int(str(val).strip())
            except (ValueError, TypeError):
                return None

        s_in_start = _safe_year(in_start)
        s_ex_start = _safe_year(ex_start)
        s_in_end = _safe_year(in_end)
        s_ex_end = _safe_year(ex_end)

        if s_in_start is not None and s_ex_start is not None:
            if abs(s_in_start - s_ex_start) <= 1:
                return idx
        elif s_in_end is not None and s_ex_end is not None:
            if abs(s_in_end - s_ex_end) <= 1:
                return idx
        elif s_in_start is None and s_in_end is None and s_ex_start is None and s_ex_end is None:
            return idx

    return None


def populate_candidate_from_result(
    candidate: CandidatePlayer,
    result: AdapterResult,
) -> CandidatePlayer:
    """Map adapter result fields onto a CandidatePlayer and transition state.

    Populates data fields and records granular field-level provenance (#27)
    for every fact extracted. If the candidate already has observations from
    another source, observations are merged without silently overwriting.

    Args:
        candidate: A CandidatePlayer instance.
        result: The AdapterResult from a source adapter.

    Returns:
        The same candidate instance, mutated in place.
    """
    if not result.success:
        for err in result.errors:
            candidate.record_error(
                error_type=err.error_type.value,
                message=err.message,
                details=err.details,
                retryable=err.retryable,
            )
        return candidate

    retrieved_at = result.source_metadata.get("retrieved_at") or now_utc_iso()
    source_url = result.source_metadata.get("url")
    confidence_level = _determine_confidence_level(result.source_name)

    # 1. Full name
    if result.player_name:
        if not candidate.full_name:
            candidate.full_name = result.player_name
        candidate.record_observation(
            field_path="full_name",
            source=result.source_name,
            source_id=result.source_id,
            raw_value=result.player_name,
            retrieved_at=retrieved_at,
            confidence_level=confidence_level,
            source_url=source_url,
        )

    # 2. Aliases
    if result.aliases:
        from services.candidate_normalization import clean_text

        for alias in result.aliases:
            if not alias or not str(alias).strip():
                continue
            clean_a = clean_text(str(alias)).lower()
            target_idx = None
            for idx, existing in enumerate(candidate.aliases):
                if clean_text(str(existing)).lower() == clean_a:
                    target_idx = idx
                    break

            if target_idx is None:
                candidate.aliases.append(alias)
                target_idx = len(candidate.aliases) - 1

            candidate.record_observation(
                field_path=f"aliases[{target_idx}]",
                source=result.source_name,
                source_id=result.source_id,
                raw_value=alias,
                retrieved_at=retrieved_at,
                confidence_level=confidence_level,
                source_url=source_url,
            )

    # 3. Birth year
    if result.birth_year is not None:
        if candidate.birth_year is None:
            candidate.birth_year = result.birth_year
        candidate.record_observation(
            field_path="birth_year",
            source=result.source_name,
            source_id=result.source_id,
            raw_value=result.birth_year,
            retrieved_at=retrieved_at,
            confidence_level=confidence_level,
            source_url=source_url,
        )

    # 4. Nationality
    if result.nationality:
        if not candidate.nationality:
            candidate.nationality = result.nationality
        meta = {"nationality_raw": result.nationality_raw} if result.nationality_raw else {}
        candidate.record_observation(
            field_path="nationality",
            source=result.source_name,
            source_id=result.source_id,
            raw_value=result.nationality,
            retrieved_at=retrieved_at,
            confidence_level=confidence_level,
            source_url=source_url,
            metadata=meta,
        )

    # 5. Position
    if result.position:
        if not candidate.position:
            candidate.position = result.position
        candidate.record_observation(
            field_path="position",
            source=result.source_name,
            source_id=result.source_id,
            raw_value=result.position,
            retrieved_at=retrieved_at,
            confidence_level=confidence_level,
            source_url=source_url,
        )

    # 6. Career stops and field provenance
    if result.career:
        is_initial_career = len(candidate.career) == 0
        initial_count = len(candidate.career)
        matched_indices: set[int] = set()

        for in_idx, raw_entry in enumerate(result.career):
            entry = dict(raw_entry)
            matched_idx = None
            if not is_initial_career:
                matched_idx = _find_matching_career_stop(
                    candidate.career[:initial_count],
                    entry,
                    excluded_indices=matched_indices,
                )
                if matched_idx is not None:
                    matched_indices.add(matched_idx)

            if matched_idx is not None:
                # La tappa esiste gia' da una fonte precedente: arricchisce i campi mancanti e registra le osservazioni
                stop_target = candidate.career[matched_idx]
                team_hint = str(stop_target.get("team")) if stop_target.get("team") else None
                stop_id = stop_target.setdefault(
                    "_stop_id",
                    make_career_stop_id(result.source_name, matched_idx, team_hint),
                )
                curr_idx = matched_idx
                # Arricchisce campi assenti nel candidato
                for k in ("country", "league", "start_year", "end_year", "apps", "goals", "loan"):
                    if stop_target.get(k) is None and entry.get(k) is not None:
                        stop_target[k] = entry[k]
            else:
                # Nuova tappa di carriera
                entry_hint = str(entry.get("team")) if entry.get("team") else None
                stop_id = entry.get("stop_id") or make_career_stop_id(
                    result.source_name, len(candidate.career), entry_hint
                )
                entry["_stop_id"] = stop_id
                candidate.career.append(entry)
                curr_idx = len(candidate.career) - 1



            # Registra osservazioni per ogni campo della tappa
            for prop in ("team", "country", "league", "start_year", "end_year", "apps", "goals", "loan"):
                if entry.get(prop) is not None:
                    candidate.record_observation(
                        field_path=f"career[{curr_idx}].{prop}",
                        source=result.source_name,
                        source_id=result.source_id,
                        raw_value=entry[prop],
                        retrieved_at=retrieved_at,
                        confidence_level=confidence_level,
                        source_url=source_url,
                        stop_id=stop_id,
                    )

    # 7. Preserva raw data per auditing e backward-compatibility
    if "sources" not in candidate.raw_data:
        # Se raw_data ha la vecchia struttura piatta, la migriamo salvando prima old_raw
        old_raw = copy.deepcopy(candidate.raw_data)
        old_src = old_raw.get("source_name")
        candidate.raw_data = {"sources": {}}
        if old_src:
            candidate.raw_data["sources"][old_src] = old_raw

    candidate.raw_data["sources"][result.source_name] = {
        "source_name": result.source_name,
        "source_id": result.source_id,
        "source_metadata": dict(result.source_metadata),
        "raw_payload": dict(result.raw_payload),
    }
    # Mantiene anche la compatibilita con accessi diretti di test a raw_data["source_name"]
    candidate.raw_data["source_name"] = result.source_name
    candidate.raw_data["source_id"] = result.source_id
    candidate.raw_data["source_metadata"] = dict(result.source_metadata)
    candidate.raw_data["raw_payload"] = dict(result.raw_payload)

    # 8. Record non-fatal errors from the result
    for err in result.errors:
        candidate.record_error(
            error_type=err.error_type.value,
            message=err.message,
            details=err.details,
            retryable=err.retryable,
            increment_retry_count=False,
        )

    # 9. Aggiorna flag conflitti nei metadati
    candidate.metadata["has_source_conflicts"] = candidate.provenance.has_conflicts()

    # 10. Transizione di stato DISCOVERED -> FETCHED
    if candidate.can_transition_to(CandidateState.FETCHED):
        candidate.transition_to(
            CandidateState.FETCHED,
            reason=f"Dati recuperati da {result.source_name}",
            actor=f"adapter:{result.source_name}",
        )

    return candidate


def merge_adapter_result(
    candidate: CandidatePlayer,
    result: AdapterResult,
) -> CandidatePlayer:
    """Aggiunge i dati di una sorgente addizionale al candidato preservando la provenienza.

    Equivalente a chiamare populate_candidate_from_result su un candidato gia' istanziato.
    """
    return populate_candidate_from_result(candidate, result)


def record_adapter_failure(
    candidate: CandidatePlayer,
    error: AdapterError,
) -> CandidatePlayer:
    """Record a structured adapter failure in the candidate error log.

    Increments the retry count if the error is retryable. Does NOT
    transition state — the orchestration layer decides whether to retry,
    try another source, or move to REVIEW_REQUIRED.

    Args:
        candidate: The CandidatePlayer to record the error on.
        error: The structured AdapterError from the adapter.

    Returns:
        The same candidate instance, mutated in place.
    """
    candidate.record_error(
        error_type=error.error_type.value,
        message=error.message,
        details={
            "source_name": error.source_name,
            **error.details,
        },
        retryable=error.retryable,
    )
    return candidate
