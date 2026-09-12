"""Unit tests for Candidate Player normalization service (#26)."""
import copy

from services.candidate_finding import CandidateFinding, FindingCode, FindingSeverity
from services.candidate_normalization import (
    clean_text,
    normalize_aliases,
    normalize_candidate,
    normalize_club_name,
    normalize_country,
    normalize_league_name,
    normalize_position,
    parse_loan_flag,
    resolve_historical_league_with_temporal_evidence,
    strip_wiki_markup,
)
from services.candidate_player import CandidatePlayer, CandidateState


def test_strip_wiki_markup_and_clean_text():
    # Links with label
    assert strip_wiki_markup("[[A.C. Milan|Milan]]") == "Milan"
    # Simple links
    assert strip_wiki_markup("[[Real Madrid]]") == "Real Madrid"
    # Templates
    assert strip_wiki_markup("{{Bio|...}} Francesco Totti") == "Francesco Totti"
    # Whitespace and typography
    assert clean_text("  Zinédine   Zidane  ") == "Zinédine Zidane"
    assert clean_text("N’Golo Kante’") == "N'Golo Kante'"
    assert clean_text("Paris – Saint-Germain") == "Paris - Saint-Germain"


def test_normalize_country():
    # IOC / ISO codes
    assert normalize_country("ITA") == "Italia"
    assert normalize_country("FRA") == "Francia"
    assert normalize_country("ESP") == "Spagna"
    assert normalize_country("DEU") == "Germania"
    assert normalize_country("ARG") == "Argentina"
    assert normalize_country("BRA") == "Brasile"
    assert normalize_country("USA") == "USA"
    # Adjectives
    assert normalize_country("italiano") == "Italia"
    assert normalize_country("french") == "Francia"
    assert normalize_country("spagnolo") == "Spagna"
    assert normalize_country("argentino") == "Argentina"
    # Fallback to cleaned
    assert normalize_country("San Marino") == "San Marino"
    assert normalize_country(None) is None


def test_normalize_position():
    assert normalize_position("Goalkeeper") == "Portiere"
    assert normalize_position("GK") == "Portiere"
    assert normalize_position("difensore") == "Difensore"
    assert normalize_position("Defender") == "Difensore"
    assert normalize_position("Midfielder") == "Centrocampista"
    assert normalize_position("FW") == "Attaccante"
    assert normalize_position("Striker") == "Attaccante"
    assert normalize_position("Ala") == "Centrocampista"
    assert normalize_position(None) is None


def test_normalize_aliases():
    raw = ["Messi", "lionel messi", "Messi", " LEO MESSI  ", ""]
    norm = normalize_aliases(raw, full_name="Lionel Andrés Messi")
    assert norm == ["messi", "lionel messi", "leo messi", "lionel andrés messi"]


def test_normalize_known_club_aliases():
    # Known aliases map deterministically
    team, findings = normalize_club_name("PSG")
    assert team == "Paris Saint-Germain"
    assert any(f.code == FindingCode.CLUB_NORMALIZED for f in findings)

    team, _ = normalize_club_name("Man Utd")
    assert team == "Manchester United"

    team, _ = normalize_club_name("Spurs")
    assert team == "Tottenham"

    team, _ = normalize_club_name("Barcellona")
    assert team == "Barcelona"

    team, _ = normalize_club_name("Leeds")
    assert team == "Leeds United"

    team, _ = normalize_club_name("Schalke")
    assert team == "Schalke 04"


def test_normalize_unfamiliar_club_no_fuzzy_guess():
    # An unfamiliar club must NOT be guessed as a famous club
    team, findings = normalize_club_name("Real Frontera FC")
    assert team == "Real Frontera FC"
    # No false normalization finding
    assert not any(f.code == FindingCode.CLUB_NORMALIZED for f in findings)

    team2, _ = normalize_club_name("Barcellona Pozzo di Gotto")
    assert team2 == "Barcellona Pozzo di Gotto"


def test_normalize_club_unresolved_qid():
    team, findings = normalize_club_name("Q1853")
    assert team == "Q1853"
    assert any(f.code == FindingCode.CLUB_UNRESOLVED_QID and f.severity == FindingSeverity.ERROR for f in findings)


def test_normalize_ambiguous_club_aliases_never_silently_resolved():
    """Ambiguous club aliases (Sporting, Inter, Real, Racing, etc.) must NEVER be silently resolved."""
    ambiguous_examples = ["Sporting", "Inter", "Real", "Racing", "Nacional", "Dynamo", "Dinamo", "United", "City"]
    for raw_name in ambiguous_examples:
        team, findings = normalize_club_name(raw_name)
        # Preserves cleaned original value without mapping to a canonical club
        assert team == raw_name
        # Emits CLUB_AMBIGUOUS_ALIAS
        assert any(f.code == FindingCode.CLUB_AMBIGUOUS_ALIAS for f in findings), f"Expected CLUB_AMBIGUOUS_ALIAS for {raw_name}"
        # Does NOT emit CLUB_NORMALIZED
        assert not any(f.code == FindingCode.CLUB_NORMALIZED for f in findings), f"Unexpected CLUB_NORMALIZED for {raw_name}"


def test_parse_loan_flag_safe():
    """Deterministic parsing for booleans, ints, and string representations."""
    # Booleans
    assert parse_loan_flag(True) is True
    assert parse_loan_flag(False) is False

    # Integers
    assert parse_loan_flag(1) is True
    assert parse_loan_flag(0) is False

    # Strings: true / 1
    assert parse_loan_flag("true") is True
    assert parse_loan_flag("True") is True
    assert parse_loan_flag(" TRUE ") is True
    assert parse_loan_flag("1") is True

    # Strings: false / 0
    assert parse_loan_flag("false") is False
    assert parse_loan_flag("False") is False
    assert parse_loan_flag(" FALSE ") is False
    assert parse_loan_flag("0") is False

    # Unknown or arbitrary values must NOT silently become True
    assert parse_loan_flag("si") is None
    assert parse_loan_flag("yes") is None
    assert parse_loan_flag("arbitrary") is None
    assert parse_loan_flag(2) is None
    assert parse_loan_flag(-1) is None
    assert parse_loan_flag(None) is False


def test_career_stop_loan_string_normalization():
    """String 'false' and '0' in career stops must normalize to boolean False, not True."""
    cand = CandidatePlayer(
        candidate_id="cand_loan_strings",
        source="wikipedia",
        source_id="Loan_Test",
        full_name="Loan Test",
        nationality="ITA",
        career=[
            {"team": "Milan", "country": "Italia", "league": "Serie A", "start_year": 2010, "end_year": 2012, "loan": "false"},
            {"team": "Monza", "country": "Italia", "league": "Serie A", "start_year": 2012, "end_year": 2014, "loan": "0"},
            {"team": "Napoli", "country": "Italia", "league": "Serie A", "start_year": 2014, "end_year": 2016, "loan": "true"},
            {"team": "Genoa", "country": "Italia", "league": "Serie A", "start_year": 2016, "end_year": 2018, "loan": "1"},
        ],
    )
    cand.transition_to(CandidateState.FETCHED)
    normalize_candidate(cand)

    assert cand.career[0]["loan"] is False
    assert cand.career[1]["loan"] is False
    assert cand.career[2]["loan"] is True
    assert cand.career[3]["loan"] is True


def test_known_club_missing_league_remains_missing():
    """A known club with missing league must keep league as missing (not guessed)."""
    candidate = CandidatePlayer(
        candidate_id="cand_known_club_league",
        source="wikipedia",
        source_id="Roma_Player",
        full_name="Roma Player",
        nationality="ITA",
        career=[
            {"team": "Roma", "start_year": 2010, "end_year": 2015}
        ],
    )
    candidate.transition_to(CandidateState.FETCHED)
    normalize_candidate(candidate)

    stop = candidate.career[0]
    assert stop["team"] == "Roma"
    # Country is inferred because Roma is unambiguous
    assert stop["country"] == "Italia"
    # League is NOT inferred and remains missing
    assert stop.get("league") is None
    # Explicit extension point is present and returns None until season-aware resolution is implemented
    assert resolve_historical_league_with_temporal_evidence("Roma", "Italia", 2010, 2015) is None


def test_normalize_league_name():
    assert normalize_league_name("fussball bundesliga") == "Bundesliga"
    assert normalize_league_name("primera division", "Spagna") == "La Liga"
    assert normalize_league_name("serie a", "Brasile") == "Brasileirao"
    assert normalize_league_name("super league", "Svizzera") == "Swiss Super League"


def test_normalize_candidate_full_lifecycle():
    candidate = CandidatePlayer(
        candidate_id="cand_test_totti",
        source="wikipedia",
        source_id="Francesco_Totti",
        full_name="[[Francesco Totti]]",
        nationality="ITA",
        position="forward",
        aliases=["Er Pupone", "TOTTI"],
        career=[
            {
                "team": "roma",
                "start_year": "1992",
                "end_year": "2017",
                "loan": "false",
                "apps": "619",
                "goals": "250",
            }
        ],
    )
    candidate.transition_to(CandidateState.FETCHED)

    norm_cand = normalize_candidate(candidate)

    assert norm_cand.status == CandidateState.NORMALIZED
    assert norm_cand.full_name == "Francesco Totti"
    assert norm_cand.nationality == "Italia"
    assert norm_cand.position == "Attaccante"
    assert "er pupone" in norm_cand.aliases
    assert "totti" in norm_cand.aliases
    assert "francesco totti" in norm_cand.aliases

    stop = norm_cand.career[0]
    assert stop["team"] == "Roma"
    assert stop["country"] == "Italia"
    # Historical league is preserved missing without temporal evidence
    assert stop.get("league") is None
    assert stop["start_year"] == 1992
    assert stop["end_year"] == 2017
    # String "false" deterministically parsed to boolean False
    assert stop["loan"] is False
    assert stop["apps"] == 619
    assert stop["goals"] == 250

    # Normalization findings in metadata
    norm_findings = norm_cand.metadata.get("normalization_findings", [])
    assert len(norm_findings) > 0


def test_normalization_career_ordering():
    # Career with loan in wrong order
    candidate = CandidatePlayer(
        candidate_id="cand_biabiany",
        source="wikipedia",
        source_id="Jonathan_Biabiany",
        full_name="Jonathan Biabiany",
        nationality="Francia",
        career=[
            {"team": "Chievo", "country": "Italia", "league": "Serie A", "start_year": 2007, "end_year": 2008, "loan": True},
            {"team": "Inter", "country": "Italia", "league": "Serie A", "start_year": 2007, "end_year": 2010},
        ],
    )
    candidate.transition_to(CandidateState.FETCHED)

    normalize_candidate(candidate)

    assert candidate.status == CandidateState.NORMALIZED
    # Canonical order: Inter first, then Chievo loan
    assert candidate.career[0]["team"] == "Inter"
    assert candidate.career[1]["team"] == "Chievo"


def test_normalization_idempotency():
    candidate = CandidatePlayer(
        candidate_id="cand_messi_idempotent",
        source="wikipedia",
        source_id="Lionel_Messi",
        full_name="Lionel Messi",
        nationality="ARG",
        position="forward",
        aliases=["messi", "leo messi"],
        career=[
            {"team": "barcelona", "start_year": "2004", "end_year": "2021", "loan": False},
            {"team": "psg", "country": "Francia", "league": "Ligue 1", "start_year": "2021", "end_year": "2023"},
        ],
    )
    candidate.transition_to(CandidateState.FETCHED)

    # First normalization run
    normalize_candidate(candidate)
    assert candidate.status == CandidateState.NORMALIZED
    snapshot_1 = copy.deepcopy(candidate.to_dict())

    # Second normalization run on the same candidate
    normalize_candidate(candidate)
    snapshot_2 = copy.deepcopy(candidate.to_dict())

    # State, career, and warnings should be completely stable
    assert snapshot_1["status"] == snapshot_2["status"]
    assert snapshot_1["full_name"] == snapshot_2["full_name"]
    assert snapshot_1["nationality"] == snapshot_2["nationality"]
    assert snapshot_1["position"] == snapshot_2["position"]
    assert snapshot_1["career"] == snapshot_2["career"]
    assert snapshot_1["aliases"] == snapshot_2["aliases"]
    assert snapshot_1["validation_warnings"] == snapshot_2["validation_warnings"]
    assert snapshot_1["metadata"]["normalization_findings"] == snapshot_2["metadata"]["normalization_findings"]
    # State history should not have an additional redundant transition
    assert len(snapshot_1["state_history"]) == len(snapshot_2["state_history"])


def test_wikipedia_shaped_candidate():
    """Candidate populated from Wikipedia raw adapter wikitext."""
    candidate = CandidatePlayer(
        candidate_id="cand_wiki_del_piero",
        source="wikipedia",
        source_id="Alessandro_Del_Piero",
        full_name="[[Alessandro Del Piero]]",
        nationality="italiano",
        position="Attaccante",
        aliases=["Pinturicchio", "Del Piero"],
        career=[
            {"team": "Padova", "country": "Italia", "league": "Serie B", "start_year": 1991, "end_year": 1993},
            {"team": "Juventus", "country": "Italia", "league": "Serie A", "start_year": 1993, "end_year": 2012},
            {"team": "Sydney FC", "country": "Australia", "league": "A-League", "start_year": 2012, "end_year": 2014},
        ],
    )
    candidate.transition_to(CandidateState.FETCHED)
    normalize_candidate(candidate)

    assert candidate.status == CandidateState.NORMALIZED
    assert candidate.full_name == "Alessandro Del Piero"
    assert candidate.nationality == "Italia"
    assert "del piero" in candidate.aliases


def test_wikidata_shaped_candidate_with_qids():
    """Candidate populated from Wikidata with unresolved QIDs."""
    candidate = CandidatePlayer(
        candidate_id="cand_wd_unresolved",
        source="wikidata",
        source_id="Q12345",
        full_name="Q12345",
        nationality="ITA",
        position="MF",
        career=[
            {"team": "Q1853", "start_year": 2015, "end_year": 2020},
        ],
    )
    candidate.transition_to(CandidateState.FETCHED)
    normalize_candidate(candidate)

    # QIDs must NOT be pretended to be resolved club names
    assert candidate.status == CandidateState.NORMALIZED
    assert candidate.full_name == "Q12345"
    assert candidate.career[0]["team"] == "Q1853"
    findings = [CandidateFinding.from_dict(d) for d in candidate.metadata["normalization_findings"]]
    assert any(f.code == FindingCode.PLAYER_NAME_MALFORMED for f in findings)
    assert any(f.code == FindingCode.CLUB_UNRESOLVED_QID for f in findings)
