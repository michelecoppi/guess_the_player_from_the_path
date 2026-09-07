from services.player_pool import (
    filter_players,
    get_all_players,
    get_answer_aliases,
    get_incomplete_or_unverified_players,
    validate_player,
)


def test_dataset_loads_and_has_players():
    players = get_all_players()
    assert len(players) > 10


def test_all_selectable_players_pass_validation():
    for player in get_all_players():
        assert validate_player(player) == [], f"{player['id']} non valido ma incluso nel pool"


def test_unverified_players_excluded_by_default():
    all_players = get_all_players(include_unverified=True)
    verified_only = get_all_players(include_unverified=False)
    assert len(verified_only) <= len(all_players)
    assert all(p.get("verified", False) for p in verified_only)


def test_incomplete_player_is_flagged():
    incomplete_player = {
        "id": "test_incomplete",
        "full_name": "Test Player",
        "aliases": ["test player"],
        "nationality": "Italia",
        "career": [{"team": "Solo Club", "country": "Italia", "league": "Serie A", "start_year": 2020}],
    }
    problems = validate_player(incomplete_player, min_teams=2)
    assert any("percorso troppo corto" in p for p in problems)


def test_player_missing_fields_is_flagged():
    broken_player = {"id": "broken", "career": []}
    problems = validate_player(broken_player)
    assert len(problems) > 0


def test_get_incomplete_or_unverified_report_has_reasons():
    report = get_incomplete_or_unverified_players()
    for entry in report:
        assert entry["problems"]


def test_filter_players_min_teams():
    players = get_all_players()
    filtered = filter_players(players, {"min_teams": 6})
    assert all(len(p["career"]) >= 6 for p in filtered)


def test_filter_players_max_teams():
    players = get_all_players()
    filtered = filter_players(players, {"max_teams": 2})
    assert all(len(p["career"]) <= 2 for p in filtered)


def test_answer_aliases_include_full_name():
    players = get_all_players()
    player = next(p for p in players if p["id"] == "messi")
    aliases = get_answer_aliases(player)
    assert "lionel messi" in aliases
    assert "messi" in aliases
