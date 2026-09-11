"""Test per il validatore di ambiente e configurazione (tools.check_environment)."""
import json
import os
import sys
from unittest.mock import patch

import pytest

from tools.check_environment import CheckStatus, EnvironmentValidator, main


@pytest.fixture(autouse=True)
def isolate_env():
    """Isola os.environ per evitare che le variabili caricate dai test alterino altri moduli della suite."""
    old_env = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(old_env)


@pytest.fixture
def temp_project(tmp_path):
    """Crea una struttura fittizia di progetto valida."""
    # Data directory
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "players.json").write_text(
        json.dumps({
            "_comment": "Test dataset",
            "players": [
                {
                    "id": "player_1",
                    "full_name": "Paolo Maldini",
                    "aliases": ["Maldini"],
                    "career": [{"team": "Milan", "years": "1984-2009"}],
                }
            ],
        }),
        encoding="utf-8",
    )
    (data_dir / "config.json").write_text(json.dumps({"rules": "standard"}), encoding="utf-8")
    (data_dir / "event_templates.json").write_text(json.dumps({"events": []}), encoding="utf-8")
    (data_dir / "shop.json").write_text(json.dumps({"items": []}), encoding="utf-8")

    # Webapp directory
    webapp_dir = tmp_path / "webapp"
    webapp_dir.mkdir()
    for name in [
        "index.html",
        "client.js",
        "strings.js",
        "arena.js",
        "referrals.js",
        "legal.css",
        "terms.html",
        "privacy.html",
    ]:
        (webapp_dir / name).write_text("/* test */", encoding="utf-8")

    # .env
    env_file = tmp_path / ".env"
    env_file.write_text(
        "BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ123456789\n"
        "BOT_USERNAME=guess_the_player_bot\n"
        "ADMIN_TELEGRAM_IDS=12345,67890\n",
        encoding="utf-8",
    )
    return tmp_path


def test_python_version_check_passes_on_current_python(temp_project):
    validator = EnvironmentValidator(project_root=temp_project, mode="dev")
    validator.check_python_version()
    assert len(validator.results) == 1
    item = validator.results[0]
    assert item.status == CheckStatus.PASS
    assert "soddisfa il requisito minimo" in item.message


def test_python_version_check_fails_on_old_python(temp_project):
    validator = EnvironmentValidator(project_root=temp_project, mode="dev")
    with patch.object(sys, "version_info", (3, 10, 8)):
        validator.check_python_version()
    assert len(validator.results) == 1
    item = validator.results[0]
    assert item.status == CheckStatus.FAIL
    assert "richiede Python 3.11" in item.message
    assert item.remediation is not None


def test_datasets_check_passes_on_valid_structure(temp_project):
    validator = EnvironmentValidator(project_root=temp_project, mode="dev")
    validator.check_datasets_and_files()
    assert not validator.has_failures
    for item in validator.results:
        assert item.status == CheckStatus.PASS


def test_datasets_check_fails_on_missing_file(temp_project):
    (temp_project / "data" / "players.json").unlink()
    validator = EnvironmentValidator(project_root=temp_project, mode="dev")
    validator.check_datasets_and_files()
    failures = [r for r in validator.results if r.status == CheckStatus.FAIL]
    assert len(failures) == 1
    assert "data/players.json" in failures[0].name
    assert failures[0].remediation is not None


def test_datasets_check_fails_on_corrupted_json(temp_project):
    (temp_project / "data" / "config.json").write_text("{corrupted: json,", encoding="utf-8")
    validator = EnvironmentValidator(project_root=temp_project, mode="dev")
    validator.check_datasets_and_files()
    failures = [r for r in validator.results if r.status == CheckStatus.FAIL]
    assert len(failures) == 1
    assert "data/config.json" in failures[0].name
    assert "JSON non valido" in failures[0].message


def test_datasets_check_fails_on_missing_webapp_assets(temp_project):
    (temp_project / "webapp" / "index.html").unlink()
    validator = EnvironmentValidator(project_root=temp_project, mode="dev")
    validator.check_datasets_and_files()
    failures = [r for r in validator.results if r.status == CheckStatus.FAIL]
    assert any("Static Files" in f.name for f in failures)


def test_telegram_config_validation(temp_project, monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123456:ABC-DEF1234ghIkl-zyx57W2v1u1234567")
    monkeypatch.setenv("BOT_USERNAME", "test_bot")
    monkeypatch.setenv("ADMIN_TELEGRAM_IDS", "1001, 1002")

    validator = EnvironmentValidator(project_root=temp_project, mode="dev")
    validator.check_telegram_configuration()

    statuses = {r.name: r.status for r in validator.results}
    assert statuses["BOT_TOKEN"] == CheckStatus.PASS
    assert statuses["BOT_USERNAME"] == CheckStatus.PASS
    assert statuses["ADMIN_TELEGRAM_IDS"] == CheckStatus.PASS


def test_telegram_config_missing_token_fails(temp_project, monkeypatch):
    validator = EnvironmentValidator(project_root=temp_project, mode="dev")
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    validator.check_telegram_configuration()

    failures = [r for r in validator.results if r.name == "BOT_TOKEN"]
    assert len(failures) == 1
    assert failures[0].status == CheckStatus.FAIL


def test_telegram_config_at_sign_in_username_warns(temp_project, monkeypatch):
    validator = EnvironmentValidator(project_root=temp_project, mode="dev")
    monkeypatch.setenv("BOT_TOKEN", "123456:valid_format_test_token_1234567890")
    monkeypatch.setenv("BOT_USERNAME", "@test_bot")
    validator.check_telegram_configuration()

    username_check = next(r for r in validator.results if r.name == "BOT_USERNAME")
    assert username_check.status == CheckStatus.WARN
    assert "@" in username_check.message


def test_firebase_emulator_check(temp_project, monkeypatch):
    validator = EnvironmentValidator(project_root=temp_project, mode="dev")
    monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", "127.0.0.1:8571")
    monkeypatch.delenv("FIREBASE_CREDENTIALS_PATH", raising=False)
    validator.check_firebase_configuration()

    # Se l'emulatore non e' acceso durante il test unitario, riceve un WARN actionable
    emulator_result = next(r for r in validator.results if "Firestore Emulator" in r.name)
    assert emulator_result.status in (CheckStatus.PASS, CheckStatus.WARN)
    assert "FIRESTORE_EMULATOR_HOST" in emulator_result.message or "attivo" in emulator_result.message


def test_firebase_credentials_file_validation(temp_project, monkeypatch):
    cred_file = temp_project / "fake-key.json"
    cred_file.write_text(json.dumps({
        "type": "service_account",
        "project_id": "test-project-123",
        "client_email": "bot@test-project-123.iam.gserviceaccount.com",
    }), encoding="utf-8")

    validator = EnvironmentValidator(project_root=temp_project, mode="dev")
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    monkeypatch.setenv("FIREBASE_CREDENTIALS_PATH", str(cred_file))
    validator.check_firebase_configuration()

    cred_result = next(r for r in validator.results if r.name == "FIREBASE_CREDENTIALS_PATH")
    assert cred_result.status == CheckStatus.PASS
    assert "test-project-123" in cred_result.message


def test_firebase_no_config_fails_with_actionable_solution(temp_project, monkeypatch):
    validator = EnvironmentValidator(project_root=temp_project, mode="dev")
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    monkeypatch.delenv("FIREBASE_CREDENTIALS_PATH", raising=False)
    validator.check_firebase_configuration()

    db_result = next(r for r in validator.results if r.name == "Database Setup")
    assert db_result.status == CheckStatus.FAIL
    assert db_result.remediation is not None
    assert "FIRESTORE_EMULATOR_HOST" in db_result.remediation


def test_cloud_tasks_dev_mode_vs_prod_mode(temp_project, monkeypatch):
    monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("TASK_SECRET", raising=False)
    monkeypatch.delenv("TASKS_QUEUE", raising=False)
    monkeypatch.delenv("BROADCAST_QUEUE", raising=False)

    # In dev mode, missing secrets are INFO
    dev_validator = EnvironmentValidator(project_root=temp_project, mode="dev")
    dev_validator.check_cloud_tasks_and_hardening()
    assert not any(r.status == CheckStatus.FAIL for r in dev_validator.results)

    # In prod mode, missing secrets are FAIL
    prod_validator = EnvironmentValidator(project_root=temp_project, mode="prod")
    prod_validator.check_cloud_tasks_and_hardening()
    prod_failures = [r for r in prod_validator.results if r.status == CheckStatus.FAIL]
    assert len(prod_failures) >= 4


def test_cloud_tasks_secret_regex_validation(temp_project, monkeypatch):
    monkeypatch.setenv("WEBHOOK_SECRET", "too-short")
    monkeypatch.setenv("TASK_SECRET", "contains spaces and invalid chars!")
    validator = EnvironmentValidator(project_root=temp_project, mode="dev")
    validator.check_cloud_tasks_and_hardening()

    failures = [r for r in validator.results if r.status == CheckStatus.FAIL]
    assert len(failures) == 2
    assert any("WEBHOOK_SECRET" in f.name for f in failures)
    assert any("TASK_SECRET" in f.name for f in failures)


def test_miniapp_url_validation(temp_project, monkeypatch):
    monkeypatch.setenv("PUBLIC_BASE_URL", "http://insecure.test")

    # In dev mode, http is accepted with warning/pass
    dev_validator = EnvironmentValidator(project_root=temp_project, mode="dev")
    dev_validator.check_miniapp_and_urls()
    assert not dev_validator.has_failures

    # In prod mode, http without https is FAIL
    prod_validator = EnvironmentValidator(project_root=temp_project, mode="prod")
    prod_validator.check_miniapp_and_urls()
    assert prod_validator.has_failures
    assert any("https://" in r.message for r in prod_validator.results if r.status == CheckStatus.FAIL)


def test_main_cli_returns_expected_exit_codes(temp_project, monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123456:valid_test_token_123456789012345")
    monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", "127.0.0.1:8571")
    monkeypatch.delenv("FIREBASE_CREDENTIALS_PATH", raising=False)

    # Test dev mode with valid project -> 0
    test_args = ["--project-root", str(temp_project), "--mode", "dev"]
    with patch.object(sys, "argv", ["check_environment.py"] + test_args):
        assert main() == 0

    # Test prod mode on incomplete setup -> 1
    test_prod_args = ["--project-root", str(temp_project), "--mode", "prod"]
    with patch.object(sys, "argv", ["check_environment.py"] + test_prod_args):
        assert main() == 1


def test_json_output_mode(temp_project, monkeypatch, capsys):
    monkeypatch.setenv("BOT_TOKEN", "123456:valid_test_token_123456789012345")
    monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", "127.0.0.1:8571")
    monkeypatch.delenv("FIREBASE_CREDENTIALS_PATH", raising=False)
    test_args = ["--project-root", str(temp_project), "--mode", "dev", "--json"]
    with patch.object(sys, "argv", ["check_environment.py"] + test_args):
        code = main()
        assert code == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["mode"] == "dev"
    assert "checks" in payload
    assert isinstance(payload["checks"], list)
