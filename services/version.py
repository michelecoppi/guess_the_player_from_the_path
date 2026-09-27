"""Reads the application's canonical release version and exact build identity (#49).

Two different things, deliberately kept apart — see
docs/release-checklist.md § Release version vs. deployed build identity:

- `get_version()`: the *formal release version*, the single source of truth being the
  `VERSION` file at the repository root. Bumped deliberately at release time
  (`tools/release.py bump`), so it can lag behind what is actually running — this
  repository deploys every green `main` commit continuously, tagged releases are opt-in.
- `get_build_revision()`: the *exact deployed build*, read from `K_REVISION`, which Cloud
  Run injects into every running instance and which an operator cannot spoof by forgetting
  to bump `VERSION`. Returns None outside Cloud Run (local dev, tests) rather than
  fabricating a git SHA the runtime has no way to actually prove.

This module is intentionally tiny and dependency-free so bot.py (and, later, #18's
error-tracking `release` tag) can import it without pulling in release-tooling code;
`tools/release.py` reads the `VERSION` file independently.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

_VERSION_FILE = Path(__file__).resolve().parent.parent / "VERSION"
_FALLBACK = "0.0.0-unknown"


@lru_cache(maxsize=1)
def get_version() -> str:
    """Returns the current formal release version, or a fallback if VERSION is missing/empty."""
    try:
        value = _VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return _FALLBACK
    return value or _FALLBACK


def get_build_revision() -> Optional[str]:
    """Returns the exact Cloud Run revision serving this instance, or None if not on Cloud Run.

    `K_REVISION` is set by the Cloud Run runtime itself (not by our deploy step), so it is
    trustworthy proof of *which build* is running — unlike `get_version()`, it cannot go
    stale because nobody remembered to bump it.
    """
    return os.environ.get("K_REVISION") or None
