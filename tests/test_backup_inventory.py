"""The backup inventory must match the code, the docs and the workflows (#50).

The pre-#50 exporter kept its own hand-written list and silently missed `referrals`,
`app_duels` and `group_rounds`. Here the collection names are scanned out of the source, so a
new collection cannot be added without a deliberate backup decision.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import yaml

from services.firestore_backup import inventory

ROOT = Path(__file__).resolve().parents[1]
SCANNED = [ROOT / "bot.py", ROOT / "admin_ui.py", *(ROOT / "apps").rglob("*.py"), *(ROOT / "domains").rglob("*.py"),
           *(ROOT / "services").rglob("*.py"),
           *(ROOT / "handlers").rglob("*.py"), *(ROOT / "admin_pages").rglob("*.py"), *(ROOT / "scripts").glob("*.py")]
DOC = (ROOT / "docs" / "backup-recovery.md").read_text(encoding="utf-8")


def _string_constants(tree):
    return {target.id: node.value.value
            for node in ast.walk(tree) if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
            for target in node.targets if isinstance(target, ast.Name)}


def collection_names_in_code():
    """Every collection name passed to `.collection()`/`.collection_group()` that can be
    resolved statically: literals, module constants and `module.CONSTANT` attributes."""
    trees = {path: ast.parse(path.read_text(encoding="utf-8")) for path in SCANNED if "firestore_backup" not in path.parts}
    global_constants: dict[str, str] = {}
    for tree in trees.values():
        global_constants.update(_string_constants(tree))
    found = {}
    for path, tree in trees.items():
        local = _string_constants(tree)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in ("collection", "collection_group") and node.args):
                continue
            arg = node.args[0]
            name = None
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                name = arg.value
            elif isinstance(arg, ast.Name):
                name = local.get(arg.id)
            elif isinstance(arg, ast.Attribute):
                name = global_constants.get(arg.attr)
            if name:
                found.setdefault(name, f"{path.relative_to(ROOT)}:{node.lineno}")
    return found


def test_the_scanner_sees_the_collections_the_old_backup_missed():
    names = collection_names_in_code()
    for name in ("referrals", "app_duels", "group_rounds", "work_receipts", "update_locks", "daily_jobs",
                 "monthly_closures", "users", "history", "participants", "members", "players"):
        assert name in names, name


def test_every_collection_in_the_code_is_classified():
    known = set(inventory.all_names())
    for policy in inventory.INVENTORY:
        known.update(policy.subcollections)
    unknown = {name: where for name, where in collection_names_in_code().items() if name not in known}
    assert not unknown, f"classify these in services/firestore_backup/inventory.py: {unknown}"


def test_every_inventory_entry_is_still_used_by_the_code():
    names = collection_names_in_code()
    stale = [name for name in inventory.all_names() if name not in names]
    stale += [sub for policy in inventory.INVENTORY for sub in policy.subcollections if sub not in names]
    assert not stale


def test_the_known_durable_omissions_are_now_backed_up():
    for name in ("referrals", "app_duels", "group_rounds"):
        assert name in inventory.backed_up_names()


def test_every_exclusion_is_ephemeral_and_explained():
    assert set(inventory.excluded_names()) == {"work_receipts", "update_locks"}
    for policy in inventory.INVENTORY:
        assert policy.classification in (inventory.DURABLE, inventory.RECONSTRUCTABLE, inventory.EPHEMERAL)
        assert len(policy.reason) > 40
        if not policy.backed_up:
            assert policy.classification == inventory.EPHEMERAL and not policy.recovery_critical
        if policy.classification == inventory.DURABLE:
            assert policy.backed_up


def test_the_docs_table_matches_the_inventory():
    rows = {match[1]: match for match in re.finditer(
        r"^\| `(\w+)` \| (\w+) \| (yes|no) \| ([^|]+) \| (yes|no) \|", DOC, flags=re.MULTILINE)}
    assert sorted(rows) == sorted(inventory.all_names())
    for policy in inventory.INVENTORY:
        row = rows[policy.name]
        assert row[2] == policy.classification
        assert row[3] == ("yes" if policy.backed_up else "no")
        assert re.findall(r"`(\w+)`", row[4]) == list(policy.subcollections)
        assert row[5] == ("yes" if policy.recovery_critical else "no")


def test_the_firestore_map_lists_every_inventory_collection():
    firestore_doc = (ROOT / "docs" / "firestore.md").read_text(encoding="utf-8")
    for name in inventory.all_names():
        assert f"`{name}/" in firestore_doc, name
    assert "backup-recovery.md" in firestore_doc


def test_the_release_checklist_backup_gate_points_to_the_verified_procedure():
    checklist = (ROOT / "docs" / "release-checklist.md").read_text(encoding="utf-8")
    gate = checklist.split("### 8.2 Backup gate")[1].split("## 9.")[0]
    assert "backup-recovery.md" in gate
    assert "restore_firestore.py validate" in gate
    assert "does not export `referrals`" not in checklist


# ---------------------------------------------------------------------------
# Workflows
# ---------------------------------------------------------------------------

def _workflow(name):
    path = ROOT / ".github" / "workflows" / name
    return yaml.safe_load(path.read_text(encoding="utf-8")), path.read_text(encoding="utf-8")


def _steps(data):
    return [step for job in data["jobs"].values() for step in job["steps"]]


def test_the_weekly_backup_keeps_wif_retention_and_validates_before_upload():
    data, text = _workflow("backup.yml")
    on = data.get(True, data.get("on"))
    assert on["schedule"] and "workflow_dispatch" in on
    assert data["permissions"] == {"contents": "read", "id-token": "write"}
    steps = _steps(data)
    auth = next(step for step in steps if step.get("uses", "").startswith("google-github-actions/auth"))
    assert set(auth["with"]) == {"workload_identity_provider", "service_account"}
    assert "credentials_json" not in text
    uses = [step.get("uses", "") or step.get("run", "") for step in steps]
    export = next(i for i, step in enumerate(uses) if "backup_firestore.py" in step)
    validate = next(i for i, step in enumerate(uses) if "restore_firestore.py validate" in step)
    upload = next(i for i, step in enumerate(uses) if step.startswith("actions/upload-artifact"))
    assert export < validate < upload
    upload_step = steps[upload]
    assert upload_step["with"]["retention-days"] >= 365
    assert upload_step["with"]["if-no-files-found"] == "error"
    assert "run" in upload_step["with"]["name"] or "outputs.name" in upload_step["with"]["name"]
    assert "--expect-source-project" in text


def test_the_restore_verification_workflow_cannot_reach_production():
    data, text = _workflow("restore-verification.yml")
    on = data.get(True, data.get("on"))
    assert on["schedule"] and "workflow_dispatch" in on
    assert data["permissions"] == {"contents": "read"}
    assert "secrets." not in text
    assert "google-github-actions/auth" not in text
    assert "--allow-production" not in text
    assert "guess-the-player-from-path-bot" not in text
    steps = _steps(data)
    test_step = next(step for step in steps if "test_backup_restore_emulator.py" in step.get("run", ""))
    assert test_step["env"]["FIRESTORE_EMULATOR_HOST"].startswith("127.0.0.1:")
