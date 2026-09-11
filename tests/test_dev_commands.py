from unittest.mock import MagicMock, patch

from tools.dev import COMMANDS, main


def test_commands_table_has_all_required_tasks():
    expected = {
        "check-env",
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
    }
    assert expected.issubset(COMMANDS.keys())


def test_help_command_returns_zero(capsys):
    assert main(["--help"]) == 0
    captured = capsys.readouterr()
    assert "Comandi disponibili:" in captured.out
    assert "check-env" in captured.out
    assert "emulator" in captured.out


def test_unknown_command_returns_one(capsys):
    assert main(["unknown-task-xyz"]) == 1
    captured = capsys.readouterr()
    assert "comando sconosciuto 'unknown-task-xyz'" in captured.out


def test_alias_resolution_dispatches_correctly():
    mock_env = MagicMock(return_value=0)
    mock_test = MagicMock(return_value=0)
    with patch.dict(COMMANDS, {"check-env": (mock_env, "desc"), "test": (mock_test, "desc")}):
        assert main(["env", "--extra"]) == 0
        mock_env.assert_called_once_with(["--extra"])

        assert main(["tests", "-k", "unit"]) == 0
        mock_test.assert_called_once_with(["-k", "unit"])


def test_command_execution_failure_propagates_exit_code():
    with patch("tools.dev._run_cmd", return_value=42):
        code = main(["lint"])
        assert code == 42
