"""Tests for the canonical version reader used at runtime (#49)."""
from __future__ import annotations

from services import version


def test_get_version_reads_repo_version_file():
    # Uses the real VERSION file at the repo root: must be a non-empty SemVer-shaped string.
    version.get_version.cache_clear()
    value = version.get_version()
    assert value != version._FALLBACK
    assert value.strip() == value
    assert value.count(".") == 2


def test_get_version_falls_back_when_file_missing(tmp_path, monkeypatch):
    version.get_version.cache_clear()
    monkeypatch.setattr(version, "_VERSION_FILE", tmp_path / "does-not-exist" / "VERSION")
    try:
        assert version.get_version() == version._FALLBACK
    finally:
        version.get_version.cache_clear()


def test_get_version_falls_back_when_file_empty(tmp_path, monkeypatch):
    version.get_version.cache_clear()
    empty = tmp_path / "VERSION"
    empty.write_text("   \n", encoding="utf-8")
    monkeypatch.setattr(version, "_VERSION_FILE", empty)
    try:
        assert version.get_version() == version._FALLBACK
    finally:
        version.get_version.cache_clear()


def test_get_version_is_cached(monkeypatch):
    version.get_version.cache_clear()
    calls = {"count": 0}
    real_read_text = type(version._VERSION_FILE).read_text

    def counting_read_text(self, *args, **kwargs):
        calls["count"] += 1
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(type(version._VERSION_FILE), "read_text", counting_read_text)
    try:
        version.get_version()
        version.get_version()
        assert calls["count"] == 1
    finally:
        version.get_version.cache_clear()
