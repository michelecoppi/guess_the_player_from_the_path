"""Glue layer between source adapters and Candidate Player Core.

Provides functions to:
1. Populate a CandidatePlayer from a successful AdapterResult;
2. Record structured adapter failures into the candidate error log;
3. Transition the candidate appropriately (DISCOVERED → FETCHED, or
   DISCOVERED → REVIEW_REQUIRED on partial/ambiguous data).

Does NOT perform normalization, validation, or production promotion.
Those responsibilities belong to #26 and #15.
"""
from __future__ import annotations

from services.adapters.base import AdapterError, AdapterResult
from services.candidate_player import (
    CandidatePlayer,
    CandidateState,
)


def populate_candidate_from_result(
    candidate: CandidatePlayer,
    result: AdapterResult,
) -> CandidatePlayer:
    """Map adapter result fields onto a CandidatePlayer and transition state.

    If the result is successful and contains usable data, transitions to
    ``FETCHED``.  If the result is partial (success but with errors, or
    missing critical fields), transitions to ``REVIEW_REQUIRED``.

    On a failed result, records errors and does NOT transition — callers
    should use ``record_adapter_failure`` instead.

    Args:
        candidate: A CandidatePlayer in ``DISCOVERED`` state.
        result: The AdapterResult from a source adapter.

    Returns:
        The same candidate instance, mutated in place.
    """
    if not result.success:
        # Record all errors from the failed result
        for err in result.errors:
            candidate.record_error(
                error_type=err.error_type.value,
                message=err.message,
                details=err.details,
                retryable=err.retryable,
            )
        return candidate

    # Populate data fields from the result
    if result.player_name:
        candidate.full_name = result.player_name
    if result.aliases:
        candidate.aliases = list(result.aliases)
    if result.birth_year is not None:
        candidate.birth_year = result.birth_year
    if result.nationality:
        candidate.nationality = result.nationality
    if result.position:
        candidate.position = result.position
    if result.career:
        candidate.career = [dict(c) for c in result.career]

    # Store raw source data and metadata for provenance (#27)
    candidate.raw_data = {
        "source_name": result.source_name,
        "source_id": result.source_id,
        "source_metadata": dict(result.source_metadata),
        "raw_payload": dict(result.raw_payload),
    }

    # Record non-fatal errors from the result
    for err in result.errors:
        candidate.record_error(
            error_type=err.error_type.value,
            message=err.message,
            details=err.details,
            retryable=err.retryable,
            increment_retry_count=False,
        )

    # Determine target state
    is_partial = _is_partial_result(result)

    if is_partial and candidate.can_transition_to(CandidateState.REVIEW_REQUIRED):
        candidate.transition_to(
            CandidateState.REVIEW_REQUIRED,
            reason=f"Dati parziali da {result.source_name}: campi mancanti",
            actor=f"adapter:{result.source_name}",
        )
    elif candidate.can_transition_to(CandidateState.FETCHED):
        candidate.transition_to(
            CandidateState.FETCHED,
            reason=f"Dati recuperati da {result.source_name}",
            actor=f"adapter:{result.source_name}",
        )

    return candidate


def record_adapter_failure(
    candidate: CandidatePlayer,
    error: AdapterError,
) -> CandidatePlayer:
    """Record a structured adapter failure in the candidate error log.

    Increments the retry count if the error is retryable.  Does NOT
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


def _is_partial_result(result: AdapterResult) -> bool:
    """Determine if an AdapterResult has significant missing data.

    A result is considered partial if it's missing the player name OR
    has fewer than 2 career stops (the dataset minimum) OR has non-fatal
    errors recorded.
    """
    if not result.player_name:
        return True
    if len(result.career) < 2:
        return True
    if result.errors:
        return True
    return False
