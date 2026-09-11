"""Unit tests for Candidate Player validation service (#26)."""
import hashlib
import os

from services.candidate_finding import CandidateFinding, FindingCode, FindingSeverity
from services.candidate_player import CandidatePlayer, CandidateState
from services.candidate_validation import (
    process_candidate,
    validate_candidate,
)

_PLAYERS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "players.json")


def _get_players_json_hash() -> str:
    with open(_PLAYERS_PATH, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def test_clean_valid_career_transitions_to_validated():
    """A clean, coherent candidate transitions NORMALIZED -> VALIDATED."""
    candidate = CandidatePlayer(
        candidate_id="cand_valid_messi",
        source="wikipedia",
        source_id="Lionel_Messi",
        full_name="Lionel Messi",
        nationality="Argentina",
        position="Attaccante",
        birth_year=1987,
        aliases=["messi", "leo messi"],
        career=[
            {"team": "Barcelona", "country": "Spagna", "league": "La Liga", "start_year": 2004, "end_year": 2021},
            {"team": "Paris Saint-Germain", "country": "Francia", "league": "Ligue 1", "start_year": 2021, "end_year": 2023},
            {"team": "Inter Miami", "country": "USA", "league": "MLS", "start_year": 2023, "end_year": None},
        ],
    )
    candidate.transition_to(CandidateState.FETCHED)
    candidate.transition_to(CandidateState.NORMALIZED)

    validated = validate_candidate(candidate, current_year_provider=lambda: 2026)

    assert validated.status == CandidateState.VALIDATED
    assert validated.validation_errors == []
    assert validated.confidence_score is not None
    assert validated.confidence_score >= 0.9


def test_empty_career_transitions_to_review_required():
    candidate = CandidatePlayer(
        candidate_id="cand_empty_career",
        source="wikipedia",
        source_id="Player_Empty",
        full_name="Player Empty",
        nationality="Italia",
        position="Centrocampista",
        career=[],
    )
    candidate.transition_to(CandidateState.FETCHED)
    candidate.transition_to(CandidateState.NORMALIZED)

    validate_candidate(candidate)

    assert candidate.status == CandidateState.REVIEW_REQUIRED
    assert any("Carriera vuota" in err for err in candidate.validation_errors)
    findings = [CandidateFinding.from_dict(d) for d in candidate.metadata["validation_findings"]]
    assert any(f.code == FindingCode.CAREER_EMPTY and f.severity == FindingSeverity.ERROR for f in findings)


def test_single_team_without_one_club_flag_requires_review():
    candidate = CandidatePlayer(
        candidate_id="cand_short_career",
        source="wikipedia",
        source_id="Short_Career",
        full_name="Short Career",
        nationality="Italia",
        position="Difensore",
        career=[
            {"team": "Milan", "country": "Italia", "league": "Serie A", "start_year": 2010, "end_year": 2015}
        ],
    )
    candidate.transition_to(CandidateState.FETCHED)
    candidate.transition_to(CandidateState.NORMALIZED)

    validate_candidate(candidate)

    assert candidate.status == CandidateState.REVIEW_REQUIRED
    findings = [CandidateFinding.from_dict(d) for d in candidate.metadata["validation_findings"]]
    assert any(f.code == FindingCode.CAREER_TOO_SHORT for f in findings)


def test_single_team_with_one_club_flag_is_valid():
    candidate = CandidatePlayer(
        candidate_id="cand_one_club_totti",
        source="wikipedia",
        source_id="Francesco_Totti",
        full_name="Francesco Totti",
        nationality="Italia",
        position="Attaccante",
        birth_year=1976,
        career=[
            {"team": "Roma", "country": "Italia", "league": "Serie A", "start_year": 1992, "end_year": 2017}
        ],
        metadata={"one_club_career": True},
    )
    candidate.transition_to(CandidateState.FETCHED)
    candidate.transition_to(CandidateState.NORMALIZED)

    validate_candidate(candidate, current_year_provider=lambda: 2026)

    assert candidate.status == CandidateState.VALIDATED
    assert candidate.validation_errors == []


def test_duplicate_stop_requires_review():
    candidate = CandidatePlayer(
        candidate_id="cand_duplicate_stop",
        source="wikipedia",
        source_id="Dup_Stop",
        full_name="Dup Stop",
        nationality="Italia",
        position="Centrocampista",
        career=[
            {"team": "Juventus", "country": "Italia", "league": "Serie A", "start_year": 2015, "end_year": 2018},
            {"team": "Juventus", "country": "Italia", "league": "Serie A", "start_year": 2015, "end_year": 2018},
        ],
    )
    candidate.transition_to(CandidateState.FETCHED)
    candidate.transition_to(CandidateState.NORMALIZED)

    validate_candidate(candidate)

    assert candidate.status == CandidateState.REVIEW_REQUIRED
    findings = [CandidateFinding.from_dict(d) for d in candidate.metadata["validation_findings"]]
    assert any(f.code == FindingCode.CAREER_DUPLICATE_STOP for f in findings)


def test_same_club_in_distinct_legitimate_periods_is_valid():
    """Returns to a previous club in separated years (e.g. Lukaku or Pogba) is valid."""
    candidate = CandidatePlayer(
        candidate_id="cand_return_club",
        source="wikipedia",
        source_id="Return_Player",
        full_name="Return Player",
        nationality="Belgio",
        position="Attaccante",
        birth_year=1993,
        career=[
            {"team": "Chelsea", "country": "Inghilterra", "league": "Premier League", "start_year": 2011, "end_year": 2014},
            {"team": "Everton", "country": "Inghilterra", "league": "Premier League", "start_year": 2014, "end_year": 2017},
            {"team": "Chelsea", "country": "Inghilterra", "league": "Premier League", "start_year": 2021, "end_year": 2022},
        ],
    )
    candidate.transition_to(CandidateState.FETCHED)
    candidate.transition_to(CandidateState.NORMALIZED)

    validate_candidate(candidate, current_year_provider=lambda: 2026)

    assert candidate.status == CandidateState.VALIDATED
    assert candidate.validation_errors == []


def test_invalid_start_end_range():
    # 1. end_year < start_year
    cand1 = CandidatePlayer(
        candidate_id="cand_invalid_years",
        source="wikipedia",
        source_id="Inv_Years",
        full_name="Inv Years",
        nationality="Spagna",
        career=[
            {"team": "Valencia", "country": "Spagna", "league": "La Liga", "start_year": 2015, "end_year": 2010},
            {"team": "Villarreal", "country": "Spagna", "league": "La Liga", "start_year": 2016, "end_year": 2018},
        ],
    )
    cand1.transition_to(CandidateState.FETCHED)
    cand1.transition_to(CandidateState.NORMALIZED)
    validate_candidate(cand1)
    assert cand1.status == CandidateState.REVIEW_REQUIRED
    findings1 = [CandidateFinding.from_dict(d) for d in cand1.metadata["validation_findings"]]
    assert any(f.code == FindingCode.CAREER_INVALID_RANGE for f in findings1)

    # 2. debut before age 14
    cand2 = CandidatePlayer(
        candidate_id="cand_child_debut",
        source="wikipedia",
        source_id="Child_Debut",
        full_name="Child Debut",
        nationality="Spagna",
        birth_year=2000,
        career=[
            {"team": "Betis", "country": "Spagna", "league": "La Liga", "start_year": 2010, "end_year": 2015},
            {"team": "Sevilla", "country": "Spagna", "league": "La Liga", "start_year": 2015, "end_year": 2020},
        ],
    )
    cand2.transition_to(CandidateState.FETCHED)
    cand2.transition_to(CandidateState.NORMALIZED)
    validate_candidate(cand2)
    assert cand2.status == CandidateState.REVIEW_REQUIRED


def test_future_year_detection_with_injected_provider():
    candidate = CandidatePlayer(
        candidate_id="cand_future_year",
        source="wikipedia",
        source_id="Future_Year",
        full_name="Future Year",
        nationality="Germania",
        career=[
            {"team": "Dortmund", "country": "Germania", "league": "Bundesliga", "start_year": 2020, "end_year": 2035},
            {"team": "Bayern", "country": "Germania", "league": "Bundesliga", "start_year": 2035, "end_year": 2038},
        ],
    )
    candidate.transition_to(CandidateState.FETCHED)
    candidate.transition_to(CandidateState.NORMALIZED)

    # Injected current year = 2026
    validate_candidate(candidate, current_year_provider=lambda: 2026)

    assert candidate.status == CandidateState.REVIEW_REQUIRED
    findings = [CandidateFinding.from_dict(d) for d in candidate.metadata["validation_findings"]]
    assert any(f.code == FindingCode.CAREER_FUTURE_YEAR for f in findings)


def test_ongoing_career_valid_at_tail_invalid_in_middle():
    # Valid ongoing career (None at last stop)
    cand_tail = CandidatePlayer(
        candidate_id="cand_ongoing_tail",
        source="wikipedia",
        source_id="Tail_Ongoing",
        full_name="Tail Ongoing",
        nationality="Italia",
        career=[
            {"team": "Atalanta", "country": "Italia", "league": "Serie A", "start_year": 2018, "end_year": 2022},
            {"team": "Lazio", "country": "Italia", "league": "Serie A", "start_year": 2022, "end_year": None},
        ],
    )
    cand_tail.transition_to(CandidateState.FETCHED)
    cand_tail.transition_to(CandidateState.NORMALIZED)
    validate_candidate(cand_tail, current_year_provider=lambda: 2026)
    assert cand_tail.status == CandidateState.VALIDATED

    # Invalid ongoing career (None in middle with later stops starting after)
    cand_mid = CandidatePlayer(
        candidate_id="cand_ongoing_mid",
        source="wikipedia",
        source_id="Mid_Ongoing",
        full_name="Mid Ongoing",
        nationality="Italia",
        career=[
            {"team": "Atalanta", "country": "Italia", "league": "Serie A", "start_year": 2018, "end_year": None},
            {"team": "Lazio", "country": "Italia", "league": "Serie A", "start_year": 2022, "end_year": 2024},
        ],
    )
    cand_mid.transition_to(CandidateState.FETCHED)
    cand_mid.transition_to(CandidateState.NORMALIZED)
    validate_candidate(cand_mid, current_year_provider=lambda: 2026)
    assert cand_mid.status == CandidateState.REVIEW_REQUIRED


def test_legitimate_same_year_transfer_is_valid():
    candidate = CandidatePlayer(
        candidate_id="cand_same_year_transfer",
        source="wikipedia",
        source_id="Same_Year",
        full_name="Same Year",
        nationality="Italia",
        career=[
            {"team": "Sampdoria", "country": "Italia", "league": "Serie A", "start_year": 2015, "end_year": 2018},
            {"team": "Torino", "country": "Italia", "league": "Serie A", "start_year": 2018, "end_year": 2021},
        ],
    )
    candidate.transition_to(CandidateState.FETCHED)
    candidate.transition_to(CandidateState.NORMALIZED)
    validate_candidate(candidate, current_year_provider=lambda: 2026)
    assert candidate.status == CandidateState.VALIDATED


def test_legitimate_loan_overlap_is_valid():
    """Loan covered by parent contract is valid."""
    candidate = CandidatePlayer(
        candidate_id="cand_valid_loan",
        source="wikipedia",
        source_id="Loan_Player",
        full_name="Loan Player",
        nationality="Italia",
        career=[
            {"team": "Inter", "country": "Italia", "league": "Serie A", "start_year": 2015, "end_year": 2020},
            {"team": "Chievo", "country": "Italia", "league": "Serie A", "start_year": 2016, "end_year": 2017, "loan": True},
            {"team": "Monza", "country": "Italia", "league": "Serie A", "start_year": 2020, "end_year": 2023},
        ],
    )
    candidate.transition_to(CandidateState.FETCHED)
    candidate.transition_to(CandidateState.NORMALIZED)
    validate_candidate(candidate, current_year_provider=lambda: 2026)
    assert candidate.status == CandidateState.VALIDATED


def test_suspicious_multi_year_permanent_overlap_requires_review():
    """Two permanent contracts overlapping by multiple years is impossible."""
    candidate = CandidatePlayer(
        candidate_id="cand_suspicious_overlap",
        source="wikipedia",
        source_id="Overlap_Player",
        full_name="Overlap Player",
        nationality="Francia",
        career=[
            {"team": "Lyon", "country": "Francia", "league": "Ligue 1", "start_year": 2010, "end_year": 2016},
            {"team": "Marseille", "country": "Francia", "league": "Ligue 1", "start_year": 2012, "end_year": 2018},
        ],
    )
    candidate.transition_to(CandidateState.FETCHED)
    candidate.transition_to(CandidateState.NORMALIZED)
    validate_candidate(candidate, current_year_provider=lambda: 2026)

    assert candidate.status == CandidateState.REVIEW_REQUIRED
    findings = [CandidateFinding.from_dict(d) for d in candidate.metadata["validation_findings"]]
    assert any(f.code == FindingCode.CAREER_OVERLAP for f in findings)


def test_missing_country_and_league_require_review():
    candidate = CandidatePlayer(
        candidate_id="cand_missing_data",
        source="wikipedia",
        source_id="Missing_Data",
        full_name="Missing Data",
        nationality="Italia",
        career=[
            {"team": "UnknownClub", "country": None, "league": None, "start_year": 2015, "end_year": 2018},
            {"team": "Milan", "country": "Italia", "league": "Serie A", "start_year": 2018, "end_year": 2021},
        ],
    )
    candidate.transition_to(CandidateState.FETCHED)
    candidate.transition_to(CandidateState.NORMALIZED)
    validate_candidate(candidate)

    assert candidate.status == CandidateState.REVIEW_REQUIRED
    findings = [CandidateFinding.from_dict(d) for d in candidate.metadata["validation_findings"]]
    assert any(f.code == FindingCode.CLUB_MISSING_COUNTRY for f in findings)
    assert any(f.code == FindingCode.CLUB_MISSING_LEAGUE for f in findings)


def test_malformed_player_and_club_names():
    # 1. Player name is raw Wikidata QID
    cand1 = CandidatePlayer(
        candidate_id="cand_qid_player",
        source="wikidata",
        source_id="Q9999",
        full_name="Q9999",
        nationality="Italia",
        career=[
            {"team": "Roma", "country": "Italia", "league": "Serie A", "start_year": 2015, "end_year": 2018},
            {"team": "Lazio", "country": "Italia", "league": "Serie A", "start_year": 2018, "end_year": 2021},
        ],
    )
    cand1.transition_to(CandidateState.FETCHED)
    cand1.transition_to(CandidateState.NORMALIZED)
    validate_candidate(cand1)
    assert cand1.status == CandidateState.REVIEW_REQUIRED
    findings1 = [CandidateFinding.from_dict(d) for d in cand1.metadata["validation_findings"]]
    assert any(f.code == FindingCode.PLAYER_NAME_MALFORMED for f in findings1)

    # 2. Club name is raw Wikidata QID
    cand2 = CandidatePlayer(
        candidate_id="cand_qid_club",
        source="wikidata",
        source_id="Player_QID_Club",
        full_name="Good Player",
        nationality="Italia",
        career=[
            {"team": "Q1853", "country": "Italia", "league": "Serie A", "start_year": 2015, "end_year": 2018},
            {"team": "Lazio", "country": "Italia", "league": "Serie A", "start_year": 2018, "end_year": 2021},
        ],
    )
    cand2.transition_to(CandidateState.FETCHED)
    cand2.transition_to(CandidateState.NORMALIZED)
    validate_candidate(cand2)
    assert cand2.status == CandidateState.REVIEW_REQUIRED
    findings2 = [CandidateFinding.from_dict(d) for d in cand2.metadata["validation_findings"]]
    assert any(f.code == FindingCode.CLUB_UNRESOLVED_QID for f in findings2)


def test_ambiguous_alias_with_existing_production_player():
    """An alias that collides with an existing production player requires review."""
    candidate = CandidatePlayer(
        candidate_id="cand_colliding_alias",
        source="wikipedia",
        source_id="Different_Messi",
        full_name="Other Guy",
        nationality="Spagna",
        aliases=["lionel messi"],  # Belongs to production player 'messi'
        career=[
            {"team": "Sevilla", "country": "Spagna", "league": "La Liga", "start_year": 2015, "end_year": 2018},
            {"team": "Betis", "country": "Spagna", "league": "La Liga", "start_year": 2018, "end_year": 2021},
        ],
    )
    candidate.transition_to(CandidateState.FETCHED)
    candidate.transition_to(CandidateState.NORMALIZED)
    validate_candidate(candidate)

    assert candidate.status == CandidateState.REVIEW_REQUIRED
    findings = [CandidateFinding.from_dict(d) for d in candidate.metadata["validation_findings"]]
    assert any(f.code == FindingCode.PLAYER_ALIAS_AMBIGUOUS for f in findings)


def test_structured_finding_serialization():
    finding = CandidateFinding(
        code=FindingCode.CAREER_DUPLICATE_STOP,
        severity=FindingSeverity.ERROR,
        message="Tappa duplicata",
        field_path="career[1]",
        input_value={"team": "Inter"},
        context={"index": 1},
        requires_review=True,
    )
    serialized = finding.to_dict()
    restored = CandidateFinding.from_dict(serialized)

    assert restored.code == finding.code
    assert restored.severity == finding.severity
    assert restored.message == finding.message
    assert restored.field_path == finding.field_path
    assert restored.input_value == finding.input_value
    assert restored.context == finding.context
    assert restored.requires_review is True


def test_end_to_end_process_candidate_pipeline():
    """Full lifecycle execution: FETCHED -> NORMALIZED -> VALIDATED."""
    candidate = CandidatePlayer(
        candidate_id="cand_e2e_totti",
        source="wikipedia",
        source_id="Francesco_Totti",
        full_name="[[Francesco Totti]]",
        nationality="ITA",
        position="forward",
        aliases=["Er Pupone"],
        career=[
            {"team": "roma", "start_year": "1992", "end_year": "2017"}
        ],
        metadata={"one_club_career": True},
    )
    candidate.transition_to(CandidateState.FETCHED)

    processed = process_candidate(candidate, current_year_provider=lambda: 2026)

    assert processed.status == CandidateState.VALIDATED
    assert processed.full_name == "Francesco Totti"
    assert processed.nationality == "Italia"
    assert processed.position == "Attaccante"
    assert processed.career[0]["team"] == "Roma"
    assert processed.career[0]["country"] == "Italia"
    assert processed.career[0]["league"] == "Serie A"
    assert processed.career[0]["start_year"] == 1992
    assert processed.career[0]["end_year"] == 2017


def test_production_dataset_safety_invariant():
    """CRITICAL SAFETY TEST: Normalization and validation must NEVER modify data/players.json."""
    initial_hash = _get_players_json_hash()

    # Create various dirty, clean, and corrupt candidates
    candidates = [
        CandidatePlayer(
            candidate_id="cand_safe_1",
            source="wikipedia",
            source_id="Clean",
            full_name="Clean Player",
            nationality="Italia",
            career=[
                {"team": "Milan", "country": "Italia", "league": "Serie A", "start_year": 2010, "end_year": 2015},
                {"team": "Juventus", "country": "Italia", "league": "Serie A", "start_year": 2015, "end_year": 2020},
            ],
        ),
        CandidatePlayer(
            candidate_id="cand_safe_2",
            source="wikidata",
            source_id="Corrupt",
            full_name="Q9999",
            nationality="XYZ",
            career=[],
        ),
    ]

    for cand in candidates:
        cand.transition_to(CandidateState.FETCHED)
        process_candidate(cand)

    final_hash = _get_players_json_hash()
    assert initial_hash == final_hash, "data/players.json was modified! Safety invariant violated!"
