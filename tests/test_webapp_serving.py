import os
import shutil
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from starlette.testclient import TestClient

import bot
from apps.api import miniapp, static
from services import firebase_service

PREVIEW_MODULE = "scripts.preview_webapp"


def test_webapp_serving_and_revalidation():
    """/app is the mini app itself now (#81/#115 rollout): the V2 bundle, not a legacy page."""
    client = TestClient(bot.app)
    response = client.get("/app")
    if not os.path.exists(os.path.join(static.DIST_DIR, "index.html")):
        assert response.status_code == 503
        return

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "ETag" in response.headers
    etag = response.headers["ETag"]

    # Revalidation returns 304
    revalidated = client.get("/app", headers={"If-None-Match": etag})
    assert revalidated.status_code == 304


def test_the_retired_app_v2_path_is_gone():
    """/app/v2 was only the preview path of the current mini app (#146)."""
    client = TestClient(bot.app, follow_redirects=False)
    assert client.get("/app/v2").status_code == 404


def test_tiktok_verification_serves_only_the_exact_file(monkeypatch, tmp_path):
    verification_dir = tmp_path / "site-verification"
    verification_dir.mkdir()
    filename = "tiktokAbC123.txt"
    content = b"tiktok-developers-site-verification=AbC123\n"
    (verification_dir / filename).write_bytes(content)
    monkeypatch.setattr(static, "VERIFICATION_DIR", verification_dir)
    client = TestClient(bot.app)

    response = client.get(f"/{filename}")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/plain; charset=utf-8"
    assert response.content == content

    for path in (
        "/tiktokMissing.txt",
        "/tiktok.txt",
        "/tiktokabc.html",
        "/privacy.txt",
        "/tiktok..%2Fterms.txt",
        "/tiktok" + "x" * 129 + ".txt",
    ):
        assert client.get(path).status_code == 404, path

    for path in ("/terms", "/privacy", "/legal.css"):
        assert client.get(path).status_code == 200, path


def test_tiktok_verification_does_not_follow_symlinks_outside_the_directory(monkeypatch, tmp_path):
    verification_dir = tmp_path / "site-verification"
    verification_dir.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    try:
        (verification_dir / "tiktokOutside.txt").symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("Creating symlinks requires extra privileges on this host")
    monkeypatch.setattr(static, "VERIFICATION_DIR", verification_dir)

    assert TestClient(bot.app).get("/tiktokOutside.txt").status_code == 404


def test_webapp_assets_serving_and_security():
    client = TestClient(bot.app)
    assets_dir = os.path.join(static.DIST_DIR, "assets")
    if not os.path.exists(assets_dir):
        return

    asset_files = [f for f in os.listdir(assets_dir) if os.path.isfile(os.path.join(assets_dir, f))]
    assert len(asset_files) > 0, "Build artifacts missing in webapp/dist/assets"

    sample_asset = asset_files[0]
    response = client.get(f"/app/assets/{sample_asset}")
    assert response.status_code == 200
    assert "public, max-age=31536000, immutable" in response.headers["cache-control"]

    # Traversal security check via HTTP (percent-encoded traversal reaches route handler)
    bad_encoded = client.get("/app/assets/%2e%2e/%2e%2e/bot.py")
    assert bad_encoded.status_code == 403

    # Client-side normalized traversal
    bad_normalized = client.get("/app/assets/../../bot.py")
    assert bad_normalized.status_code in (403, 404)


def test_webapp_assets_sibling_directory_containment():
    """Harden path containment: sibling directories sharing the same string prefix must not be accessible."""
    client = TestClient(bot.app)
    dist_dir = Path(static.DIST_DIR).resolve()
    sibling_dir = dist_dir / "assets_sibling"
    sibling_file = sibling_dir / "secret.txt"

    try:
        sibling_dir.mkdir(parents=True, exist_ok=True)
        sibling_file.write_text("sensitive_data", encoding="utf-8")

        # 1. HTTP percent-encoded traversal targeting sibling directory
        response = client.get("/app/assets/%2e%2e/assets_sibling/secret.txt")
        assert response.status_code == 403

        # 2. Direct route handler containment check (verifies Path.is_relative_to behavior)
        with pytest.raises(HTTPException) as exc_info:
            static.webapp_assets("../assets_sibling/secret.txt", None)
        assert exc_info.value.status_code == 403
    finally:
        if sibling_dir.exists():
            shutil.rmtree(sibling_dir, ignore_errors=True)


def test_webapp_api_backend_contract_requires_body_initdata(monkeypatch):
    """The FastAPI backend expects initData in the JSON request body at /app/api/me.

    Header-based X-Telegram-Init-Data is NOT accepted by the backend, and
    the profile route is /app/api/me, NOT /app/api/profile.
    """
    client = TestClient(bot.app)

    # 1. /app/api/profile does not exist on the backend
    profile_response = client.post("/app/api/profile", json={"initData": "dummy"})
    assert profile_response.status_code == 404

    # 2. Sending X-Telegram-Init-Data header without body initData fails with 401
    header_only_response = client.post(
        "/app/api/me",
        headers={"X-Telegram-Init-Data": "dummy_header_token"},
        json={"lightweight": True},
    )
    assert header_only_response.status_code == 401
    assert "initdata" in header_only_response.json().get("detail", "").lower()

    # 3. Supplying initData in the JSON body satisfies _webapp_user extraction
    def fake_user_id_from_init_data(init_data, token):
        if init_data == "valid_body_token":
            return 42
        raise ValueError("initData non valida")

    monkeypatch.setattr(miniapp, "user_id_from_init_data", fake_user_id_from_init_data)
    monkeypatch.setattr(firebase_service, "get_user_data", lambda uid: {"first_name": "TestUser", "language": "it"})
    monkeypatch.setattr(firebase_service, "get_daily_path", lambda *args: None)

    valid_response = client.post(
        "/app/api/me",
        json={"initData": "valid_body_token", "lightweight": True},
    )
    assert valid_response.status_code == 200
    data = valid_response.json()
    assert data["user"]["name"] == "TestUser"


@pytest.fixture
def preview_webapp(monkeypatch):
    """Import scripts/preview_webapp.py and undo what the import does to the process.

    The preview replaces services.firebase_service functions with in-memory stubs at import
    time (reserve_checkout always answers "ok", for example) and prepends the repo root to
    sys.path. Left in place, those stubs leak into every later test that uses the real
    module. The import is also forced fresh, so the stubs are active for this test even if
    the module had been imported before.
    """
    import scripts

    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.delitem(sys.modules, PREVIEW_MODULE, raising=False)
    monkeypatch.delattr(scripts, "preview_webapp", raising=False)
    saved = dict(vars(firebase_service))
    try:
        from scripts import preview_webapp as module

        yield module
    finally:
        for name in set(vars(firebase_service)) - set(saved):
            delattr(firebase_service, name)
        for name, value in saved.items():
            if vars(firebase_service).get(name) is not value:
                setattr(firebase_service, name, value)
        # monkeypatch only restores entries that existed before; drop the fresh import.
        sys.modules.pop(PREVIEW_MODULE, None)
        vars(scripts).pop("preview_webapp", None)


def test_preview_webapp_guess_contract(preview_webapp):
    """Preview webapp /app/api/guess must accept 'answer' payload matching production contract."""
    client = TestClient(preview_webapp.app)

    res_wrong = client.post("/app/api/guess", json={"answer": "Messi"})
    assert res_wrong.status_code == 200
    data_wrong = res_wrong.json()
    assert data_wrong["status"] == "wrong"
    assert data_wrong["comparison"]["name"] == "Messi"

    name = preview_webapp._challenge()["correct_answers"][0]
    res_correct = client.post("/app/api/guess", json={"answer": name})
    assert res_correct.status_code == 200
    assert res_correct.json()["status"] == "correct"
    assert res_correct.json()["answer"]
    assert res_correct.json()["points_awarded"] == 4


def test_preview_profile_populates_the_full_top_ten(preview_webapp):
    client = TestClient(preview_webapp.app)
    response = client.post("/app/api/me", json={})
    assert response.status_code == 200
    rows = response.json()["leaderboard"]
    assert [row["position"] for row in rows] == list(range(1, 11))
    assert len({row["profile_id"] for row in rows}) == 10
    assert [row["points"] for row in rows] == sorted(
        (row["points"] for row in rows), reverse=True
    )
    assert sum(row["me"] for row in rows) == 1


def test_preview_arena_routes_do_not_shadow_each_other(preview_webapp):
    client = TestClient(preview_webapp.app)
    for mode in ("duel", "training", "events", "story"):
        response = client.post("/app/api/arena", json={"mode": mode, "action": "list"})
        assert response.status_code == 200, (mode, response.text)

