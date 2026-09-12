"""Tests for security audit and scanning tooling (#19)."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from tools.security import (
    check_security_exceptions_validity,
    run_detect_secrets,
    run_npm_audit,
    run_pip_audit,
)


def test_check_security_exceptions_validity_active():
    exceptions = [
        {
            "package": "some-pkg",
            "advisory_id": "GHSA-1234",
            "reason": "Temporary acceptance",
            "review_by": "2099-01-01",
        }
    ]
    active, errors = check_security_exceptions_validity(exceptions, current_date="2026-09-12")
    assert len(active) == 1
    assert len(errors) == 0


def test_check_security_exceptions_validity_expired():
    exceptions = [
        {
            "package": "expired-pkg",
            "advisory_id": "GHSA-5678",
            "reason": "Old exception",
            "review_by": "2026-01-01",
        }
    ]
    active, errors = check_security_exceptions_validity(exceptions, current_date="2026-09-12")
    assert len(active) == 0
    assert len(errors) == 1
    assert "EXPIRED" in errors[0]
    assert "expired-pkg" in errors[0]


def test_check_security_exceptions_validity_missing_review_by():
    exceptions = [
        {
            "package": "bad-pkg",
            "advisory_id": "GHSA-9999",
            "reason": "No date provided",
        }
    ]
    active, errors = check_security_exceptions_validity(exceptions, current_date="2026-09-12")
    assert len(active) == 0
    assert len(errors) == 1
    assert "missing 'review_by'" in errors[0]


def test_run_pip_audit_with_exempted_vulnerability(tmp_path):
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("vulnerable-lib==1.0.0\n", encoding="utf-8")

    exc_file = tmp_path / "security-exceptions.json"
    exc_file.write_text(
        json.dumps(
            [
                {
                    "package": "vulnerable-lib",
                    "advisory_id": "PYSEC-2026-0001",
                    "reason": "Accepted for test",
                    "review_by": "2099-12-31",
                }
            ]
        ),
        encoding="utf-8",
    )

    mock_audit_output = {
        "dependencies": [
            {
                "name": "vulnerable-lib",
                "version": "1.0.0",
                "vulns": [
                    {
                        "id": "PYSEC-2026-0001",
                        "fix_versions": ["1.1.0"],
                        "aliases": ["GHSA-xxxx"],
                    }
                ],
            }
        ],
        "fixes": [],
    }

    mock_proc = MagicMock()
    mock_proc.stdout = json.dumps(mock_audit_output)
    mock_proc.stderr = ""
    mock_proc.returncode = 1

    with patch("subprocess.run", return_value=mock_proc):
        res = run_pip_audit(req_file, exc_file, current_date="2026-09-12")
        assert res.passed is True
        assert "1 documented exception(s)" in res.summary


def test_run_pip_audit_with_unexempted_vulnerability(tmp_path):
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("vulnerable-lib==1.0.0\n", encoding="utf-8")

    exc_file = tmp_path / "security-exceptions.json"
    exc_file.write_text("[]", encoding="utf-8")

    mock_audit_output = {
        "dependencies": [
            {
                "name": "vulnerable-lib",
                "version": "1.0.0",
                "vulns": [
                    {
                        "id": "PYSEC-2026-9999",
                        "fix_versions": ["2.0.0"],
                        "aliases": [],
                    }
                ],
            }
        ],
        "fixes": [],
    }

    mock_proc = MagicMock()
    mock_proc.stdout = json.dumps(mock_audit_output)
    mock_proc.stderr = ""
    mock_proc.returncode = 1

    with patch("subprocess.run", return_value=mock_proc):
        res = run_pip_audit(req_file, exc_file, current_date="2026-09-12")
        assert res.passed is False
        assert len(res.errors) == 1
        assert "vulnerable-lib" in res.errors[0]
        assert "PYSEC-2026-9999" in res.errors[0]


def test_run_detect_secrets_passes_when_matches_baseline(tmp_path):
    baseline_file = tmp_path / ".secrets.baseline"
    baseline_data = {
        "results": {
            "tests/dummy.py": [
                {
                    "hashed_secret": "hash_abc_123",
                    "line_number": 10,
                    "type": "Secret Keyword",
                }
            ]
        }
    }
    baseline_file.write_text(json.dumps(baseline_data), encoding="utf-8")

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = json.dumps(baseline_data)

    with patch("subprocess.run", return_value=mock_proc):
        res = run_detect_secrets(baseline_file, tmp_path)
        assert res.passed is True
        assert "1 baseline exception(s)" in res.summary


def test_run_detect_secrets_fails_on_new_secret(tmp_path):
    baseline_file = tmp_path / ".secrets.baseline"
    baseline_file.write_text(json.dumps({"results": {}}), encoding="utf-8")

    scan_output = {
        "results": {
            "src/config.py": [
                {
                    "hashed_secret": "new_secret_hash_456",
                    "line_number": 42,
                    "type": "API Key",
                }
            ]
        }
    }

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = json.dumps(scan_output)

    with patch("subprocess.run", return_value=mock_proc):
        res = run_detect_secrets(baseline_file, tmp_path)
        assert res.passed is False
        assert len(res.errors) == 1
        assert "src/config.py:42" in res.errors[0]
        assert "API Key" in res.errors[0]


def test_run_npm_audit_missing_directory(tmp_path):
    res = run_npm_audit(tmp_path / "nonexistent")
    assert res.passed is True
    assert "skipped" in res.summary


def test_run_npm_audit_failure(tmp_path):
    pkg_file = tmp_path / "package.json"
    pkg_file.write_text('{"name": "test"}', encoding="utf-8")

    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.stdout = "1 high severity vulnerability found"
    mock_proc.stderr = ""

    with patch("subprocess.run", return_value=mock_proc):
        res = run_npm_audit(tmp_path, audit_level="high")
        assert res.passed is False
        assert "Failed" in res.summary
