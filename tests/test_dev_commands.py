import sys
from unittest.mock import MagicMock, patch

from tools.dev import COMMANDS, main


def test_commands_table_has_all_required_tasks():
    expected = {
        "check-env",
        "check-api",
        "test",
        "test-cov",
        "test-node",
        "lint",
        "typecheck",
        "syntax",
        "dataset-check",
        "check",
        "api",
        "admin",
        "webapp",
        "emulator",
        "security-check",
        "dataset-regression-check",
        "dataset-baseline-update",
        "release-version",
        "release-check",
        "release-notes",
        "perf-report",
        "architecture",
    }
    assert expected.issubset(COMMANDS.keys())


def test_release_commands_delegate_to_tools_release():
    with patch("tools.dev._run_cmd", return_value=0) as mock_run:
        from tools.dev import main as dev_main

        assert dev_main(["release-version"]) == 0
        assert mock_run.call_args[0][0] == [sys.executable, "-m", "tools.release", "version"]

        assert dev_main(["release-check", "--tag", "v1.0.0"]) == 0
        assert mock_run.call_args[0][0] == [
            sys.executable, "-m", "tools.release", "check", "--tag", "v1.0.0",
        ]

        assert dev_main(["release-notes"]) == 0
        assert mock_run.call_args[0][0] == [sys.executable, "-m", "tools.release", "notes"]


def test_perf_report_delegates_to_tools_perf_report():
    with patch("tools.dev._run_cmd", return_value=0) as mock_run:
        assert main(["perf-report", "--fetch", "--days", "7"]) == 0
        assert mock_run.call_args[0][0] == [sys.executable, "-m", "tools.perf_report", "--fetch", "--days", "7"]


def test_architecture_delegates_to_tools_architecture():
    with patch("tools.dev._run_cmd", return_value=0) as mock_run:
        assert main(["architecture", "--graph"]) == 0
        assert mock_run.call_args[0][0] == [sys.executable, "-m", "tools.architecture", "--graph"]


def test_help_command_returns_zero(capsys):
    assert main(["--help"]) == 0
    captured = capsys.readouterr()
    assert "Comandi disponibili:" in captured.out
    assert "check-env" in captured.out
    assert "check-api" in captured.out
    assert "emulator" in captured.out


def test_unknown_command_returns_one(capsys):
    assert main(["unknown-task-xyz"]) == 1
    captured = capsys.readouterr()
    assert "comando sconosciuto 'unknown-task-xyz'" in captured.out


def test_alias_resolution_dispatches_correctly():
    mock_env = MagicMock(return_value=0)
    mock_test = MagicMock(return_value=0)
    mock_api_check = MagicMock(return_value=0)
    with patch.dict(COMMANDS, {
        "check-env": (mock_env, "desc"),
        "test": (mock_test, "desc"),
        "check-api": (mock_api_check, "desc"),
    }):
        assert main(["env", "--extra"]) == 0
        mock_env.assert_called_once_with(["--extra"])

        assert main(["tests", "-k", "unit"]) == 0
        mock_test.assert_called_once_with(["-k", "unit"])

        assert main(["api-check"]) == 0
        mock_api_check.assert_called_once_with([])


def test_command_execution_failure_propagates_exit_code():
    with patch("tools.dev._run_cmd", return_value=42):
        code = main(["lint"])
        assert code == 42


def test_api_command_blocks_when_lifespan_secrets_missing(monkeypatch, capsys):
    monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("TASK_SECRET", raising=False)
    monkeypatch.delenv("TASKS_QUEUE", raising=False)
    monkeypatch.delenv("BROADCAST_QUEUE", raising=False)
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)

    with patch("tools.dev._run_cmd") as mock_run:
        code = main(["api"])
        assert code == 1
        mock_run.assert_not_called()

    captured = capsys.readouterr()
    assert "ERRORE AVVIO API" in captured.out
    assert "check_environment --mode api" in captured.out


def test_api_command_launches_when_configured(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SECRET", "a" * 48)
    monkeypatch.setenv("TASK_SECRET", "b" * 48)
    monkeypatch.setenv("TASKS_QUEUE", "projects/p/locations/l/queues/tasks")
    monkeypatch.setenv("BROADCAST_QUEUE", "projects/p/locations/l/queues/broadcast")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://localhost:8000")

    with patch("tools.dev._run_cmd", return_value=0) as mock_run:
        code = main(["api"])
        assert code == 0
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "uvicorn" in cmd
        assert "bot:app" in cmd
