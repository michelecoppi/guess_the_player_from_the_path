"""Deterministic release helper (#49).

Read-only by default (`version`, `check`, `notes`). `bump` mutates the canonical
version and CHANGELOG.md locally but never touches git or any remote system: it does
not commit, tag, push, or deploy. Those steps stay explicit operator actions — see
docs/release-checklist.md for the full process this tool supports.

Usage:
    python -m tools.release version
    python -m tools.release check [--tag vX.Y.Z]
    python -m tools.release bump <major|minor|patch> [--allow-empty] [--date YYYY-MM-DD]
    python -m tools.release notes [X.Y.Z]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT_DIR = Path(__file__).resolve().parents[1]
VERSION_PATH = ROOT_DIR / "VERSION"
CHANGELOG_PATH = ROOT_DIR / "CHANGELOG.md"
PACKAGE_JSON_PATH = ROOT_DIR / "package.json"
REQUIRED_RELEASE_FILES = (
    VERSION_PATH,
    CHANGELOG_PATH,
    ROOT_DIR / "docs" / "release-checklist.md",
)

SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_HEADING_RE = re.compile(r"^## \[(?P<name>[^\]]+)\](?: - (?P<date>\d{4}-\d{2}-\d{2}))?\s*$")
_SUBHEADING_RE = re.compile(r"^### ")


def read_version(path: Optional[Path] = None) -> str:
    """Reads and strips the canonical VERSION file. Raises FileNotFoundError if missing."""
    return (path or VERSION_PATH).read_text(encoding="utf-8").strip()


def is_valid_semver(value: str) -> bool:
    """MAJOR.MINOR.PATCH only (no pre-release/build metadata) — see release policy."""
    return bool(SEMVER_RE.match(value))


def bump_semver(current: str, level: str) -> str:
    if not is_valid_semver(current):
        raise ValueError(f"'{current}' is not a valid MAJOR.MINOR.PATCH version")
    major, minor, patch = (int(part) for part in current.split("."))
    if level == "major":
        return f"{major + 1}.0.0"
    if level == "minor":
        return f"{major}.{minor + 1}.0"
    if level == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"unknown bump level '{level}' (use major, minor or patch)")


def read_package_json_version(path: Optional[Path] = None) -> Optional[str]:
    try:
        data = json.loads((path or PACKAGE_JSON_PATH).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    version = data.get("version")
    return version if isinstance(version, str) else None


def _split_sections(text: str) -> list[tuple[str, Optional[str], int, int]]:
    """Returns (name, date_or_None, body_start_line, body_end_line) for each `## [...]` heading."""
    lines = text.splitlines()
    headings = []
    for index, line in enumerate(lines):
        match = _HEADING_RE.match(line)
        if match:
            headings.append((match.group("name"), match.group("date"), index))
    sections = []
    for position, (name, date, start) in enumerate(headings):
        end = headings[position + 1][2] if position + 1 < len(headings) else len(lines)
        sections.append((name, date, start + 1, end))
    return sections


def get_changelog_section(text: str, name: str) -> Optional[str]:
    """Returns the raw body text of a `## [name]` section, or None if absent."""
    lines = text.splitlines()
    for section_name, _date, start, end in _split_sections(text):
        if section_name == name:
            return "\n".join(lines[start:end]).strip("\n")
    return None


def changelog_has_dated_entry(text: str, version: str) -> bool:
    return any(
        name == version and date is not None for name, date, _start, _end in _split_sections(text)
    )


def unreleased_is_empty(text: str) -> bool:
    """True if the Unreleased section has no content beyond its `### ` subheadings."""
    body = get_changelog_section(text, "Unreleased")
    if body is None:
        return True
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or _SUBHEADING_RE.match(stripped):
            continue
        return False
    return True


def build_bumped_changelog(text: str, new_version: str, release_date: str) -> str:
    """Moves the Unreleased body into a new dated section and resets Unreleased to blank."""
    sections = _split_sections(text)
    unreleased = next((s for s in sections if s[0] == "Unreleased"), None)
    if unreleased is None:
        raise ValueError("CHANGELOG.md has no '## [Unreleased]' section")
    lines = text.splitlines()
    _name, _date, start, end = unreleased
    unreleased_body = lines[start:end]

    blank_body = ["", "### Added", "", "### Changed", "", "### Fixed", "", "### Security", ""]
    new_section_heading = f"## [{new_version}] - {release_date}"

    new_lines = lines[:start] + blank_body + [new_section_heading] + unreleased_body + lines[end:]
    result = "\n".join(new_lines)
    if not result.endswith("\n"):
        result += "\n"
    return result


def _git(args: list[str]) -> Optional[str]:
    try:
        proc = subprocess.run(
            ["git", *args], cwd=str(ROOT_DIR), capture_output=True, text=True, check=True
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return proc.stdout.strip()


def git_head_sha() -> Optional[str]:
    return _git(["rev-parse", "HEAD"])


def git_is_dirty() -> Optional[bool]:
    status = _git(["status", "--porcelain"])
    return None if status is None else bool(status)


def check_required_files() -> list[str]:
    return [str(p.relative_to(ROOT_DIR)) for p in REQUIRED_RELEASE_FILES if not p.exists()]


def run_check(tag: Optional[str] = None) -> tuple[list[str], dict]:
    """Runs deterministic release-metadata validation. Returns (errors, summary)."""
    errors: list[str] = []

    missing_files = check_required_files()
    for path in missing_files:
        errors.append(f"required release file missing: {path}")

    version = None
    if VERSION_PATH.exists():
        version = read_version()
        if not is_valid_semver(version):
            errors.append(f"VERSION contains an invalid SemVer string: '{version}'")

    package_version = read_package_json_version()
    if version and package_version and package_version != version:
        errors.append(
            f"package.json version ('{package_version}') does not match VERSION ('{version}')"
        )

    changelog_text = None
    unreleased_empty = None
    if CHANGELOG_PATH.exists():
        changelog_text = CHANGELOG_PATH.read_text(encoding="utf-8")
        if get_changelog_section(changelog_text, "Unreleased") is None:
            errors.append("CHANGELOG.md has no '## [Unreleased]' section")
        else:
            unreleased_empty = unreleased_is_empty(changelog_text)

    tag_version = None
    if tag is not None:
        tag_version = tag[1:] if tag.startswith("v") else tag
        if not is_valid_semver(tag_version):
            errors.append(f"tag '{tag}' does not resolve to a valid MAJOR.MINOR.PATCH version")
        elif version and tag_version != version:
            errors.append(f"tag version ('{tag_version}') does not match VERSION ('{version}')")
        if changelog_text is not None and tag_version and not changelog_has_dated_entry(
            changelog_text, tag_version
        ):
            errors.append(f"CHANGELOG.md has no dated entry for '{tag_version}'")

    summary = {
        "version": version,
        "package_json_version": package_version,
        "tag": tag,
        "tag_version": tag_version,
        "head_sha": git_head_sha(),
        "working_tree_dirty": git_is_dirty(),
        "unreleased_empty": unreleased_empty,
        "missing_files": missing_files,
    }
    return errors, summary


def _print_summary(summary: dict) -> None:
    print("\n=== Release summary ===")
    print(f"  version            : {summary.get('version')}")
    print(f"  package.json version: {summary.get('package_json_version')}")
    if summary.get("tag") is not None:
        print(f"  tag                : {summary.get('tag')} (-> {summary.get('tag_version')})")
    print(f"  HEAD SHA           : {summary.get('head_sha')}")
    print(f"  working tree dirty : {summary.get('working_tree_dirty')}")
    print(f"  Unreleased empty   : {summary.get('unreleased_empty')}")


def cmd_version(_args: argparse.Namespace) -> int:
    try:
        print(read_version())
    except FileNotFoundError:
        print(f"error: {VERSION_PATH} not found", file=sys.stderr)
        return 1
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    errors, summary = run_check(tag=args.tag)
    _print_summary(summary)
    if errors:
        print("\n[FAIL] Release check found problems:")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("\n[OK] Release metadata is consistent.")
    return 0


def cmd_bump(args: argparse.Namespace) -> int:
    try:
        current = read_version()
    except FileNotFoundError:
        print(f"error: {VERSION_PATH} not found", file=sys.stderr)
        return 1

    try:
        new_version = bump_semver(current, args.level)
    except ValueError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1

    if not CHANGELOG_PATH.exists():
        print(f"error: {CHANGELOG_PATH} not found", file=sys.stderr)
        return 1
    changelog_text = CHANGELOG_PATH.read_text(encoding="utf-8")

    if unreleased_is_empty(changelog_text) and not args.allow_empty:
        print(
            "error: CHANGELOG.md '## [Unreleased]' has no entries — nothing to release.\n"
            "       Add entries first, or pass --allow-empty to bump anyway.",
            file=sys.stderr,
        )
        return 1

    release_date = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    new_changelog = build_bumped_changelog(changelog_text, new_version, release_date)

    VERSION_PATH.write_text(new_version + "\n", encoding="utf-8")
    CHANGELOG_PATH.write_text(new_changelog, encoding="utf-8")

    updated_package_json = False
    if PACKAGE_JSON_PATH.exists():
        raw = PACKAGE_JSON_PATH.read_text(encoding="utf-8")
        replaced, count = re.subn(
            r'("version"\s*:\s*")[^"]*(")', rf"\g<1>{new_version}\g<2>", raw, count=1
        )
        if count == 1:
            PACKAGE_JSON_PATH.write_text(replaced, encoding="utf-8")
            updated_package_json = True

    print(f"Bumped version: {current} -> {new_version} ({args.level})")
    print(f"  updated: {VERSION_PATH.relative_to(ROOT_DIR)}")
    print(f"  updated: {CHANGELOG_PATH.relative_to(ROOT_DIR)} (Unreleased -> [{new_version}] - {release_date})")
    if updated_package_json:
        print(f"  updated: {PACKAGE_JSON_PATH.relative_to(ROOT_DIR)}")
    print(
        "\nNothing was committed, tagged, pushed or deployed. Review the diff, commit it,\n"
        "then follow docs/release-checklist.md to tag and deploy."
    )
    return 0


def cmd_notes(args: argparse.Namespace) -> int:
    if not CHANGELOG_PATH.exists():
        print(f"error: {CHANGELOG_PATH} not found", file=sys.stderr)
        return 1
    text = CHANGELOG_PATH.read_text(encoding="utf-8")
    name = "Unreleased" if args.version is None else args.version.lstrip("v")
    body = get_changelog_section(text, name)
    if body is None:
        print(f"error: no '## [{name}]' section in CHANGELOG.md", file=sys.stderr)
        return 1
    print(body.strip("\n"))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m tools.release", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("version", help="Print the current canonical version")

    check_parser = subparsers.add_parser("check", help="Validate release metadata (read-only)")
    check_parser.add_argument("--tag", default=None, help="Validate against this git tag (e.g. v1.2.0)")

    bump_parser = subparsers.add_parser("bump", help="Bump VERSION and move Unreleased into CHANGELOG.md")
    bump_parser.add_argument("level", choices=["major", "minor", "patch"])
    bump_parser.add_argument("--allow-empty", action="store_true", help="Bump even if Unreleased is empty")
    bump_parser.add_argument("--date", default=None, help="Release date YYYY-MM-DD (default: today UTC)")

    notes_parser = subparsers.add_parser("notes", help="Print CHANGELOG notes for a version (default: Unreleased)")
    notes_parser.add_argument("version", nargs="?", default=None, help="e.g. 1.2.0 or v1.2.0")

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handlers = {
        "version": cmd_version,
        "check": cmd_check,
        "bump": cmd_bump,
        "notes": cmd_notes,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
