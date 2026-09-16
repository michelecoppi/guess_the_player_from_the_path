"""Regression tests for two review fixes to the release-management docs/code (#49):

1. `VERSION` (formal release label) must never be documented/exposed as if it alone proved
   what's deployed — a separate, runtime-provided build identity (`revision`) must exist
   and be referenced everywhere the docs talk about "what's actually running."
2. The release lifecycle must document version-bump-then-commit, so the release candidate
   SHA is unambiguous (the commit *containing* the bump, not a commit chosen before it).

These assert on doc text and source code together, so a future edit that silently drifts
one away from the other (e.g. renaming `revision` in bot.py without updating the docs) is
caught here rather than discovered at release time.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE_DOC = (ROOT / "docs" / "release-checklist.md").read_text(encoding="utf-8")
# The service root endpoint (GET /) lives with the static routes since #110.
ROOT_ENDPOINT_PY = (ROOT / "apps" / "api" / "static.py").read_text(encoding="utf-8")
VERSION_SERVICE = (ROOT / "services" / "version.py").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Release version vs. deployed build identity
# ---------------------------------------------------------------------------


def test_docs_have_a_dedicated_version_vs_revision_section():
    assert "Release version vs. deployed build identity" in RELEASE_DOC


def test_docs_reference_k_revision_as_the_runtime_source_of_truth():
    assert "K_REVISION" in RELEASE_DOC


def test_docs_explicitly_warn_against_treating_version_as_proof():
    assert "as if `version` alone proved it" in RELEASE_DOC


def test_docs_state_untagged_deploys_can_exist_between_releases():
    assert "untagged" in RELEASE_DOC.lower()


def test_bot_root_endpoint_exposes_both_version_and_revision():
    assert '"version": version.get_version()' in ROOT_ENDPOINT_PY
    assert '"revision": version.get_build_revision()' in ROOT_ENDPOINT_PY


def test_version_service_does_not_fabricate_a_git_sha():
    # get_build_revision must only ever read a runtime-provided identifier (K_REVISION),
    # never something this repo can't actually prove (e.g. reading .git itself).
    assert "K_REVISION" in VERSION_SERVICE
    assert "subprocess" not in VERSION_SERVICE
    assert ".git" not in VERSION_SERVICE


def test_release_evidence_format_records_revision_not_just_version():
    evidence_section = RELEASE_DOC.split("## 12. Release evidence")[1].split("## 13.")[0]
    assert "deployed revision" in evidence_section
    assert "proof" in evidence_section.lower()


# ---------------------------------------------------------------------------
# Release lifecycle ordering: bump/commit happens before "release candidate" is named
# ---------------------------------------------------------------------------


def _lifecycle_section():
    start = RELEASE_DOC.index("## 4. Release lifecycle")
    end = RELEASE_DOC.index("## 5. Release checklist")
    return RELEASE_DOC[start:end]


def _lifecycle_diagram():
    """Just the fenced ASCII flow, not the surrounding prose (which mentions "release
    candidate" and "commit" in explanatory sentences ahead of the diagram itself).
    """
    section = _lifecycle_section()
    fence_start = section.index("```\n") + len("```\n")
    fence_end = section.index("```", fence_start)
    return section[fence_start:fence_end]


def test_lifecycle_prepares_release_before_naming_the_candidate():
    diagram = _lifecycle_diagram()
    prepare_index = diagram.index("prepare release")
    candidate_index = diagram.index("release candidate")
    assert prepare_index < candidate_index, (
        "docs must bump/commit release metadata BEFORE the commit is called a release "
        "candidate — bumping on top of an already-chosen candidate silently swaps in an "
        "unvalidated SHA"
    )


def test_lifecycle_commits_the_bump_before_the_candidate_step():
    diagram = _lifecycle_diagram()
    commit_index = diagram.index("commit / merge")
    candidate_index = diagram.index("release candidate")
    assert commit_index < candidate_index


def test_lifecycle_validates_before_tagging():
    diagram = _lifecycle_diagram()
    candidate_index = diagram.index("release candidate")
    validation_index = diagram.index("validation")
    tag_index = diagram.rindex("tag ")
    assert candidate_index < validation_index < tag_index


def test_lifecycle_explains_why_ordering_matters():
    section = _lifecycle_section()
    assert "writes files" in section
    assert "no ambiguity" in section.lower()


def test_bump_tool_docs_point_at_the_lifecycle_section():
    tooling_section = RELEASE_DOC.split("## 7. Release tooling")[1].split("## 8.")[0]
    assert "§4" in tooling_section or "release candidate" in tooling_section
