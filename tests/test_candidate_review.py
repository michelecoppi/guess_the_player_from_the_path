"""Tests for Candidate Player Review Queue and Approval Workflow (#15).

Verifies the end-to-end domain and service layer for review, edit, approval,
merge, reject, source-wrong, retry ingestion, authorization, and data integrity.
"""
from __future__ import annotations

import concurrent.futures
import json
from pathlib import Path
from typing import Any

import pytest

from domains.players.adapters.base import AdapterResult, CareerEntry
from domains.players.candidates.model import CandidatePlayer, CandidateState
from domains.players.candidates.repository import FileCandidatePlayerRepository
from domains.players.candidates.review import (
    AdminIdentity,
    CandidateReviewService,
    ReviewAction,
    ReviewAuthError,
    ReviewForbiddenError,
    ReviewStatus,
    find_possible_duplicates,
    make_production_player_id,
)
from services.player_pool import validate_dataset


@pytest.fixture
def temp_env(tmp_path: Path):
    """Creates an isolated filesystem environment with mock players.json and candidates."""
    cand_dir = tmp_path / "candidates"
    cand_dir.mkdir(parents=True, exist_ok=True)
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir(parents=True, exist_ok=True)

    players_file = tmp_path / "players.json"
    initial_players = {
        "_comment": "Test dataset",
        "players": [
            {
                "id": "messi",
                "full_name": "Lionel Messi",
                "aliases": ["messi", "lionel messi", "leo messi"],
                "nationality": "Argentina",
                "position": "Attaccante",
                "birth_year": 1987,
                "popularity": 5,
                "verified": True,
                "career": [
                    {
                        "team": "Barcelona",
                        "country": "Spagna",
                        "league": "La Liga",
                        "start_year": 2004,
                        "end_year": 2021,
                        "apps": 520,
                        "goals": 474,
                    },
                    {
                        "team": "Paris Saint-Germain",
                        "country": "Francia",
                        "league": "Ligue 1",
                        "start_year": 2021,
                        "end_year": 2023,
                        "apps": 58,
                        "goals": 22,
                    },
                ],
            },
            {
                "id": "totti",
                "full_name": "Francesco Totti",
                "aliases": ["totti", "francesco totti", "er pupone"],
                "nationality": "Italia",
                "position": "Attaccante",
                "birth_year": 1976,
                "popularity": 5,
                "verified": True,
                "one_club_career": True,
                "career": [
                    {
                        "team": "Roma",
                        "country": "Italia",
                        "league": "Serie A",
                        "start_year": 1992,
                        "end_year": 2017,
                        "apps": 619,
                        "goals": 250,
                    }
                ],
            },
        ],
    }
    with open(players_file, "w", encoding="utf-8") as f:
        json.dump(initial_players, f, indent=2)

    repo = FileCandidatePlayerRepository(storage_dir=cand_dir)
    admin_ids = [100, 200]

    service = CandidateReviewService(
        candidate_repo=repo,
        players_path=players_file,
        backup_dir=backup_dir,
        admin_ids=admin_ids,
        current_year_provider=lambda: 2026,
    )

    return {
        "service": service,
        "repo": repo,
        "players_file": players_file,
        "cand_dir": cand_dir,
        "backup_dir": backup_dir,
        "admin_ids": admin_ids,
        "admin": AdminIdentity(user_id=100, username="superadmin"),
        "stranger": AdminIdentity(user_id=999, username="random_user"),
    }


def create_sample_candidate(
    cand_id: str = "cand_sample_1",
    name: str = "Alessandro Del Piero",
    state: CandidateState = CandidateState.READY,
    source: str = "wikipedia",
    career: list[dict[str, Any]] | None = None,
    revision: int = 1,
    birth_year: int = 1974,
    aliases: list[str] | None = None,
) -> CandidatePlayer:
    if career is None:
        career = [
            {
                "team": "Padova",
                "country": "Italia",
                "league": "Serie B",
                "start_year": 1991,
                "end_year": 1993,
                "apps": 14,
                "goals": 1,
            },
            {
                "team": "Juventus",
                "country": "Italia",
                "league": "Serie A",
                "start_year": 1993,
                "end_year": 2012,
                "apps": 513,
                "goals": 208,
            },
        ]

    if aliases is None:
        aliases = [name.lower()]
        parts = name.split()
        if len(parts) > 1:
            aliases.append(parts[-1].lower())

    cand = CandidatePlayer(
        candidate_id=cand_id,
        source=source,
        source_id="item_sample",
        _status=state,
        revision=revision,
        full_name=name,
        aliases=aliases,
        nationality="Italia",
        position="Attaccante",
        birth_year=birth_year,
        popularity=5,
        career=career,
    )
    return cand


# ---------------------------------------------------------------------------
# 1. Review Queue & Projections
# ---------------------------------------------------------------------------

def test_list_reviewable_candidates(temp_env):
    service = temp_env["service"]
    repo = temp_env["repo"]
    admin = temp_env["admin"]

    c1 = create_sample_candidate("cand_1", "Player One", state=CandidateState.READY)
    c2 = create_sample_candidate("cand_2", "Player Two", state=CandidateState.VALIDATED)
    c3 = create_sample_candidate("cand_3", "Player Three", state=CandidateState.REVIEW_REQUIRED)

    repo.save(c1)
    repo.save(c2)
    repo.save(c3)

    page = service.list_queue(admin)
    assert page.total == 3
    ids = {item.candidate_id for item in page.items}
    assert ids == {"cand_1", "cand_2", "cand_3"}


def test_exclude_terminal_candidates(temp_env):
    service = temp_env["service"]
    repo = temp_env["repo"]
    admin = temp_env["admin"]

    c1 = create_sample_candidate("cand_ready", "Player Ready", state=CandidateState.READY)
    c2 = create_sample_candidate("cand_app", "Player Approved", state=CandidateState.APPROVED)
    c3 = create_sample_candidate("cand_rej", "Player Rejected", state=CandidateState.REJECTED)

    repo.save(c1)
    repo.save(c2)
    repo.save(c3)

    page = service.list_queue(admin)
    assert page.total == 1
    assert page.items[0].candidate_id == "cand_ready"


def test_queue_filtering(temp_env):
    service = temp_env["service"]
    repo = temp_env["repo"]
    admin = temp_env["admin"]

    c1 = create_sample_candidate("cand_1", "Zinedine Zidane", source="wikipedia", state=CandidateState.READY)
    c2 = create_sample_candidate("cand_2", "Thierry Henry", source="wikidata", state=CandidateState.VALIDATED)
    c3 = create_sample_candidate("cand_3", "Patrick Vieira", source="wikipedia", state=CandidateState.REVIEW_REQUIRED)
    c3.validation_warnings.append("Warning check")

    repo.save(c1)
    repo.save(c2)
    repo.save(c3)

    # Filter by state
    p_ready = service.list_queue(admin, state=CandidateState.READY)
    assert p_ready.total == 1
    assert p_ready.items[0].full_name == "Zinedine Zidane"

    # Filter by source
    p_wiki = service.list_queue(admin, source="wikidata")
    assert p_wiki.total == 1
    assert p_wiki.items[0].full_name == "Thierry Henry"

    # Filter by warnings
    p_warn = service.list_queue(admin, has_warnings=True)
    assert p_warn.total == 1
    assert p_warn.items[0].full_name == "Patrick Vieira"

    # Search by name
    p_search = service.list_queue(admin, search="zidane")
    assert p_search.total == 1
    assert p_search.items[0].candidate_id == "cand_1"


def test_queue_pagination_bounds(temp_env):
    service = temp_env["service"]
    repo = temp_env["repo"]
    admin = temp_env["admin"]

    for i in range(15):
        c = create_sample_candidate(f"cand_{i:02d}", f"Player {i:02d}", state=CandidateState.READY)
        repo.save(c)

    p1 = service.list_queue(admin, limit=5, offset=0)
    assert p1.total == 15
    assert len(p1.items) == 5

    p2 = service.list_queue(admin, limit=5, offset=5)
    assert len(p2.items) == 5
    assert p1.items[0].candidate_id != p2.items[0].candidate_id

    # Bound clamps
    p_clamp = service.list_queue(admin, limit=500, offset=-10)
    assert p_clamp.limit == 100
    assert p_clamp.offset == 0


def test_detail_projection_sanitized(temp_env):
    service = temp_env["service"]
    repo = temp_env["repo"]
    admin = temp_env["admin"]

    c = create_sample_candidate("cand_proj", "Andrea Pirlo", state=CandidateState.READY)
    c.raw_data = {"internal_provider_id": "fixture_internal_val", "raw_provider_dump": {"xyz": 123}}
    c.metadata["telegram_init_data"] = "user_id=123&auth_date=1600000000"
    repo.save(c)

    proj = service.get_candidate_detail(admin, "cand_proj")
    assert proj.candidate_id == "cand_proj"
    assert proj.full_name == "Andrea Pirlo"
    assert proj.revision == 1

    d = proj.to_dict()
    # Ensure sensitive raw structures are omitted from projection
    assert "raw_data" not in d
    assert "telegram_init_data" not in json.dumps(d)


def test_duplicate_suggestions(temp_env):
    # Production dataset has Messi (1987, Argentina, Barcelona/PSG) and Totti (1976, Italia, Roma)
    prod_players = temp_env["service"]._load_production_players()

    # Exact name match
    cand_messi = create_sample_candidate("c_m", "Lionel Messi", state=CandidateState.READY)
    dups_m = find_possible_duplicates(cand_messi, prod_players)
    assert len(dups_m) >= 1
    assert dups_m[0].player_id == "messi"
    assert dups_m[0].confidence >= 0.95

    # Alias match
    cand_totti_alias = create_sample_candidate("c_t", "Er Pupone", state=CandidateState.READY)
    dups_t = find_possible_duplicates(cand_totti_alias, prod_players)
    assert len(dups_t) >= 1
    assert dups_t[0].player_id == "totti"

    # Career overlap match: candidate playing for Barcelona and PSG
    cand_career_overlap = create_sample_candidate(
        "c_overlap",
        "Different Name",
        state=CandidateState.READY,
        career=[
            {"team": "Barcelona", "country": "Spagna", "league": "La Liga", "start_year": 2010, "end_year": 2015},
            {"team": "Paris Saint-Germain", "country": "Francia", "league": "Ligue 1", "start_year": 2015, "end_year": 2020},
        ],
    )
    dups_overlap = find_possible_duplicates(cand_career_overlap, prod_players)
    assert any(d.player_id == "messi" for d in dups_overlap)


# ---------------------------------------------------------------------------
# 2. Authorization
# ---------------------------------------------------------------------------

def test_authorized_admin_permitted(temp_env):
    service = temp_env["service"]
    admin = temp_env["admin"]
    # Does not raise
    page = service.list_queue(admin)
    assert isinstance(page.items, list)


def test_unauthenticated_rejected(temp_env):
    service = temp_env["service"]
    with pytest.raises(ReviewAuthError):
        service.list_queue(None)  # type: ignore[arg-type]


def test_invalid_auth_rejected(temp_env):
    service = temp_env["service"]
    with pytest.raises(ReviewAuthError):
        service.list_queue("not_an_admin_identity")  # type: ignore[arg-type]


def test_normal_user_forbidden(temp_env):
    service = temp_env["service"]
    stranger = temp_env["stranger"]
    with pytest.raises(ReviewForbiddenError):
        service.list_queue(stranger)


# ---------------------------------------------------------------------------
# 3. Approve & Production Safety
# ---------------------------------------------------------------------------

def test_approve_valid_ready_candidate(temp_env):
    service = temp_env["service"]
    repo = temp_env["repo"]
    admin = temp_env["admin"]

    cand = create_sample_candidate("cand_delpiero", "Alessandro Del Piero", state=CandidateState.READY)
    repo.save(cand)

    result = service.approve(admin, "cand_delpiero", expected_revision=1)
    assert result.success is True
    assert result.status == ReviewStatus.SUCCESS
    assert result.promoted_player_id == "alessandro_del_piero"

    # Verify candidate updated
    updated_cand = repo.get_by_id("cand_delpiero")
    assert updated_cand.status == CandidateState.APPROVED
    assert updated_cand.revision == 2
    assert updated_cand.metadata["promoted_player_id"] == "alessandro_del_piero"
    assert len(updated_cand.state_history) == 1

    # Verify production dataset updated
    prod_players = service._load_production_players()
    del_piero_prod = next((p for p in prod_players if p["id"] == "alessandro_del_piero"), None)
    assert del_piero_prod is not None
    assert del_piero_prod["full_name"] == "Alessandro Del Piero"
    assert del_piero_prod["verified"] is True
    assert len(del_piero_prod["career"]) == 2
    assert del_piero_prod["source"] == "wikipedia"
    assert del_piero_prod["source_id"] == "item_sample"
    assert del_piero_prod["active"] is False  # career ends 2012, well in the past
    assert "career_last_checked_at" in del_piero_prod


def test_approve_valid_validated_candidate(temp_env):
    service = temp_env["service"]
    repo = temp_env["repo"]
    admin = temp_env["admin"]

    cand = create_sample_candidate("cand_val", "Gianluigi Buffon", state=CandidateState.VALIDATED)
    cand.career = [
        {"team": "Parma", "country": "Italia", "league": "Serie A", "start_year": 1995, "end_year": 2001, "apps": 168, "goals": 0},
        {"team": "Juventus", "country": "Italia", "league": "Serie A", "start_year": 2001, "end_year": 2018, "apps": 509, "goals": 0},
    ]
    repo.save(cand)

    result = service.approve(admin, "cand_val", expected_revision=1)
    assert result.success is True
    assert result.status == ReviewStatus.SUCCESS
    assert result.promoted_player_id == "gianluigi_buffon"


def test_approve_stale_revision_rejected(temp_env):
    service = temp_env["service"]
    repo = temp_env["repo"]
    admin = temp_env["admin"]

    cand = create_sample_candidate("cand_stale", "Paolo Maldini", state=CandidateState.READY, revision=4)
    repo.save(cand)

    # Reviewer sends expected_revision=3 when actual is 4
    result = service.approve(admin, "cand_stale", expected_revision=3)
    assert result.success is False
    assert result.status == ReviewStatus.STALE_REVISION


def test_approve_invalid_fsm_state_rejected(temp_env):
    service = temp_env["service"]
    repo = temp_env["repo"]
    admin = temp_env["admin"]

    cand = create_sample_candidate("cand_disc", "Future Star", state=CandidateState.DISCOVERED)
    repo.save(cand)

    result = service.approve(admin, "cand_disc", expected_revision=1)
    assert result.success is False
    assert result.status == ReviewStatus.INVALID_STATE


def test_approve_unresolved_blocking_error_rejected(temp_env):
    service = temp_env["service"]
    repo = temp_env["repo"]
    admin = temp_env["admin"]

    # Candidate with empty career (blocking error)
    cand = create_sample_candidate("cand_err", "Broken Career", state=CandidateState.REVIEW_REQUIRED, career=[])
    repo.save(cand)

    result = service.approve(admin, "cand_err", expected_revision=1)
    assert result.success is False
    assert result.status == ReviewStatus.UNRESOLVED_CONFLICT


def test_approve_idempotent_retry(temp_env):
    service = temp_env["service"]
    repo = temp_env["repo"]
    admin = temp_env["admin"]

    cand = create_sample_candidate("cand_idem", "Roberto Baggio", state=CandidateState.READY)
    repo.save(cand)

    res1 = service.approve(admin, "cand_idem", expected_revision=1)
    assert res1.success is True
    assert res1.status == ReviewStatus.SUCCESS

    # Second approval call
    res2 = service.approve(admin, "cand_idem", expected_revision=2)
    assert res2.success is True
    assert res2.status == ReviewStatus.ALREADY_PROCESSED
    assert res2.promoted_player_id == res1.promoted_player_id

    # Verify no duplicate player in data/players.json
    prod_players = service._load_production_players()
    baggio_entries = [p for p in prod_players if p["id"] == "roberto_baggio"]
    assert len(baggio_entries) == 1


def test_approve_production_id_collision_handling(temp_env):
    service = temp_env["service"]
    repo = temp_env["repo"]
    admin = temp_env["admin"]

    # Candidate with duplicate player_id_override ("messi" already in production)
    cand_dup = create_sample_candidate("cand_dup", "Another Messi", state=CandidateState.READY)
    cand_dup.aliases = ["another messi"]
    repo.save(cand_dup)

    result_override = service.approve(admin, "cand_dup", expected_revision=1, player_id_override="messi")
    assert result_override.success is False
    assert result_override.status == ReviewStatus.DUPLICATE_PLAYER

    # Candidate with distinct valid name and career
    cand_christian = create_sample_candidate(
        "cand_christian",
        "Christian Totti",
        state=CandidateState.READY,
        birth_year=2005,
        aliases=["christian totti", "c totti"],
        career=[
            {"team": "Frosinone", "country": "Italia", "league": "Serie A", "start_year": 2023, "end_year": 2024, "apps": 5, "goals": 0},
            {"team": "Rayo Vallecano", "country": "Spagna", "league": "La Liga", "start_year": 2024, "end_year": 2026, "apps": 10, "goals": 1},
        ],
    )
    repo.save(cand_christian)
    result_auto = service.approve(admin, "cand_christian", expected_revision=1)
    assert result_auto.success is True
    assert result_auto.promoted_player_id == "christian_totti"


def test_approve_backup_created_and_dataset_valid(temp_env):
    service = temp_env["service"]
    repo = temp_env["repo"]
    admin = temp_env["admin"]
    backup_dir = temp_env["backup_dir"]

    cand = create_sample_candidate("cand_bk", "Fabio Cannavaro", state=CandidateState.READY)
    repo.save(cand)

    result = service.approve(admin, "cand_bk", expected_revision=1)
    assert result.success is True

    # Verify backup exists
    backups = list(backup_dir.glob("players-review-*.json"))
    assert len(backups) >= 1

    # Verify dataset is strictly valid
    prod_players = service._load_production_players()
    assert validate_dataset(prod_players) == []


def test_approve_failure_rollback_preserves_production(temp_env, monkeypatch):
    service = temp_env["service"]
    repo = temp_env["repo"]
    admin = temp_env["admin"]

    cand = create_sample_candidate("cand_crash", "Crash Test Dummy", state=CandidateState.READY)
    repo.save(cand)

    before_players = service._load_production_players()

    # Simulate crash during candidate save after production write
    def crashing_save(*args, **kwargs):
        raise RuntimeError("Simulated database crash")

    monkeypatch.setattr(repo, "save_if_revision", crashing_save)
    monkeypatch.setattr(repo, "save", crashing_save)

    result = service.approve(admin, "cand_crash", expected_revision=1)
    assert result.success is False
    assert result.status == ReviewStatus.PERSISTENCE_FAILURE

    # Verify production dataset was rolled back to original state
    after_players = service._load_production_players()
    assert len(after_players) == len(before_players)
    assert not any(p["id"] == "crash_test_dummy" for p in after_players)


# ---------------------------------------------------------------------------
# 4. Edit-before-approve
# ---------------------------------------------------------------------------

def test_edit_allowed_fields(temp_env):
    service = temp_env["service"]
    repo = temp_env["repo"]
    admin = temp_env["admin"]

    cand = create_sample_candidate(
        "cand_edit",
        "Giorgio Chiellini",
        state=CandidateState.READY,
        birth_year=1984,
        career=[
            {"team": "Livorno", "country": "Italia", "league": "Serie B", "start_year": 2000, "end_year": 2004, "apps": 55, "goals": 4},
            {"team": "Juventus", "country": "Italia", "league": "Serie A", "start_year": 2005, "end_year": 2022, "apps": 425, "goals": 27},
        ],
    )
    repo.save(cand)

    updates = {
        "full_name": "Giorgio Chiellini",
        "nationality": "Italia",
        "birth_year": 1984,
        "popularity": 5,
        "aliases": ["chiellini", "giorgione"],
    }
    result = service.edit(admin, "cand_edit", expected_revision=1, updates=updates, reason="Aggiunto alias e corretto anno")
    assert result.success is True
    assert result.status == ReviewStatus.SUCCESS

    updated = repo.get_by_id("cand_edit")
    assert updated.birth_year == 1984
    assert updated.revision == 2
    assert "chiellini" in updated.aliases

    # Verify audit event
    events = updated.metadata.get("review_events", [])
    assert len(events) == 1
    assert events[0]["action"] == ReviewAction.EDIT.value
    assert events[0]["reason"] == "Aggiunto alias e corretto anno"


def test_edit_forbidden_fields_rejected(temp_env):
    service = temp_env["service"]
    repo = temp_env["repo"]
    admin = temp_env["admin"]

    cand = create_sample_candidate("cand_hacker", "Legit Player", state=CandidateState.READY)
    repo.save(cand)

    # Attempt to illegally mutate state, revision, or candidate_id
    updates = {
        "status": "APPROVED",
        "revision": 999,
        "candidate_id": "malicious_id",
    }
    result = service.edit(admin, "cand_hacker", expected_revision=1, updates=updates)
    assert result.success is False
    assert result.status == ReviewStatus.FORBIDDEN_FIELD

    # Verify candidate was not mutated
    c_after = repo.get_by_id("cand_hacker")
    assert c_after.status == CandidateState.READY
    assert c_after.revision == 1


def test_edit_reruns_normalization_and_validation(temp_env):
    service = temp_env["service"]
    repo = temp_env["repo"]
    admin = temp_env["admin"]

    cand = create_sample_candidate("cand_norm", "Pau Gasol", state=CandidateState.VALIDATED)
    repo.save(cand)

    # Edit into invalid career: empty career list
    result = service.edit(admin, "cand_norm", expected_revision=1, updates={"career": []})
    assert result.success is True

    # State should automatically move to REVIEW_REQUIRED due to blocking validation error
    updated = repo.get_by_id("cand_norm")
    assert updated.status == CandidateState.REVIEW_REQUIRED
    assert len(updated.validation_errors) > 0


def test_edit_stale_revision_rejected(temp_env):
    service = temp_env["service"]
    repo = temp_env["repo"]
    admin = temp_env["admin"]

    cand = create_sample_candidate("cand_stale_edit", "Player Stale", state=CandidateState.READY, revision=3)
    repo.save(cand)

    result = service.edit(admin, "cand_stale_edit", expected_revision=2, updates={"full_name": "New Name"})
    assert result.success is False
    assert result.status == ReviewStatus.STALE_REVISION


# ---------------------------------------------------------------------------
# 5. Reject
# ---------------------------------------------------------------------------

def test_reject_valid_candidate(temp_env):
    service = temp_env["service"]
    repo = temp_env["repo"]
    admin = temp_env["admin"]

    cand = create_sample_candidate("cand_rej", "Invalid Candidate", state=CandidateState.REVIEW_REQUIRED)
    repo.save(cand)

    result = service.reject(admin, "cand_rej", expected_revision=1, reason="Carriera incompleta e fonti discordanti")
    assert result.success is True
    assert result.status == ReviewStatus.SUCCESS

    updated = repo.get_by_id("cand_rej")
    assert updated.status == CandidateState.REJECTED
    assert updated.is_terminal() is True
    assert updated.state_history[-1].reason == "Carriera incompleta e fonti discordanti"


def test_reject_idempotent(temp_env):
    service = temp_env["service"]
    repo = temp_env["repo"]
    admin = temp_env["admin"]

    cand = create_sample_candidate("cand_rej_idemp", "Reject Idemp", state=CandidateState.REVIEW_REQUIRED)
    repo.save(cand)

    res1 = service.reject(admin, "cand_rej_idemp", expected_revision=1, reason="Not football player")
    assert res1.success is True

    res2 = service.reject(admin, "cand_rej_idemp", expected_revision=2, reason="Not football player")
    assert res2.success is True
    assert res2.status == ReviewStatus.ALREADY_PROCESSED


def test_terminal_candidate_cannot_reenter(temp_env):
    service = temp_env["service"]
    repo = temp_env["repo"]
    admin = temp_env["admin"]

    cand = create_sample_candidate("cand_term", "Terminal Player", state=CandidateState.REJECTED)
    repo.save(cand)

    # Attempt to approve
    res_app = service.approve(admin, "cand_term", expected_revision=1)
    assert res_app.success is False
    assert res_app.status == ReviewStatus.INVALID_STATE

    # Attempt to edit
    res_edit = service.edit(admin, "cand_term", expected_revision=1, updates={"full_name": "New"})
    assert res_edit.success is False
    assert res_edit.status == ReviewStatus.INVALID_STATE

    # Attempt to retry
    res_retry = service.retry_ingestion(admin, "cand_term", expected_revision=1)
    assert res_retry.success is False
    assert res_retry.status == ReviewStatus.INVALID_STATE


# ---------------------------------------------------------------------------
# 6. Merge
# ---------------------------------------------------------------------------

def test_merge_valid_target_player(temp_env):
    service = temp_env["service"]
    repo = temp_env["repo"]
    admin = temp_env["admin"]

    cand = create_sample_candidate("cand_merge", "Leo Messi", state=CandidateState.READY)
    repo.save(cand)

    result = service.merge(admin, "cand_merge", expected_revision=1, target_player_id="messi", reason="Duplicato di Messi")
    assert result.success is True
    assert result.status == ReviewStatus.SUCCESS
    assert result.promoted_player_id == "messi"

    updated = repo.get_by_id("cand_merge")
    assert updated.status == CandidateState.APPROVED
    assert updated.metadata["review_decision"] == "MERGED"
    assert updated.metadata["merged_into_player_id"] == "messi"

    # Verify no duplicate player in data/players.json
    prod_players = service._load_production_players()
    assert len([p for p in prod_players if p["id"] == "messi"]) == 1
    assert not any(p["id"] == "cand_merge" for p in prod_players)


def test_merge_nonexistent_target_rejected(temp_env):
    service = temp_env["service"]
    repo = temp_env["repo"]
    admin = temp_env["admin"]

    cand = create_sample_candidate("cand_merge_ghost", "Ghost Player", state=CandidateState.READY)
    repo.save(cand)

    result = service.merge(admin, "cand_merge_ghost", expected_revision=1, target_player_id="nonexistent_id", reason="Test")
    assert result.success is False
    assert result.status == ReviewStatus.INVALID_MERGE_TARGET


def test_merge_idempotent(temp_env):
    service = temp_env["service"]
    repo = temp_env["repo"]
    admin = temp_env["admin"]

    cand = create_sample_candidate("cand_merge_idemp", "Leo Messi", state=CandidateState.READY)
    repo.save(cand)

    res1 = service.merge(admin, "cand_merge_idemp", expected_revision=1, target_player_id="messi", reason="Merge 1")
    assert res1.success is True

    res2 = service.merge(admin, "cand_merge_idemp", expected_revision=2, target_player_id="messi", reason="Merge 2")
    assert res2.success is True
    assert res2.status == ReviewStatus.ALREADY_PROCESSED


# ---------------------------------------------------------------------------
# 7. Source Wrong
# ---------------------------------------------------------------------------

def test_source_wrong_recorded(temp_env):
    service = temp_env["service"]
    repo = temp_env["repo"]
    admin = temp_env["admin"]

    cand = create_sample_candidate("cand_bad_src", "Bad Data", state=CandidateState.REVIEW_REQUIRED)
    repo.save(cand)

    result = service.mark_source_wrong(admin, "cand_bad_src", expected_revision=1, source="wikipedia", reason="Vandalismo pagina")
    assert result.success is True
    assert result.status == ReviewStatus.SUCCESS

    updated = repo.get_by_id("cand_bad_src")
    assert updated.status == CandidateState.REVIEW_REQUIRED
    assert updated.metadata["source_unreliable"] is True
    assert any(s["source"] == "wikipedia" for s in updated.metadata.get("unreliable_sources", []))


# ---------------------------------------------------------------------------
# 8. Retry
# ---------------------------------------------------------------------------

def test_retry_uses_existing_pipeline(temp_env):
    service = temp_env["service"]
    repo = temp_env["repo"]
    admin = temp_env["admin"]

    cand = create_sample_candidate("cand_retry", "Incomplete Player", state=CandidateState.REVIEW_REQUIRED, career=[])
    repo.save(cand)

    # Mock adapter fetcher that returns complete fresh data
    def mock_fetcher(source: str, source_id: str):
        return AdapterResult(
            source_name=source,
            source_id=source_id,
            success=True,
            player_name="Fresh Ingested Name",
            nationality="Italia",
            birth_year=1980,
            position="Difensore",
            career=[
                CareerEntry(team="Milan", country="Italia", league="Serie A", start_year=2000, end_year=2010),
                CareerEntry(team="Monza", country="Italia", league="Serie B", start_year=2010, end_year=2012),
            ],
        )

    result = service.retry_ingestion(admin, "cand_retry", expected_revision=1, adapter_fetcher=mock_fetcher)
    assert result.success is True
    assert result.status == ReviewStatus.SUCCESS

    updated = repo.get_by_id("cand_retry")
    # Fresh data has no errors, so state should advance to VALIDATED
    assert updated.status == CandidateState.VALIDATED
    assert updated.full_name == "Fresh Ingested Name"
    assert updated.revision >= 2


def test_retry_illegal_state_rejected(temp_env):
    service = temp_env["service"]
    repo = temp_env["repo"]
    admin = temp_env["admin"]

    cand = create_sample_candidate("cand_app_no_retry", "Approved Player", state=CandidateState.APPROVED)
    repo.save(cand)

    result = service.retry_ingestion(admin, "cand_app_no_retry", expected_revision=1)
    assert result.success is False
    assert result.status == ReviewStatus.INVALID_STATE


# ---------------------------------------------------------------------------
# 9. Data Integrity & Hardening
# ---------------------------------------------------------------------------

def test_make_production_player_id_determinism_and_collision():
    existing = {"francesco_totti", "lionel_messi"}
    pid1 = make_production_player_id("Alessandro Del Piero", existing, birth_year=1974)
    assert pid1 == "alessandro_del_piero"

    # Collision resolution
    pid_col = make_production_player_id("Francesco Totti", existing, birth_year=1976)
    assert pid_col == "francesco_totti_1976"

    # Multiple collisions
    existing.add("francesco_totti_1976")
    pid_col2 = make_production_player_id("Francesco Totti", existing, birth_year=1976)
    assert pid_col2 == "francesco_totti_2"


def test_path_traversal_rejection(temp_env):
    repo = temp_env["repo"]
    with pytest.raises(ValueError, match="candidate_id non valido per il filesystem"):
        repo.get_by_id("../../etc/passwd")


def test_interrupted_write_preserves_production_dataset(temp_env):
    service = temp_env["service"]
    before = service._load_production_players()
    assert len(before) == 2

    # Verify writing invalid players raises and doesn't destroy original file
    with pytest.raises(Exception):
        # Pass something un-dumpable
        service._atomic_write_production_dataset([{"bad_object": object()}])

    after = service._load_production_players()
    assert len(after) == 2


# ---------------------------------------------------------------------------
# 10. Concurrency & Race Condition Regressions (#15)
# ---------------------------------------------------------------------------

def test_concurrent_two_reviewers_same_candidate_race(temp_env):
    """Two reviewers operating from the same initial revision race to mutate the same candidate."""
    service = temp_env["service"]
    repo = temp_env["repo"]
    admin1 = AdminIdentity(user_id=100, username="admin1")
    admin2 = AdminIdentity(user_id=200, username="admin2")

    cand = create_sample_candidate("cand_race_cas", "Concurrency Candidate", state=CandidateState.READY)
    repo.save(cand)

    def op_edit():
        return service.edit(admin1, "cand_race_cas", expected_revision=1, updates={"popularity": 4})

    def op_reject():
        return service.reject(admin2, "cand_race_cas", expected_revision=1, reason="Conflicting info")

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(op_edit)
        f2 = executor.submit(op_reject)
        r1 = f1.result()
        r2 = f2.result()

    successes = [r for r in (r1, r2) if r.success and r.status == ReviewStatus.SUCCESS]
    stales = [r for r in (r1, r2) if not r.success and r.status == ReviewStatus.STALE_REVISION]

    assert len(successes) == 1, f"Expected exactly 1 winner, got {len(successes)}"
    assert len(stales) == 1, f"Expected exactly 1 stale rejection, got {len(stales)}"

    final_cand = repo.get_by_id("cand_race_cas")
    assert final_cand.revision == 2
    if successes[0].status == ReviewStatus.SUCCESS and successes[0] == r1:
        assert final_cand.popularity == 4
    else:
        assert final_cand.status == CandidateState.REJECTED


def test_concurrent_two_different_candidates_approved_both_survive(temp_env):
    """Two distinct candidates approved concurrently must both survive in data/players.json without lost updates."""
    service = temp_env["service"]
    repo = temp_env["repo"]
    admin1 = AdminIdentity(user_id=100, username="admin1")
    admin2 = AdminIdentity(user_id=200, username="admin2")

    c1 = create_sample_candidate(
        "cand_c1", "Xavi Hernandez", state=CandidateState.READY, birth_year=1980, aliases=["xavi hernandez"]
    )
    c1.career = [
        {"team": "Barcelona", "country": "Spagna", "league": "La Liga", "start_year": 1998, "end_year": 2015, "apps": 505, "goals": 58},
        {"team": "Al-Sadd", "country": "Qatar", "league": "Qatar Stars League", "start_year": 2015, "end_year": 2019, "apps": 82, "goals": 21},
    ]
    repo.save(c1)

    c2 = create_sample_candidate(
        "cand_c2", "Andres Iniesta", state=CandidateState.READY, birth_year=1984, aliases=["andres iniesta"]
    )
    c2.career = [
        {"team": "Barcelona", "country": "Spagna", "league": "La Liga", "start_year": 2002, "end_year": 2018, "apps": 442, "goals": 35},
        {"team": "Vissel Kobe", "country": "Giappone", "league": "J1 League", "start_year": 2018, "end_year": 2023, "apps": 114, "goals": 21},
    ]
    repo.save(c2)

    def approve_c1():
        return service.approve(admin1, "cand_c1", expected_revision=1, allow_warnings=True)

    def approve_c2():
        return service.approve(admin2, "cand_c2", expected_revision=1, allow_warnings=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(approve_c1)
        f2 = executor.submit(approve_c2)
        r1 = f1.result()
        r2 = f2.result()

    assert r1.success is True, f"Approval 1 failed: {r1.message}"
    assert r2.success is True, f"Approval 2 failed: {r2.message}"

    players = service._load_production_players()
    player_ids = [p["id"] for p in players]

    # Both initial base players (messi, totti) and both new players must be in production
    assert "messi" in player_ids
    assert "totti" in player_ids
    assert "xavi_hernandez" in player_ids
    assert "andres_iniesta" in player_ids
    assert len(players) == 4
    assert len(set(player_ids)) == 4


def test_concurrent_generated_id_collision_handling(temp_env):
    """Two candidates resolving to colliding production IDs must re-evaluate inside mutation lock."""
    service = temp_env["service"]
    repo = temp_env["repo"]
    admin1 = AdminIdentity(user_id=100, username="admin1")
    admin2 = AdminIdentity(user_id=200, username="admin2")

    c1 = create_sample_candidate(
        "cand_ron_1", "Ronaldo Nazario", state=CandidateState.READY, birth_year=1976, aliases=["ronaldo nazario"]
    )
    c1.career = [
        {"team": "Cruzeiro", "country": "Brasile", "league": "Brasileirão", "start_year": 1993, "end_year": 1994, "apps": 14, "goals": 12},
        {"team": "PSV", "country": "Olanda", "league": "Eredivisie", "start_year": 1994, "end_year": 1996, "apps": 46, "goals": 42},
    ]
    repo.save(c1)

    c2 = create_sample_candidate(
        "cand_ron_2", "Cristiano Ronaldo", state=CandidateState.READY, birth_year=1985, aliases=["cristiano ronaldo"]
    )
    c2.career = [
        {"team": "Sporting CP", "country": "Portogallo", "league": "Primeira Liga", "start_year": 2002, "end_year": 2003, "apps": 25, "goals": 3},
        {"team": "Manchester United", "country": "Inghilterra", "league": "Premier League", "start_year": 2003, "end_year": 2009, "apps": 196, "goals": 84},
    ]
    repo.save(c2)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(lambda: service.approve(admin1, "cand_ron_1", expected_revision=1, player_id_override="the_legend", allow_warnings=True))
        f2 = executor.submit(lambda: service.approve(admin2, "cand_ron_2", expected_revision=1, player_id_override="the_legend", allow_warnings=True))
        r1 = f1.result()
        r2 = f2.result()

    successes = [r for r in (r1, r2) if r.success and r.status == ReviewStatus.SUCCESS]
    failures = [r for r in (r1, r2) if not r.success and r.status == ReviewStatus.DUPLICATE_PLAYER]

    assert len(successes) == 1, f"Expected 1 winner, got {len(successes)}"
    assert len(failures) == 1, f"Expected 1 duplicate rejection, got {len(failures)}"
    assert failures[0].status == ReviewStatus.DUPLICATE_PLAYER

    players = service._load_production_players()
    ids = [p["id"] for p in players]
    assert "the_legend" in ids
    assert ids.count("the_legend") == 1


def test_candidate_persistence_failure_rollback_isolation(temp_env, monkeypatch):
    """Candidate persistence failure rolls back only its own candidate, preserving prior approvals."""
    service = temp_env["service"]
    repo = temp_env["repo"]
    admin = temp_env["admin"]

    # Candidate 1 approves normally
    c1 = create_sample_candidate("cand_prior", "Prior Player", state=CandidateState.READY, aliases=["prior player"])
    repo.save(c1)
    res1 = service.approve(admin, "cand_prior", expected_revision=1)
    assert res1.success is True

    # Candidate 2 fails during candidate persistence
    c2 = create_sample_candidate("cand_fail_save", "Fail Save Player", state=CandidateState.READY, aliases=["fail save player"])
    repo.save(c2)

    orig_save_if_rev = repo.save_if_revision
    def crashing_save(cand, expected_persisted_revision):
        if cand.candidate_id == "cand_fail_save":
            raise RuntimeError("Disk write failed on candidate file")
        return orig_save_if_rev(cand, expected_persisted_revision)

    monkeypatch.setattr(repo, "save_if_revision", crashing_save)

    res2 = service.approve(admin, "cand_fail_save", expected_revision=1)
    assert res2.success is False
    assert res2.status == ReviewStatus.PERSISTENCE_FAILURE

    # Candidate 1 is still safely in production!
    players = service._load_production_players()
    p_ids = [p["id"] for p in players]
    assert "prior_player" in p_ids
    assert "fail_save_player" not in p_ids


def test_missing_production_dataset_fails_closed(temp_env):
    """If data/players.json is missing, approval fails closed without mutating candidate or creating file."""
    service = temp_env["service"]
    repo = temp_env["repo"]
    admin = temp_env["admin"]

    cand = create_sample_candidate("cand_miss", "Missing File Player", state=CandidateState.READY)
    repo.save(cand)

    # Delete players.json
    players_path = Path(service._players_path)
    if players_path.is_file():
        players_path.unlink()

    res = service.approve(admin, "cand_miss", expected_revision=1)
    assert res.success is False
    assert res.status == ReviewStatus.PERSISTENCE_FAILURE
    assert not players_path.is_file()

    # Candidate untouched
    unchanged = repo.get_by_id("cand_miss")
    assert unchanged.status == CandidateState.READY
    assert unchanged.revision == 1


def test_malformed_production_dataset_fails_closed(temp_env):
    """If data/players.json is corrupt/malformed, approval fails closed without modifying dataset."""
    service = temp_env["service"]
    repo = temp_env["repo"]
    admin = temp_env["admin"]

    cand = create_sample_candidate("cand_malf", "Malformed File Player", state=CandidateState.READY)
    repo.save(cand)

    players_path = Path(service._players_path)
    with open(players_path, "w", encoding="utf-8") as f:
        f.write("{corrupt_json_syntax: true")

    res = service.approve(admin, "cand_malf", expected_revision=1)
    assert res.success is False
    assert res.status == ReviewStatus.PERSISTENCE_FAILURE

    unchanged = repo.get_by_id("cand_malf")
    assert unchanged.status == CandidateState.READY
    assert unchanged.revision == 1


def test_unique_backups_within_same_second(temp_env):
    """Multiple backups created in rapid succession generate collision-free unique filenames."""
    service = temp_env["service"]
    filenames = set()
    for i in range(10):
        fname, dest = service._backup_production_dataset(f"cand_{i}")
        assert dest.is_file()
        filenames.add(fname)

    assert len(filenames) == 10, "Expected 10 unique backup snapshot filenames"


def test_unresolved_provenance_conflict_blocks_approval(temp_env):
    """Candidate with genuine provenance conflict between sources is blocked from production promotion."""
    service = temp_env["service"]
    repo = temp_env["repo"]
    admin = temp_env["admin"]

    cand = create_sample_candidate("cand_conf", "Conflicting Player", state=CandidateState.READY)
    # Add genuine conflict between wikipedia and wikidata
    cand.record_observation(field_path="full_name", source="wikipedia", source_id="wiki_1", raw_value="Wikipedia Name")
    cand.record_observation(field_path="full_name", source="wikidata", source_id="wd_1", raw_value="Wikidata Disagreeing Name")

    repo.save(cand)

    res = service.approve(admin, "cand_conf", expected_revision=1)
    assert res.success is False
    assert res.status == ReviewStatus.UNRESOLVED_CONFLICT
    assert "full_name" in res.conflicts

    # Production dataset unchanged
    players = service._load_production_players()
    assert not any(p["full_name"] == "Conflicting Player" for p in players)


def test_warnings_require_explicit_acceptance(temp_env):
    """Candidate with validation warnings is rejected by default unless allow_warnings=True is passed."""
    service = temp_env["service"]
    repo = temp_env["repo"]
    admin = temp_env["admin"]

    cand = create_sample_candidate("cand_warn_exp", "Warning Player", state=CandidateState.VALIDATED)
    cand.validation_warnings = ["Età anomala rilevata"]
    repo.save(cand)

    # 1. Default allow_warnings=False -> rejected
    res_rejected = service.approve(admin, "cand_warn_exp", expected_revision=1, allow_warnings=False)
    assert res_rejected.success is False
    assert res_rejected.status == ReviewStatus.VALIDATION_FAILED
    assert len(res_rejected.warnings) > 0

    # 2. Explicit allow_warnings=True -> accepted
    res_accepted = service.approve(admin, "cand_warn_exp", expected_revision=1, allow_warnings=True)
    assert res_accepted.success is True
    assert res_accepted.status == ReviewStatus.SUCCESS


def test_edit_from_non_reviewable_state_rejected(temp_env):
    """Edit attempted from a non-reviewable state (e.g. DISCOVERED) returns INVALID_STATE."""
    service = temp_env["service"]
    repo = temp_env["repo"]
    admin = temp_env["admin"]

    cand = create_sample_candidate("cand_disc_edit", "Discovered Player", state=CandidateState.DISCOVERED)
    repo.save(cand)

    res = service.edit(admin, "cand_disc_edit", expected_revision=1, updates={"birth_year": 1990})
    assert res.success is False
    assert res.status == ReviewStatus.INVALID_STATE


def test_merge_from_non_reviewable_state_rejected(temp_env):
    """Merge attempted from a non-reviewable state returns INVALID_STATE."""
    service = temp_env["service"]
    repo = temp_env["repo"]
    admin = temp_env["admin"]

    cand = create_sample_candidate("cand_disc_merge", "Discovered Player", state=CandidateState.DISCOVERED)
    repo.save(cand)

    res = service.merge(admin, "cand_disc_merge", expected_revision=1, target_player_id="messi", reason="Test")
    assert res.success is False
    assert res.status == ReviewStatus.INVALID_STATE


def test_source_wrong_recovery_path(temp_env):
    """Source marked wrong preserves evidence in REVIEW_REQUIRED and allows recovery retry with alternative source."""
    service = temp_env["service"]
    repo = temp_env["repo"]
    admin = temp_env["admin"]

    cand = create_sample_candidate("cand_sw_rec", "Initial Bad Source Player", state=CandidateState.READY)
    repo.save(cand)

    # 1. Mark source wrong
    res_sw = service.mark_source_wrong(admin, "cand_sw_rec", expected_revision=1, source="wikipedia", reason="Fake data")
    assert res_sw.success is True
    assert res_sw.status == ReviewStatus.SUCCESS

    mid_cand = repo.get_by_id("cand_sw_rec")
    assert mid_cand.status == CandidateState.REVIEW_REQUIRED
    assert mid_cand.revision == 2

    # 2. Retry with alternative source B (e.g. wikidata)
    def mock_wikidata_fetcher(source: str, source_id: str):
        return AdapterResult(
            source_name="wikidata",
            source_id="Q9999",
            success=True,
            player_name="Recovered Name",
            nationality="Italia",
            birth_year=1980,
            position="Centrocampista",
            career=[
                CareerEntry(team="Juventus", country="Italia", league="Serie A", start_year=2000, end_year=2010),
                CareerEntry(team="Milan", country="Italia", league="Serie A", start_year=2010, end_year=2015),
            ],
        )

    res_retry = service.retry_ingestion(admin, "cand_sw_rec", expected_revision=2, adapter_fetcher=mock_wikidata_fetcher)
    assert res_retry.success is True
    assert res_retry.status == ReviewStatus.SUCCESS

    final_cand = repo.get_by_id("cand_sw_rec")
    assert final_cand.status == CandidateState.VALIDATED
    assert final_cand.full_name == "Recovered Name"

    # Both events preserved in audit history
    history = final_cand.metadata.get("review_events", [])
    actions = [h["action"] for h in history]
    assert ReviewAction.SOURCE_WRONG.value in actions
    assert ReviewAction.RETRY.value in actions


def test_retry_actually_invokes_existing_ingestion_pipeline(temp_env, monkeypatch):
    """Retry without custom adapter_fetcher actually resolves and invokes standard adapter."""
    service = temp_env["service"]
    repo = temp_env["repo"]
    admin = temp_env["admin"]

    cand = create_sample_candidate("cand_pipe_retry", "Incomplete Player", state=CandidateState.REVIEW_REQUIRED)
    cand.source = "wikipedia"
    cand.source_id = "Sample_Page"
    repo.save(cand)

    called_with = []
    def mock_fetch_player(self, identifier: str):
        called_with.append(identifier)
        return AdapterResult(
            source_name="wikipedia",
            source_id=identifier,
            success=True,
            player_name="Fresh Ingested Name",
            nationality="Italia",
            birth_year=1982,
            position="Difensore",
            career=[
                CareerEntry(team="Inter", country="Italia", league="Serie A", start_year=2002, end_year=2012),
                CareerEntry(team="Roma", country="Italia", league="Serie A", start_year=2012, end_year=2015),
            ],
        )

    from domains.players.adapters.wikipedia import WikipediaAdapter
    monkeypatch.setattr(WikipediaAdapter, "fetch_player", mock_fetch_player)

    res = service.retry_ingestion(admin, "cand_pipe_retry", expected_revision=1, adapter_fetcher=None)
    assert res.success is True
    assert called_with == ["Sample_Page"]

    updated = repo.get_by_id("cand_pipe_retry")
    assert updated.full_name == "Fresh Ingested Name"


def test_retry_without_resolvable_adapter_fails_closed(temp_env):
    """Retry on candidate with unknown source returns SOURCE_ERROR and does not revalidate stale data."""
    service = temp_env["service"]
    repo = temp_env["repo"]
    admin = temp_env["admin"]

    cand = create_sample_candidate("cand_no_adapter", "Stale Player", state=CandidateState.REVIEW_REQUIRED)
    cand.source = "unsupported_foreign_db"
    repo.save(cand)

    res = service.retry_ingestion(admin, "cand_no_adapter", expected_revision=1, adapter_fetcher=None)
    assert res.success is False
    assert res.status == ReviewStatus.SOURCE_ERROR

    unchanged = repo.get_by_id("cand_no_adapter")
    assert unchanged.status == CandidateState.REVIEW_REQUIRED
    assert unchanged.revision == 1


def test_sensitive_exception_details_do_not_leak(temp_env, monkeypatch):
    """Internal filesystem paths and raw exception details do not leak into ReviewResult.message."""
    service = temp_env["service"]
    repo = temp_env["repo"]
    admin = temp_env["admin"]

    cand = create_sample_candidate("cand_leak_test", "Leak Test Player", state=CandidateState.READY)
    repo.save(cand)

    sensitive_path = "C:\\Users\\Coppi\\secret_certs\\production_credentials.pem"

    def leaking_fetcher(*args, **kwargs):
        raise ValueError(f"Crash reading sensitive cert at {sensitive_path}")

    res = service.retry_ingestion(admin, "cand_leak_test", expected_revision=1, adapter_fetcher=leaking_fetcher)
    assert res.success is False
    assert sensitive_path not in res.message
    assert "secret_certs" not in res.message
    assert "Crash reading" not in res.message


# ---------------------------------------------------------------------------
# 11. SOURCE_WRONG → Alternative Source → Approval (regression suite)
# ---------------------------------------------------------------------------

def test_source_wrong_retry_with_explicit_source_uses_real_adapter(temp_env, monkeypatch):
    """End-to-end: SOURCE_WRONG + retry_source → real adapter invoked, old observation preserved, approval succeeds.

    Flow:
    1. Candidate starts with source=wikipedia (wikipedia observation recorded).
    2. Reviewer marks that specific wikipedia entity as SOURCE_WRONG (with source_id).
    3. retry_ingestion(..., retry_source="wikidata", retry_source_id="Q9999") is called without
       adapter_fetcher → the *real* WikidataAdapter.fetch_player must be resolved and invoked.
    4. Wikidata returns a clean result; both wikipedia and wikidata observations are present in provenance.
    5. The wikipedia observation is excluded from blocking-conflict evaluation.
    6. approve_candidate() succeeds and the player lands in the production dataset.
    """
    from domains.players.adapters.base import AdapterResult, CareerEntry
    from domains.players.adapters.wikidata import WikidataAdapter

    service = temp_env["service"]
    repo = temp_env["repo"]
    admin = temp_env["admin"]

    # Set up candidate with wikipedia observation for full_name
    cand = create_sample_candidate(
        "cand_sw_e2e",
        "Wikipedia Wrong Name",
        state=CandidateState.READY,
        source="wikipedia",
    )
    cand.source_id = "Wrong_Wikipedia_Page"
    # Record the wikipedia observation explicitly (simulates a prior populate step)
    cand.record_observation(
        field_path="full_name",
        source="wikipedia",
        source_id="Wrong_Wikipedia_Page",
        raw_value="Wikipedia Wrong Name",
    )
    repo.save(cand)
    rev_after_save = repo.get_by_id("cand_sw_e2e").revision

    # 1. Mark wikipedia entity as SOURCE_WRONG (with source_id)
    res_sw = service.mark_source_wrong(
        admin,
        "cand_sw_e2e",
        expected_revision=rev_after_save,
        source="wikipedia",
        source_id="Wrong_Wikipedia_Page",
        reason="Page was vandalized",
    )
    assert res_sw.success is True, res_sw.message
    mid = repo.get_by_id("cand_sw_e2e")
    assert mid.status == CandidateState.REVIEW_REQUIRED
    assert any(e.get("source_id") == "Wrong_Wikipedia_Page" for e in mid.metadata.get("unreliable_sources", []))

    # 2. Patch WikidataAdapter to avoid real HTTP and verify it is called
    called_with: list[str] = []

    def mock_wikidata_fetch(self: Any, identifier: str) -> AdapterResult:
        called_with.append(identifier)
        return AdapterResult(
            source_name="wikidata",
            source_id=identifier,
            success=True,
            player_name="Wikidata Correct Name",
            nationality="Italia",
            birth_year=1979,
            position="Centrocampista",
            career=[
                CareerEntry(team="Milan", country="Italia", league="Serie A", start_year=1999, end_year=2012),
                CareerEntry(team="Roma", country="Italia", league="Serie A", start_year=2012, end_year=2015),
            ],
        )

    monkeypatch.setattr(WikidataAdapter, "fetch_player", mock_wikidata_fetch)

    # 3. Retry using the real adapter resolver, explicit wikidata source
    rev_before_retry = repo.get_by_id("cand_sw_e2e").revision
    res_retry = service.retry_ingestion(
        admin,
        "cand_sw_e2e",
        expected_revision=rev_before_retry,
        retry_source="wikidata",
        retry_source_id="Q9999",
        # adapter_fetcher deliberately omitted → real resolver path
    )
    assert res_retry.success is True, res_retry.message
    assert called_with == ["Q9999"], "WikidataAdapter.fetch_player must be called with the explicit source_id"

    after_retry = repo.get_by_id("cand_sw_e2e")
    # Active source identity updated to successful retry source
    assert after_retry.source == "wikidata"
    assert after_retry.source_id == "Q9999"
    assert res_retry.projection.source == "wikidata"
    assert res_retry.projection.source_id == "Q9999"
    assert res_retry.projection.has_source_conflicts is False
    # Wikidata player name applied
    assert after_retry.full_name == "Wikidata Correct Name"
    # Both observations still present in provenance (auditable)
    fp = after_retry.provenance.get_provenance_for_path("full_name")
    assert fp is not None
    obs_wiki = fp.get_observation("wikipedia")
    obs_wdata = fp.get_observation("wikidata")
    assert obs_wiki is not None, "Wikipedia observation must remain in provenance"
    assert obs_wdata is not None, "Wikidata observation must be present"
    assert obs_wiki.raw_value == "Wikipedia Wrong Name"
    assert obs_wdata.raw_value == "Wikidata Correct Name"

    # 4. The wikipedia observation is excluded from blocking-conflict evaluation
    from domains.players.candidates.review import get_candidate_provenance_conflicts
    conflicts = get_candidate_provenance_conflicts(after_retry)
    assert "full_name" not in conflicts, (
        f"Wikipedia observation must not create a blocking conflict for full_name. Conflicts: {conflicts}"
    )

    # 5. Review history contains both events
    history = after_retry.metadata.get("review_events", [])
    actions = [h["action"] for h in history]
    assert ReviewAction.SOURCE_WRONG.value in actions
    assert ReviewAction.RETRY.value in actions

    # 6. Approval must succeed
    rev_before_approve = repo.get_by_id("cand_sw_e2e").revision
    res_approve = service.approve_candidate(
        admin,
        "cand_sw_e2e",
        expected_revision=rev_before_approve,
        allow_warnings=True,
    )
    assert res_approve.success is True, f"Approval must succeed after SOURCE_WRONG + retry: {res_approve.message} | conflicts: {res_approve.conflicts}"
    prod = service._load_production_players()
    assert any(p["full_name"] == "Wikidata Correct Name" for p in prod), "Player must be in production dataset"


def test_retry_without_alternative_fails_closed_when_source_marked_unreliable(temp_env, monkeypatch):
    """Retry without retry_source must return SOURCE_ERROR when current source is marked unreliable.

    No adapter must be invoked; the candidate must remain unchanged.
    """
    from domains.players.adapters.wikipedia import WikipediaAdapter

    service = temp_env["service"]
    repo = temp_env["repo"]
    admin = temp_env["admin"]

    cand = create_sample_candidate("cand_sw_blocked", "Blocked Player", state=CandidateState.READY)
    cand.source = "wikipedia"
    cand.source_id = "Vandalized_Page"
    repo.save(cand)

    # Mark wikipedia SOURCE_WRONG (with source_id so identity is precise)
    mid_rev = repo.get_by_id("cand_sw_blocked").revision
    res_sw = service.mark_source_wrong(
        admin,
        "cand_sw_blocked",
        expected_revision=mid_rev,
        source="wikipedia",
        source_id="Vandalized_Page",
        reason="Vandalized",
    )
    assert res_sw.success is True

    # Patch WikipediaAdapter to detect if it is called (it must NOT be)
    wiki_called: list[str] = []

    def spy_fetch(self: Any, identifier: str) -> AdapterResult:
        wiki_called.append(identifier)
        return AdapterResult(source_name="wikipedia", source_id=identifier, success=True, player_name="Should Not Be Used")

    monkeypatch.setattr(WikipediaAdapter, "fetch_player", spy_fetch)

    # Retry without providing retry_source (no adapter_fetcher either → production path)
    rev_before = repo.get_by_id("cand_sw_blocked").revision
    res_retry = service.retry_ingestion(
        admin,
        "cand_sw_blocked",
        expected_revision=rev_before,
        # retry_source deliberately omitted → should fail closed
    )
    assert res_retry.success is False
    assert res_retry.status == ReviewStatus.SOURCE_ERROR
    assert "wikipedia" in res_retry.message.lower() or "non attendibile" in res_retry.message
    assert wiki_called == [], "WikipediaAdapter must NOT be invoked when source is marked unreliable"

    # Candidate must be unchanged
    unchanged = repo.get_by_id("cand_sw_blocked")
    assert unchanged.revision == rev_before
    assert unchanged.status == CandidateState.REVIEW_REQUIRED


def test_trusted_sources_conflict_remains_blocking_after_source_wrong(temp_env):
    """Conflicts among still-trusted sources remain blocking even after some source is marked wrong.

    Scenario:
    - wikipedia (entity W1) provides full_name = "Name A"
    - wikidata (entity D1) provides full_name = "Name B"
    - wikipedia W1 is marked SOURCE_WRONG.
    - Only wikidata remains trusted → no cross-source conflict → approval may proceed.

    Separate verification:
    - If NEITHER source is marked wrong, the conflict still blocks approval (fail-closed).
    """
    from domains.players.candidates.review import get_candidate_provenance_conflicts

    service = temp_env["service"]
    repo = temp_env["repo"]
    admin = temp_env["admin"]

    # --- Part A: conflict cleared after wikipedia is marked wrong ---
    cand_a = create_sample_candidate("cand_conflict_cleared", "Name A", state=CandidateState.READY)
    cand_a.source = "wikipedia"
    cand_a.source_id = "PageW1"
    cand_a.record_observation(
        field_path="full_name", source="wikipedia", source_id="PageW1", raw_value="Name A"
    )
    cand_a.record_observation(
        field_path="full_name", source="wikidata", source_id="D1", raw_value="Name B"
    )
    # Verify conflict exists before any SOURCE_WRONG
    conflicts_before = get_candidate_provenance_conflicts(cand_a)
    assert "full_name" in conflicts_before, "Conflict must exist with two trusted differing sources"

    # Mark wikipedia SOURCE_WRONG
    cand_a.metadata.setdefault("unreliable_sources", []).append({
        "source": "wikipedia",
        "source_id": "PageW1",
        "reason": "Test",
        "marked_at": "2026-01-01T00:00:00Z",
        "marked_by": 100,
    })
    conflicts_after = get_candidate_provenance_conflicts(cand_a)
    assert "full_name" not in conflicts_after, (
        "Conflict must be cleared after wikipedia entity is marked wrong; "
        f"only wikidata remains trusted. Conflicts: {conflicts_after}"
    )

    # --- Part B: if BOTH are trusted (no SOURCE_WRONG), conflict still blocks ---
    cand_b = create_sample_candidate("cand_conflict_blocks", "Name A", state=CandidateState.READY)
    cand_b.record_observation(
        field_path="full_name", source="wikipedia", source_id="PageW1", raw_value="Name A"
    )
    cand_b.record_observation(
        field_path="full_name", source="wikidata", source_id="D1", raw_value="Name B"
    )
    repo.save(cand_b)

    # No SOURCE_WRONG → conflict must block approval
    rev_b = repo.get_by_id("cand_conflict_blocks").revision
    res_approve = service.approve_candidate(admin, "cand_conflict_blocks", expected_revision=rev_b)
    assert res_approve.success is False
    assert res_approve.status == ReviewStatus.UNRESOLVED_CONFLICT
    assert "full_name" in res_approve.conflicts


def test_review_projection_conflict_status_uses_review_aware_policy():
    """Projection conflict status uses review-aware conflict policy, excluding SOURCE_WRONG.

    - Wikipedia X + Wikidata Y with neither rejected:
      projection.has_source_conflicts == True
    - Wikipedia X + Wikidata Y with Wikipedia entity marked SOURCE_WRONG:
      projection.has_source_conflicts == False
      Both observations remain visible in field_observations.
    """
    from domains.players.candidates.review import build_review_projection

    cand = create_sample_candidate("cand_proj_test", "Entity X", state=CandidateState.READY)
    cand.source = "wikipedia"
    cand.source_id = "Entity_X"
    cand.record_observation(
        field_path="full_name",
        source="wikipedia",
        source_id="Entity_X",
        raw_value="Entity X",
    )
    cand.record_observation(
        field_path="full_name",
        source="wikidata",
        source_id="Q9999",
        raw_value="Entity Y",
    )

    # 1. Neither rejected → projection.has_source_conflicts == True
    proj_unfiltered = build_review_projection(cand, [])
    assert proj_unfiltered.has_source_conflicts is True
    assert len(proj_unfiltered.field_observations["full_name"]) == 2

    # 2. Wikipedia entity marked SOURCE_WRONG → projection.has_source_conflicts == False
    cand.metadata.setdefault("unreliable_sources", []).append({
        "source": "wikipedia",
        "source_id": "Entity_X",
        "reason": "Wrong entity matched",
        "marked_at": "2026-01-01T00:00:00Z",
        "marked_by": 100,
    })
    proj_filtered = build_review_projection(cand, [])
    assert proj_filtered.has_source_conflicts is False

    # Both observations must still remain visible in field_observations
    obs_list = proj_filtered.field_observations["full_name"]
    assert len(obs_list) == 2
    sources = {obs["source"] for obs in obs_list}
    assert sources == {"wikipedia", "wikidata"}
    values = {obs["raw_value"] for obs in obs_list}
    assert values == {"Entity X", "Entity Y"}


def test_successful_alternative_source_retry_updates_active_source_identity(temp_env, monkeypatch):
    """Wikipedia source marked wrong → explicit Wikidata retry succeeds:

    - Candidate.source == "wikidata"
    - Candidate.source_id == "Q9999"
    - projection.source and projection.source_id match
    - Old Wikipedia provenance still exists
    - SOURCE_WRONG history still exists
    """
    from domains.players.adapters.base import AdapterResult, CareerEntry
    from domains.players.adapters.wikidata import WikidataAdapter

    service = temp_env["service"]
    repo = temp_env["repo"]
    admin = temp_env["admin"]

    cand = create_sample_candidate(
        "cand_active_src",
        "Wrong Wiki Name",
        state=CandidateState.READY,
        source="wikipedia",
    )
    cand.source_id = "Wrong_Wikipedia_Page"
    cand.record_observation(
        field_path="full_name",
        source="wikipedia",
        source_id="Wrong_Wikipedia_Page",
        raw_value="Wrong Wiki Name",
    )
    repo.save(cand)
    rev1 = repo.get_by_id("cand_active_src").revision

    # Mark wikipedia source wrong
    res_sw = service.mark_source_wrong(
        admin,
        "cand_active_src",
        expected_revision=rev1,
        source="wikipedia",
        source_id="Wrong_Wikipedia_Page",
        reason="Vandalized page",
    )
    assert res_sw.success is True
    rev2 = repo.get_by_id("cand_active_src").revision

    # Monkeypatch WikidataAdapter
    def mock_fetch(self: Any, identifier: str) -> AdapterResult:
        return AdapterResult(
            source_name="wikidata",
            source_id=identifier,
            success=True,
            player_name="Recovered Wikidata Name",
            nationality="Italia",
            birth_year=1990,
            position="Difensore",
            career=[
                CareerEntry(team="Milan", country="Italia", league="Serie A", start_year=2010, end_year=2020),
            ],
        )

    monkeypatch.setattr(WikidataAdapter, "fetch_player", mock_fetch)

    # Explicit Wikidata retry
    res_retry = service.retry_ingestion(
        admin,
        "cand_active_src",
        expected_revision=rev2,
        retry_source="wikidata",
        retry_source_id="Q9999",
    )
    assert res_retry.success is True

    candidate_after = repo.get_by_id("cand_active_src")
    assert candidate_after.source == "wikidata"
    assert candidate_after.source_id == "Q9999"
    assert res_retry.projection.source == "wikidata"
    assert res_retry.projection.source_id == "Q9999"
    assert res_retry.projection.has_source_conflicts is False

    # Old Wikipedia provenance still exists
    fp = candidate_after.provenance.get_provenance_for_path("full_name")
    assert fp is not None
    assert fp.get_observation("wikipedia") is not None
    assert fp.get_observation("wikidata") is not None
    assert fp.get_observation("wikipedia").raw_value == "Wrong Wiki Name"
    assert fp.get_observation("wikidata").raw_value == "Recovered Wikidata Name"

    # SOURCE_WRONG history still exists
    history = candidate_after.metadata.get("review_events", [])
    actions = [h["action"] for h in history]
    assert ReviewAction.SOURCE_WRONG.value in actions
    assert ReviewAction.RETRY.value in actions
    unreliable = candidate_after.metadata.get("unreliable_sources", [])
    assert any(u.get("source") == "wikipedia" and u.get("source_id") == "Wrong_Wikipedia_Page" for u in unreliable)


def test_retry_without_override_after_recovery_resolves_updated_source(temp_env, monkeypatch):
    """After successful Wikidata recovery, retry_ingestion() with no override resolves Wikidata, NOT rejected Wikipedia."""
    from domains.players.adapters.base import AdapterResult, CareerEntry
    from domains.players.adapters.wikidata import WikidataAdapter
    from domains.players.adapters.wikipedia import WikipediaAdapter

    service = temp_env["service"]
    repo = temp_env["repo"]
    admin = temp_env["admin"]

    cand = create_sample_candidate(
        "cand_no_override",
        "Wrong Wiki Name",
        state=CandidateState.READY,
        source="wikipedia",
    )
    cand.source_id = "Wrong_Wiki_Page"
    cand.record_observation(
        field_path="full_name",
        source="wikipedia",
        source_id="Wrong_Wiki_Page",
        raw_value="Wrong Wiki Name",
    )
    repo.save(cand)
    rev1 = repo.get_by_id("cand_no_override").revision

    # Mark wikipedia wrong
    res_sw = service.mark_source_wrong(
        admin,
        "cand_no_override",
        expected_revision=rev1,
        source="wikipedia",
        source_id="Wrong_Wiki_Page",
        reason="Vandalized",
    )
    assert res_sw.success is True

    # Track adapter calls
    wiki_calls: list[str] = []
    wikidata_calls: list[str] = []

    def mock_wiki(self: Any, identifier: str) -> AdapterResult:
        wiki_calls.append(identifier)
        return AdapterResult(source_name="wikipedia", source_id=identifier, success=True, player_name="Should Not Call Wiki")

    def mock_wikidata(self: Any, identifier: str) -> AdapterResult:
        wikidata_calls.append(identifier)
        return AdapterResult(
            source_name="wikidata",
            source_id=identifier,
            success=True,
            player_name="Legitimate Wikidata Name",
            nationality="Italia",
            birth_year=1991,
            position="Attaccante",
            career=[
                CareerEntry(team="Inter", country="Italia", league="Serie A", start_year=2011, end_year=2021),
            ],
        )

    monkeypatch.setattr(WikipediaAdapter, "fetch_player", mock_wiki)
    monkeypatch.setattr(WikidataAdapter, "fetch_player", mock_wikidata)

    # 1. Recovery with explicit retry_source="wikidata", retry_source_id="Q9999"
    rev2 = repo.get_by_id("cand_no_override").revision
    res1 = service.retry_ingestion(
        admin,
        "cand_no_override",
        expected_revision=rev2,
        retry_source="wikidata",
        retry_source_id="Q9999",
    )
    assert res1.success is True
    assert wikidata_calls == ["Q9999"]
    assert wiki_calls == []

    # 2. Subsequent retry with NO override (retry_source=None)
    rev3 = repo.get_by_id("cand_no_override").revision
    res2 = service.retry_ingestion(
        admin,
        "cand_no_override",
        expected_revision=rev3,
        # retry_source and retry_source_id deliberately omitted
    )
    assert res2.success is True
    # Proves it resolved Wikidata (now the active source), NOT the rejected Wikipedia source
    assert wikidata_calls == ["Q9999", "Q9999"]
    assert wiki_calls == [], "Rejected Wikipedia adapter must never be invoked"
    assert res2.projection.source == "wikidata"
    assert res2.projection.source_id == "Q9999"




# ---------------------------------------------------------------------------
# Feature flag `player_pipeline` (#51)
# ---------------------------------------------------------------------------

def _pipeline_off():
    from services import feature_flags
    feature_flags.set_service(feature_flags.FeatureFlagService(
        lambda: {"schema_version": 1, "revision": 1, "flags": {"player_pipeline": {"enabled": False}}}, ttl=300))


def test_retry_ingestion_is_refused_without_calling_any_source_when_the_pipeline_is_disabled(temp_env):
    _pipeline_off()
    service, repo, admin = temp_env["service"], temp_env["repo"], temp_env["admin"]
    repo.save(create_sample_candidate("cand_flag_off", "Paused Player", state=CandidateState.REVIEW_REQUIRED, career=[]))
    before = repo.get_by_id("cand_flag_off").to_dict()

    def fetcher(source, source_id):
        pytest.fail("no external source may be contacted while player_pipeline is disabled")

    result = service.retry_ingestion(admin, "cand_flag_off", expected_revision=1, adapter_fetcher=fetcher)
    assert result.success is False
    assert result.status == ReviewStatus.FEATURE_DISABLED
    assert repo.get_by_id("cand_flag_off").to_dict() == before


def test_retry_ingestion_still_checks_authorization_before_the_flag(temp_env):
    _pipeline_off()
    temp_env["repo"].save(create_sample_candidate("cand_flag_auth", "Someone", state=CandidateState.REVIEW_REQUIRED))
    with pytest.raises(ReviewForbiddenError):
        temp_env["service"].retry_ingestion(temp_env["stranger"], "cand_flag_auth", expected_revision=1)


def test_existing_candidates_can_still_be_approved_and_rejected_with_the_pipeline_disabled(temp_env):
    _pipeline_off()
    service, repo, admin = temp_env["service"], temp_env["repo"], temp_env["admin"]
    repo.save(create_sample_candidate("cand_flag_ok", "Alessandro Del Piero", state=CandidateState.READY))
    repo.save(create_sample_candidate("cand_flag_no", "Wrong Person", state=CandidateState.REVIEW_REQUIRED))

    assert service.approve(admin, "cand_flag_ok", expected_revision=1).status == ReviewStatus.SUCCESS
    rejected = service.reject_candidate(admin, "cand_flag_no", expected_revision=1, reason="dati errati")
    assert rejected.success is True


def test_an_injected_gate_overrides_the_global_flag(temp_env, tmp_path):
    service = CandidateReviewService(
        candidate_repo=temp_env["repo"], players_path=temp_env["service"]._players_path,
        backup_dir=tmp_path / "bk", admin_ids=[100], ingestion_enabled=lambda: False,
    )
    temp_env["repo"].save(create_sample_candidate("cand_flag_inject", "Injected", state=CandidateState.REVIEW_REQUIRED))
    result = service.retry_ingestion(temp_env["admin"], "cand_flag_inject", expected_revision=1,
                                     adapter_fetcher=lambda s, i: pytest.fail("gated"))
    assert result.status == ReviewStatus.FEATURE_DISABLED
