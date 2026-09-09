import json

import pytest

from services import shop, webapp_api


def test_public_profile_only_exposes_statistics_and_equipped_cosmetics(monkeypatch):
    data = {
        "first_name": "Anna", "players_guessed": 50, "points_totali": 123,
        "cosmetics": {"owned": ["neon", "sostenitore_titolo", "fuoco", "ghiaccio"],
                      "equipped": {"theme": "neon", "title": "sostenitore_titolo", "frame": "fuoco"},
                      "looks": [{"name": "PRIVATE_LOOK"}]},
        "chat_id": "PRIVATE_CHAT", "leagues": ["PRIVATE_LEAGUE"],
        "shop_checkout": {"query_id": "PRIVATE_PAYMENT"},
        "daily_hints": "PRIVATE_HINTS", "daily_attempts": 2,
    }
    monkeypatch.setattr(webapp_api.firebase_service, "get_user_data", lambda uid: data)
    result = webapp_api.build_public_profile(42, "en")
    assert set(result) == {"user", "cosmetics", "wearing"}
    assert result["user"]["name"] == "Anna"
    assert result["cosmetics"]["theme"] == shop.get_item("neon")["style"]
    assert result["cosmetics"]["title"]["label"] == "Supporter"
    assert result["cosmetics"]["frame"]["spin"]
    encoded = json.dumps(result)
    assert "PRIVATE_" not in encoded
    assert "ghiaccio" not in encoded  # owned, but not worn
    assert "owned" not in encoded and "looks" not in encoded
    assert len(result["wearing"]) == 5


@pytest.mark.parametrize("target", [None, True, -1, 0, "42", [], {}, 2**53])
def test_invalid_public_profile_ids_do_not_query_firestore(monkeypatch, target):
    monkeypatch.setattr(webapp_api.firebase_service, "get_user_data", lambda uid: pytest.fail("Invalid lookup"))
    assert webapp_api.build_public_profile(target) is None


def test_deleted_user_profile_is_unavailable(monkeypatch):
    monkeypatch.setattr(webapp_api.firebase_service, "get_user_data", lambda uid: None)
    assert webapp_api.build_public_profile(42) is None


def test_refunded_cosmetics_do_not_remain_in_public_profile(monkeypatch):
    monkeypatch.setattr(webapp_api.firebase_service, "get_user_data", lambda uid: {
        "cosmetics": {"owned": [], "equipped": {"theme": "neon"}},
    })
    assert webapp_api.build_public_profile(42)["cosmetics"]["equipped"]["theme"] == "notturno"


def test_leaderboard_links_use_real_user_ids_and_equipped_badges(monkeypatch):
    monkeypatch.setattr(webapp_api.firebase_service, "get_top_users", lambda limit: [{
        "telegram_id": 42, "username": "Anna", "points": 3,
        "players_guessed": 10, "cosmetics": {"equipped": {"badge": "traguardo_esploratore"}},
    }])
    row = webapp_api._leaderboard(42)[0]
    assert row["profile_id"] == 42
    assert row["badge"] == "🧭"
    assert row["me"]
