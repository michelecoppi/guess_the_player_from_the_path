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


# ---------------------------------------------------------------------------
# get_build_revision — exact deployed build identity, separate from VERSION
# ---------------------------------------------------------------------------


def test_get_build_revision_reads_k_revision(monkeypatch):
    monkeypatch.setenv("K_REVISION", "guess-the-player-00042-abc")
    assert version.get_build_revision() == "guess-the-player-00042-abc"


def test_get_build_revision_none_when_not_on_cloud_run(monkeypatch):
    monkeypatch.delenv("K_REVISION", raising=False)
    assert version.get_build_revision() is None


def test_get_build_revision_none_when_k_revision_empty(monkeypatch):
    monkeypatch.setenv("K_REVISION", "")
    assert version.get_build_revision() is None


def test_get_build_revision_does_not_fabricate_a_git_sha(monkeypatch):
    """Outside Cloud Run there is nothing the runtime can prove about its own build — the
    function must not invent a value (e.g. reading a local .git directory) to fill the gap.
    """
    monkeypatch.delenv("K_REVISION", raising=False)
    monkeypatch.delenv("GITHUB_SHA", raising=False)
    assert version.get_build_revision() is None
