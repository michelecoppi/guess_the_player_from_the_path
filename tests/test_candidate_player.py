"""Unit tests for Candidate Player domain model, states, transitions, errors, and IDs."""
import json
import re

import pytest

from services.candidate_player import (
    CandidateError,
    CandidatePlayer,
    CandidateState,
    InvalidStateTransitionError,
    make_candidate_id,
    make_candidate_id_from_name,
)


def test_candidate_creation_defaults():
    candidate = CandidatePlayer(
        candidate_id="cand_wiki_francesco_totti",
        source="wikipedia",
        source_id="Francesco_Totti",
    )

    assert candidate.candidate_id == "cand_wiki_francesco_totti"
    assert candidate.source == "wikipedia"
    assert candidate.source_id == "Francesco_Totti"
    assert candidate.status == CandidateState.DISCOVERED
    assert candidate.created_at != ""
    assert candidate.updated_at != ""
    assert candidate.last_transition_at is None
    assert candidate.state_history == []
    assert candidate.errors == []
    assert candidate.last_error is None
    assert candidate.retry_count == 0
    assert candidate.max_retries == 3
    assert candidate.is_terminal() is False
    assert candidate.can_retry() is True


def test_candidate_creation_validation():
    with pytest.raises(ValueError, match="candidate_id non puo' essere vuoto"):
        CandidatePlayer(candidate_id="", source="wikipedia", source_id="123")

    with pytest.raises(ValueError, match="source e source_id devono essere valorizzati"):
        CandidatePlayer(candidate_id="cand_1", source="", source_id="123")

    with pytest.raises(ValueError, match="source e source_id devono essere valorizzati"):
        CandidatePlayer(candidate_id="cand_1", source="wiki", source_id="")


def test_status_immutability_and_protection():
    """Verifica che lo stato del ciclo di vita non sia mutabile direttamente
    e che non possa essere impostato arbitrariamente tramite costruttore standard."""
    cand = CandidatePlayer(candidate_id="cand_protect", source="wiki", source_id="1")
    assert cand.status == CandidateState.DISCOVERED

    # 1. Tentativo di mutazione diretta di status solleva AttributeError
    with pytest.raises(AttributeError, match="Lo stato del candidato non puo' essere modificato direttamente"):
        cand.status = CandidateState.APPROVED  # type: ignore[misc]
    assert cand.status == CandidateState.DISCOVERED

    # 2. Tentativo di passare 'status' al costruttore pubblico solleva TypeError
    with pytest.raises(TypeError, match="unexpected keyword argument 'status'"):
        CandidatePlayer(  # type: ignore[call-arg]
            candidate_id="cand_bypass",
            source="wiki",
            source_id="2",
            status=CandidateState.APPROVED,
        )

    # 3. Solo transition_to() puo' avanzare lo stato attraverso il grafo validato
    cand.transition_to(CandidateState.FETCHED)
    assert cand.status == CandidateState.FETCHED

    # 4. Deserializzazione da persistenza (from_dict) ripristina lo stato corretto
    restored = CandidatePlayer.from_dict({
        "candidate_id": "cand_restored",
        "source": "wiki",
        "source_id": "3",
        "status": CandidateState.VALIDATED.value,
    })
    assert restored.status == CandidateState.VALIDATED


def test_deterministic_id_generation():
    id1 = make_candidate_id("wikipedia", "Francesco Totti")
    id2 = make_candidate_id("wikipedia", "Francesco Totti")

    # Deterministico: chiamate identiche restituiscono l'ID identico
    assert id1 == id2
    assert id1.startswith("cand_wikipedia_francesco_totti_")

    # Sicuro per filesystem e URL: solo caratteri alfanumerici e underscore
    assert re.fullmatch(r"cand_[a-z0-9_]+", id1) is not None

    # Accenti e caratteri speciali
    id_accent = make_candidate_id("wikipedia", "Pelé")
    assert id_accent.startswith("cand_wikipedia_pele_")

    id_apostrophe = make_candidate_id("wiki", "N'Golo Kanté")
    assert id_apostrophe.startswith("cand_wiki_n_golo_kante_")

    # Wikidata Q-ID
    id_wd = make_candidate_id("wikidata", "Q1853")
    assert id_wd.startswith("cand_wikidata_q1853_")


def test_deterministic_id_collision_resistance():
    """Verifica che identificatori grezzi distinti (che prima collassavano allo stesso slug)
    producano candidate_id distinti grazie all'hash crittografico stabile."""
    id_dash = make_candidate_id("wiki", "A-B")
    id_slash = make_candidate_id("wiki", "A/B")
    id_underscore = make_candidate_id("wiki", "A_B")
    id_space = make_candidate_id("wiki", "A B")

    # Devono essere tutti e 4 distinti
    unique_ids = {id_dash, id_slash, id_underscore, id_space}
    assert len(unique_ids) == 4, f"Collisione rilevata tra identificatori distinti: {unique_ids}"

    # Tutti mantengono lo slug leggibile come prefisso
    assert id_dash.startswith("cand_wiki_a_b_")
    assert id_slash.startswith("cand_wiki_a_b_")
    assert id_underscore.startswith("cand_wiki_a_b_")
    assert id_space.startswith("cand_wiki_a_b_")

    # Anche la sorgente differenzia l'ID
    id_wiki = make_candidate_id("wikipedia", "player_1")
    id_wd = make_candidate_id("wikidata", "player_1")
    assert id_wiki != id_wd


def test_deterministic_id_invalid_inputs():
    with pytest.raises(ValueError, match="source e source_id devono essere stringhe valide"):
        make_candidate_id("", "foo")
    with pytest.raises(ValueError, match="source e source_id devono essere stringhe valide"):
        make_candidate_id("wiki", "")


def test_deterministic_id_from_name():
    id1 = make_candidate_id_from_name("Lionel Messi", 1987)
    id2 = make_candidate_id_from_name("Lionel Messi", 1987)
    assert id1 == id2
    assert id1.startswith("cand_lionel_messi_1987_")

    id_no_year = make_candidate_id_from_name("Zinedine Zidane")
    assert id_no_year.startswith("cand_zinedine_zidane_")

    # Collision resistance on names with hyphens vs spaces
    id_hyphen = make_candidate_id_from_name("Jean-Pierre Papin", 1963)
    id_space = make_candidate_id_from_name("Jean Pierre Papin", 1963)
    assert id_hyphen != id_space

    with pytest.raises(ValueError, match="full_name deve essere una stringa valida"):
        make_candidate_id_from_name("   ")


def test_legal_transitions_lifecycle_happy_path():
    cand = CandidatePlayer(
        candidate_id="cand_test_player",
        source="wiki",
        source_id="Test_Player",
    )
    assert cand.status == CandidateState.DISCOVERED
    assert cand.can_transition_to(CandidateState.FETCHED) is True
    assert cand.can_transition_to(CandidateState.APPROVED) is False

    # 1. DISCOVERED -> FETCHED
    rec1 = cand.transition_to(CandidateState.FETCHED, reason="Fetched raw wiki page", actor="adapter_wiki")
    assert cand.status == CandidateState.FETCHED
    assert cand.last_transition_at is not None
    assert len(cand.state_history) == 1
    assert rec1.from_state == CandidateState.DISCOVERED
    assert rec1.to_state == CandidateState.FETCHED
    assert rec1.reason == "Fetched raw wiki page"
    assert rec1.actor == "adapter_wiki"

    # 2. FETCHED -> NORMALIZED
    cand.transition_to(CandidateState.NORMALIZED, reason="Cleaned club names")
    assert cand.status == CandidateState.NORMALIZED
    assert len(cand.state_history) == 2

    # 3. NORMALIZED -> VALIDATED
    cand.transition_to(CandidateState.VALIDATED, reason="Career consistency checks passed")
    assert cand.status == CandidateState.VALIDATED
    assert len(cand.state_history) == 3

    # 4. VALIDATED -> READY
    cand.transition_to(CandidateState.READY, reason="Ready for reviewer queue")
    assert cand.status == CandidateState.READY
    assert len(cand.state_history) == 4

    # 5. READY -> APPROVED (terminal)
    cand.transition_to(CandidateState.APPROVED, reason="Admin approved", actor="admin_coppi")
    assert cand.status == CandidateState.APPROVED
    assert len(cand.state_history) == 5
    assert cand.is_terminal() is True


def test_legal_transitions_review_and_rejected():
    cand = CandidatePlayer(
        candidate_id="cand_test_player_2",
        source="wiki",
        source_id="Test_Player_2",
    )
    cand.transition_to(CandidateState.FETCHED)
    # FETCHED -> REVIEW_REQUIRED
    cand.transition_to(CandidateState.REVIEW_REQUIRED, reason="Ambiguous nationality detected")
    assert cand.status == CandidateState.REVIEW_REQUIRED

    # REVIEW_REQUIRED -> NORMALIZED (retry/reprocess normalization)
    cand.transition_to(CandidateState.NORMALIZED, reason="Re-running normalization with override")
    assert cand.status == CandidateState.NORMALIZED

    # NORMALIZED -> REVIEW_REQUIRED
    cand.transition_to(CandidateState.REVIEW_REQUIRED, reason="Still dubious")
    assert cand.status == CandidateState.REVIEW_REQUIRED

    # REVIEW_REQUIRED -> REJECTED (terminal)
    cand.transition_to(CandidateState.REJECTED, reason="Confirmed duplicate of existing player")
    assert cand.status == CandidateState.REJECTED
    assert cand.is_terminal() is True


def test_illegal_transitions_rejected():
    cand = CandidatePlayer(
        candidate_id="cand_illegal_test",
        source="wiki",
        source_id="P1",
    )

    # DISCOVERED non puo' saltare direttamente a VALIDATED, READY o APPROVED
    invalid_targets = [
        CandidateState.NORMALIZED,
        CandidateState.VALIDATED,
        CandidateState.REVIEW_REQUIRED,
        CandidateState.READY,
        CandidateState.APPROVED,
    ]
    for target in invalid_targets:
        with pytest.raises(InvalidStateTransitionError) as exc_info:
            cand.transition_to(target)
        err = exc_info.value
        assert err.candidate_id == "cand_illegal_test"
        assert err.current_state == CandidateState.DISCOVERED
        assert err.target_state == target
        # Lo stato non deve essere mutato in caso di errore
        assert cand.status == CandidateState.DISCOVERED
        assert len(cand.state_history) == 0


def test_terminal_states_cannot_transition():
    # Test APPROVED terminal
    cand_app = CandidatePlayer(candidate_id="cand_app", source="wiki", source_id="A1")
    cand_app.transition_to(CandidateState.FETCHED)
    cand_app.transition_to(CandidateState.NORMALIZED)
    cand_app.transition_to(CandidateState.VALIDATED)
    cand_app.transition_to(CandidateState.APPROVED)
    assert cand_app.is_terminal() is True

    for target in CandidateState:
        with pytest.raises(InvalidStateTransitionError):
            cand_app.transition_to(target)
    assert cand_app.status == CandidateState.APPROVED

    # Test REJECTED terminal
    cand_rej = CandidatePlayer(candidate_id="cand_rej", source="wiki", source_id="R1")
    cand_rej.transition_to(CandidateState.REJECTED)
    assert cand_rej.is_terminal() is True

    for target in CandidateState:
        with pytest.raises(InvalidStateTransitionError):
            cand_rej.transition_to(target)
    assert cand_rej.status == CandidateState.REJECTED


def test_error_recording_and_retry_tracking():
    cand = CandidatePlayer(
        candidate_id="cand_err_test",
        source="wiki",
        source_id="ErrPlayer",
        max_retries=2,
    )
    assert cand.retry_count == 0
    assert cand.can_retry() is True

    # 1. Registra primo errore retryable
    err1 = cand.record_error(
        error_type="HTTP_TIMEOUT",
        message="Request to wikipedia timed out",
        details={"status_code": 504, "endpoint": "https://it.wikipedia.org/..."},
        retryable=True,
    )
    assert isinstance(err1, CandidateError)
    assert err1.error_type == "HTTP_TIMEOUT"
    assert err1.state == CandidateState.DISCOVERED
    assert cand.retry_count == 1
    assert cand.last_error == err1
    assert len(cand.errors) == 1
    assert cand.can_retry() is True

    # 2. Registra secondo errore
    err2 = cand.record_error(
        error_type="HTTP_500",
        message="Internal server error on source",
        retryable=True,
    )
    assert cand.retry_count == 2
    assert cand.last_error == err2
    assert len(cand.errors) == 2
    # Raggiunta la soglia massima: can_retry deve essere False
    assert cand.can_retry() is False

    # 3. Errore non retryable non incrementa retry_count
    err3 = cand.record_error(
        error_type="PARSE_FATAL",
        message="HTML is corrupt",
        retryable=False,
    )
    assert cand.retry_count == 2
    assert len(cand.errors) == 3
    assert err3.retryable is False

    # 4. Reset dei retry
    cand.reset_retries()
    assert cand.retry_count == 0
    assert cand.can_retry() is True


def test_serialization_round_trip():
    cand = CandidatePlayer(
        candidate_id="cand_messi_test",
        source="wikipedia",
        source_id="Lionel_Messi",
        full_name="Lionel Messi",
        aliases=["messi", "leo messi"],
        nationality="Argentina",
        position="Attaccante",
        birth_year=1987,
        popularity=5,
        career=[
            {"team": "Barcelona", "country": "Spagna", "league": "La Liga", "start_year": 2004, "end_year": 2021},
            {"team": "PSG", "country": "Francia", "league": "Ligue 1", "start_year": 2021, "end_year": 2023},
        ],
        raw_data={"infobox_title": "Lionel Andrés Messi Cuccittini"},
        validation_warnings=["Club 'PSG' normalized to 'Paris Saint-Germain'"],
        validation_errors=[],
        confidence_score=0.98,
        metadata={"tags": ["legend", "ballon_dor"]},
    )
    cand.transition_to(CandidateState.FETCHED, reason="Fetched")
    cand.record_error(error_type="MINOR_WARNING", message="Slow response", retryable=False)

    data = cand.to_dict()
    # Verifica che sia JSON serializzabile
    json_str = json.dumps(data, indent=2)
    loaded_data = json.loads(json_str)

    restored = CandidatePlayer.from_dict(loaded_data)

    assert restored.candidate_id == cand.candidate_id
    assert restored.source == cand.source
    assert restored.source_id == cand.source_id
    assert restored.status == cand.status
    assert restored.full_name == cand.full_name
    assert restored.aliases == cand.aliases
    assert restored.nationality == cand.nationality
    assert restored.birth_year == cand.birth_year
    assert restored.career == cand.career
    assert restored.raw_data == cand.raw_data
    assert restored.validation_warnings == cand.validation_warnings
    assert restored.confidence_score == cand.confidence_score
    assert len(restored.state_history) == 1
    assert restored.state_history[0].from_state == CandidateState.DISCOVERED
    assert restored.state_history[0].to_state == CandidateState.FETCHED
    assert len(restored.errors) == 1
    assert restored.errors[0].error_type == "MINOR_WARNING"
    assert restored.metadata == cand.metadata
