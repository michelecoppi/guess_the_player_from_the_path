"""Validates the production Deploy workflow ordering guarantees (#174)."""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "deploy.yml"


def _load():
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


def _job():
    return _load()["jobs"]["deploy"]


def test_deploy_runs_only_after_successful_ci_on_main():
    data = _load()
    on = data.get(True, data.get("on"))
    assert on["workflow_run"] == {
        "workflows": ["CI"],
        "types": ["completed"],
        "branches": ["main"],
    }
    assert _job()["if"] == "${{ github.event.workflow_run.conclusion == 'success' }}"


def test_deploys_are_serialized_without_cancelling_a_running_deploy():
    # Job-level, not workflow-level: a failed CI (job skipped by `if`) must not enter the
    # queue and displace a valid pending deploy.
    assert "concurrency" not in _load()
    assert _job()["concurrency"] == {
        "group": "deploy-production",
        "cancel-in-progress": False,
    }


def test_first_step_selects_the_main_tip_with_green_ci():
    steps = _job()["steps"]
    target = steps[0]
    assert target["id"] == "target"
    script = target["run"]
    assert "repos/$REPO/commits/main" in script
    assert "head_sha=$tip" in script
    assert "event=push" in script
    assert '"$conclusion" = "success"' in script


def test_every_later_step_is_gated_on_the_selected_commit():
    steps = _job()["steps"][1:]
    assert steps
    for step in steps:
        assert step["if"] == "${{ steps.target.outputs.sha != '' }}"
    checkout = next(s for s in steps if s.get("uses", "").startswith("actions/checkout@"))
    assert checkout["with"]["ref"] == "${{ steps.target.outputs.sha }}"
    assert "head_sha" not in str(checkout)


def test_deploy_pins_the_execution_environment():
    """#264: the environment is chosen on purpose (faster cold start), never left to Cloud Run.
    Removing the flag would not revert it: a rollback sets gen2 explicitly."""
    deploy = next(s for s in _job()["steps"] if "gcloud run deploy" in s.get("run", ""))
    assert "--execution-environment gen1" in deploy["run"]
    assert "--max-instances 10" in deploy["run"]


def test_permissions_allow_reading_ci_runs_and_nothing_more():
    assert _load()["permissions"] == {
        "actions": "read",
        "contents": "read",
        "id-token": "write",
    }
