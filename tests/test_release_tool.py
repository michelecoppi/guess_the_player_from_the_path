"""Tests for the deterministic release helper (#49)."""
from __future__ import annotations

import json
import subprocess

import pytest

from tools import release

# ---------------------------------------------------------------------------
# SemVer validation and bumping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["0.1.0", "1.2.3", "10.20.30", "0.0.0"])
def test_is_valid_semver_accepts_plain_semver(value):
    assert release.is_valid_semver(value)


@pytest.mark.parametrize(
    "value", ["1.2", "1.2.3.4", "v1.2.3", "1.2.3-rc.1", "01.2.3", "1.2.03", "", "latest"]
)
def test_is_valid_semver_rejects_malformed_values(value):
    assert not release.is_valid_semver(value)


@pytest.mark.parametrize(
    "current, level, expected",
    [
        ("1.2.3", "patch", "1.2.4"),
        ("1.2.3", "minor", "1.3.0"),
        ("1.2.3", "major", "2.0.0"),
        ("0.9.9", "patch", "0.9.10"),
    ],
)
def test_bump_semver(current, level, expected):
    assert release.bump_semver(current, level) == expected


def test_bump_semver_rejects_invalid_current_version():
    with pytest.raises(ValueError):
        release.bump_semver("not-a-version", "patch")


def test_bump_semver_rejects_unknown_level():
    with pytest.raises(ValueError):
        release.bump_semver("1.0.0", "sideways")


# ---------------------------------------------------------------------------
# CHANGELOG parsing
# ---------------------------------------------------------------------------

SAMPLE_CHANGELOG = """# Changelog

## [Unreleased]

### Added

- Something new.

### Changed

### Fixed

### Security

## [0.1.0] - 2026-09-14

Baseline.
"""

EMPTY_UNRELEASED_CHANGELOG = """# Changelog

## [Unreleased]

### Added

### Changed

### Fixed

### Security

## [0.1.0] - 2026-09-14

Baseline.
"""


def test_get_changelog_section_returns_body():
    body = release.get_changelog_section(SAMPLE_CHANGELOG, "Unreleased")
    assert "Something new." in body


def test_get_changelog_section_missing_returns_none():
    assert release.get_changelog_section(SAMPLE_CHANGELOG, "9.9.9") is None


def test_changelog_has_dated_entry_true_for_release_section():
    assert release.changelog_has_dated_entry(SAMPLE_CHANGELOG, "0.1.0")


def test_changelog_has_dated_entry_false_for_unreleased():
    assert not release.changelog_has_dated_entry(SAMPLE_CHANGELOG, "Unreleased")


def test_changelog_has_dated_entry_false_when_missing():
    assert not release.changelog_has_dated_entry(SAMPLE_CHANGELOG, "5.0.0")


def test_unreleased_is_empty_false_when_content_present():
    assert not release.unreleased_is_empty(SAMPLE_CHANGELOG)


def test_unreleased_is_empty_true_when_only_subheadings():
    assert release.unreleased_is_empty(EMPTY_UNRELEASED_CHANGELOG)


def test_unreleased_is_empty_true_when_section_missing():
    assert release.unreleased_is_empty("# Changelog\n\n## [0.1.0] - 2026-09-14\n")


def test_build_bumped_changelog_moves_unreleased_into_dated_section():
    result = release.build_bumped_changelog(SAMPLE_CHANGELOG, "0.2.0", "2026-10-01")
    assert "## [0.2.0] - 2026-10-01" in result
    assert "Something new." in result
    assert release.unreleased_is_empty(result)
    # Original dated release section must still be present untouched.
    assert "## [0.1.0] - 2026-09-14" in result


def test_build_bumped_changelog_requires_unreleased_section():
    with pytest.raises(ValueError):
        release.build_bumped_changelog("# Changelog\n\n## [0.1.0] - 2026-09-14\n", "0.2.0", "2026-10-01")


# ---------------------------------------------------------------------------
# package.json version reading — fail closed on any malformed metadata (#49 review)
# ---------------------------------------------------------------------------


def test_read_package_json_version_returns_valid_version(tmp_path):
    path = tmp_path / "package.json"
    path.write_text(json.dumps({"name": "x", "version": "1.2.3"}), encoding="utf-8")
    assert release.read_package_json_version(path) == "1.2.3"


def test_read_package_json_version_missing_file_raises(tmp_path):
    with pytest.raises(release.PackageJsonError):
        release.read_package_json_version(tmp_path / "does-not-exist.json")


def test_read_package_json_version_malformed_json_raises(tmp_path):
    path = tmp_path / "package.json"
    path.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(release.PackageJsonError):
        release.read_package_json_version(path)


def test_read_package_json_version_missing_version_field_raises(tmp_path):
    path = tmp_path / "package.json"
    path.write_text(json.dumps({"name": "x"}), encoding="utf-8")
    with pytest.raises(release.PackageJsonError):
        release.read_package_json_version(path)


def test_read_package_json_version_non_string_version_raises(tmp_path):
    path = tmp_path / "package.json"
    path.write_text(json.dumps({"name": "x", "version": 123}), encoding="utf-8")
    with pytest.raises(release.PackageJsonError):
        release.read_package_json_version(path)


def test_read_package_json_version_blank_version_raises(tmp_path):
    path = tmp_path / "package.json"
    path.write_text(json.dumps({"name": "x", "version": "   "}), encoding="utf-8")
    with pytest.raises(release.PackageJsonError):
        release.read_package_json_version(path)


def test_read_package_json_version_top_level_array_raises(tmp_path):
    path = tmp_path / "package.json"
    path.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")
    with pytest.raises(release.PackageJsonError):
        release.read_package_json_version(path)


def test_build_package_json_update_replaces_version_only():
    raw = '{\r\n  "name": "x",\r\n  "version": "0.1.0"\r\n}\r\n'
    updated = release.build_package_json_update(raw, "0.2.0")
    assert '"version": "0.2.0"' in updated
    assert '"name": "x"' in updated
    # Formatting (CRLF, indentation) must be preserved, not reformatted via json.dumps.
    assert updated.count("\r\n") == raw.count("\r\n")


def test_build_package_json_update_raises_when_version_field_absent():
    with pytest.raises(release.PackageJsonError):
        release.build_package_json_update('{"name": "x"}', "0.2.0")


# ---------------------------------------------------------------------------
# check (read-only)
# ---------------------------------------------------------------------------


def _write_repo_fixture(tmp_path, *, version="0.1.0", package_version="0.1.0", changelog=SAMPLE_CHANGELOG):
    (tmp_path / "VERSION").write_text(version + "\n", encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "release-checklist.md").write_text("# Release checklist\n", encoding="utf-8")
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "x", "version": package_version}), encoding="utf-8"
    )


def _patch_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(release, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(release, "VERSION_PATH", tmp_path / "VERSION")
    monkeypatch.setattr(release, "CHANGELOG_PATH", tmp_path / "CHANGELOG.md")
    monkeypatch.setattr(release, "PACKAGE_JSON_PATH", tmp_path / "package.json")
    monkeypatch.setattr(
        release,
        "REQUIRED_RELEASE_FILES",
        (tmp_path / "VERSION", tmp_path / "CHANGELOG.md", tmp_path / "docs" / "release-checklist.md"),
    )
    # git metadata is best-effort and irrelevant to what's under test here.
    monkeypatch.setattr(release, "git_head_sha", lambda: "deadbeef")
    monkeypatch.setattr(release, "git_is_dirty", lambda: False)


def test_run_check_passes_on_consistent_repo(tmp_path, monkeypatch):
    _write_repo_fixture(tmp_path)
    _patch_paths(monkeypatch, tmp_path)
    errors, summary = release.run_check()
    assert errors == []
    assert summary["version"] == "0.1.0"


def test_run_check_detects_invalid_semver(tmp_path, monkeypatch):
    _write_repo_fixture(tmp_path, version="not-a-version", package_version="not-a-version")
    _patch_paths(monkeypatch, tmp_path)
    errors, _summary = release.run_check()
    assert any("invalid SemVer" in e for e in errors)


def test_run_check_detects_package_json_drift(tmp_path, monkeypatch):
    _write_repo_fixture(tmp_path, version="0.1.0", package_version="0.2.0")
    _patch_paths(monkeypatch, tmp_path)
    errors, _summary = release.run_check()
    assert any("does not match VERSION" in e for e in errors)


def test_run_check_detects_missing_package_json(tmp_path, monkeypatch):
    _write_repo_fixture(tmp_path)
    (tmp_path / "package.json").unlink()
    _patch_paths(monkeypatch, tmp_path)
    errors, summary = release.run_check()
    assert any("package.json not found" in e for e in errors)
    assert summary["package_json_version"] is None


def test_run_check_detects_malformed_package_json(tmp_path, monkeypatch):
    _write_repo_fixture(tmp_path)
    (tmp_path / "package.json").write_text("{not valid json", encoding="utf-8")
    _patch_paths(monkeypatch, tmp_path)
    errors, summary = release.run_check()
    assert any("not valid JSON" in e for e in errors)
    assert summary["package_json_version"] is None


def test_run_check_detects_missing_version_field_in_package_json(tmp_path, monkeypatch):
    _write_repo_fixture(tmp_path)
    (tmp_path / "package.json").write_text(json.dumps({"name": "x"}), encoding="utf-8")
    _patch_paths(monkeypatch, tmp_path)
    errors, _summary = release.run_check()
    assert any("no valid string 'version'" in e for e in errors)


def test_run_check_detects_non_string_version_in_package_json(tmp_path, monkeypatch):
    _write_repo_fixture(tmp_path)
    (tmp_path / "package.json").write_text(json.dumps({"name": "x", "version": 123}), encoding="utf-8")
    _patch_paths(monkeypatch, tmp_path)
    errors, _summary = release.run_check()
    assert any("no valid string 'version'" in e for e in errors)


def test_run_check_malformed_package_json_does_not_also_report_bogus_drift(tmp_path, monkeypatch):
    """A malformed package.json must produce exactly one clear error, not a confusing
    'None does not match VERSION' — the drift check should never fire without a real value.
    """
    _write_repo_fixture(tmp_path)
    (tmp_path / "package.json").write_text("{not valid json", encoding="utf-8")
    _patch_paths(monkeypatch, tmp_path)
    errors, _summary = release.run_check()
    assert not any("does not match VERSION" in e for e in errors)


def test_run_check_detects_missing_required_files(tmp_path, monkeypatch):
    _write_repo_fixture(tmp_path)
    (tmp_path / "docs" / "release-checklist.md").unlink()
    _patch_paths(monkeypatch, tmp_path)
    errors, summary = release.run_check()
    assert any("required release file missing" in e for e in errors)
    assert summary["missing_files"]


def test_run_check_with_tag_requires_matching_dated_entry(tmp_path, monkeypatch):
    _write_repo_fixture(tmp_path)
    _patch_paths(monkeypatch, tmp_path)
    errors, _summary = release.run_check(tag="v0.9.0")
    assert any("does not match VERSION" in e for e in errors)


def test_run_check_with_matching_tag_and_dated_entry_passes(tmp_path, monkeypatch):
    _write_repo_fixture(tmp_path)
    _patch_paths(monkeypatch, tmp_path)
    errors, _summary = release.run_check(tag="v0.1.0")
    assert errors == []


def test_run_check_with_tag_missing_changelog_entry(tmp_path, monkeypatch):
    _write_repo_fixture(tmp_path, version="0.2.0", package_version="0.2.0")
    _patch_paths(monkeypatch, tmp_path)
    errors, _summary = release.run_check(tag="v0.2.0")
    assert any("no dated entry" in e for e in errors)


def test_check_does_not_modify_any_file(tmp_path, monkeypatch):
    _write_repo_fixture(tmp_path)
    _patch_paths(monkeypatch, tmp_path)
    before = {p.name: p.read_text(encoding="utf-8") for p in tmp_path.rglob("*") if p.is_file()}
    release.run_check()
    after = {p.name: p.read_text(encoding="utf-8") for p in tmp_path.rglob("*") if p.is_file()}
    assert before == after


# ---------------------------------------------------------------------------
# bump (local file mutation only — never git/remote)
# ---------------------------------------------------------------------------


def test_cmd_bump_updates_version_and_changelog(tmp_path, monkeypatch, capsys):
    _write_repo_fixture(tmp_path)
    _patch_paths(monkeypatch, tmp_path)
    args = release.build_parser().parse_args(["bump", "minor", "--date", "2026-10-01"])
    code = release.cmd_bump(args)
    assert code == 0
    assert release.read_version(tmp_path / "VERSION") == "0.2.0"
    changelog = (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## [0.2.0] - 2026-10-01" in changelog
    assert release.unreleased_is_empty(changelog)
    package_data = json.loads((tmp_path / "package.json").read_text(encoding="utf-8"))
    assert package_data["version"] == "0.2.0"


def test_cmd_bump_refuses_when_unreleased_empty(tmp_path, monkeypatch):
    _write_repo_fixture(tmp_path, changelog=EMPTY_UNRELEASED_CHANGELOG)
    _patch_paths(monkeypatch, tmp_path)
    args = release.build_parser().parse_args(["bump", "patch"])
    code = release.cmd_bump(args)
    assert code == 1
    assert release.read_version(tmp_path / "VERSION") == "0.1.0"


def test_cmd_bump_allow_empty_overrides_refusal(tmp_path, monkeypatch):
    _write_repo_fixture(tmp_path, changelog=EMPTY_UNRELEASED_CHANGELOG)
    _patch_paths(monkeypatch, tmp_path)
    args = release.build_parser().parse_args(["bump", "patch", "--allow-empty", "--date", "2026-10-01"])
    code = release.cmd_bump(args)
    assert code == 0
    assert release.read_version(tmp_path / "VERSION") == "0.1.1"


def test_cmd_bump_preflight_fails_closed_on_malformed_package_json(tmp_path, monkeypatch, capsys):
    """Regression for the fail-closed bump requirement: a malformed package.json must abort
    the whole bump *before* VERSION or CHANGELOG.md are touched — never a half-applied bump.
    """
    _write_repo_fixture(tmp_path)
    original_version_text = (tmp_path / "VERSION").read_text(encoding="utf-8")
    original_changelog_text = (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8")
    (tmp_path / "package.json").write_text("{not valid json", encoding="utf-8")
    _patch_paths(monkeypatch, tmp_path)

    args = release.build_parser().parse_args(["bump", "patch", "--date", "2026-10-01"])
    code = release.cmd_bump(args)

    assert code == 1
    assert (tmp_path / "VERSION").read_text(encoding="utf-8") == original_version_text
    assert (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8") == original_changelog_text
    assert "package.json" in capsys.readouterr().err


def test_cmd_bump_preflight_fails_closed_when_package_json_missing(tmp_path, monkeypatch):
    _write_repo_fixture(tmp_path)
    original_version_text = (tmp_path / "VERSION").read_text(encoding="utf-8")
    original_changelog_text = (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8")
    (tmp_path / "package.json").unlink()
    _patch_paths(monkeypatch, tmp_path)

    args = release.build_parser().parse_args(["bump", "patch", "--date", "2026-10-01"])
    code = release.cmd_bump(args)

    assert code == 1
    assert (tmp_path / "VERSION").read_text(encoding="utf-8") == original_version_text
    assert (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8") == original_changelog_text


def test_cmd_bump_preflight_fails_closed_when_version_field_missing_from_package_json(tmp_path, monkeypatch):
    _write_repo_fixture(tmp_path)
    original_version_text = (tmp_path / "VERSION").read_text(encoding="utf-8")
    original_changelog_text = (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8")
    (tmp_path / "package.json").write_text(json.dumps({"name": "x"}), encoding="utf-8")
    _patch_paths(monkeypatch, tmp_path)

    args = release.build_parser().parse_args(["bump", "patch", "--date", "2026-10-01"])
    code = release.cmd_bump(args)

    assert code == 1
    assert (tmp_path / "VERSION").read_text(encoding="utf-8") == original_version_text
    assert (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8") == original_changelog_text


def test_cmd_bump_preflight_runs_before_any_write_is_observed(tmp_path, monkeypatch):
    """Belt-and-suspenders: patch write_text itself to prove it is never called when the
    package.json preflight fails, rather than only checking the end-state content.
    """
    _write_repo_fixture(tmp_path)
    (tmp_path / "package.json").write_text("{not valid json", encoding="utf-8")
    _patch_paths(monkeypatch, tmp_path)

    from pathlib import Path

    real_write_text = Path.write_text
    calls = []

    def spy_write_text(self, *args, **kwargs):
        calls.append(self)
        return real_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", spy_write_text)
    args = release.build_parser().parse_args(["bump", "patch", "--date", "2026-10-01"])
    assert release.cmd_bump(args) == 1
    assert calls == []


def test_cmd_bump_never_calls_git_or_subprocess(tmp_path, monkeypatch):
    _write_repo_fixture(tmp_path)
    _patch_paths(monkeypatch, tmp_path)

    def _forbidden(*args, **kwargs):
        raise AssertionError("tools.release bump must never shell out (git/deploy/etc.)")

    monkeypatch.setattr(subprocess, "run", _forbidden)
    args = release.build_parser().parse_args(["bump", "patch", "--date", "2026-10-01"])
    assert release.cmd_bump(args) == 0


def test_cmd_bump_does_not_touch_git_repo_state(tmp_path, monkeypatch):
    """Guards against future changes accidentally adding a git/tag/push call to bump."""
    _write_repo_fixture(tmp_path)
    _patch_paths(monkeypatch, tmp_path)
    assert not (tmp_path / ".git").exists()
    args = release.build_parser().parse_args(["bump", "patch", "--date", "2026-10-01"])
    release.cmd_bump(args)
    assert not (tmp_path / ".git").exists()


# ---------------------------------------------------------------------------
# notes
# ---------------------------------------------------------------------------


def test_cmd_notes_default_prints_unreleased(tmp_path, monkeypatch, capsys):
    _write_repo_fixture(tmp_path)
    _patch_paths(monkeypatch, tmp_path)
    args = release.build_parser().parse_args(["notes"])
    assert release.cmd_notes(args) == 0
    assert "Something new." in capsys.readouterr().out


def test_cmd_notes_specific_version_strips_leading_v(tmp_path, monkeypatch, capsys):
    _write_repo_fixture(tmp_path)
    _patch_paths(monkeypatch, tmp_path)
    args = release.build_parser().parse_args(["notes", "v0.1.0"])
    assert release.cmd_notes(args) == 0
    assert "Baseline." in capsys.readouterr().out


def test_cmd_notes_unknown_version_fails(tmp_path, monkeypatch):
    _write_repo_fixture(tmp_path)
    _patch_paths(monkeypatch, tmp_path)
    args = release.build_parser().parse_args(["notes", "9.9.9"])
    assert release.cmd_notes(args) == 1


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------


def test_main_version_command(tmp_path, monkeypatch, capsys):
    _write_repo_fixture(tmp_path)
    _patch_paths(monkeypatch, tmp_path)
    assert release.main(["version"]) == 0
    assert capsys.readouterr().out.strip() == "0.1.0"


def test_main_requires_a_subcommand():
    with pytest.raises(SystemExit):
        release.build_parser().parse_args([])
