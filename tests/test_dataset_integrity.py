from services.player_pool import (
    _load_raw_players,
    get_all_players,
    validate_dataset,
    validate_player,
)
from services.dataset_health import build_report


def test_real_dataset_has_no_integrity_problems():
    problems = validate_dataset()
    assert problems == [], "Problemi nel dataset:\n" + "\n".join(problems)


def test_no_two_players_share_an_answer():
    # Il caso peggiore per il giocatore: scrive una risposta esatta e il bot la rifiuta
    # perche' quell'alias appartiene a un altro calciatore.
    aliases = {}
    for player in _load_raw_players():
        for alias in player.get("aliases", []):
            alias = alias.lower().strip()
            assert alias not in aliases or aliases[alias] == player["id"], (
                f"alias '{alias}' condiviso da {aliases.get(alias)} e {player['id']}"
            )
            aliases[alias] = player["id"]


def test_one_club_career_flag_allows_single_team_players():
    bandiera = {
        "id": "bandiera",
        "full_name": "Bandiera Test",
        "aliases": ["bandiera"],
        "nationality": "Italia",
        "one_club_career": True,
        "career": [{"team": "Solo Club", "country": "Italia", "league": "Serie A", "start_year": 2000, "end_year": 2018}],
    }
    assert validate_player(bandiera, min_teams=2) == []

    senza_flag = dict(bandiera)
    senza_flag.pop("one_club_career")
    assert any("percorso troppo corto" in p for p in validate_player(senza_flag, min_teams=2))


def test_one_club_flag_with_multiple_teams_is_flagged():
    player = {
        "id": "sbagliato",
        "full_name": "Test",
        "aliases": ["test"],
        "nationality": "Italia",
        "one_club_career": True,
        "career": [
            {"team": "A", "country": "Italia", "league": "Serie A", "start_year": 2000, "end_year": 2005},
            {"team": "B", "country": "Italia", "league": "Serie A", "start_year": 2005, "end_year": 2010},
        ],
    }
    assert any("one_club_career" in p for p in validate_player(player))


def test_chronology_errors_are_detected():
    player = {
        "id": "cronologia",
        "full_name": "Test Cronologia",
        "aliases": ["test cronologia"],
        "nationality": "Italia",
        "birth_year": 1990,
        "career": [
            {"team": "B", "country": "Italia", "league": "Serie A", "start_year": 2015, "end_year": 2010},
            {"team": "A", "country": "Italia", "league": "Serie A", "start_year": 2008, "end_year": 2015},
        ],
    }
    problems = validate_player(player)
    assert any("precedente all'inizio" in p for p in problems)
    assert any("ordine cronologico" in p for p in problems)


def test_ambiguous_alias_is_detected_at_dataset_level():
    players = [
        {
            "id": "uno", "full_name": "Uno Test", "aliases": ["ronaldo"], "nationality": "Brasile",
            "career": [
                {"team": "A", "country": "Italia", "league": "Serie A", "start_year": 2000, "end_year": 2005},
                {"team": "B", "country": "Italia", "league": "Serie A", "start_year": 2005, "end_year": 2010},
            ],
        },
        {
            "id": "due", "full_name": "Due Test", "aliases": ["ronaldo"], "nationality": "Portogallo",
            "career": [
                {"team": "C", "country": "Italia", "league": "Serie A", "start_year": 2000, "end_year": 2005},
                {"team": "D", "country": "Italia", "league": "Serie A", "start_year": 2005, "end_year": 2010},
            ],
        },
    ]
    problems = validate_dataset(players, min_teams=2)
    assert any("alias ambiguo" in p for p in problems)


def test_dataset_supports_more_days_than_the_no_repeat_window():
    # Se il pool e' piu' piccolo della finestra anti-ripetizione, il bot e' costretto a
    # riproporre calciatori gia' usati: e' il segnale che il dataset va ampliato.
    report = build_report()
    assert report["selectable"] > report["history_days_no_repeat"], report["warnings"]


def test_every_difficulty_bucket_has_candidates():
    report = build_report()
    for level, count in report["by_difficulty"].items():
        assert count > 0, f"nessun giocatore nella fascia '{level}': la rotazione difficolta' non funziona"


def test_selectable_players_are_all_verified_and_valid():
    for player in get_all_players():
        assert player.get("verified") is True
        assert validate_player(player) == []
