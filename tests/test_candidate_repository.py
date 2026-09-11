"""Unit tests for CandidatePlayerRepository implementations (in-memory and file-backed)
and critical isolation guards protecting data/players.json.
"""
import hashlib
import json
from pathlib import Path

import pytest

from services.candidate_player import CandidatePlayer, CandidateState
from services.repos.candidates import (
    CandidateRepositoryError,
    FileCandidatePlayerRepository,
    InMemoryCandidatePlayerRepository,
)


@pytest.fixture
def sample_candidate() -> CandidatePlayer:
    return CandidatePlayer(
        candidate_id="cand_wiki_del_piero",
        source="wikipedia",
        source_id="Alessandro_Del_Piero",
        full_name="Alessandro Del Piero",
        aliases=["del piero", "alessandro del piero", "pinturicchio"],
        nationality="Italia",
        position="Attaccante",
        birth_year=1974,
        popularity=5,
        career=[
            {"team": "Padova", "country": "Italia", "league": "Serie B", "start_year": 1991, "end_year": 1993},
            {"team": "Juventus", "country": "Italia", "league": "Serie A", "start_year": 1993, "end_year": 2012},
        ],
    )


# ---------------------------------------------------------------------------
# Test InMemoryCandidatePlayerRepository
# ---------------------------------------------------------------------------


def test_in_memory_repository_crud(sample_candidate: CandidatePlayer):
    repo = InMemoryCandidatePlayerRepository()
    assert repo.count() == 0
    assert repo.get_by_id(sample_candidate.candidate_id) is None
    assert repo.exists(sample_candidate.candidate_id) is False

    # Save
    repo.save(sample_candidate)
    assert repo.count() == 1
    assert repo.exists(sample_candidate.candidate_id) is True

    # Get by ID
    loaded = repo.get_by_id(sample_candidate.candidate_id)
    assert loaded is not None
    assert loaded.candidate_id == sample_candidate.candidate_id
    assert loaded.full_name == "Alessandro Del Piero"

    # Isolamento da modifiche dirette all'oggetto in-memory
    loaded.full_name = "Modified Del Piero"
    fresh_loaded = repo.get_by_id(sample_candidate.candidate_id)
    assert fresh_loaded is not None
    assert fresh_loaded.full_name == "Alessandro Del Piero"

    # Delete
    assert repo.delete(sample_candidate.candidate_id) is True
    assert repo.count() == 0
    assert repo.get_by_id(sample_candidate.candidate_id) is None
    assert repo.delete(sample_candidate.candidate_id) is False


def test_in_memory_repository_filtering_and_pagination():
    repo = InMemoryCandidatePlayerRepository()

    c1 = CandidatePlayer(candidate_id="cand_1", source="wiki", source_id="1")
    c2 = CandidatePlayer(candidate_id="cand_2", source="wiki", source_id="2")
    c2.transition_to(CandidateState.FETCHED)
    c3 = CandidatePlayer(candidate_id="cand_3", source="wiki", source_id="3")
    c3.transition_to(CandidateState.FETCHED)
    c4 = CandidatePlayer(candidate_id="cand_4", source="wiki", source_id="4")
    c4.transition_to(CandidateState.FETCHED)
    c4.transition_to(CandidateState.NORMALIZED)
    c4.transition_to(CandidateState.VALIDATED)
    c4.transition_to(CandidateState.READY)

    for c in (c1, c2, c3, c4):
        repo.save(c)

    assert repo.count() == 4
    assert repo.count(CandidateState.FETCHED) == 2
    assert repo.count(CandidateState.READY) == 1
    assert repo.count(CandidateState.APPROVED) == 0

    # List all con ordinamento e paginazione
    all_cand = repo.list_all()
    assert [c.candidate_id for c in all_cand] == ["cand_1", "cand_2", "cand_3", "cand_4"]

    paginated = repo.list_all(limit=2, offset=1)
    assert [c.candidate_id for c in paginated] == ["cand_2", "cand_3"]

    # Filter by state
    fetched = repo.find_by_state(CandidateState.FETCHED)
    assert [c.candidate_id for c in fetched] == ["cand_2", "cand_3"]

    ready = repo.find_by_state(CandidateState.READY)
    assert len(ready) == 1
    assert ready[0].candidate_id == "cand_4"


# ---------------------------------------------------------------------------
# Test FileCandidatePlayerRepository
# ---------------------------------------------------------------------------


def test_file_repository_crud(tmp_path: Path, sample_candidate: CandidatePlayer):
    storage_dir = tmp_path / "candidates"
    repo = FileCandidatePlayerRepository(storage_dir=storage_dir)

    assert repo.count() == 0
    assert repo.exists(sample_candidate.candidate_id) is False
    assert repo.get_by_id(sample_candidate.candidate_id) is None

    # Save
    repo.save(sample_candidate)
    assert repo.count() == 1
    assert repo.exists(sample_candidate.candidate_id) is True

    # Verifica che il file esista su disco con formato JSON valido
    expected_file = storage_dir / f"{sample_candidate.candidate_id}.json"
    assert expected_file.is_file()
    with open(expected_file, "r", encoding="utf-8") as f:
        raw_json = json.load(f)
    assert raw_json["candidate_id"] == sample_candidate.candidate_id
    assert raw_json["full_name"] == "Alessandro Del Piero"

    # Get by ID (round-trip da disco)
    loaded = repo.get_by_id(sample_candidate.candidate_id)
    assert loaded is not None
    assert loaded.candidate_id == sample_candidate.candidate_id
    assert loaded.full_name == sample_candidate.full_name
    assert loaded.career == sample_candidate.career
    assert loaded.status == CandidateState.DISCOVERED

    # Aggiornamento dello stato e ri-salvataggio
    loaded.transition_to(CandidateState.FETCHED, reason="Fetched career")
    repo.save(loaded)

    reloaded = repo.get_by_id(sample_candidate.candidate_id)
    assert reloaded is not None
    assert reloaded.status == CandidateState.FETCHED
    assert len(reloaded.state_history) == 1
    assert reloaded.state_history[0].to_state == CandidateState.FETCHED

    # Delete
    assert repo.delete(sample_candidate.candidate_id) is True
    assert not expected_file.exists()
    assert repo.count() == 0
    assert repo.get_by_id(sample_candidate.candidate_id) is None
    assert repo.delete(sample_candidate.candidate_id) is False


def test_file_repository_atomic_write(tmp_path: Path, sample_candidate: CandidatePlayer):
    storage_dir = tmp_path / "atomic_candidates"
    repo = FileCandidatePlayerRepository(storage_dir=storage_dir)
    repo.save(sample_candidate)

    # Verifica che non rimangano file temporanei .tmp_ nella cartella
    tmp_files = list(storage_dir.glob(".tmp_*"))
    assert tmp_files == []


def test_file_repository_path_traversal_protection(tmp_path: Path):
    repo = FileCandidatePlayerRepository(storage_dir=tmp_path)
    with pytest.raises(ValueError, match="candidate_id non valido per il filesystem"):
        repo.save(CandidatePlayer(candidate_id="../hacked", source="w", source_id="1"))

    with pytest.raises(ValueError, match="candidate_id non valido per il filesystem"):
        repo.get_by_id("../../etc/passwd")


def test_file_repository_filtering_and_counts(tmp_path: Path):
    repo = FileCandidatePlayerRepository(storage_dir=tmp_path / "pool")

    p1 = CandidatePlayer(candidate_id="cand_a", source="w", source_id="1")
    p2 = CandidatePlayer(candidate_id="cand_b", source="w", source_id="2")
    p2.transition_to(CandidateState.FETCHED)
    p3 = CandidatePlayer(candidate_id="cand_c", source="w", source_id="3")
    p3.transition_to(CandidateState.FETCHED)
    p4 = CandidatePlayer(candidate_id="cand_d", source="w", source_id="4")
    p4.transition_to(CandidateState.FETCHED)
    p4.transition_to(CandidateState.REVIEW_REQUIRED)

    for p in (p1, p2, p3, p4):
        repo.save(p)

    assert repo.count() == 4
    assert repo.count(CandidateState.DISCOVERED) == 1
    assert repo.count(CandidateState.FETCHED) == 2
    assert repo.count(CandidateState.REVIEW_REQUIRED) == 1
    assert repo.count(CandidateState.APPROVED) == 0

    fetched = repo.find_by_state(CandidateState.FETCHED)
    assert len(fetched) == 2
    assert [c.candidate_id for c in fetched] == ["cand_b", "cand_c"]


# ---------------------------------------------------------------------------
# Critical Safety & Dataset Isolation Tests
# ---------------------------------------------------------------------------


def test_safety_guard_rejects_targeting_production_dataset(tmp_path: Path):
    """Verifica che il repository rifiuti categoricamente di essere inizializzato
    su percorsi coincidenti con data/players.json."""
    base_dir = Path(__file__).resolve().parents[1]
    prod_path = base_dir / "data" / "players.json"

    # Tentativo esplicito di puntare a data/players.json come storage
    with pytest.raises(CandidateRepositoryError, match="Violazione di sicurezza"):
        FileCandidatePlayerRepository(storage_dir=prod_path)

    # Tentativo di usare una cartella chiamata 'players.json'
    fake_prod = tmp_path / "players.json"
    with pytest.raises(CandidateRepositoryError, match="Violazione di sicurezza"):
        FileCandidatePlayerRepository(storage_dir=fake_prod)


def test_safety_production_dataset_never_modified(tmp_path: Path, sample_candidate: CandidatePlayer):
    """Test di invariante assoluto: durante tutte le operazioni di salvataggio,
    transizione, aggiornamento e cancellazione di candidati, il file di produzione
    data/players.json NON subisce alcuna modifica."""
    base_dir = Path(__file__).resolve().parents[1]
    prod_file = base_dir / "data" / "players.json"
    assert prod_file.exists(), f"File di produzione non trovato a {prod_file}"

    # 1. Calcola hash e metadati prima dell'esecuzione
    with open(prod_file, "rb") as f:
        content_before = f.read()
    hash_before = hashlib.sha256(content_before).hexdigest()
    mtime_before = prod_file.stat().st_mtime_ns
    size_before = prod_file.stat().st_size

    # 2. Esegui ciclo completo su candidato con FileCandidatePlayerRepository
    repo = FileCandidatePlayerRepository(storage_dir=tmp_path / "candidates_sandbox")
    repo.save(sample_candidate)

    loaded = repo.get_by_id(sample_candidate.candidate_id)
    assert loaded is not None
    loaded.transition_to(CandidateState.FETCHED)
    loaded.transition_to(CandidateState.NORMALIZED)
    loaded.transition_to(CandidateState.VALIDATED)
    loaded.transition_to(CandidateState.READY)
    loaded.transition_to(CandidateState.APPROVED)
    repo.save(loaded)

    all_cand = repo.list_all()
    assert len(all_cand) == 1
    repo.delete(sample_candidate.candidate_id)

    # 3. Verifica invariante sul file di produzione
    with open(prod_file, "rb") as f:
        content_after = f.read()
    hash_after = hashlib.sha256(content_after).hexdigest()
    mtime_after = prod_file.stat().st_mtime_ns
    size_after = prod_file.stat().st_size

    assert hash_before == hash_after, "CRITICO: hash di data/players.json e' cambiato!"
    assert size_before == size_after, "CRITICO: dimensione di data/players.json e' cambiata!"
    assert mtime_before == mtime_after, "CRITICO: timestamp mtime di data/players.json e' cambiato!"


def test_no_automatic_promotion_to_player_pool(tmp_path: Path, sample_candidate: CandidatePlayer):
    """Verifica che l'approvazione di un candidato NON lo inserisca automaticamente
    nel pool dei giocatori utilizzabili dal gioco."""
    from services.player_pool import _load_raw_players

    repo = FileCandidatePlayerRepository(storage_dir=tmp_path / "candidates_sandbox")
    sample_candidate.transition_to(CandidateState.FETCHED)
    sample_candidate.transition_to(CandidateState.NORMALIZED)
    sample_candidate.transition_to(CandidateState.VALIDATED)
    sample_candidate.transition_to(CandidateState.APPROVED)
    repo.save(sample_candidate)

    raw_players = _load_raw_players()
    existing_ids = {p.get("id") for p in raw_players}

    # Il candidate_id non deve mai apparire tra gli ID del pool di gioco
    assert sample_candidate.candidate_id not in existing_ids
    assert "cand_wiki_del_piero" not in existing_ids
