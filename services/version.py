"""Reads the application's canonical release version (#49).

The single source of truth is the `VERSION` file at the repository root — see
docs/release-checklist.md. This module is intentionally tiny and dependency-free so
bot.py (and, later, #18's error-tracking `release` tag) can import it without pulling in
release-tooling code; `tools/release.py` reads the same file independently.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_VERSION_FILE = Path(__file__).resolve().parent.parent / "VERSION"
_FALLBACK = "0.0.0-unknown"


@lru_cache(maxsize=1)
def get_version() -> str:
    """Returns the current release version, or a fallback if VERSION is missing/empty."""
    try:
        value = _VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return _FALLBACK
    return value or _FALLBACK
