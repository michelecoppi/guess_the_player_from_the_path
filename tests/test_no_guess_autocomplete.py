from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_mini_app_does_not_offer_player_name_suggestions():
    bundle_js = next((ROOT / "webapp" / "dist" / "assets").glob("index-*.js")).read_text(encoding="utf-8")
    server = (ROOT / "apps" / "api" / "miniapp.py").read_text(encoding="utf-8")

    assert "/app/api/players" not in bundle_js
    assert "suggestions" not in bundle_js
    assert '@router.post("/app/api/players")' not in server
