"""Validates the release-check CI gate workflow (#49)."""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "release-check.yml"


def _load():
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


def test_workflow_is_valid_yaml():
    data = _load()
    assert isinstance(data, dict)


def test_workflow_triggers_only_on_version_tags():
    data = _load()
    on = data.get(True, data.get("on"))
    assert "push" in on
    assert on["push"]["tags"] == ["v*.*.*"]
    assert "pull_request" not in on
    assert "branches" not in on.get("push", {})


def test_workflow_uses_least_privilege_permissions():
    data = _load()
    assert data["permissions"] == {"contents": "read"}


def test_workflow_does_not_duplicate_the_full_test_suite():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    for forbidden in ("pytest", "npm run build", "ruff check", "mypy", "npm audit"):
        assert forbidden not in text


def test_workflow_runs_release_check_with_tag():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "python -m tools.release check --tag" in text
    assert "GITHUB_REF_NAME" in text
