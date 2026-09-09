from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_mini_app_does_not_offer_player_name_suggestions():
    page = (ROOT / "webapp" / "index.html").read_text(encoding="utf-8")
    server = (ROOT / "bot.py").read_text(encoding="utf-8")

    assert "/app/api/players" not in page
    assert 'id="suggestions"' not in page
    assert '@app.post("/app/api/players")' not in server
