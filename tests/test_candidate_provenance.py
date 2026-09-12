"""Deterministic unit tests for Candidate Player Provenance (#27).

Covers:
- Provenance record serialization & deserialization;
- Candidate Player lifecycle round-trip persistence;
- Wikipedia and Wikidata observations;
- Multiple source observations for the same field;
- Conflicting values preserved with conflict flags;
- Consensus/identical values from multiple sources;
- Retrieval timestamp preservation;
- Explainable confidence levels and scores;
- Raw value -> normalized value lineage and transformations;
- Career stop field provenance;
- Career reordering immunity via stable _stop_id;
- Missing field provenance behavior;
- Normalization and validation integration;
- Non-ASCII and Unicode characters;
- Strict isolation: zero mutations to data/players.json;
- Backward compatibility with pre-existing candidates lacking provenance.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from services.adapters.base import AdapterResult, CareerEntry
from services.adapters.candidate_integration import (
    merge_adapter_result,
    populate_candidate_from_result,
)
from services.candidate_finding import FindingCode, FindingSeverity
from services.candidate_normalization import normalize_candidate
from services.candidate_player import (
    CandidatePlayer,
    CandidateState,
)
from services.candidate_provenance import (
    CandidateProvenance,
    ConfidenceLevel,
    FieldProvenance,
    NormalizationRecord,
    SourceObservation,
    score_for_confidence_level,
)
from services.candidate_validation import validate_candidate_data
from services.repos.candidates import (
    FileCandidatePlayerRepository,
    InMemoryCandidatePlayerRepository,
)

_PLAYERS_JSON = Path(__file__).resolve().parents[1] / "data" / "players.json"


def _hash_file(path: Path) -> str:
    """Calculates the SHA-256 digest of a file to verify zero modifications."""
    if not path.is_file():
        return ""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


# ---------------------------------------------------------------------------
# 1. Domain Models, Serialization, and Confidence Semantics
# ---------------------------------------------------------------------------


def test_confidence_level_semantics():
    """Verify confidence level mapping to explainable deterministic scores."""
    assert score_for_confidence_level(ConfidenceLevel.EXACT_STRUCTURED) == 1.0
    assert score_for_confidence_level(ConfidenceLevel.PARSED_CLAIM) == 0.9
    assert score_for_confidence_level(ConfidenceLevel.PARSER_DERIVED) == 0.75
    assert score_for_confidence_level(ConfidenceLevel.INFERRED_NORMALIZED) == 0.6
    assert score_for_confidence_level(ConfidenceLevel.AMBIGUOUS) == 0.3
    # String input support
    assert score_for_confidence_level("exact_structured") == 1.0


def test_source_observation_serialization():
    """Verify SourceObservation serialization and deserialization."""
    fixed_time = "2026-09-12T01:30:00Z"
    obs = SourceObservation(
        source="wikipedia",
        source_id="Lionel_Messi",
        retrieved_at=fixed_time,
        confidence=0.9,
        confidence_level=ConfidenceLevel.PARSED_CLAIM.value,
        raw_value="Lionel Messi",
        normalized_value="Lionel Messi",
        source_url="https://it.wikipedia.org/wiki/Lionel_Messi",
        metadata={"revision_id": 998877},
        adapter_version="wikipedia_v1",
    )

    data = obs.to_dict()
    assert data["source"] == "wikipedia"
    assert data["source_id"] == "Lionel_Messi"
    assert data["retrieved_at"] == fixed_time
    assert data["confidence"] == 0.9
    assert data["confidence_level"] == "parsed_claim"
    assert data["raw_value"] == "Lionel Messi"
    assert data["source_url"] == "https://it.wikipedia.org/wiki/Lionel_Messi"
    assert data["metadata"]["revision_id"] == 998877
    assert data["adapter_version"] == "wikipedia_v1"

    restored = SourceObservation.from_dict(data)
    assert restored.source == obs.source
    assert restored.source_id == obs.source_id
    assert restored.retrieved_at == obs.retrieved_at
    assert restored.confidence == obs.confidence
    assert restored.confidence_level == obs.confidence_level
    assert restored.raw_value == obs.raw_value
    assert restored.source_url == obs.source_url
    assert restored.metadata == obs.metadata
    assert restored.adapter_version == obs.adapter_version


def test_normalization_record_serialization():
    """Verify NormalizationRecord serialization and round-trip."""
    fixed_time = "2026-09-12T01:35:00Z"
    rec = NormalizationRecord(
        raw_value="PSG",
        normalized_value="Paris Saint-Germain",
        finding_code=FindingCode.CLUB_NORMALIZED,
        rule="CONSOLIDATED_CLUB_ALIASES",
        timestamp=fixed_time,
    )
    data = rec.to_dict()
    assert data["raw_value"] == "PSG"
    assert data["normalized_value"] == "Paris Saint-Germain"
    assert data["finding_code"] == FindingCode.CLUB_NORMALIZED
    assert data["rule"] == "CONSOLIDATED_CLUB_ALIASES"
    assert data["timestamp"] == fixed_time

    restored = NormalizationRecord.from_dict(data)
    assert restored.raw_value == rec.raw_value
    assert restored.normalized_value == rec.normalized_value
    assert restored.finding_code == rec.finding_code
    assert restored.rule == rec.rule
    assert restored.timestamp == rec.timestamp


def test_field_provenance_conflict_and_support_resolution():
    """Verify FieldProvenance conflict detection and supporting source extraction."""
    fp = FieldProvenance(field_path="career[0].team", stop_id="stop_1", current_value="Inter")

    # Wikipedia observation: "Inter Milan"
    obs_wiki = SourceObservation(
        source="wikipedia",
        source_id="Francesco_Totti",
        retrieved_at="2026-09-12T01:00:00Z",
        confidence=0.9,
        confidence_level=ConfidenceLevel.PARSED_CLAIM.value,
        raw_value="Inter Milan",
        normalized_value="Inter",
    )
    fp.add_observation(obs_wiki)

    assert fp.has_multiple_sources() is False
    assert fp.has_conflict() is False
    assert fp.supporting_sources("Inter") == ["wikipedia"]

    # Wikidata observation agreeing on normalized value "Inter"
    obs_wd = SourceObservation(
        source="wikidata",
        source_id="Q1853",
        retrieved_at="2026-09-12T01:05:00Z",
        confidence=1.0,
        confidence_level=ConfidenceLevel.EXACT_STRUCTURED.value,
        raw_value="Inter",
        normalized_value="Inter",
    )
    fp.add_observation(obs_wd)

    assert fp.has_multiple_sources() is True
    # Discrepancy resolved through normalization: no conflict
    assert fp.has_conflict() is False
    assert set(fp.supporting_sources("Inter")) == {"wikipedia", "wikidata"}
    assert fp.conflicting_sources("Inter") == []

    # Third source providing conflicting value
    obs_dispute = SourceObservation(
        source="transfermarkt",
        source_id="player_99",
        retrieved_at="2026-09-12T01:10:00Z",
        confidence=0.8,
        confidence_level=ConfidenceLevel.PARSER_DERIVED.value,
        raw_value="AC Milan",
        normalized_value="AC Milan",
    )
    fp.add_observation(obs_dispute)

    assert fp.has_conflict() is True
    assert set(fp.supporting_sources("Inter")) == {"wikipedia", "wikidata"}
    assert fp.conflicting_sources("Inter") == ["transfermarkt"]


# ---------------------------------------------------------------------------
# 2. CandidatePlayer Integration and Repository Persistence Round-Trip
# ---------------------------------------------------------------------------


def test_candidate_player_backward_compatibility_empty_provenance():
    """Verify that candidates created without provenance deserialize cleanly with defaults."""
    legacy_data: dict[str, Any] = {
        "candidate_id": "cand_legacy_123",
        "source": "wikipedia",
        "source_id": "Legacy_Player",
        "status": "DISCOVERED",
        "full_name": "Legacy Player",
    }
    candidate = CandidatePlayer.from_dict(legacy_data)
    assert candidate.provenance is not None
    assert isinstance(candidate.provenance, CandidateProvenance)
    assert candidate.provenance.fields == {}
    assert candidate.provenance.has_conflicts() is False

    serialized = candidate.to_dict()
    assert "provenance" in serialized
    assert serialized["provenance"]["fields"] == {}


def test_candidate_persistence_roundtrip_in_memory():
    """Verify that provenance survives create -> save -> reload in InMemoryCandidatePlayerRepository."""
    repo = InMemoryCandidatePlayerRepository()
    cand = CandidatePlayer(
        candidate_id="cand_test_mem",
        source="wikipedia",
        source_id="Player_One",
        full_name="Player One",
    )
    cand.record_observation(
        field_path="full_name",
        source="wikipedia",
        source_id="Player_One",
        raw_value="Player One",
        confidence_level=ConfidenceLevel.PARSED_CLAIM,
    )
    cand.record_observation(
        field_path="nationality",
        source="wikidata",
        source_id="Q100",
        raw_value="Italia",
        confidence_level=ConfidenceLevel.EXACT_STRUCTURED,
    )

    repo.save(cand)
    loaded = repo.get_by_id("cand_test_mem")
    assert loaded is not None
    assert loaded.provenance is not None
    assert "full_name" in loaded.provenance.fields
    assert "nationality" in loaded.provenance.fields

    obs_name = loaded.provenance.get_source_observations("full_name")
    assert len(obs_name) == 1
    assert obs_name[0].source == "wikipedia"
    assert obs_name[0].raw_value == "Player One"
    assert obs_name[0].confidence == 0.9

    obs_nat = loaded.provenance.get_source_observations("nationality")
    assert len(obs_nat) == 1
    assert obs_nat[0].source == "wikidata"
    assert obs_nat[0].confidence == 1.0


def test_candidate_persistence_full_lifecycle_roundtrip_file(tmp_path: Path):
    """Verify complete lifecycle round-trip:
    create -> save -> reload -> normalize -> validate -> save -> reload.
    """
    repo = FileCandidatePlayerRepository(storage_dir=tmp_path)

    # 1. Create candidate and record adapter observations
    cand = CandidatePlayer(
        candidate_id="cand_test_file_cycle",
        source="wikipedia",
        source_id="Del_Piero",
        full_name="Alessandro Del Piero",
        nationality="Italia",
        position="Attaccante",
        birth_year=1974,
        career=[
            {"team": "Padova", "country": "Italia", "league": "Serie B", "start_year": 1991, "end_year": 1993, "_stop_id": "stop_padova"},
            {"team": "Juventus", "country": "Italia", "league": "Serie A", "start_year": 1993, "end_year": 2012, "_stop_id": "stop_juve"},
        ],
    )
    cand.transition_to(CandidateState.FETCHED)

    cand.record_observation("full_name", "wikipedia", "Del_Piero", "Alessandro Del Piero")
    cand.record_observation("career[0].team", "wikipedia", "Del_Piero", "Padova", stop_id="stop_padova")
    cand.record_observation("career[1].team", "wikipedia", "Del_Piero", "Juventus", stop_id="stop_juve")

    # 2. Save to filesystem
    repo.save(cand)

    # 3. Reload from filesystem
    loaded_1 = repo.get_by_id("cand_test_file_cycle")
    assert loaded_1 is not None
    assert loaded_1.provenance.get_provenance_for_path("career[0].team").stop_id == "stop_padova"

    # 4. Normalize
    normalize_candidate(loaded_1)
    assert loaded_1.status == CandidateState.NORMALIZED

    # 5. Validate
    findings = validate_candidate_data(loaded_1)
    assert not any(f.severity == FindingSeverity.ERROR for f in findings)
    loaded_1.transition_to(CandidateState.VALIDATED)

    # 6. Save again
    repo.save(loaded_1)

    # 7. Final reload
    loaded_2 = repo.get_by_id("cand_test_file_cycle")
    assert loaded_2 is not None
    assert loaded_2.status == CandidateState.VALIDATED
    assert loaded_2.provenance.get_provenance_for_path("full_name") is not None
    assert loaded_2.provenance.get_provenance_for_stop("stop_padova", "team") is not None


# ---------------------------------------------------------------------------
# 3. Multi-Source Integration & Adapter Boundary
# ---------------------------------------------------------------------------


def test_adapter_result_population_and_provenance():
    """Verify that populate_candidate_from_result establishes complete field-level provenance."""
    cand = CandidatePlayer(
        candidate_id="cand_totti",
        source="wikipedia",
        source_id="Francesco_Totti",
    )

    wiki_result = AdapterResult(
        source_name="wikipedia",
        source_id="Francesco_Totti",
        success=True,
        player_name="Francesco Totti",
        aliases=["er pupone"],
        birth_year=1976,
        nationality="Italia",
        position="Attaccante",
        career=[
            CareerEntry(
                team="Roma",
                country="Italia",
                league="Serie A",
                start_year=1992,
                end_year=2017,
                apps=619,
                goals=250,
            )
        ],
        source_metadata={
            "retrieved_at": "2026-09-12T02:00:00Z",
            "url": "https://it.wikipedia.org/wiki/Francesco_Totti",
        },
    )

    populate_candidate_from_result(cand, wiki_result)

    assert cand.status == CandidateState.FETCHED
    assert cand.full_name == "Francesco Totti"
    assert cand.birth_year == 1976
    assert cand.nationality == "Italia"

    # Check field provenance
    prov = cand.provenance
    assert "full_name" in prov.fields
    assert "birth_year" in prov.fields
    assert "nationality" in prov.fields
    assert "position" in prov.fields
    assert "aliases[0]" in prov.fields
    assert "career[0].team" in prov.fields
    assert "career[0].apps" in prov.fields

    team_prov = prov.get_provenance_for_path("career[0].team")
    assert team_prov is not None
    assert team_prov.current_value == "Roma"
    assert len(team_prov.observations) == 1
    assert team_prov.observations[0].source == "wikipedia"
    assert team_prov.observations[0].source_url == "https://it.wikipedia.org/wiki/Francesco_Totti"
    assert team_prov.observations[0].retrieved_at == "2026-09-12T02:00:00Z"
    assert team_prov.observations[0].confidence == 0.9
    assert team_prov.stop_id is not None


def test_multi_source_merge_agreement_and_conflicts():
    """Verify overlapping ingestion from Wikipedia and Wikidata:
    agreements produce consensus, conflicts preserve both observations.
    """
    cand = CandidatePlayer(
        candidate_id="cand_messi_multi",
        source="wikipedia",
        source_id="Lionel_Messi",
    )

    # 1. Wikipedia fetch
    wiki_result = AdapterResult(
        source_name="wikipedia",
        source_id="Lionel_Messi",
        success=True,
        player_name="Lionel Messi",
        birth_year=1987,
        nationality="Argentina",
        position="Attaccante",
        career=[
            CareerEntry(
                team="Barcellona",
                country="Spagna",
                league="La Liga",
                start_year=2004,
                end_year=2021,
                apps=520,
            ),
            CareerEntry(
                team="PSG",
                country="Francia",
                league="Ligue 1",
                start_year=2021,
                end_year=2023,
                apps=58,
            ),
        ],
        source_metadata={"retrieved_at": "2026-09-12T02:10:00Z", "url": "https://it.wikipedia.org/wiki/Lionel_Messi"},
    )
    populate_candidate_from_result(cand, wiki_result)

    # 2. Wikidata fetch
    wikidata_result = AdapterResult(
        source_name="wikidata",
        source_id="Q615",
        success=True,
        player_name="Lionel Messi",
        birth_year=1987,
        nationality="Argentina",
        position="Attaccante",
        career=[
            CareerEntry(
                team="FC Barcelona",
                country="Spagna",
                league="La Liga",
                start_year=2004,
                end_year=2021,
                apps=520,
            ),
            CareerEntry(
                team="Paris Saint-Germain FC",
                country="Francia",
                league="Ligue 1",
                start_year=2021,
                end_year=2023,
                apps=75,  # Conflicting apps count!
            ),
        ],
        source_metadata={"retrieved_at": "2026-09-12T02:15:00Z", "url": "https://www.wikidata.org/wiki/Q615"},
    )
    merge_adapter_result(cand, wikidata_result)

    prov = cand.provenance

    # Player name: consensus
    name_prov = prov.get_provenance_for_path("full_name")
    assert name_prov is not None
    assert name_prov.has_multiple_sources() is True
    assert name_prov.has_conflict() is False
    assert set(name_prov.supporting_sources()) == {"wikipedia", "wikidata"}

    # Birth year: consensus
    year_prov = prov.get_provenance_for_path("birth_year")
    assert year_prov is not None
    assert year_prov.has_conflict() is False
    assert set(year_prov.supporting_sources()) == {"wikipedia", "wikidata"}

    # Stop 1 apps: conflicting numbers (58 vs 75)
    apps_prov = prov.get_provenance_for_path("career[1].apps")
    assert apps_prov is not None
    assert apps_prov.has_multiple_sources() is True
    assert apps_prov.has_conflict() is True
    assert apps_prov.conflicting_sources(58) == ["wikidata"]
    assert apps_prov.supporting_sources(58) == ["wikipedia"]
    assert apps_prov.supporting_sources(75) == ["wikidata"]

    # Global conflict indicator
    assert prov.has_conflicts() is True
    conflicts = prov.get_conflicts()
    assert "career[1].apps" in conflicts


# ---------------------------------------------------------------------------
# 4. Normalization Lineage & Career Reordering Stability
# ---------------------------------------------------------------------------


def test_normalization_lineage_traceability():
    """Verify that normalize_candidate records transformations and finding codes into provenance."""
    cand = CandidatePlayer(
        candidate_id="cand_norm_trace",
        source="wikipedia",
        source_id="Test_Player",
        full_name="  test  player  ",
        nationality="italiano",
        position="attaccante",
        career=[
            {
                "team": "psg",
                "country": "",
                "league": "ligue 1",
                "start_year": 2020,
                "end_year": 2022,
                "_stop_id": "stop_psg",
            }
        ],
    )
    cand.transition_to(CandidateState.FETCHED)

    # Initial observation
    cand.record_observation("career[0].team", "wikipedia", "Test_Player", "psg", stop_id="stop_psg")
    cand.record_observation("nationality", "wikipedia", "Test_Player", "italiano")

    normalize_candidate(cand)

    assert cand.full_name == "test player"
    assert cand.nationality == "Italia"
    assert cand.career[0]["team"] == "Paris Saint-Germain"
    assert cand.career[0]["country"] == "Francia"  # Deduced from dataset

    prov = cand.provenance
    # Nationality lineage
    nat_prov = prov.get_provenance_for_path("nationality")
    assert nat_prov is not None
    assert nat_prov.normalized_value == "Italia"
    assert len(nat_prov.transformations) == 1
    assert nat_prov.transformations[0].raw_value == "italiano"
    assert nat_prov.transformations[0].normalized_value == "Italia"


    # Team lineage
    team_prov = prov.get_provenance_for_path("career[0].team")
    assert team_prov is not None
    assert team_prov.normalized_value == "Paris Saint-Germain"
    assert len(team_prov.transformations) >= 1
    tr = team_prov.transformations[0]
    assert tr.raw_value == "psg"
    assert tr.normalized_value == "Paris Saint-Germain"
    assert tr.finding_code == FindingCode.CLUB_NORMALIZED


def test_career_reordering_does_not_corrupt_provenance():
    """Verify that career reordering via order_career preserves stop provenance via _stop_id."""
    cand = CandidatePlayer(
        candidate_id="cand_reorder",
        source="wikipedia",
        source_id="Reordered_Player",
        full_name="Reordered Player",
        nationality="Italia",
        position="Attaccante",
        # Out-of-order career: later team first, earlier team second
        career=[
            {
                "team": "Juventus",
                "country": "Italia",
                "league": "Serie A",
                "start_year": 2010,
                "end_year": 2015,
                "apps": 150,
                "_stop_id": "stop_juve",
            },
            {
                "team": "Padova",
                "country": "Italia",
                "league": "Serie B",
                "start_year": 2005,
                "end_year": 2010,
                "apps": 80,
                "_stop_id": "stop_padova",
            },
        ],
    )
    cand.transition_to(CandidateState.FETCHED)

    # Initial observations with indices corresponding to input order
    cand.record_observation("career[0].team", "wikipedia", "P", "Juventus", stop_id="stop_juve")
    cand.record_observation("career[0].apps", "wikipedia", "P", 150, stop_id="stop_juve")
    cand.record_observation("career[1].team", "wikipedia", "P", "Padova", stop_id="stop_padova")
    cand.record_observation("career[1].apps", "wikipedia", "P", 80, stop_id="stop_padova")

    # Run normalization (which executes order_career and reindex_career_paths)
    normalize_candidate(cand)

    # Verify career was chronologically ordered: Padova (2005) is now stop 0, Juventus (2010) is stop 1
    assert cand.career[0]["team"] == "Padova"
    assert cand.career[0]["_stop_id"] == "stop_padova"
    assert cand.career[1]["team"] == "Juventus"
    assert cand.career[1]["_stop_id"] == "stop_juve"

    prov = cand.provenance
    # The indexed path career[0].team must now point to Padova!
    padova_prov = prov.get_provenance_for_path("career[0].team")
    assert padova_prov is not None
    assert padova_prov.stop_id == "stop_padova"
    assert padova_prov.observations[0].raw_value == "Padova"

    # And career[1].team must point to Juventus!
    juve_prov = prov.get_provenance_for_path("career[1].team")
    assert juve_prov is not None
    assert juve_prov.stop_id == "stop_juve"
    assert juve_prov.observations[0].raw_value == "Juventus"

    # Querying by stable stop_id returns the exact record regardless of index
    assert prov.get_provenance_for_stop("stop_padova", "apps").observations[0].raw_value == 80
    assert prov.get_provenance_for_stop("stop_juve", "apps").observations[0].raw_value == 150


# ---------------------------------------------------------------------------
# 5. Unicode and Non-ASCII Character Handling
# ---------------------------------------------------------------------------


def test_unicode_and_special_character_preservation():
    """Verify that accented characters, apostrophes, and non-ASCII names are preserved."""
    cand = CandidatePlayer(
        candidate_id="cand_unicode",
        source="wikipedia",
        source_id="Pelé",
        full_name="Pelé",
    )
    cand.record_observation(
        field_path="full_name",
        source="wikipedia",
        source_id="Pelé",
        raw_value="Edson Arantes do Nascimento, detto Pelé",
    )
    cand.record_observation(
        field_path="career[0].team",
        source="wikipedia",
        source_id="Pelé",
        raw_value="Cádiz CF",
        stop_id="stop_cadiz",
    )

    prov = cand.provenance
    name_prov = prov.get_provenance_for_path("full_name")
    assert "Pelé" in name_prov.observations[0].raw_value

    stop_prov = prov.get_provenance_for_path("career[0].team")
    assert stop_prov.observations[0].raw_value == "Cádiz CF"

    # Round trip to JSON dict and back
    dict_repr = prov.to_dict()
    json_str = json.dumps(dict_repr, ensure_ascii=False)
    restored_dict = json.loads(json_str)
    restored_prov = CandidateProvenance.from_dict(restored_dict)

    assert restored_prov.get_provenance_for_path("career[0].team").observations[0].raw_value == "Cádiz CF"


# ---------------------------------------------------------------------------
# 6. Production Dataset Safety Guard
# ---------------------------------------------------------------------------


def test_production_dataset_zero_mutation_guarantee():
    """Critical safety test: verifies data/players.json is strictly untouched."""
    assert _PLAYERS_JSON.is_file(), "data/players.json deve esistere nel repository"
    hash_before = _hash_file(_PLAYERS_JSON)

    # Perform extensive provenance and candidate operations
    cand = CandidatePlayer(
        candidate_id="cand_safety_check",
        source="wikipedia",
        source_id="Safety_Player",
        full_name="Safety Player",
        nationality="Italia",
        position="Attaccante",
        career=[
            {"team": "Milan", "country": "Italia", "league": "Serie A", "start_year": 2000, "end_year": 2005}
        ],
    )
    cand.transition_to(CandidateState.FETCHED)
    cand.record_observation("full_name", "wikipedia", "Safety_Player", "Safety Player")
    normalize_candidate(cand)
    validate_candidate_data(cand)

    hash_after = _hash_file(_PLAYERS_JSON)
    assert hash_before == hash_after, "data/players.json NON deve essere modificato dalle operazioni di provenance"


# ---------------------------------------------------------------------------
# 7. Focused Review Regression Tests (PR #62)
# ---------------------------------------------------------------------------


def test_legacy_raw_data_survives_subsequent_adapter_merge():
    """Regression test 1: Prove complete legacy raw payload survives migration and merge."""
    legacy_payload = {
        "source_name": "wikipedia",
        "source_id": "Legacy_Player",
        "source_metadata": {"url": "https://it.wikipedia.org/wiki/Legacy", "rev_id": 8877},
        "raw_payload": {"infobox": "{{Bio|nome=Legacy}}", "sections": ["Carriera"]},
    }
    cand = CandidatePlayer(
        candidate_id="cand_legacy_preserve",
        source="wikipedia",
        source_id="Legacy_Player",
        full_name="Legacy Player",
        raw_data=copy.deepcopy(legacy_payload),
    )
    cand.transition_to(CandidateState.FETCHED)

    # Ingest a second adapter result
    wikidata_result = AdapterResult(
        source_name="wikidata",
        source_id="Q12345",
        success=True,
        player_name="Legacy Player",
        birth_year=1991,
        source_metadata={"url": "https://www.wikidata.org/wiki/Q12345"},
        raw_payload={"claims": {"P569": "1991"}},
    )
    merge_adapter_result(cand, wikidata_result)

    # 1. Check sources structure
    assert "sources" in cand.raw_data
    assert "wikipedia" in cand.raw_data["sources"]
    assert "wikidata" in cand.raw_data["sources"]

    # 2. Complete old source payload preserved
    old_wiki = cand.raw_data["sources"]["wikipedia"]
    assert old_wiki["source_name"] == "wikipedia"
    assert old_wiki["source_id"] == "Legacy_Player"
    assert old_wiki["source_metadata"] == legacy_payload["source_metadata"]
    assert old_wiki["raw_payload"] == legacy_payload["raw_payload"]

    # 3. New source payload correctly stored
    new_wdata = cand.raw_data["sources"]["wikidata"]
    assert new_wdata["source_name"] == "wikidata"
    assert new_wdata["source_id"] == "Q12345"
    assert new_wdata["raw_payload"] == {"claims": {"P569": "1991"}}

    # 4. Backward-compatible top-level fields preserved
    assert cand.raw_data["source_name"] == "wikidata"
    assert cand.raw_data["source_id"] == "Q12345"


def test_career_stop_matching_no_substring_and_ambiguous_aliases():
    """Regression test 2: Prove career stop matching rejects substrings and ambiguous aliases,
    while accepting deterministic aliases and exact cleaned matches.
    """
    # 1. Inter and Inter Miami remain separate even with identical/adjacent years
    cand = CandidatePlayer(candidate_id="cand_inter_test", source="wikipedia", source_id="p1")
    wiki_res = AdapterResult(
        source_name="wikipedia",
        source_id="p1",
        success=True,
        player_name="Test Player",
        career=[
            CareerEntry(team="Inter", country="Italia", league="Serie A", start_year=2023, end_year=2024),
        ],
    )
    populate_candidate_from_result(cand, wiki_res)

    wikidata_res = AdapterResult(
        source_name="wikidata",
        source_id="Q1",
        success=True,
        player_name="Test Player",
        career=[
            CareerEntry(team="Inter Miami", country="USA", league="MLS", start_year=2023, end_year=2024),
        ],
    )
    merge_adapter_result(cand, wikidata_res)

    # Must NOT have merged into 1 stop!
    assert len(cand.career) == 2
    assert cand.career[0]["team"] == "Inter"
    assert cand.career[1]["team"] == "Inter Miami"

    # 2. True deterministic alias: PSG and Paris Saint-Germain match
    cand_psg = CandidatePlayer(candidate_id="cand_psg_test", source="wikipedia", source_id="p2")
    res_psg1 = AdapterResult(
        source_name="wikipedia",
        source_id="p2",
        success=True,
        player_name="Player PSG",
        career=[
            CareerEntry(team="PSG", country="Francia", league="Ligue 1", start_year=2020, end_year=2022),
        ],
    )
    populate_candidate_from_result(cand_psg, res_psg1)

    res_psg2 = AdapterResult(
        source_name="wikidata",
        source_id="Q2",
        success=True,
        player_name="Player PSG",
        career=[
            CareerEntry(team="Paris Saint-Germain", country="Francia", league="Ligue 1", start_year=2020, end_year=2022),
        ],
    )
    merge_adapter_result(cand_psg, res_psg2)

    # Must have merged into a single stop
    assert len(cand_psg.career) == 1
    stop_prov = cand_psg.provenance.get_provenance_for_path("career[0].team")
    assert stop_prov is not None
    assert len(stop_prov.observations) == 2

    # 3. Ambiguous aliases: Real vs Real Madrid, United vs Manchester United never merge
    cand_ambig = CandidatePlayer(candidate_id="cand_ambig_test", source="wikipedia", source_id="p3")
    res_ambig1 = AdapterResult(
        source_name="wikipedia",
        source_id="p3",
        success=True,
        player_name="Player Ambig",
        career=[
            CareerEntry(team="Real", country="Spagna", start_year=2015, end_year=2018),
            CareerEntry(team="United", country="Inghilterra", start_year=2018, end_year=2020),
        ],
    )
    populate_candidate_from_result(cand_ambig, res_ambig1)

    res_ambig2 = AdapterResult(
        source_name="wikidata",
        source_id="Q3",
        success=True,
        player_name="Player Ambig",
        career=[
            CareerEntry(team="Real Madrid", country="Spagna", start_year=2015, end_year=2018),
            CareerEntry(team="Manchester United", country="Inghilterra", start_year=2018, end_year=2020),
        ],
    )
    merge_adapter_result(cand_ambig, res_ambig2)

    # Must preserve all 4 stops separately because Real and United are ambiguous
    assert len(cand_ambig.career) == 4
    teams_present = [s["team"] for s in cand_ambig.career]
    assert "Real" in teams_present
    assert "Real Madrid" in teams_present
    assert "United" in teams_present
    assert "Manchester United" in teams_present


def test_multi_source_alias_provenance_and_reindexing():
    """Regression test 3:
    1. Wikipedia aliases [A, B]
    2. Wikidata aliases [C, A]
    3. resulting Candidate aliases
    4. correct observations attached to A/B/C without index collisions
    5. normalization/dedup round-trip
    """
    cand = CandidatePlayer(candidate_id="cand_alias_test", source="wikipedia", source_id="p_alias")

    # 1. Wikipedia fetch: [A, B]
    wiki_res = AdapterResult(
        source_name="wikipedia",
        source_id="p_alias",
        success=True,
        player_name="Target Player",
        aliases=["AliasAlpha", "AliasBeta"],
    )
    populate_candidate_from_result(cand, wiki_res)

    assert cand.aliases == ["AliasAlpha", "AliasBeta"]
    prov = cand.provenance
    assert "aliases[0]" in prov.fields
    assert "aliases[1]" in prov.fields
    assert prov.fields["aliases[0]"].observations[0].source == "wikipedia"
    assert prov.fields["aliases[0]"].observations[0].raw_value == "AliasAlpha"
    assert prov.fields["aliases[1]"].observations[0].source == "wikipedia"
    assert prov.fields["aliases[1]"].observations[0].raw_value == "AliasBeta"

    # 2. Wikidata fetch: [C, A]
    wikidata_res = AdapterResult(
        source_name="wikidata",
        source_id="Q_alias",
        success=True,
        player_name="Target Player",
        aliases=["AliasGamma", "AliasAlpha"],
    )
    merge_adapter_result(cand, wikidata_res)

    # 3. Resulting candidate aliases: [AliasAlpha, AliasBeta, AliasGamma]
    assert cand.aliases == ["AliasAlpha", "AliasBeta", "AliasGamma"]

    # 4. Correct observations attached to A, B, C:
    # A is at index 0: shared provenance between wikipedia and wikidata
    prov_a = prov.get_provenance_for_path("aliases[0]")
    assert prov_a is not None
    assert len(prov_a.observations) == 2
    sources_a = {obs.source for obs in prov_a.observations}
    assert sources_a == {"wikipedia", "wikidata"}
    assert prov_a.has_conflict() is False

    # B is at index 1: from wikipedia only
    prov_b = prov.get_provenance_for_path("aliases[1]")
    assert prov_b is not None
    assert len(prov_b.observations) == 1
    assert prov_b.observations[0].source == "wikipedia"
    assert prov_b.observations[0].raw_value == "AliasBeta"

    # C is at index 2: from wikidata only (NOT collided with index 0!)
    prov_c = prov.get_provenance_for_path("aliases[2]")
    assert prov_c is not None
    assert len(prov_c.observations) == 1
    assert prov_c.observations[0].source == "wikidata"
    assert prov_c.observations[0].raw_value == "AliasGamma"

    # 5. Normalization/dedup round-trip
    normalize_candidate(cand)

    assert "aliasalpha" in cand.aliases
    assert "aliasbeta" in cand.aliases
    assert "aliasgamma" in cand.aliases

    # Prove paths in provenance remain valid after normalization
    idx_a = cand.aliases.index("aliasalpha")
    idx_b = cand.aliases.index("aliasbeta")
    idx_c = cand.aliases.index("aliasgamma")

    norm_prov_a = cand.provenance.get_provenance_for_path(f"aliases[{idx_a}]")
    norm_prov_b = cand.provenance.get_provenance_for_path(f"aliases[{idx_b}]")
    norm_prov_c = cand.provenance.get_provenance_for_path(f"aliases[{idx_c}]")

    assert norm_prov_a is not None
    assert len(norm_prov_a.observations) == 2
    assert {o.source for o in norm_prov_a.observations} == {"wikipedia", "wikidata"}

    assert norm_prov_b is not None
    assert len(norm_prov_b.observations) == 1
    assert norm_prov_b.observations[0].source == "wikipedia"

    assert norm_prov_c is not None
    assert len(norm_prov_c.observations) == 1
    assert norm_prov_c.observations[0].source == "wikidata"


def test_normalization_resolves_equivalent_source_observations_real_flow():
    """Regression test 4: End-to-end test using REAL flow:
    populate_candidate_from_result(Wikipedia) -> merge_adapter_result(Wikidata) -> normalize_candidate()

    Covers:
    - Equivalent after normalization: Wikipedia 'PSG' + Wikidata 'Paris Saint-Germain'
      After normalization:
      * both raw observations remain visible;
      * both support canonical 'Paris Saint-Germain';
      * no source conflict remains.
    - Genuine conflict: Two actually different values preserve conflict after normalization.
    """
    # Case 1: Equivalent after normalization
    cand = CandidatePlayer(candidate_id="cand_real_flow_psg", source="wikipedia", source_id="p_psg")
    wiki_res = AdapterResult(
        source_name="wikipedia",
        source_id="p_psg",
        success=True,
        player_name="Kylian Mbappé",
        nationality="Francia",
        career=[
            CareerEntry(team="PSG", country="Francia", league="Ligue 1", start_year=2017, end_year=2024),
        ],
    )
    populate_candidate_from_result(cand, wiki_res)

    wikidata_res = AdapterResult(
        source_name="wikidata",
        source_id="Q_psg",
        success=True,
        player_name="Kylian Mbappé",
        nationality="Francia",
        career=[
            CareerEntry(team="Paris Saint-Germain", country="Francia", league="Ligue 1", start_year=2017, end_year=2024),
        ],
    )
    merge_adapter_result(cand, wikidata_res)

    # Before normalization, raw values differ ('PSG' vs 'Paris Saint-Germain')
    team_prov = cand.provenance.get_provenance_for_path("career[0].team")
    assert team_prov is not None
    assert len(team_prov.observations) == 2
    assert team_prov.has_conflict() is True

    # Real normalization execution
    normalize_candidate(cand)

    # After normalization:
    assert cand.career[0]["team"] == "Paris Saint-Germain"
    team_prov_after = cand.provenance.get_provenance_for_path("career[0].team")
    assert team_prov_after is not None

    obs_wiki = team_prov_after.get_observation("wikipedia")
    obs_wdata = team_prov_after.get_observation("wikidata")
    assert obs_wiki is not None
    assert obs_wdata is not None

    # Both raw observations remain visible and untouched
    assert obs_wiki.raw_value == "PSG"
    assert obs_wdata.raw_value == "Paris Saint-Germain"

    # Both support canonical Paris Saint-Germain
    assert obs_wiki.normalized_value == "Paris Saint-Germain"
    assert obs_wdata.normalized_value == "Paris Saint-Germain"

    # No source conflict remains!
    assert team_prov_after.has_conflict() is False
    assert set(team_prov_after.supporting_sources("Paris Saint-Germain")) == {"wikipedia", "wikidata"}

    # Case 2: Genuine conflict
    cand_conflict = CandidatePlayer(candidate_id="cand_real_conflict", source="wikipedia", source_id="p_conf")
    res1 = AdapterResult(
        source_name="wikipedia",
        source_id="p_conf",
        success=True,
        player_name="Player Conflict",
        career=[
            CareerEntry(team="Chelsea", country="Inghilterra", league="Premier League", start_year=2015, end_year=2018),
        ],
    )
    populate_candidate_from_result(cand_conflict, res1)

    # Construct candidate with second observation directly or simulated conflict on the same stop
    cand_conflict.record_observation(
        field_path="career[0].team",
        source="wikidata",
        source_id="Q_conf",
        raw_value="Arsenal",
        stop_id=cand_conflict.career[0]["_stop_id"],
    )

    normalize_candidate(cand_conflict)

    conf_prov = cand_conflict.provenance.get_provenance_for_path("career[0].team")
    assert conf_prov is not None
    # Chelsea and Arsenal are actually different clubs
    assert conf_prov.has_conflict() is True
    assert cand_conflict.metadata["has_source_conflicts"] is True

