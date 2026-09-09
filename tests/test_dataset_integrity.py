from services.dataset_health import build_report, unclassified_leagues
from services.player_pool import (
    _load_raw_players,
    get_all_players,
    load_config,
    validate_dataset,
    validate_player,
)


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


def _career(*stops):
    return [
        {"team": team, "country": country, "league": league,
         "start_year": 2000 + index * 2, "end_year": 2002 + index * 2}
        for index, (team, country, league) in enumerate(stops)
    ]


def _player(player_id, *stops):
    return {"id": player_id, "full_name": f"{player_id.title()} Test", "aliases": [player_id],
            "nationality": "Italia", "career": _career(*stops)}


def test_same_club_in_two_countries_is_a_problem():
    # Il caso vero da cui nasce il controllo: San Lorenzo, club argentino, marcato "Spagna"
    # in sei tappe. Il paese si vede nel percorso, quindi era un indizio falso in partita.
    players = [
        _player("uno", ("San Lorenzo", "Argentina", "Liga Profesional"), ("A", "Italia", "Serie A")),
        _player("due", ("San Lorenzo", "Spagna", "La Liga"), ("B", "Italia", "Serie A")),
    ]
    problems = validate_dataset(players, min_teams=2, config={})
    assert any("San Lorenzo" in p and "paesi diversi" in p for p in problems), problems


def test_declared_multi_country_clubs_are_accepted():
    # Al-Shabab sono due club diversi con lo stesso nome, Vojvodina e' lo stesso club in un
    # paese che ha cambiato nome: sono decisioni, e stanno scritte in config.
    players = [
        _player("uno", ("Al-Shabab", "Arabia Saudita", "Saudi Pro League"), ("A", "Italia", "Serie A")),
        _player("due", ("Al-Shabab", "Emirati Arabi Uniti", "UAE Pro League"), ("B", "Italia", "Serie A")),
    ]
    config = {"multi_country_clubs": {"Al-Shabab": "omonimi"}}
    assert not any("Al-Shabab" in p for p in validate_dataset(players, min_teams=2, config=config))


def test_a_league_named_with_the_italian_country_is_a_problem():
    # Il caso vero: "Super League Grecia" (in known_leagues) e "Super League Greece" (no)
    # convivevano nel dataset, e un quarto delle tappe greche pesava come campionato
    # sconosciuto. La grafia ibrida e' il punto in cui la doppia scrittura nasce.
    players = [_player("uno", ("A", "Grecia", "Super League Grecia"), ("B", "Italia", "Serie A"))]
    problems = validate_dataset(players, min_teams=2, config={})
    assert any("Super League Grecia" in p and "in italiano" in p for p in problems), problems


def test_a_country_spelled_the_same_in_both_languages_is_not_a_hybrid():
    # "Paraguay" e "Nigeria" si scrivono uguale in italiano e in inglese: un campionato che
    # li contiene non e' un nome ibrido, e segnalarlo sarebbe solo rumore.
    players = [
        _player("uno", ("A", "Paraguay", "Primera Division Paraguay"), ("B", "Italia", "Serie A")),
        _player("due", ("C", "Nigeria", "Nigeria Premier League"), ("D", "Italia", "Serie A")),
    ]
    assert not any("in italiano" in p for p in validate_dataset(players, min_teams=2, config={}))


def test_country_name_inside_a_longer_word_is_not_a_hybrid():
    # "Uruguayan Primera Division" contiene "Uruguay" solo come prefisso di un aggettivo.
    players = [_player("uno", ("A", "Uruguay", "Uruguayan Primera Division"), ("B", "Italia", "Serie A"))]
    assert not any("in italiano" in p for p in validate_dataset(players, min_teams=2, config={}))


def test_league_spelling_check_ignores_accents_and_punctuation():
    # La classe di errore che il README segnalava gia': "Segunda Division" / "Segunda
    # Division" con l'accento sono due chiavi diverse per top_leagues/known_leagues.
    players = [_player("uno", ("A", "Spagna", "Segunda Division"), ("B", "Spagna", "Segunda División"))]
    assert any("modi diversi" in p for p in validate_dataset(players, min_teams=2, config={}))


def test_distinct_leagues_are_not_confused():
    players = [_player("uno", ("A", "Grecia", "Super League Greece"), ("B", "Grecia", "Super League Greece 2"))]
    assert not any("modi diversi" in p for p in validate_dataset(players, min_teams=2, config={}))


def test_every_configured_league_name_exists_in_the_dataset():
    # Una voce di known_leagues che nessuna tappa usa e' quasi sempre un nome scritto in un
    # modo nel dataset e in un altro in config: la classificazione non si applica a niente.
    used = {stop.get("league") for player in _load_raw_players() for stop in player.get("career", [])}
    config = load_config()
    for league in config.get("top_leagues", []) + config.get("known_leagues", []):
        assert league in used, f"'{league}' e' classificato in config.json ma non compare nel dataset"


def test_frequent_unclassified_leagues_are_reported():
    players = [_player(f"p{n}", ("A", "Cina", "Chinese Super League"), ("B", "Italia", "Serie A"))
               for n in range(3)]
    config = {"top_leagues": ["Serie A"], "known_leagues": [], "unclassified_league_warning_min": 3}
    assert unclassified_leagues(players, config) == [("Chinese Super League", 3)]
    # Sotto soglia non e' un avviso: la coda lunga dei campionati minori e' normale.
    config["unclassified_league_warning_min"] = 4
    assert unclassified_leagues(players, config) == []
