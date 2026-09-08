import pytest

from services.difficulty import (
    DIFFICULTY_ORDER,
    compute_difficulty,
    compute_difficulty_score,
    explain_difficulty,
    group_players_by_difficulty,
    points_for_difficulty,
)
from services.player_pool import _load_raw_players, get_all_players, get_player_by_id

# Fasce che una scheda puo' raggiungere partendo da una certa notorieta': i modificatori sul
# percorso valgono al massimo 5.5 punti, cioe' poco piu' di un gradino di notorieta' (4).
# Tabella documentata in docs/difficolta.md, sezione 2.
REACHABLE_BUCKETS = {
    5: {"easy", "medium"},
    4: {"easy", "medium", "hard"},
    3: {"medium", "hard", "impossible"},
    2: {"hard", "impossible"},
    1: {"impossible"},
}


def test_difficulty_is_always_a_known_bucket():
    for player in get_all_players():
        assert compute_difficulty(player) in DIFFICULTY_ORDER


@pytest.mark.parametrize(
    "player_id, expected_popularity, expected_difficulty",
    [
        # Casi di riferimento di docs/difficolta.md, sezione 3. I primi due erano sbagliati
        # prima della taratura (Del Piero medium, Forlan impossible, De Ligt hard);
        # gli ultimi tre sono le ancore della scala di notorieta': una leggenda di club non
        # puo' superare 'medium', 'hard' e' il livello Jankto, 'impossible' quello Constant.
        ("delpiero", 5, "easy"),
        ("totti", 5, "easy"),
        ("forlan", 4, "medium"),
        ("de_ligt", 4, "medium"),
        ("julio_cesar", 4, "medium"),
        ("jankto", 3, "hard"),
        ("kevin_constant", 1, "impossible"),
    ],
)
def test_reference_players_stay_in_their_documented_bucket(player_id, expected_popularity, expected_difficulty):
    player = get_player_by_id(player_id)
    assert player is not None, f"scheda mancante: {player_id}"
    assert player.get("popularity") == expected_popularity
    assert compute_difficulty(player) == expected_difficulty


def test_fame_dominates_the_path():
    """Il percorso puo' spostare un giocatore di una fascia, mai di due.

    E' la promessa del modello: senza questo vincolo un famoso girovago torna 'impossible'
    (il caso Forlan) e la difficolta' smette di dire qualcosa sul giocatore.
    """
    for player in get_all_players():
        popularity = player.get("popularity", 3)
        assert compute_difficulty(player) in REACHABLE_BUCKETS[popularity], (
            f"{player['id']} (popularity {popularity}) e' finito in "
            f"{compute_difficulty(player)}, fuori dalle fasce raggiungibili"
        )


def test_known_leagues_weigh_less_than_unknown_ones():
    """Ajax e Boca non possono pesare come una seconda divisione asiatica."""
    base = {"popularity": 3, "career": [{"team": "A", "country": "Italia", "league": "Serie A"}]}

    def with_second_stop(league, country):
        return {
            "popularity": 3,
            "career": base["career"] + [{"team": "B", "country": country, "league": league}],
        }

    top = with_second_stop("La Liga", "Spagna")
    known = with_second_stop("Eredivisie", "Olanda")
    obscure = with_second_stop("Qatar Stars League", "Qatar")

    assert compute_difficulty_score(top) < compute_difficulty_score(known)
    assert compute_difficulty_score(known) < compute_difficulty_score(obscure)


def test_explain_difficulty_components_sum_to_the_score():
    player = get_player_by_id("forlan")
    explained = explain_difficulty(player)
    assert explained["difficulty"] == compute_difficulty(player)
    assert explained["score"] == pytest.approx(compute_difficulty_score(player))
    assert sum(explained["components"].values()) == pytest.approx(explained["score"])


def test_curated_dataset_covers_every_bucket():
    """La curatela non deve lasciare scoperta una fascia.

    Guarda l'intero dataset, schede non ancora verificate comprese: quante siano gia'
    approvate e' una domanda operativa diversa, e ha gia' il suo controllo in
    test_dataset_integrity.test_every_difficulty_bucket_has_candidates (che ragiona sul pool
    davvero selezionabile). Qui interessa che i giocatori per quel livello esistano: se
    mancano, nessuna approvazione risolve il problema.
    """
    groups = group_players_by_difficulty(_load_raw_players())
    empty = [level for level, players in groups.items() if not players]
    assert not empty, f"fasce senza candidati nel dataset: {empty}"


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
