"""Security audit and scanning tooling (#19).

Provides deterministic security verifications for:
1. Python dependencies (pip-audit with structured exceptions in security-exceptions.json);
2. Secret scanning (detect-secrets with baseline suppression in .secrets.baseline);
3. Node dependencies (npm audit --audit-level=high for webapp).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


@dataclass
class SecurityCheckResult:
    name: str
    passed: bool
    summary: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _get_today_iso() -> str:
    """Returns today's date in UTC as YYYY-MM-DD."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def check_security_exceptions_validity(
    exceptions: list[dict[str, Any]],
    current_date: Optional[str] = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Validates exceptions schema and checks for expiration.

    Returns:
        (active_exceptions, expiration_errors)
    """
    today = current_date or _get_today_iso()
    active: list[dict[str, Any]] = []
    expired_errors: list[str] = []

    for exc in exceptions:
        pkg = exc.get("package", "unknown")
        adv_id = exc.get("advisory_id", "unknown")
        review_by = exc.get("review_by", "")

        if not review_by:
            expired_errors.append(f"Security exception for '{pkg}' ({adv_id}) is missing 'review_by' date.")
            continue

        if review_by < today:
            expired_errors.append(
                f"Security exception EXPIRED for '{pkg}' ({adv_id}) on {review_by}. "
                f"Must be upgraded or review date extended with documented rationale."
            )
        else:
            active.append(exc)

    return active, expired_errors


def run_pip_audit(
    requirements_file: Path,
    exceptions_file: Path,
    current_date: Optional[str] = None,
) -> SecurityCheckResult:
    """Audits Python dependencies for known CVEs/advisories with exception handling."""
    if not requirements_file.is_file():
        return SecurityCheckResult(
            name="pip-audit",
            passed=False,
            summary="Requirements file not found",
            errors=[f"File not found: {requirements_file}"],
        )

    # Load exceptions
    exceptions: list[dict[str, Any]] = []
    if exceptions_file.is_file():
        try:
            with open(exceptions_file, "r", encoding="utf-8") as f:
                exceptions = json.load(f)
        except Exception as e:
            return SecurityCheckResult(
                name="pip-audit",
                passed=False,
                summary="Failed to parse security-exceptions.json",
                errors=[str(e)],
            )

    active_exceptions, expired_errors = check_security_exceptions_validity(
        exceptions, current_date=current_date
    )

    # Run pip-audit in JSON format
    cmd = [sys.executable, "-m", "pip_audit", "-r", str(requirements_file), "-f", "json"]
    proc = subprocess.run(cmd, capture_output=True, text=True)

    try:
        data = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except json.JSONDecodeError:
        return SecurityCheckResult(
            name="pip-audit",
            passed=False,
            summary="Failed to parse pip-audit JSON output",
            errors=[proc.stderr or proc.stdout or f"Exit code {proc.returncode}"],
        )

    unexempted: list[str] = []
    exempted_count = 0

    dependencies = data.get("dependencies", [])
    for dep in dependencies:
        pkg_name = dep.get("name", "")
        pkg_version = dep.get("version", "")
        vulns = dep.get("vulns", [])

        for v in vulns:
            vid = v.get("id", "")
            aliases = v.get("aliases", [])
            fix_versions = v.get("fix_versions", [])

            # Check if covered by any active exception
            matched_exc = None
            for exc in active_exceptions:
                if exc.get("package", "").lower() == pkg_name.lower():
                    target_id = exc.get("advisory_id", "")
                    if target_id == vid or target_id in aliases:
                        matched_exc = exc
                        break

            if matched_exc:
                exempted_count += 1
            else:
                alias_info = f" ({', '.join(aliases)})" if aliases else ""
                fix_info = f", fixed in: {', '.join(fix_versions)}" if fix_versions else ""
                unexempted.append(
                    f"Package '{pkg_name}' v{pkg_version} has vulnerability {vid}{alias_info}{fix_info}"
                )

    all_errors = list(expired_errors) + unexempted
    passed = len(all_errors) == 0

    summary = (
        f"Passed with {exempted_count} documented exception(s)"
        if (passed and exempted_count > 0)
        else ("Passed with 0 vulnerabilities" if passed else f"Failed with {len(all_errors)} issue(s)")
    )

    return SecurityCheckResult(
        name="pip-audit",
        passed=passed,
        summary=summary,
        errors=all_errors,
    )


def run_detect_secrets(
    baseline_file: Path,
    project_root: Path,
) -> SecurityCheckResult:
    """Scans repository files for secrets and compares against baseline."""
    baseline_findings: set[tuple[str, str]] = set()
    if baseline_file.is_file():
        try:
            with open(baseline_file, "r", encoding="utf-8") as f:
                bdata = json.load(f)
            for fname, items in bdata.get("results", {}).items():
                norm_fname = fname.replace("\\", "/")
                for item in items:
                    hsecret = item.get("hashed_secret", "")
                    if hsecret:
                        baseline_findings.add((norm_fname, hsecret))
        except Exception as e:
            return SecurityCheckResult(
                name="detect-secrets",
                passed=False,
                summary="Failed to read .secrets.baseline",
                errors=[str(e)],
            )

    cmd = ["detect-secrets", "scan"]
    try:
        proc = subprocess.run(cmd, cwd=str(project_root), capture_output=True, text=True)
    except FileNotFoundError:
        return SecurityCheckResult(
            name="detect-secrets",
            passed=False,
            summary="detect-secrets command not found in PATH",
            errors=["detect-secrets executable is not installed or not in PATH"],
        )

    if proc.returncode != 0:
        return SecurityCheckResult(
            name="detect-secrets",
            passed=False,
            summary="detect-secrets scan failed",
            errors=[proc.stderr or f"Exit code {proc.returncode}"],
        )

    try:
        scan_data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return SecurityCheckResult(
            name="detect-secrets",
            passed=False,
            summary="Failed to parse detect-secrets JSON output",
            errors=[proc.stdout[:500]],
        )

    new_secrets: list[str] = []
    current_results = scan_data.get("results", {})
    for fname, items in current_results.items():
        norm_fname = fname.replace("\\", "/")
        for item in items:
            hsecret = item.get("hashed_secret", "")
            if (norm_fname, hsecret) not in baseline_findings:
                line_no = item.get("line_number", "?")
                stype = item.get("type", "Secret")
                new_secrets.append(
                    f"New secret detected in {norm_fname}:{line_no} [type: {stype}, hash: {hsecret[:10]}...]"
                )

    passed = len(new_secrets) == 0
    summary = (
        f"Passed ({len(baseline_findings)} baseline exception(s))"
        if passed
        else f"Failed with {len(new_secrets)} new potential secret(s)"
    )

    return SecurityCheckResult(
        name="detect-secrets",
        passed=passed,
        summary=summary,
        errors=new_secrets,
    )


def run_npm_audit(
    project_root: Path,
    audit_level: str = "high",
) -> SecurityCheckResult:
    """Runs npm audit on frontend dependencies with the given severity threshold."""
    target_dir = project_root
    if not (target_dir / "package.json").is_file():
        if (target_dir / "webapp" / "package.json").is_file():
            target_dir = target_dir / "webapp"
        else:
            return SecurityCheckResult(
                name="npm-audit",
                passed=True,
                summary="package.json not found; skipped",
            )

    npm_cmd = "npm.cmd" if os.name == "nt" else "npm"
    cmd = [npm_cmd, "audit", f"--audit-level={audit_level}"]
    proc = subprocess.run(cmd, cwd=str(target_dir), capture_output=True, text=True)

    passed = proc.returncode == 0
    errors = []
    if not passed:
        output = (proc.stdout + "\n" + proc.stderr).strip()
        errors.append(output or f"npm audit returned exit code {proc.returncode}")

    summary = (
        f"Passed (--audit-level={audit_level})"
        if passed
        else f"Failed: found vulnerabilities with severity >= {audit_level}"
    )

    return SecurityCheckResult(
        name="npm-audit",
        passed=passed,
        summary=summary,
        errors=errors,
    )


def run_security_suite(
    project_root: Optional[Path] = None,
    audit_level: str = "high",
) -> int:
    """Runs the unified security scanning suite."""
    root = project_root or Path.cwd()
    req_file = root / "requirements.txt"
    exc_file = root / "security-exceptions.json"
    baseline_file = root / ".secrets.baseline"

    print("=== Security & Vulnerability Audit (#19) ===")
    results = [
        run_pip_audit(req_file, exc_file),
        run_detect_secrets(baseline_file, root),
        run_npm_audit(root, audit_level=audit_level),
    ]

    all_passed = True
    for r in results:
        status_tag = "[PASS]" if r.passed else "[FAIL]"
        print(f"  {status_tag} {r.name:<16} - {r.summary}")
        if not r.passed:
            all_passed = False
            for err in r.errors:
                print(f"         ! {err}")

    print("-" * 50)
    if all_passed:
        print("RESULT: PASS - All security checks passed.")
        return 0

    print("RESULT: FAIL - Security issues detected.")
    return 1


if __name__ == "__main__":
    sys.exit(run_security_suite())
