import json

import pytest

from services import shop, webapp_api


def test_public_profile_only_exposes_statistics_and_equipped_cosmetics(monkeypatch):
    data = {
        "first_name": "Anna", "players_guessed": 50, "points_totali": 123,
        "cosmetics": {"owned": ["neon", "sostenitore_titolo", "fuoco", "ghiaccio"],
                      "equipped": {"theme": "neon", "title": "sostenitore_titolo", "frame": "fuoco"},
                      "looks": [{"name": "PRIVATE_LOOK"}]},
        "trophies": ["1_giramondo_20260907", "3_PRIVATEEVENT_20251201"],
        "chat_id": "PRIVATE_CHAT", "leagues": ["PRIVATE_LEAGUE"],
        "shop_checkout": {"query_id": "PRIVATE_PAYMENT"},
        "daily_hints": "PRIVATE_HINTS", "daily_attempts": 2,
    }
    monkeypatch.setattr(webapp_api.firebase_service, "get_user_data", lambda uid: data)
    result = webapp_api.build_public_profile(42, "en")
    assert set(result) == {"user", "cosmetics", "wearing", "trophies"}
    assert result["user"]["name"] == "Anna"
    assert result["cosmetics"]["theme"] == shop.get_item("neon")["style"]
    assert result["cosmetics"]["title"]["label"] == "Supporter"
    assert result["cosmetics"]["frame"]["spin"]
    # Solo i trofei appesi al profilo: non avendo scelto, il ripiego sono i migliori, uno
    # per volta fino a tre - non la bacheca intera.
    assert [one["code"] for one in result["trophies"]] == ["1_giramondo_20260907",
                                                           "3_PRIVATEEVENT_20251201"]
    encoded = json.dumps(result)
    assert "PRIVATE_" not in encoded
    assert "ghiaccio" not in encoded  # owned, but not worn
    assert "owned" not in encoded and "looks" not in encoded
    assert len(result["wearing"]) == len(shop.KINDS)


def test_public_profile_shows_only_the_trophies_that_were_pinned(monkeypatch):
    """La bacheca intera e' di chi la possiede. Da fuori si vede quello che ha scelto di
    appendere, e niente altro."""
    monkeypatch.setattr(webapp_api.firebase_service, "get_user_data", lambda uid: {
        "first_name": "Anna",
        "trophies": ["1_giramondo_20261001", "2_PRIVATETROPHY_20261101", "MON_July_3_2026_1"],
        "cosmetics": {"owned": [], "equipped": {},
                      "pinned": ["MON_July_3_2026_1", "1_giramondo_20261001"]},
    })
    result = webapp_api.build_public_profile(42, "en")
    assert [one["code"] for one in result["trophies"]] == ["MON_July_3_2026_1", "1_giramondo_20261001"]
    assert "PRIVATETROPHY" not in json.dumps(result)


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


def test_public_profile_search_returns_only_safe_summary_fields(monkeypatch):
    seen = []
    monkeypatch.setattr(webapp_api.firebase_service, "find_users_by_first_name", lambda prefix, limit: seen.append((prefix, limit)) or [{
        "telegram_id": 42, "first_name": "Anna Maria", "points_totali": 12, "players_guessed": 10,
        "trophies": ["1_event"], "chat_id": "PRIVATE", "leagues": ["PRIVATE"],
        "cosmetics": {"equipped": {"badge": "traguardo_esploratore"}},
    }])
    result = webapp_api.search_public_profiles("  anna   maria ")
    assert seen == [("Anna Maria", 10)]
    assert result == [{"profile_id": 42, "name": "Anna Maria", "badge": "🧭", "points": 12, "trophies": 1}]
    assert "PRIVATE" not in json.dumps(result)


@pytest.mark.parametrize("query", [None, "", " ", "a", [], {}])
def test_public_profile_search_rejects_short_or_invalid_queries(monkeypatch, query):
    monkeypatch.setattr(webapp_api.firebase_service, "find_users_by_first_name", lambda *args: pytest.fail("Invalid search"))
    assert webapp_api.search_public_profiles(query) == []
