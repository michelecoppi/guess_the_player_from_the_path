import os
import shutil
from pathlib import Path

import pytest
from fastapi import HTTPException
from starlette.testclient import TestClient

import bot


def test_webapp_legacy_serving_unaffected():
    client = TestClient(bot.app)
    response = client.get("/app")
    assert response.status_code == 200
    assert "Guess the Player" in response.text
    assert "webapp/client.js" in response.text or "/app/client.js" in response.text


def test_webapp_v2_serving_and_revalidation():
    client = TestClient(bot.app)
    response = client.get("/app/v2")
    if not os.path.exists(os.path.join(bot.DIST_DIR, "index.html")):
        assert response.status_code == 503
        return

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "ETag" in response.headers
    etag = response.headers["ETag"]

    # Revalidation returns 304
    revalidated = client.get("/app/v2", headers={"If-None-Match": etag})
    assert revalidated.status_code == 304


def test_webapp_v2_assets_serving_and_security():
    client = TestClient(bot.app)
    assets_dir = os.path.join(bot.DIST_DIR, "assets")
    if not os.path.exists(assets_dir):
        return

    asset_files = [f for f in os.listdir(assets_dir) if os.path.isfile(os.path.join(assets_dir, f))]
    assert len(asset_files) > 0, "Build artifacts missing in webapp/dist/assets"

    sample_asset = asset_files[0]
    response = client.get(f"/app/v2/assets/{sample_asset}")
    assert response.status_code == 200
    assert "public, max-age=31536000, immutable" in response.headers["cache-control"]

    # Traversal security check via HTTP (percent-encoded traversal reaches route handler)
    bad_encoded = client.get("/app/v2/assets/%2e%2e/%2e%2e/bot.py")
    assert bad_encoded.status_code == 403

    # Client-side normalized traversal
    bad_normalized = client.get("/app/v2/assets/../../bot.py")
    assert bad_normalized.status_code in (403, 404)


def test_webapp_v2_assets_sibling_directory_containment():
    """Harden path containment: sibling directories sharing the same string prefix must not be accessible."""
    client = TestClient(bot.app)
    dist_dir = Path(bot.DIST_DIR).resolve()
    sibling_dir = dist_dir / "assets_sibling"
    sibling_file = sibling_dir / "secret.txt"

    try:
        sibling_dir.mkdir(parents=True, exist_ok=True)
        sibling_file.write_text("sensitive_data", encoding="utf-8")

        # 1. HTTP percent-encoded traversal targeting sibling directory
        response = client.get("/app/v2/assets/%2e%2e/assets_sibling/secret.txt")
        assert response.status_code == 403

        # 2. Direct route handler containment check (verifies Path.is_relative_to behavior)
        with pytest.raises(HTTPException) as exc_info:
            bot.webapp_v2_assets("../assets_sibling/secret.txt", None)
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

    monkeypatch.setattr(bot, "user_id_from_init_data", fake_user_id_from_init_data)
    monkeypatch.setattr(bot.firebase_service, "get_user_data", lambda uid: {"first_name": "TestUser", "language": "it"})
    monkeypatch.setattr(bot.firebase_service, "get_daily_path", lambda *args: None)

    valid_response = client.post(
        "/app/api/me",
        json={"initData": "valid_body_token", "lightweight": True},
    )
    assert valid_response.status_code == 200
    data = valid_response.json()
    assert data["user"]["name"] == "TestUser"


def test_preview_webapp_guess_contract():
    """Preview webapp /app/api/guess must accept 'answer' payload matching production contract."""
    from scripts import preview_webapp
    client = TestClient(preview_webapp.app)

    res_wrong = client.post("/app/api/guess", json={"answer": "Messi"})
    assert res_wrong.status_code == 200
    data_wrong = res_wrong.json()
    assert data_wrong["status"] == "wrong"
    assert data_wrong["comparison"]["name"] == "Messi"

    res_correct = client.post("/app/api/guess", json={"answer": "Vitolo"})
    assert res_correct.status_code == 200
    assert res_correct.json()["status"] == "correct"

