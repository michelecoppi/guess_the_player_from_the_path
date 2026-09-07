from services.difficulty import (
    DIFFICULTY_ORDER,
    compute_difficulty,
    compute_difficulty_score,
    group_players_by_difficulty,
    points_for_difficulty,
)
from services.player_pool import get_all_players


def test_difficulty_is_always_a_known_bucket():
    for player in get_all_players():
        assert compute_difficulty(player) in DIFFICULTY_ORDER


def test_more_teams_and_lower_popularity_increase_score():
    short_famous_player = {
        "career": [{"team": "A", "country": "Italia", "league": "Serie A"}],
        "popularity": 5,
    }
    long_obscure_player = {
        "career": [
            {"team": "A", "country": "Italia", "league": "Serie A"},
            {"team": "B", "country": "Belgio", "league": "Belgian Pro League"},
            {"team": "C", "country": "Cipro", "league": "Cypriot First Division"},
            {"team": "D", "country": "Norvegia", "league": "Eliteserien"},
        ],
        "popularity": 1,
    }
    assert compute_difficulty_score(long_obscure_player) > compute_difficulty_score(short_famous_player)


def test_group_players_by_difficulty_covers_all_players():
    players = get_all_players()
    groups = group_players_by_difficulty(players)
    total = sum(len(v) for v in groups.values())
    assert total == len(players)
    assert set(groups.keys()) == set(DIFFICULTY_ORDER)


def test_points_for_difficulty_matches_existing_game_scale():
    # Deve restare coerente con points_for_difficulty in guess_handler/show_daily_path_handler
    assert points_for_difficulty("easy") == 1
    assert points_for_difficulty("medium") == 2
    assert points_for_difficulty("hard") == 3
    assert points_for_difficulty("impossible") == 4
    assert points_for_difficulty("unknown") == 0
