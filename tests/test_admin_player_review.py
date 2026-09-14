"""Tests for the Admin Review Queue page (#35), the Streamlit glue over #15's
``services.candidate_review.CandidateReviewService``.

These tests exercise wiring, rendering and the mutation call sites only — the domain
rules themselves (FSM transitions, validation, provenance conflicts, CAS, backups) are
already covered exhaustively by tests/test_candidate_review.py and are intentionally
NOT re-verified here. Everything runs against temporary repositories/datasets; nothing
touches production data.
"""
from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import admin_pages.player_review as player_review
import admin_pages.shared as shared
from services.adapters.base import AdapterResult
from services.candidate_player import CandidatePlayer, CandidateState
from services.candidate_review import AdminIdentity, CandidateReviewService, ReviewStatus
from services.repos.candidates import FileCandidatePlayerRepository

REPO_ROOT = Path(__file__).resolve().parents[1]


def make_candidate(
    cand_id,
    name="Test Player",
    state=CandidateState.READY,
    revision=1,
    source="wikipedia",
    source_id="Test_Player",
    career=None,
    **extra,
):
    if career is None:
        # Two clubs, well within a plausible career span for a 1974-born player:
        # avoids incidental VALIDATION_FAILED findings unrelated to what each test wants.
        career = [
            {"team": "Club A", "country": "Italia", "league": "Serie A", "start_year": 1993, "end_year": 2000,
             "apps": 100, "goals": 10},
            {"team": "Club B", "country": "Italia", "league": "Serie A", "start_year": 2000, "end_year": 2010,
             "apps": 200, "goals": 20},
        ]
    return CandidatePlayer(
        candidate_id=cand_id,
        source=source,
        source_id=source_id,
        _status=state,
        revision=revision,
        full_name=name,
        aliases=[name.lower()],
        nationality="Italia",
        position="Attaccante",
        birth_year=1974,
        popularity=3,
        career=career,
        **extra,
    )


@pytest.fixture
def env(tmp_path):
    players_file = tmp_path / "players.json"
    players_file.write_text(json.dumps({"_comment": "t", "players": []}), encoding="utf-8")
    repo = FileCandidatePlayerRepository(storage_dir=tmp_path / "candidates")
    service = CandidateReviewService(
        candidate_repo=repo,
        players_path=players_file,
        backup_dir=tmp_path / "backup",
        admin_ids=[100],
        current_year_provider=lambda: 2026,
        adapter_resolver=lambda source, source_id: None,
    )
    admin = AdminIdentity(user_id=100, username="admin_ui")
    return {"service": service, "repo": repo, "players_file": players_file, "admin": admin}


def patch_wiring(monkeypatch, service, admin):
    monkeypatch.setattr(player_review, "get_review_service", lambda: service)
    monkeypatch.setattr(player_review, "get_admin_identity", lambda: admin)
    st.cache_data.clear()


RENDER_SCRIPT = """
from admin_pages.shared import render_flash
from admin_pages.player_review import render
render_flash()
render("2026-09-14", None)
"""


# ---------------------------------------------------------------------------
# 1. Page registration
# ---------------------------------------------------------------------------

def test_page_registered_in_admin_ui_nav():
    src = (REPO_ROOT / "admin_ui.py").read_text(encoding="utf-8")
    assert "player_review" in src
    assert "🔎 Review giocatori" in src
    assert "player_review.render" in src


def test_render_is_callable():
    assert callable(player_review.render)


# ---------------------------------------------------------------------------
# 2. Service construction reuses the real ingestion repository/config
# ---------------------------------------------------------------------------

def test_review_service_uses_real_candidate_repository_and_config():
    service = shared.get_review_service()
    assert isinstance(service, CandidateReviewService)
    assert isinstance(service._repo, FileCandidatePlayerRepository)
    # Same default directory the ingestion pipeline's FileCandidatePlayerRepository() uses.
    assert service._repo._dir == (REPO_ROOT / "data" / "candidates").resolve()
    assert service._players_path == (REPO_ROOT / "data" / "players.json").resolve()


def test_admin_identity_comes_from_shared_admin_telegram_ids(monkeypatch):
    monkeypatch.setattr(shared, "ADMIN_TELEGRAM_IDS", [])
    assert shared.get_admin_identity() is None

    monkeypatch.setattr(shared, "ADMIN_TELEGRAM_IDS", [777, 888])
    identity = shared.get_admin_identity()
    assert identity is not None
    assert identity.user_id == 777


# ---------------------------------------------------------------------------
# 3. Structural guards: no domain-logic / persistence duplication in the UI
# ---------------------------------------------------------------------------

def test_admin_page_never_touches_players_json_or_adapters_directly():
    src = inspect.getsource(player_review)
    lowered = src.lower()
    assert "wikipediaadapter" not in lowered
    assert "wikidataadapter" not in lowered
    assert "raw_payload" not in lowered
    assert "open(" not in src
    assert "json.dump(" not in src


# ---------------------------------------------------------------------------
# 4. Missing admin config blocks mutations safely
# ---------------------------------------------------------------------------

def test_missing_admin_config_blocks_page(monkeypatch):
    monkeypatch.setattr(player_review, "get_admin_identity", lambda: None)
    st.cache_data.clear()
    result = AppTest.from_string(RENDER_SCRIPT).run(timeout=20)
    assert not result.exception
    assert any("ADMIN_TELEGRAM_IDS" in e.value for e in result.error)
    # No queue content should have been requested/rendered when blocked.
    assert len(result.dataframe) == 0


# ---------------------------------------------------------------------------
# 5. Queue overview counts are sourced from the service, not recomputed
# ---------------------------------------------------------------------------

def test_overview_counts_match_service(env, monkeypatch):
    service, admin = env["service"], env["admin"]
    repo = env["repo"]

    repo.save(make_candidate("c1", state=CandidateState.READY))
    repo.save(make_candidate("c2", state=CandidateState.VALIDATED))
    c3 = make_candidate("c3", state=CandidateState.REVIEW_REQUIRED)
    c3.validation_warnings = ["qualcosa da controllare"]
    repo.save(c3)
    repo.save(make_candidate("c4", state=CandidateState.APPROVED))  # not reviewable, excluded

    patch_wiring(monkeypatch, service, admin)
    result = AppTest.from_string(RENDER_SCRIPT).run(timeout=20)
    assert not result.exception

    expected_total = service.list_queue(admin, limit=1).total
    expected_ready = service.list_queue(admin, state=CandidateState.READY, limit=1).total
    expected_warnings = service.list_queue(admin, has_warnings=True, limit=1).total

    assert expected_total == 3
    assert expected_ready == 1
    assert expected_warnings == 1

    metric_values = {m.label: m.value for m in result.metric}
    assert metric_values["Totale revisionabili"] == str(expected_total)
    assert metric_values["Pronti"] == str(expected_ready)
    assert metric_values["Con warning/errori"] == str(expected_warnings)


# ---------------------------------------------------------------------------
# 6. Queue table reflects service projection fields verbatim
# ---------------------------------------------------------------------------

def test_queue_table_reflects_projection_fields(env, monkeypatch):
    service, admin = env["service"], env["admin"]
    repo = env["repo"]
    repo.save(make_candidate("clean_cand", name="Clean Player", state=CandidateState.READY))

    patch_wiring(monkeypatch, service, admin)
    result = AppTest.from_string(RENDER_SCRIPT).run(timeout=20)
    assert not result.exception

    tables = [df.value for df in result.dataframe]
    row = None
    for table in tables:
        if "id" in table.columns and "Clean Player" in list(table.get("nome", [])):
            row = table[table["id"] == "clean_cand"].iloc[0]
            break
    assert row is not None
    assert row["errori"] == 0
    assert row["warning"] == 0
    assert row["conflitti fonti"] == "—"
    assert row["duplicati"] == "—"


# ---------------------------------------------------------------------------
# 7. Full flow: queue -> detail -> warning -> explicit approval -> promoted,
#    gone from the active queue. Also proves the displayed revision is what's sent.
# ---------------------------------------------------------------------------

def test_full_flow_approve_with_explicit_warning_ack(env, monkeypatch):
    service, admin = env["service"], env["admin"]
    repo, players_file = env["repo"], env["players_file"]

    cand = make_candidate("cand_ready", name="Ready Player", state=CandidateState.READY)
    cand.validation_warnings = ["Età anomala rilevata"]
    repo.save(cand)

    patch_wiring(monkeypatch, service, admin)
    at = AppTest.from_string(RENDER_SCRIPT).run(timeout=20)
    assert not at.exception

    at.button(key="open_cand_ready").click().run()
    assert not at.exception

    # Without the explicit warning-ack checkbox, approval must be refused client-side.
    at.checkbox(key="approve_confirm_cand_ready_1").check().run()
    at.button(key="approve_submit_cand_ready_1").click().run()
    assert not at.exception
    still_ready = repo.get_by_id("cand_ready")
    assert still_ready.status == CandidateState.READY
    assert any("warning" in e.value.lower() for e in at.error)

    # Explicit ack -> approval succeeds and reloads.
    at.checkbox(key="approve_ack_warnings_cand_ready_1").check().run()
    at.button(key="approve_submit_cand_ready_1").click().run()
    assert not at.exception

    approved = repo.get_by_id("cand_ready")
    assert approved.status == CandidateState.APPROVED
    promoted_id = approved.metadata.get("promoted_player_id")
    assert promoted_id

    players = json.loads(players_file.read_text(encoding="utf-8"))["players"]
    matches = [p for p in players if p["id"] == promoted_id]
    assert len(matches) == 1  # appears exactly once
    assert matches[0]["full_name"] == "Ready Player"
    # The Admin never invents the production id: it is whatever the service generated.
    assert promoted_id != "cand_ready"

    # Gone from the active (reviewable) queue.
    assert service.list_queue(admin, limit=10).total == 0


# ---------------------------------------------------------------------------
# 8. STALE_REVISION requires a reload, never an automatic retry
# ---------------------------------------------------------------------------

def test_stale_revision_requires_explicit_reload(env, monkeypatch):
    service, admin = env["service"], env["admin"]
    repo = env["repo"]

    cand = make_candidate("cand_stale", name="Stale Player", state=CandidateState.READY)
    repo.save(cand)

    patch_wiring(monkeypatch, service, admin)
    at = AppTest.from_string(RENDER_SCRIPT).run(timeout=20)
    at.button(key="open_cand_stale").click().run()
    assert not at.exception

    # Simulate a concurrent edit bumping the persisted revision behind the UI's back.
    concurrent = repo.get_by_id("cand_stale")
    concurrent.bump_revision()
    repo.save(concurrent)

    at.checkbox(key="approve_confirm_cand_stale_1").check().run()
    at.button(key="approve_submit_cand_stale_1").click().run()
    assert not at.exception

    # Not approved: the stale attempt must not silently succeed or auto-retry.
    unchanged = repo.get_by_id("cand_stale")
    assert unchanged.status == CandidateState.READY
    assert unchanged.revision == 2
    assert any("revisione" in w.value.lower() or "revision" in w.value.lower() for w in at.warning) or any(
        "revisione" in i.value.lower() for i in at.info
    )

    # The page must reflect the fresh revision after reload (form keyed on the new revision).
    assert at.checkbox(key="approve_confirm_cand_stale_2") is not None


# ---------------------------------------------------------------------------
# 9. Reject: reason + confirmation required, revision passed through
# ---------------------------------------------------------------------------

def test_reject_requires_reason_and_uses_displayed_revision(env, monkeypatch):
    service, admin = env["service"], env["admin"]
    repo = env["repo"]
    repo.save(make_candidate("cand_reject", name="Reject Player", state=CandidateState.REVIEW_REQUIRED))

    patch_wiring(monkeypatch, service, admin)
    at = AppTest.from_string(RENDER_SCRIPT).run(timeout=20)
    at.button(key="open_cand_reject").click().run()

    # Missing reason -> refused, candidate untouched.
    at.checkbox(key="reject_confirm_cand_reject_1").check().run()
    at.button(key="reject_submit_cand_reject_1").click().run()
    assert repo.get_by_id("cand_reject").status == CandidateState.REVIEW_REQUIRED

    at.text_input(key="reject_reason_cand_reject_1").set_value("Dati non verificabili").run()
    at.button(key="reject_submit_cand_reject_1").click().run()
    assert not at.exception

    rejected = repo.get_by_id("cand_reject")
    assert rejected.status == CandidateState.REJECTED
    events = rejected.metadata.get("review_events", [])
    assert events[-1]["action"] == "REJECT"
    assert events[-1]["reason"] == "Dati non verificabili"
    # File-backed candidate record still exists: rejecting never deletes it.
    assert repo.exists("cand_reject")


# ---------------------------------------------------------------------------
# 10. Merge: never writes players.json directly, always an explicit target choice
# ---------------------------------------------------------------------------

def test_merge_never_writes_players_json_directly(env, monkeypatch):
    service, admin = env["service"], env["admin"]
    repo, players_file = env["repo"], env["players_file"]

    players_file.write_text(
        json.dumps({"_comment": "t", "players": [{"id": "esisto_gia", "full_name": "Existing Player",
                                                    "aliases": [], "nationality": "Italia", "position": "P",
                                                    "birth_year": 1980, "popularity": 3, "verified": True,
                                                    "career": [{"team": "X", "start_year": 2000, "end_year": 2010}]}]}),
        encoding="utf-8",
    )
    before = players_file.read_text(encoding="utf-8")

    repo.save(make_candidate("cand_merge", name="Merge Player", state=CandidateState.READY))

    patch_wiring(monkeypatch, service, admin)
    at = AppTest.from_string(RENDER_SCRIPT).run(timeout=20)
    at.button(key="open_cand_merge").click().run()

    target_label = next(
        v for v in at.selectbox(key="merge_target_cand_merge_1").options if "Existing Player" in v
    )
    at.selectbox(key="merge_target_cand_merge_1").select(target_label).run()
    at.text_input(key="merge_reason_cand_merge_1").set_value("Stesso giocatore, fonte diversa").run()
    at.checkbox(key="merge_confirm_cand_merge_1").check().run()
    at.button(key="merge_submit_cand_merge_1").click().run()
    assert not at.exception

    after = players_file.read_text(encoding="utf-8")
    assert before == after  # players.json is byte-for-byte untouched by a merge

    merged = repo.get_by_id("cand_merge")
    assert merged.status == CandidateState.APPROVED
    assert merged.metadata.get("merged_into_player_id") == "esisto_gia"


# ---------------------------------------------------------------------------
# 11. Source-wrong: evidence stays visible, retry never calls adapters directly
# ---------------------------------------------------------------------------

def test_source_wrong_then_retry_via_injected_adapter(env, monkeypatch):
    repo = env["repo"]
    players_file = env["players_file"]
    admin = env["admin"]

    fetched = []

    def fake_resolver(source, source_id):
        fetched.append((source, source_id))
        return AdapterResult(
            source_name="wikidata",
            source_id=source_id,
            success=True,
            player_name="Recovered Player",
            nationality="Italia",
            career=[{"team": "Recovered FC", "start_year": 2015, "end_year": 2020}],
        )

    service = CandidateReviewService(
        candidate_repo=repo,
        players_path=players_file,
        backup_dir=env["service"]._backup_dir,
        admin_ids=[100],
        current_year_provider=lambda: 2026,
        adapter_resolver=fake_resolver,
    )

    cand = make_candidate(
        "cand_sw", name="Wrong Source Player", state=CandidateState.READY, source="wikipedia", source_id="Vandalized_Page"
    )
    repo.save(cand)

    patch_wiring(monkeypatch, service, admin)
    at = AppTest.from_string(RENDER_SCRIPT).run(timeout=20)
    at.button(key="open_cand_sw").click().run()

    at.text_input(key="sw_reason_cand_sw_1").set_value("Pagina vandalizzata").run()
    at.checkbox(key="sw_confirm_cand_sw_1").check().run()
    at.button(key="sw_submit_cand_sw_1").click().run()
    assert not at.exception

    flagged = repo.get_by_id("cand_sw")
    assert flagged.status == CandidateState.REVIEW_REQUIRED
    unreliable = flagged.metadata.get("unreliable_sources", [])
    assert unreliable and unreliable[-1]["source"] == "wikipedia"
    # The rejected evidence is still present (auditable), just not authoritative.
    assert flagged.source == "wikipedia"

    # Retry against wikidata must go through the service's adapter_resolver only.
    # "Usa la fonte corrente" is disabled+unchecked automatically: the source was just
    # flagged unreliable, so an alternative source is mandatory.
    rev2 = flagged.revision
    assert at.checkbox(key=f"retry_use_current_cand_sw_{rev2}").value is False
    at.selectbox(key=f"retry_alt_source_cand_sw_{rev2}").select("wikidata").run()
    at.text_input(key=f"retry_alt_source_id_cand_sw_{rev2}").set_value("Q12345").run()
    at.button(key=f"retry_submit_cand_sw_{rev2}").click().run()
    assert not at.exception

    assert fetched == [("wikidata", "Q12345")]
    retried = repo.get_by_id("cand_sw")
    assert retried.source == "wikidata"
    assert retried.full_name == "Recovered Player"
    # Old provenance/history is preserved.
    actions = [ev.get("action") for ev in retried.metadata.get("review_events", [])]
    assert "SOURCE_WRONG" in actions
    assert "RETRY" in actions


# ---------------------------------------------------------------------------
# 12. Edit: only the #15 allow-listed fields ever leave the Admin as `updates`
# ---------------------------------------------------------------------------

def test_edit_only_sends_allow_listed_fields(env, monkeypatch):
    service, admin = env["service"], env["admin"]
    repo = env["repo"]
    repo.save(make_candidate("cand_edit", name="Edit Player", state=CandidateState.READY))

    captured = {}
    real_edit = service.edit

    def spy_edit(*args, **kwargs):
        captured["updates"] = kwargs.get("updates") if "updates" in kwargs else args[3]
        return real_edit(*args, **kwargs)

    monkeypatch.setattr(service, "edit", spy_edit)
    patch_wiring(monkeypatch, service, admin)

    at = AppTest.from_string(RENDER_SCRIPT).run(timeout=20)
    at.button(key="open_cand_edit").click().run()
    at.text_input(key="edit_nationality_cand_edit_1").set_value("Spagna").run()
    at.text_input(key="edit_reason_cand_edit_1").set_value("Correzione nazionalità").run()

    buttons = [b for b in at.button if "Salva modifiche" in (b.label or "")]
    assert buttons
    buttons[0].click().run()
    assert not at.exception

    assert "updates" in captured
    ALLOWED = {
        "full_name", "birth_year", "nationality", "position", "aliases",
        "career", "is_one_club_man", "is_retired", "popularity",
    }
    assert set(captured["updates"]).issubset(ALLOWED)
    assert captured["updates"] == {"nationality": "Spagna"}

    edited = repo.get_by_id("cand_edit")
    assert edited.nationality == "Spagna"
