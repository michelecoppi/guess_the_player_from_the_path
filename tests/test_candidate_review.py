"""Tests for Candidate Player Review Queue and Approval Workflow (#15).

Verifies the end-to-end domain and service layer for review, edit, approval,
merge, reject, source-wrong, retry ingestion, authorization, and data integrity.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from services.adapters.base import AdapterResult, CareerEntry
from services.candidate_player import (
    CandidatePlayer,
    CandidateState,
)
from services.candidate_review import (
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
from services.repos.candidates import (
    FileCandidatePlayerRepository,
)


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
    c.raw_data = {"secret_token": "SUPER_SECRET", "raw_provider_dump": {"xyz": 123}}
    c.metadata["telegram_init_data"] = "user_id=123&hash=abc"
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
    def crashing_save(c):
        raise RuntimeError("Simulated database crash")

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
    assert updated.status == CandidateState.REJECTED
    assert updated.metadata["source_unreliable"] is True
    assert updated.metadata["unreliable_source_reason"] == "Vandalismo pagina"


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
