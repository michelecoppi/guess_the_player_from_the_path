import os

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

    asset_files = os.listdir(assets_dir)
    assert len(asset_files) > 0, "Build artifacts missing in webapp/dist/assets"

    sample_asset = asset_files[0]
    response = client.get(f"/app/v2/assets/{sample_asset}")
    assert response.status_code == 200
    assert "public, max-age=31536000, immutable" in response.headers["cache-control"]

    # Traversal security check
    bad_response = client.get("/app/v2/assets/../../bot.py")
    assert bad_response.status_code in (403, 404)
