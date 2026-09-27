"""Tests for the Admin Review Queue page (#35), the Streamlit glue over #15's
``domains.players.candidates.review.CandidateReviewService``.

These tests exercise wiring, rendering and the mutation call sites only — the domain
rules themselves (FSM transitions, validation, provenance conflicts, CAS, backups) are
already covered exhaustively by tests/test_candidate_review.py and are intentionally
NOT re-verified here. Everything runs against temporary repositories/datasets; nothing
touches production data.
"""
from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import admin_pages.player_review as player_review
import admin_pages.shared as shared
from domains.players.adapters.base import AdapterResult
from domains.players.candidates.model import CandidatePlayer, CandidateState
from domains.players.candidates.repository import FileCandidatePlayerRepository
from domains.players.candidates.review import AdminIdentity, CandidateReviewService

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
# 3b. Banner wording must not claim merge writes to players.json (#86)
# ---------------------------------------------------------------------------

def test_admin_banner_does_not_claim_merge_writes_players_json(env, monkeypatch):
    """Only approve() persists to data/players.json; merge_candidate() never does
    (see test_merge_never_writes_players_json_directly). The admin banner must
    reflect that distinction instead of implying both operations write it."""
    admin = env["admin"]
    patch_wiring(monkeypatch, env["service"], admin)

    at = AppTest.from_string(RENDER_SCRIPT).run(timeout=20)
    assert not at.exception

    captions = [c.value for c in at.caption]
    banner = next(c for c in captions if f"amministratore `{admin.user_id}`" in c)

    assert "merge scrivono" not in banner
    assert "solo l'approvazione scrive" in banner.lower()
    assert "senza scrivere sul dataset" in banner.lower()


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


# ---------------------------------------------------------------------------
# 13. No combined Edit+Approve path: the reviewer can never pre-acknowledge
#     warnings before the edit itself has produced its real validation result.
# ---------------------------------------------------------------------------

def test_no_combined_edit_and_approve_path_in_ui(env, monkeypatch):
    service, admin = env["service"], env["admin"]
    repo = env["repo"]
    repo.save(make_candidate("cand_combo", name="Combo Player", state=CandidateState.READY))

    real_edit_and_approve = service.edit_and_approve
    calls = []
    monkeypatch.setattr(
        service, "edit_and_approve", lambda *a, **kw: (calls.append((a, kw)), real_edit_and_approve(*a, **kw))[1]
    )
    patch_wiring(monkeypatch, service, admin)

    at = AppTest.from_string(RENDER_SCRIPT).run(timeout=20)
    at.button(key="open_cand_combo").click().run()
    assert not at.exception

    # No "combined" checkbox/widget is reachable anywhere on the rendered detail page.
    checkbox_keys = [c.key for c in at.checkbox]
    assert not any("combined" in (k or "") for k in checkbox_keys)
    labels = [c.label for c in at.checkbox]
    assert not any("approva subito" in (lbl or "").lower() for lbl in labels)

    # Saving an edit alone never calls the combined service method.
    at.text_input(key="edit_nationality_cand_combo_1").set_value("Portogallo").run()
    save_buttons = [b for b in at.button if "Salva modifiche" in (b.label or "")]
    assert save_buttons
    save_buttons[0].click().run()
    assert not at.exception

    assert calls == []  # edit_and_approve was never invoked by the Admin UI
    edited = repo.get_by_id("cand_combo")
    assert edited.status != CandidateState.APPROVED
    assert edited.nationality == "Portogallo"


def test_admin_source_never_calls_edit_and_approve():
    src = inspect.getsource(player_review)
    assert "edit_and_approve" not in src


# ---------------------------------------------------------------------------
# 14. Edit that introduces a NEW warning: not auto-approved; refreshed detail
#     shows it; approving requires a fresh explicit ack tied to the new revision.
# ---------------------------------------------------------------------------

def test_edit_introducing_warning_requires_fresh_ack_on_new_revision(env, monkeypatch):
    service, admin = env["service"], env["admin"]
    repo, players_file = env["repo"], env["players_file"]
    repo.save(make_candidate("cand_newwarn", name="New Warning Player", state=CandidateState.READY))
    before = players_file.read_text(encoding="utf-8")

    patch_wiring(monkeypatch, service, admin)
    at = AppTest.from_string(RENDER_SCRIPT).run(timeout=20)
    at.button(key="open_cand_newwarn").click().run()
    assert not at.exception

    # Clearing the role triggers a real PLAYER_POSITION_MISSING warning only once the
    # edit actually runs — never pre-acknowledged beforehand.
    at.text_input(key="edit_position_cand_newwarn_1").set_value("").run()
    save_buttons = [b for b in at.button if "Salva modifiche" in (b.label or "")]
    save_buttons[0].click().run()
    assert not at.exception

    edited = repo.get_by_id("cand_newwarn")
    assert edited.revision == 2
    assert edited.status != CandidateState.APPROVED  # never a side-effect of Edit
    assert any("ruolo" in w.lower() for w in edited.validation_warnings)
    assert players_file.read_text(encoding="utf-8") == before  # Edit never touches production

    # The freshly reloaded projection (new revision) shows the warning to the reviewer.
    assert any("warning" in w.value.lower() for w in at.warning)
    assert any("ruolo" in m.value.lower() for m in at.markdown)

    # Approve form is now keyed on the new revision; the old revision's key is gone.
    assert at.checkbox(key="approve_ack_warnings_cand_newwarn_2") is not None
    with pytest.raises(KeyError):
        at.checkbox(key="approve_ack_warnings_cand_newwarn_1")

    # Approving without a fresh ack on the new revision is refused.
    at.checkbox(key="approve_confirm_cand_newwarn_2").check().run()
    at.button(key="approve_submit_cand_newwarn_2").click().run()
    assert not at.exception
    assert repo.get_by_id("cand_newwarn").status != CandidateState.APPROVED

    # Explicit ack on the new revision -> approval succeeds.
    at.checkbox(key="approve_ack_warnings_cand_newwarn_2").check().run()
    at.button(key="approve_submit_cand_newwarn_2").click().run()
    assert not at.exception
    assert repo.get_by_id("cand_newwarn").status == CandidateState.APPROVED


# ---------------------------------------------------------------------------
# 15. Edit that introduces a blocking error: candidate stays reviewable, Approve
#     is blocked, production dataset is unchanged.
# ---------------------------------------------------------------------------

def test_edit_introducing_blocking_error_blocks_approve_and_leaves_dataset_untouched(env, monkeypatch):
    service, admin = env["service"], env["admin"]
    repo, players_file = env["repo"], env["players_file"]
    repo.save(make_candidate("cand_newerr", name="New Error Player", state=CandidateState.READY))
    before = players_file.read_text(encoding="utf-8")

    patch_wiring(monkeypatch, service, admin)
    at = AppTest.from_string(RENDER_SCRIPT).run(timeout=20)
    at.button(key="open_cand_newerr").click().run()

    # Clearing nationality triggers a blocking PLAYER_NATIONALITY_MISSING error.
    at.text_input(key="edit_nationality_cand_newerr_1").set_value("").run()
    save_buttons = [b for b in at.button if "Salva modifiche" in (b.label or "")]
    save_buttons[0].click().run()
    assert not at.exception

    edited = repo.get_by_id("cand_newerr")
    # edit() bumps once, and the resulting READY -> REVIEW_REQUIRED transition bumps again.
    assert edited.revision == 3
    assert edited.status == CandidateState.REVIEW_REQUIRED
    assert any("nazionalità" in e.lower() for e in edited.validation_errors)
    assert players_file.read_text(encoding="utf-8") == before

    # The Approve confirmation checkbox and submit button for the new revision are both
    # disabled while blocking: a browser user cannot even attempt to approve.
    approve_confirm = at.checkbox(key="approve_confirm_cand_newerr_3")
    assert approve_confirm.disabled is True
    approve_submit = at.button(key="approve_submit_cand_newerr_3")
    assert approve_submit.disabled is True

    # Nothing was approved and production remains untouched.
    assert repo.get_by_id("cand_newerr").status == CandidateState.REVIEW_REQUIRED
    assert players_file.read_text(encoding="utf-8") == before


# ---------------------------------------------------------------------------
# 16. After Edit, the displayed revision is the updated one, not the pre-edit one.
# ---------------------------------------------------------------------------

def test_edit_reload_shows_updated_revision_not_pre_edit(env, monkeypatch):
    service, admin = env["service"], env["admin"]
    repo = env["repo"]
    repo.save(make_candidate("cand_rev", name="Revision Player", state=CandidateState.READY))

    patch_wiring(monkeypatch, service, admin)
    at = AppTest.from_string(RENDER_SCRIPT).run(timeout=20)
    at.button(key="open_cand_rev").click().run()
    assert at.checkbox(key="approve_confirm_cand_rev_1") is not None

    at.text_input(key="edit_nationality_cand_rev_1").set_value("Francia").run()
    save_buttons = [b for b in at.button if "Salva modifiche" in (b.label or "")]
    save_buttons[0].click().run()
    assert not at.exception

    # Service-side confirmation: the persisted, freshly loaded projection is at revision 2.
    fresh = service.get_candidate_detail(admin, "cand_rev")
    assert fresh.revision == 2
    assert fresh.nationality == "Francia"

    # UI-side confirmation: widgets are now keyed on revision 2, not the stale revision 1.
    assert at.checkbox(key="approve_confirm_cand_rev_2") is not None
    with pytest.raises(KeyError):
        at.checkbox(key="approve_confirm_cand_rev_1")
    assert any("revisione 2" in c.value.lower() for c in at.caption)


# ---------------------------------------------------------------------------
# 17. A stale warning acknowledgement from a previous revision cannot be reused
#     to approve a later revision without re-acknowledging.
# ---------------------------------------------------------------------------

def test_stale_warning_ack_does_not_carry_over_to_new_revision(env, monkeypatch):
    service, admin = env["service"], env["admin"]
    repo = env["repo"]
    cand = make_candidate("cand_stale_ack", name="Stale Ack Player", state=CandidateState.READY)
    cand.position = ""
    cand.validation_warnings = ["Ruolo del giocatore mancante"]
    repo.save(cand)

    patch_wiring(monkeypatch, service, admin)
    at = AppTest.from_string(RENDER_SCRIPT).run(timeout=20)
    at.button(key="open_cand_stale_ack").click().run()

    # Reviewer ticks the warning ack at revision 1 but never submits Approve.
    at.checkbox(key="approve_ack_warnings_cand_stale_ack_1").check().run()
    assert at.checkbox(key="approve_ack_warnings_cand_stale_ack_1").value is True

    # An edit (position still missing -> the same real warning recurs) bumps the revision.
    at.text_input(key="edit_nationality_cand_stale_ack_1").set_value("Belgio").run()
    save_buttons = [b for b in at.button if "Salva modifiche" in (b.label or "")]
    save_buttons[0].click().run()
    assert not at.exception

    edited = repo.get_by_id("cand_stale_ack")
    assert edited.revision == 2
    assert any("ruolo" in w.lower() for w in edited.validation_warnings)

    # The new revision's ack checkbox starts unchecked: the old tick never carries over.
    assert at.checkbox(key="approve_ack_warnings_cand_stale_ack_2").value is False

    # Approving without re-ticking is refused.
    at.checkbox(key="approve_confirm_cand_stale_ack_2").check().run()
    at.button(key="approve_submit_cand_stale_ack_2").click().run()
    assert not at.exception
    assert repo.get_by_id("cand_stale_ack").status != CandidateState.APPROVED

    # Re-ticking on the new revision succeeds.
    at.checkbox(key="approve_ack_warnings_cand_stale_ack_2").check().run()
    at.button(key="approve_submit_cand_stale_ack_2").click().run()
    assert not at.exception
    assert repo.get_by_id("cand_stale_ack").status == CandidateState.APPROVED


# ---------------------------------------------------------------------------
# 18. Merge target listing uses the new public service method, never a private one.
# ---------------------------------------------------------------------------

def test_merge_target_listing_uses_public_service_method(env, monkeypatch):
    service, admin = env["service"], env["admin"]
    repo, players_file = env["repo"], env["players_file"]
    players_file.write_text(
        json.dumps(
            {
                "_comment": "t",
                "players": [
                    {
                        "id": "prod_1",
                        "full_name": "Production Player",
                        "aliases": [],
                        "nationality": "Italia",
                        "position": "P",
                        "birth_year": 1985,
                        "popularity": 3,
                        "verified": True,
                        "career": [{"team": "X", "start_year": 2000, "end_year": 2010}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    repo.save(make_candidate("cand_merge2", name="Merge Player Two", state=CandidateState.READY))

    calls = []
    real_list_merge_targets = service.list_merge_targets
    monkeypatch.setattr(
        service, "list_merge_targets", lambda *a, **kw: (calls.append((a, kw)), real_list_merge_targets(*a, **kw))[1]
    )
    patch_wiring(monkeypatch, service, admin)

    at = AppTest.from_string(RENDER_SCRIPT).run(timeout=20)
    at.button(key="open_cand_merge2").click().run()
    assert not at.exception

    assert calls  # the merge tab called the new public method
    options = at.selectbox(key="merge_target_cand_merge2_1").options
    assert any("Production Player" in o for o in options)

    # The public method itself never leaks the full raw production record.
    targets = service.list_merge_targets(admin)
    assert targets == [
        {
            "player_id": "prod_1",
            "full_name": "Production Player",
            "birth_year": 1985,
            "nationality": "Italia",
        }
    ]


# ---------------------------------------------------------------------------
# 19. Structural: the Admin page source never reaches into underscore-prefixed
#     (private) members of CandidateReviewService.
# ---------------------------------------------------------------------------

def test_admin_page_never_accesses_private_service_members():
    src = inspect.getsource(player_review)
    # Matches e.g. `service._load_production_players(` or `service_for_options._foo` but
    # deliberately scoped to identifiers ending in "service"/"service_for_options" so it
    # doesn't false-positive on unrelated local underscore-prefixed variables/params.
    pattern = re.compile(r"\bservice(?:_for_options)?\._[a-zA-Z_][a-zA-Z0-9_]*")
    matches = pattern.findall(src)
    assert matches == [], f"Private CandidateReviewService member(s) accessed from the Admin UI: {matches}"


# ---------------------------------------------------------------------------
# 20. Production dataset does not change during Edit; it changes exactly once,
#     only on the later explicit Approve.
# ---------------------------------------------------------------------------

def test_dataset_unchanged_by_edit_changes_exactly_once_on_later_approve(env, monkeypatch):
    service, admin = env["service"], env["admin"]
    repo, players_file = env["repo"], env["players_file"]
    repo.save(make_candidate("cand_dataset", name="Dataset Player", state=CandidateState.READY))

    write_calls = []
    real_write = service._atomic_write_production_dataset

    def spy_write(players):
        write_calls.append(list(players))
        return real_write(players)

    monkeypatch.setattr(service, "_atomic_write_production_dataset", spy_write)
    patch_wiring(monkeypatch, service, admin)

    initial = players_file.read_text(encoding="utf-8")
    at = AppTest.from_string(RENDER_SCRIPT).run(timeout=20)
    at.button(key="open_cand_dataset").click().run()

    at.text_input(key="edit_nationality_cand_dataset_1").set_value("Germania").run()
    save_buttons = [b for b in at.button if "Salva modifiche" in (b.label or "")]
    save_buttons[0].click().run()
    assert not at.exception

    assert write_calls == []  # Edit alone never writes production
    assert players_file.read_text(encoding="utf-8") == initial

    at.checkbox(key="approve_confirm_cand_dataset_2").check().run()
    at.button(key="approve_submit_cand_dataset_2").click().run()
    assert not at.exception

    assert len(write_calls) == 1  # exactly one write, triggered only by the explicit Approve
    assert players_file.read_text(encoding="utf-8") != initial
    approved = repo.get_by_id("cand_dataset")
    assert approved.status == CandidateState.APPROVED
