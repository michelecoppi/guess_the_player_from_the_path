"""Lock delle dipendenze Python (#214): lettura dei pin e confronto, senza rete ne' Docker."""
from pathlib import Path
from unittest.mock import patch

import pytest

from tools import deps_lock


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_read_pins_ignores_comments_and_normalizes_names(tmp_path):
    lock = _write(
        tmp_path / "requirements.txt",
        "# generato da pip-compile\n"
        "Google_Cloud.Tasks==2.25.0\n"
        "    # via -r requirements.in\n"
        "uvloop==0.21.0 ; sys_platform != 'win32'\n"
        "-c altro.txt\n",
    )
    assert deps_lock.read_pins(lock) == {"google-cloud-tasks": "2.25.0", "uvloop": "0.21.0"}


def test_diff_pins_reports_changed_missing_and_extra_packages():
    expected = {"fastapi": "0.115.12", "httpx": "0.28.1"}
    actual = {"fastapi": "0.115.0", "starlette": "0.46.0"}
    assert deps_lock.diff_pins(expected, actual) == [
        "fastapi: lock=0.115.0 atteso=0.115.12",
        "httpx: lock=- atteso=0.28.1",
        "starlette: lock=0.46.0 atteso=-",
    ]


def test_diff_pins_is_empty_when_locks_match():
    pins = {"pillow": "12.3.0"}
    assert deps_lock.diff_pins(pins, dict(pins)) == []


def test_pip_tools_version_comes_from_requirements_dev_in(tmp_path):
    _write(tmp_path / "requirements-dev.in", "-c requirements.txt\npip-tools==7.6.1\n")
    assert deps_lock.pip_tools_version(tmp_path) == "7.6.1"


def test_pip_tools_version_must_be_pinned(tmp_path):
    _write(tmp_path / "requirements-dev.in", "pytest==9.1.1\n")
    with pytest.raises(SystemExit):
        deps_lock.pip_tools_version(tmp_path)


def test_repository_pins_pip_tools():
    assert deps_lock.pip_tools_version()


def test_check_fails_when_a_lock_is_missing(tmp_path, capsys):
    _write(tmp_path / "requirements.in", "fastapi==0.115.12\n")
    assert deps_lock.check(tmp_path) == 1
    assert "requirements.txt" in capsys.readouterr().out


def test_check_reports_stale_lock(tmp_path, capsys):
    for name in ("requirements.in", "requirements-dev.in", "requirements-dev.txt"):
        _write(tmp_path / name, "pip-tools==7.6.1\n")
    _write(tmp_path / "requirements.txt", "fastapi==0.115.0\n")

    def fake_compile(workdir):
        _write(workdir / "requirements.txt", "fastapi==0.115.12\n")
        return 0

    with patch.object(deps_lock, "compile_locks", side_effect=fake_compile):
        assert deps_lock.check(tmp_path) == 1
    assert "fastapi: lock=0.115.0 atteso=0.115.12" in capsys.readouterr().out


def test_check_passes_when_recompiling_changes_nothing(tmp_path):
    for name in ("requirements.in", "requirements-dev.in", "requirements.txt", "requirements-dev.txt"):
        _write(tmp_path / name, "pip-tools==7.6.1\n")
    with patch.object(deps_lock, "compile_locks", return_value=0):
        assert deps_lock.check(tmp_path) == 0


def test_main_rejects_unknown_arguments(capsys):
    assert deps_lock.main(["boh"]) == 2
    assert "Uso" in capsys.readouterr().out
