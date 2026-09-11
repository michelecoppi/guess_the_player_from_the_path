"""Candidate Player Validation Service.

Deterministic, reusable validation engine for Candidate Players (#26).
- Detects empty/short careers, invalid ranges, future dates, and corrupt data;
- Differentiates legitimate transfers/loans from impossible contract overlaps;
- Flags unresolved QIDs, missing countries/leagues, and ambiguous aliases;
- Uses an injectable current year provider to remain resilient across years;
- Integrates with the Candidate Player lifecycle:
  NORMALIZED -> VALIDATED (if zero ERROR findings)
  NORMALIZED -> REVIEW_REQUIRED (if at least one ERROR finding);
- Never touches or modifies data/players.json.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Callable, Optional

from services.candidate_finding import CandidateFinding, FindingCode, FindingSeverity
from services.candidate_normalization import (
    clean_text,
    get_canonical_club_index,
    normalize_candidate,
)
from services.candidate_player import CandidatePlayer, CandidateState
from services.career_order import order_career

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PLAYERS_PATH = os.path.join(_BASE_DIR, "data", "players.json")
_CONFIG_PATH = os.path.join(_BASE_DIR, "data", "config.json")

_QID_REGEX = re.compile(r"^Q\d+$")
_MIN_PLAUSIBLE_YEAR = 1890

_EXISTING_ALIASES_CACHE: Optional[dict[str, dict[str, str]]] = None
_MULTI_COUNTRY_CLUBS_CACHE: Optional[set[str]] = None


def get_default_current_year() -> int:
    """Returns the current UTC year."""
    return datetime.now(timezone.utc).year


def _load_production_alias_index() -> dict[str, dict[str, str]]:
    """Builds a read-only index of lowercase alias -> {'id': pid, 'full_name': name} from data/players.json."""
    global _EXISTING_ALIASES_CACHE
    if _EXISTING_ALIASES_CACHE is not None:
        return _EXISTING_ALIASES_CACHE

    alias_map: dict[str, dict[str, str]] = {}
    try:
        if os.path.exists(_PLAYERS_PATH):
            with open(_PLAYERS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            for p in data.get("players", []):
                pid = p.get("id", "")
                pname = p.get("full_name", "")
                entry = {"id": pid, "full_name": pname}
                for alias in p.get("aliases", []):
                    clean_a = clean_text(alias).lower()
                    if clean_a:
                        alias_map[clean_a] = entry
    except Exception:
        pass

    _EXISTING_ALIASES_CACHE = alias_map
    return _EXISTING_ALIASES_CACHE


def _load_multi_country_clubs() -> set[str]:
    """Loads allowed multi-country clubs from data/config.json."""
    global _MULTI_COUNTRY_CLUBS_CACHE
    if _MULTI_COUNTRY_CLUBS_CACHE is not None:
        return _MULTI_COUNTRY_CLUBS_CACHE

    allowed = set()
    try:
        if os.path.exists(_CONFIG_PATH):
            with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            allowed = set(cfg.get("multi_country_clubs", {}).keys())
    except Exception:
        pass

    _MULTI_COUNTRY_CLUBS_CACHE = allowed
    return _MULTI_COUNTRY_CLUBS_CACHE


def validate_candidate_data(
    candidate: CandidatePlayer,
    current_year_provider: Optional[Callable[[], int]] = None,
) -> list[CandidateFinding]:
    """Performs comprehensive deterministic validation checks on candidate data.

    Returns a list of structured CandidateFinding objects (WARNING and ERROR).
    """
    findings: list[CandidateFinding] = []
    current_year = current_year_provider() if current_year_provider else get_default_current_year()

    # 1. Player-level checks
    # Full Name
    name = candidate.full_name
    if not name or not str(name).strip():
        findings.append(
            CandidateFinding(
                code=FindingCode.PLAYER_NAME_EMPTY,
                severity=FindingSeverity.ERROR,
                message="Il nome completo del giocatore è vuoto o mancante",
                field_path="full_name",
                input_value=name,
            )
        )
    else:
        name_clean = clean_text(name)
        if _QID_REGEX.match(name_clean):
            findings.append(
                CandidateFinding(
                    code=FindingCode.PLAYER_NAME_MALFORMED,
                    severity=FindingSeverity.ERROR,
                    message=f"Il nome '{name_clean}' è un QID Wikidata non risolto",
                    field_path="full_name",
                    input_value=name,
                )
            )
        elif len(name_clean) < 2 or len(name_clean) > 80 or any(c in name for c in "{}[]<>"):
            findings.append(
                CandidateFinding(
                    code=FindingCode.PLAYER_NAME_MALFORMED,
                    severity=FindingSeverity.ERROR,
                    message=f"Nome del giocatore malformato o con markup residuo: '{name}'",
                    field_path="full_name",
                    input_value=name,
                )
            )

    # Nationality
    if not candidate.nationality or not str(candidate.nationality).strip():
        findings.append(
            CandidateFinding(
                code=FindingCode.PLAYER_NATIONALITY_MISSING,
                severity=FindingSeverity.ERROR,
                message="Nazionalità del giocatore mancante",
                field_path="nationality",
                input_value=candidate.nationality,
            )
        )

    # Position
    if not candidate.position or not str(candidate.position).strip():
        findings.append(
            CandidateFinding(
                code=FindingCode.PLAYER_POSITION_MISSING,
                severity=FindingSeverity.WARNING,
                message="Ruolo del giocatore mancante",
                field_path="position",
                input_value=candidate.position,
                requires_review=False,
            )
        )

    # Birth Year
    birth_year = candidate.birth_year
    if birth_year is not None:
        if not isinstance(birth_year, int) or isinstance(birth_year, bool):
            findings.append(
                CandidateFinding(
                    code=FindingCode.PLAYER_BIRTH_YEAR_IMPLAUSIBLE,
                    severity=FindingSeverity.ERROR,
                    message=f"Anno di nascita non numerico: {birth_year}",
                    field_path="birth_year",
                    input_value=birth_year,
                )
            )
        elif birth_year < _MIN_PLAUSIBLE_YEAR:
            findings.append(
                CandidateFinding(
                    code=FindingCode.PLAYER_BIRTH_YEAR_IMPLAUSIBLE,
                    severity=FindingSeverity.ERROR,
                    message=f"Anno di nascita implausibile ({birth_year} < {_MIN_PLAUSIBLE_YEAR})",
                    field_path="birth_year",
                    input_value=birth_year,
                )
            )
        elif birth_year > current_year:
            findings.append(
                CandidateFinding(
                    code=FindingCode.CAREER_FUTURE_YEAR,
                    severity=FindingSeverity.ERROR,
                    message=f"Anno di nascita nel futuro ({birth_year} > {current_year})",
                    field_path="birth_year",
                    input_value=birth_year,
                )
            )

    # Aliases
    prod_alias_index = _load_production_alias_index()
    for idx, alias in enumerate(candidate.aliases or []):
        alias_clean = clean_text(alias).lower()
        if _QID_REGEX.match(alias_clean):
            findings.append(
                CandidateFinding(
                    code=FindingCode.PLAYER_ALIAS_MALFORMED,
                    severity=FindingSeverity.WARNING,
                    message=f"L'alias '{alias}' è un QID Wikidata non risolto",
                    field_path=f"aliases[{idx}]",
                    input_value=alias,
                    requires_review=False,
                )
            )
        # Check collision with existing players in production dataset
        existing_owner = prod_alias_index.get(alias_clean)
        if existing_owner:
            owner_id = existing_owner["id"]
            owner_name = existing_owner["full_name"]
            cand_name = candidate.full_name or ""
            is_same = False
            if cand_name:
                cand_clean = clean_text(cand_name).lower()
                owner_clean = clean_text(owner_name).lower()
                if cand_clean == owner_clean:
                    is_same = True
                else:
                    from services.candidate_player import _clean_slug
                    if _clean_slug(cand_name) == owner_id or _clean_slug(cand_name) == _clean_slug(owner_name):
                        is_same = True

            if not is_same:
                findings.append(
                    CandidateFinding(
                        code=FindingCode.PLAYER_ALIAS_AMBIGUOUS,
                        severity=FindingSeverity.ERROR,
                        message=f"L'alias '{alias}' è già assegnato al diverso giocatore di produzione '{owner_name}' ({owner_id})",
                        field_path=f"aliases[{idx}]",
                        input_value=alias,
                        context={"conflicting_player_id": owner_id, "conflicting_player_name": owner_name},
                    )
                )

    # 2. Career-level checks
    career = candidate.career or []
    one_club = bool(candidate.metadata.get("one_club_career", False))

    if len(career) == 0:
        findings.append(
            CandidateFinding(
                code=FindingCode.CAREER_EMPTY,
                severity=FindingSeverity.ERROR,
                message="Carriera vuota: nessuna tappa registrata",
                field_path="career",
                input_value=[],
            )
        )
        return findings

    if len(career) == 1 and not one_club:
        findings.append(
            CandidateFinding(
                code=FindingCode.CAREER_TOO_SHORT,
                severity=FindingSeverity.ERROR,
                message=(
                    "Carriera di un solo club senza flag 'one_club_career': "
                    "verificare se si tratta di una bandiera o di dati incompleti"
                ),
                field_path="career",
                context={"career_len": 1},
            )
        )
    elif len(career) > 1 and one_club:
        findings.append(
            CandidateFinding(
                code=FindingCode.CAREER_ONE_CLUB_MISMATCH,
                severity=FindingSeverity.ERROR,
                message="Flag 'one_club_career' presente ma la carriera ha più di una tappa",
                field_path="career",
                context={"career_len": len(career)},
            )
        )

    # Check career ordering
    canonical_order = order_career(career)
    if canonical_order != career:
        findings.append(
            CandidateFinding(
                code=FindingCode.CAREER_ORDER,
                severity=FindingSeverity.ERROR,
                message="Le tappe di carriera non sono nel corretto ordine canonico",
                field_path="career",
            )
        )

    # 3. Stop-level checks
    canonical_clubs = get_canonical_club_index()
    multi_country = _load_multi_country_clubs()

    seen_exact_stops: set[tuple[str, Optional[int], Optional[int], bool]] = set()

    for idx, stop in enumerate(career):
        team = stop.get("team")
        country = stop.get("country")
        league = stop.get("league")
        start_year = stop.get("start_year")
        end_year = stop.get("end_year")
        loan = bool(stop.get("loan", False))
        apps = stop.get("apps")
        goals = stop.get("goals")

        # Team name
        if not team or not str(team).strip():
            findings.append(
                CandidateFinding(
                    code=FindingCode.CLUB_NAME_MISSING,
                    severity=FindingSeverity.ERROR,
                    message="Nome del club mancante nella tappa",
                    field_path=f"career[{idx}].team",
                    input_value=team,
                )
            )
        else:
            clean_team = clean_text(str(team))
            if _QID_REGEX.match(clean_team):
                findings.append(
                    CandidateFinding(
                        code=FindingCode.CLUB_UNRESOLVED_QID,
                        severity=FindingSeverity.ERROR,
                        message=f"Il club '{clean_team}' è un QID Wikidata non risolto",
                        field_path=f"career[{idx}].team",
                        input_value=team,
                    )
                )
            elif any(c in str(team) for c in "{}[]<>"):
                findings.append(
                    CandidateFinding(
                        code=FindingCode.CLUB_NAME_MALFORMED,
                        severity=FindingSeverity.ERROR,
                        message=f"Nome del club con markup o caratteri non ammessi: '{team}'",
                        field_path=f"career[{idx}].team",
                        input_value=team,
                    )
                )

        # Missing country
        if not country or not str(country).strip() or country == "?":
            findings.append(
                CandidateFinding(
                    code=FindingCode.CLUB_MISSING_COUNTRY,
                    severity=FindingSeverity.ERROR,
                    message=f"Paese mancante per il club '{team}'",
                    field_path=f"career[{idx}].country",
                    input_value=country,
                )
            )

        # Missing league
        if not league or not str(league).strip() or league == "?":
            findings.append(
                CandidateFinding(
                    code=FindingCode.CLUB_MISSING_LEAGUE,
                    severity=FindingSeverity.ERROR,
                    message=f"Campionato mancante per il club '{team}'",
                    field_path=f"career[{idx}].league",
                    input_value=league,
                )
            )

        # Multi-country mismatch
        if team and country and team not in multi_country:
            team_lower = clean_text(team).lower()
            # If club exists in canonical index with another country
            for _, (can_team, can_country, _) in canonical_clubs.items():
                if can_team.lower() == team_lower and can_country != country:
                    findings.append(
                        CandidateFinding(
                            code=FindingCode.CLUB_COUNTRY_MISMATCH,
                            severity=FindingSeverity.WARNING,
                            message=(
                                f"Il club '{team}' è associato a '{country}', mentre nel dataset è '{can_country}'"
                            ),
                            field_path=f"career[{idx}].country",
                            input_value=country,
                            context={"expected_country": can_country},
                            requires_review=False,
                        )
                    )
                    break

        # Start year checks
        if start_year is None:
            findings.append(
                CandidateFinding(
                    code=FindingCode.CAREER_INVALID_RANGE,
                    severity=FindingSeverity.ERROR,
                    message=f"Anno di inizio mancante per la tappa '{team}'",
                    field_path=f"career[{idx}].start_year",
                    input_value=start_year,
                )
            )
        elif not isinstance(start_year, int) or isinstance(start_year, bool):
            findings.append(
                CandidateFinding(
                    code=FindingCode.CAREER_INVALID_RANGE,
                    severity=FindingSeverity.ERROR,
                    message=f"Anno di inizio non numerico per la tappa '{team}': {start_year}",
                    field_path=f"career[{idx}].start_year",
                    input_value=start_year,
                )
            )
        else:
            if start_year < _MIN_PLAUSIBLE_YEAR:
                findings.append(
                    CandidateFinding(
                        code=FindingCode.CAREER_INVALID_RANGE,
                        severity=FindingSeverity.ERROR,
                        message=f"Anno di inizio implausibile per la tappa '{team}': {start_year}",
                        field_path=f"career[{idx}].start_year",
                        input_value=start_year,
                    )
                )
            elif start_year > current_year:
                findings.append(
                    CandidateFinding(
                        code=FindingCode.CAREER_FUTURE_YEAR,
                        severity=FindingSeverity.ERROR,
                        message=f"Anno di inizio nel futuro ({start_year} > {current_year}) per '{team}'",
                        field_path=f"career[{idx}].start_year",
                        input_value=start_year,
                    )
                )

            if birth_year is not None and isinstance(birth_year, int) and (start_year - birth_year < 14):
                findings.append(
                    CandidateFinding(
                        code=FindingCode.CAREER_INVALID_RANGE,
                        severity=FindingSeverity.ERROR,
                        message=(
                            f"Inizio carriera ({start_year}) incompatibile con la nascita ({birth_year}): "
                            f"meno di 14 anni ({start_year - birth_year})"
                        ),
                        field_path=f"career[{idx}].start_year",
                        input_value=start_year,
                        context={"birth_year": birth_year, "age_at_start": start_year - birth_year},
                    )
                )

        # End year checks
        if end_year is not None:
            if not isinstance(end_year, int) or isinstance(end_year, bool):
                findings.append(
                    CandidateFinding(
                        code=FindingCode.CAREER_INVALID_RANGE,
                        severity=FindingSeverity.ERROR,
                        message=f"Anno di fine non numerico per '{team}': {end_year}",
                        field_path=f"career[{idx}].end_year",
                        input_value=end_year,
                    )
                )
            else:
                if isinstance(start_year, int) and end_year < start_year:
                    findings.append(
                        CandidateFinding(
                            code=FindingCode.CAREER_INVALID_RANGE,
                            severity=FindingSeverity.ERROR,
                            message=f"Anno di fine ({end_year}) precedente all'inizio ({start_year}) per '{team}'",
                            field_path=f"career[{idx}].end_year",
                            input_value=end_year,
                        )
                    )
                elif end_year > current_year:
                    findings.append(
                        CandidateFinding(
                            code=FindingCode.CAREER_FUTURE_YEAR,
                            severity=FindingSeverity.ERROR,
                            message=f"Anno di fine nel futuro ({end_year} > {current_year}) per '{team}'",
                            field_path=f"career[{idx}].end_year",
                            input_value=end_year,
                        )
                    )
        else:
            # end_year is None (ongoing)
            # Ongoing is valid ONLY if it's the last stop (or among the last concurrent stops)
            if idx < len(career) - 1:
                # Check if subsequent stops have a start year after this one
                later_stops = [s for s in career[idx + 1:] if isinstance(s.get("start_year"), int)]
                if later_stops and any(s["start_year"] > (start_year or 0) for s in later_stops):
                    findings.append(
                        CandidateFinding(
                            code=FindingCode.CAREER_INVALID_RANGE,
                            severity=FindingSeverity.ERROR,
                            message=(
                                f"Tappa '{team}' senza anno di fine (in corso) posizionata prima "
                                f"di tappe successive"
                            ),
                            field_path=f"career[{idx}].end_year",
                            input_value=None,
                        )
                    )

        # Apps & Goals
        for stat_name, stat_val in (("apps", apps), ("goals", goals)):
            if stat_val is not None:
                if not isinstance(stat_val, int) or isinstance(stat_val, bool) or stat_val < 0:
                    findings.append(
                        CandidateFinding(
                            code=FindingCode.CAREER_APPS_GOALS_INVALID,
                            severity=FindingSeverity.ERROR,
                            message=f"Valore '{stat_name}' non valido ({stat_val}) per '{team}': atteso intero >= 0",
                            field_path=f"career[{idx}].{stat_name}",
                            input_value=stat_val,
                        )
                    )

        # Duplicate stop detection
        if team and isinstance(start_year, int):
            stop_sig = (clean_text(str(team)).lower(), start_year, end_year, loan)
            if stop_sig in seen_exact_stops:
                findings.append(
                    CandidateFinding(
                        code=FindingCode.CAREER_DUPLICATE_STOP,
                        severity=FindingSeverity.ERROR,
                        message=f"Tappa duplicata rilevata per '{team}' ({start_year}-{end_year or 'oggi'})",
                        field_path=f"career[{idx}]",
                        context={"team": team, "start_year": start_year, "end_year": end_year},
                    )
                )
            else:
                seen_exact_stops.add(stop_sig)

    # 4. Overlap analysis across stops
    # Distinguish:
    # - Legitimate loan within parent contract -> VALID
    # - Same-year transfer (A.end == B.start) -> VALID
    # - Multiple clubs in same season/year -> VALID
    # - Impossible/suspicious multi-year overlap between permanent contracts -> ERROR
    # - Loan without parent contract -> WARNING (CAREER_ORPHAN_LOAN)
    permanent_stops = [
        (i, s) for i, s in enumerate(career)
        if not s.get("loan") and isinstance(s.get("start_year"), int)
    ]

    for i in range(len(permanent_stops)):
        idx_a, stop_a = permanent_stops[i]
        start_a = stop_a["start_year"]
        end_a = stop_a.get("end_year")
        team_a = stop_a.get("team")

        for j in range(i + 1, len(permanent_stops)):
            idx_b, stop_b = permanent_stops[j]
            start_b = stop_b["start_year"]
            end_b = stop_b.get("end_year")
            team_b = stop_b.get("team")

            if clean_text(str(team_a)).lower() == clean_text(str(team_b)).lower():
                # Same club: if disjoint periods, return to club is VALID.
                # If overlapping, duplicate/overlap error.
                if end_a is None or (isinstance(end_a, int) and start_b < end_a):
                    findings.append(
                        CandidateFinding(
                            code=FindingCode.CAREER_OVERLAP,
                            severity=FindingSeverity.ERROR,
                            message=f"Periodi sovrapposti per lo stesso club '{team_a}'",
                            field_path=f"career[{idx_b}]",
                            context={"first_stop": idx_a, "second_stop": idx_b},
                        )
                    )
                continue

            # Different permanent clubs:
            # Overlap occurs if stop_b starts before stop_a ends.
            # However: in football, same-year transfer (start_b == end_a) is VALID.
            # Suspicious/impossible overlap is when start_b < end_a (by 1 or more years)
            # or if stop_a has end_year=None (ongoing) while stop_b starts later.
            if end_a is None:
                findings.append(
                    CandidateFinding(
                        code=FindingCode.CAREER_OVERLAP,
                        severity=FindingSeverity.ERROR,
                        message=(
                            f"Contratto in corso con '{team_a}' si sovrappone al contratto "
                            f"con '{team_b}' ({start_b})"
                        ),
                        field_path=f"career[{idx_b}]",
                        context={"first_stop": idx_a, "second_stop": idx_b},
                    )
                )
            elif isinstance(end_a, int) and start_b < end_a:
                # E.g. A is 2010-2015, B starts in 2012 -> 3 years overlapping permanent contracts
                overlap_years = end_a - start_b
                findings.append(
                    CandidateFinding(
                        code=FindingCode.CAREER_OVERLAP,
                        severity=FindingSeverity.ERROR,
                        message=(
                            f"Sovrapposizione pluriennale impossibile tra contratti permanenti: "
                            f"'{team_a}' ({start_a}-{end_a}) e '{team_b}' ({start_b}-{end_b or 'oggi'}) "
                            f"({overlap_years} anni di sovrapposizione)"
                        ),
                        field_path=f"career[{idx_b}]",
                        context={
                            "team_a": team_a, "years_a": f"{start_a}-{end_a}",
                            "team_b": team_b, "years_b": f"{start_b}-{end_b}",
                            "overlap_years": overlap_years,
                        },
                    )
                )

    # Loan verification: does the loan have an owning contract?
    for idx, stop in enumerate(career):
        if stop.get("loan") and isinstance(stop.get("start_year"), int):
            loan_start = stop["start_year"]
            loan_end = stop.get("end_year") or loan_start
            team_loan = stop.get("team")

            # Look for an owning permanent contract
            has_parent = False
            for _, parent in permanent_stops:
                p_start = parent["start_year"]
                p_end = parent.get("end_year")
                if p_start <= loan_start:
                    if p_end is None or (isinstance(p_end, int) and loan_end <= p_end):
                        has_parent = True
                        break

            if not has_parent:
                findings.append(
                    CandidateFinding(
                        code=FindingCode.CAREER_ORPHAN_LOAN,
                        severity=FindingSeverity.WARNING,
                        message=(
                            f"Prestito presso '{team_loan}' ({loan_start}-{loan_end}) non coperto "
                            f"da un contratto permanente contestuale"
                        ),
                        field_path=f"career[{idx}]",
                        context={"team": team_loan, "years": f"{loan_start}-{loan_end}"},
                        requires_review=False,
                    )
                )

    return findings


def calculate_confidence_score(findings: list[CandidateFinding]) -> float:
    """Calculates a deterministic quality confidence score in [0.0, 1.0]."""
    has_errors = any(f.severity == FindingSeverity.ERROR for f in findings)
    if has_errors:
        return 0.0

    score = 1.0
    for f in findings:
        if f.severity == FindingSeverity.WARNING:
            # Minor penalty per warning
            score -= 0.08

    return max(0.2, round(score, 2))


def validate_candidate(
    candidate: CandidatePlayer,
    current_year_provider: Optional[Callable[[], int]] = None,
    actor: str = "service:validation",
) -> CandidatePlayer:
    """Validates a CandidatePlayer and updates its lifecycle state.

    - Evaluates comprehensive career, player, date, and alias rules;
    - Persists structured findings in `candidate.metadata['validation_findings']`;
    - Populates `candidate.validation_warnings` and `candidate.validation_errors`;
    - Computes and updates `candidate.confidence_score`;
    - Transitions:
        - To `VALIDATED` if zero ERROR findings;
        - To `REVIEW_REQUIRED` if at least one ERROR (blocking) finding.

    Args:
        candidate: CandidatePlayer in NORMALIZED or REVIEW_REQUIRED state.
        current_year_provider: Injected callable returning current year (e.g. for testing).
        actor: System/service identifier for audit trail.

    Returns:
        The validated CandidatePlayer (mutated in-place).
    """
    findings = validate_candidate_data(candidate, current_year_provider=current_year_provider)

    errors = [f for f in findings if f.severity == FindingSeverity.ERROR]
    warnings = [f for f in findings if f.severity == FindingSeverity.WARNING]

    # Update findings in metadata
    candidate.metadata["validation_findings"] = [f.to_dict() for f in findings]

    # Update candidate warnings and errors lists (deduplicated)
    warning_msgs: list[str] = list(candidate.validation_warnings)
    for w in warnings:
        if w.message not in warning_msgs:
            warning_msgs.append(w.message)
    candidate.validation_warnings = warning_msgs

    candidate.validation_errors = [e.message for e in errors]

    # Compute confidence score
    candidate.confidence_score = calculate_confidence_score(findings)

    # State transition
    has_blocking_errors = len(errors) > 0

    if has_blocking_errors:
        target_state = CandidateState.REVIEW_REQUIRED
        reason = f"Validazione fallita con {len(errors)} errori bloccanti: {errors[0].message}"
    else:
        target_state = CandidateState.VALIDATED
        reason = (
            f"Validazione superata con successo ({len(warnings)} warning)"
            if warnings
            else "Validazione superata con successo (dati puliti)"
        )

    # Execute state transition if allowed
    if candidate.can_transition_to(target_state):
        candidate.transition_to(
            target_state,
            reason=reason,
            actor=actor,
            metadata={
                "error_count": len(errors),
                "warning_count": len(warnings),
                "confidence_score": candidate.confidence_score,
            },
        )

    return candidate


def process_candidate(
    candidate: CandidatePlayer,
    current_year_provider: Optional[Callable[[], int]] = None,
    actor: str = "service:pipeline",
) -> CandidatePlayer:
    """Convenience pipeline runner: normalizes then validates a candidate.

    Follows lifecycle:
        FETCHED -> NORMALIZED -> VALIDATED (or REVIEW_REQUIRED).
    """
    if candidate.status == CandidateState.FETCHED:
        normalize_candidate(candidate, actor=f"{actor}:normalization")

    if candidate.status == CandidateState.NORMALIZED:
        validate_candidate(
            candidate,
            current_year_provider=current_year_provider,
            actor=f"{actor}:validation",
        )

    return candidate
