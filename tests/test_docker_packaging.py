import shutil
import subprocess
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent


def test_dockerfile_multi_stage_structure():
    """Verify that Dockerfile implements a proper multi-stage build."""
    dockerfile_path = ROOT_DIR / "Dockerfile"
    assert dockerfile_path.exists(), "Dockerfile must exist at project root"

    content = dockerfile_path.read_text(encoding="utf-8")

    # 1. Node 22 build stage
    assert "node:22" in content, "Must use Node 22 stage for frontend build"
    assert "AS frontend-builder" in content or "as frontend-builder" in content.lower()
    assert "npm ci" in content, "Must install dependencies with npm ci"
    assert "npm run build" in content, "Must compile frontend with npm run build"

    # 2. Python 3.11 runtime stage
    assert "python:3.11" in content, "Must use Python 3.11 runtime"
    assert "fonts-dejavu-core" in content, "Must install system fonts for Pillow"

    # 3. Artifact copying
    assert "--from=frontend-builder" in content, "Must copy frontend artifacts from build stage"
    assert "webapp/dist" in content, "Must copy into webapp/dist"

    # 4. Security & runtime
    assert "useradd" in content and "USER app" in content, "Must run as non-root user 'app'"
    assert "EXPOSE 8000" in content
    assert 'CMD ["python", "bot.py"]' in content


def test_dockerignore_excludes_transient_artifacts():
    """Verify that .dockerignore excludes node_modules, local dist, and sensitive files."""
    dockerignore_path = ROOT_DIR / ".dockerignore"
    assert dockerignore_path.exists(), ".dockerignore must exist at project root"

    content = dockerignore_path.read_text(encoding="utf-8")
    lines = {
        line.strip()
        for line in content.splitlines()
        if line.strip() and not line.startswith("#")
    }

    expected_exclusions = [
        "node_modules/",
        "webapp/dist/",
        ".env",
        "firebase-key.json",
        ".git/",
        "tests/",
    ]
    for pattern in expected_exclusions:
        assert any(
            line == pattern or line == pattern.rstrip("/") for line in lines
        ), f".dockerignore must exclude {pattern}"


def is_docker_daemon_responsive() -> bool:
    if not shutil.which("docker"):
        return False
    try:
        res = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=5,
        )
        return res.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def test_docker_image_contains_v2_artifacts():
    """If Docker is available locally, verify that the built image contains /app/webapp/dist/index.html and assets."""
    if not is_docker_daemon_responsive():
        pytest.skip(
            "Docker daemon not available in current environment; structural tests validated."
        )

    # Inspect the built test image or build it if not present
    inspect_res = subprocess.run(
        ["docker", "image", "inspect", "guess-the-player:test"],
        capture_output=True,
    )
    if inspect_res.returncode != 0:
        build_res = subprocess.run(
            ["docker", "build", "-t", "guess-the-player:test", "."],
            cwd=str(ROOT_DIR),
            capture_output=True,
            text=True,
        )
        assert build_res.returncode == 0, f"Docker build failed: {build_res.stderr}"

    # Verify /app/webapp/dist/index.html exists in image
    verify_cmd = [
        "docker",
        "run",
        "--rm",
        "guess-the-player:test",
        "sh",
        "-c",
        "test -f /app/webapp/dist/index.html && ls /app/webapp/dist/assets/*.js",
    ]
    verify_res = subprocess.run(verify_cmd, capture_output=True, text=True)
    assert verify_res.returncode == 0, (
        f"Missing /app/webapp/dist/index.html or assets in container: {verify_res.stderr}"
    )

    # Verify node_modules does NOT exist in runtime container
    node_modules_cmd = [
        "docker",
        "run",
        "--rm",
        "guess-the-player:test",
        "sh",
        "-c",
        "test ! -d /app/node_modules",
    ]
    node_modules_res = subprocess.run(node_modules_cmd, capture_output=True, text=True)
    assert (
        node_modules_res.returncode == 0
    ), "node_modules must NOT exist in the runtime image"
