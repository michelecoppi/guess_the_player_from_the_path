import pytest

from services.difficulty import (
    DIFFICULTY_ORDER,
    band_cutoffs_100,
    compute_difficulty,
    compute_difficulty_score,
    explain_difficulty,
    group_players_by_difficulty,
    max_raw_score,
    model_fingerprint,
    points_for_difficulty,
    predict_difficulty,
    to_score_100,
)
from services.player_pool import _load_raw_players, get_all_players, get_player_by_id, load_config

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


# ---------------------------------------------------------------------------
# Scala 0-100, impronta della taratura, previsione fotografata (#21)
# ---------------------------------------------------------------------------

def _config_with(**overrides):
    config = dict(load_config())
    config.update(overrides)
    return config


def test_score_100_keeps_the_order_of_the_raw_score_and_stays_in_range():
    players = get_all_players()
    scored = sorted(players, key=compute_difficulty_score)
    scores_100 = [explain_difficulty(player)["score_100"] for player in scored]
    assert all(0 <= score <= 100 for score in scores_100)
    assert scores_100 == sorted(scores_100)


def test_score_100_spans_the_whole_scale_of_the_current_tuning():
    assert to_score_100(0) == 0.0
    assert to_score_100(max_raw_score()) == 100.0
    # Totti e' l'estremo basso anche sulla scala 0-100.
    assert predict_difficulty(get_player_by_id("totti"))["score"] == 0.0


def test_band_cutoffs_100_are_the_raw_thresholds_on_the_0_100_scale():
    thresholds = load_config()["difficulty_thresholds"]
    assert band_cutoffs_100() == {level: to_score_100(thresholds[level]) for level in ("easy", "medium", "hard")}
    # Le fasce restano decise sul grezzo: la scala serve a leggerle, non le ridefinisce.
    for player in get_all_players():
        predicted = predict_difficulty(player)
        assert predicted["band"] == compute_difficulty(player)


def test_prediction_is_reproducible_and_consistent_with_the_bucket():
    player = get_player_by_id("forlan")
    first, second = predict_difficulty(player), predict_difficulty(player)
    assert first == second
    assert first["band"] == compute_difficulty(player)
    assert first["raw_score"] == pytest.approx(compute_difficulty_score(player), abs=1e-3)


def test_fingerprint_changes_with_the_tuning_but_not_with_editorial_only_lists():
    base = model_fingerprint()
    weights = dict(load_config()["difficulty_weights"], extra_teams=0.3)
    assert model_fingerprint(_config_with(difficulty_weights=weights)) != base
    thresholds = dict(load_config()["difficulty_thresholds"], hard=14)
    assert model_fingerprint(_config_with(difficulty_thresholds=thresholds)) != base
    # obscure_leagues non cambia nessun punteggio (vedi league_tier_weight): non e' taratura.
    assert model_fingerprint(_config_with(obscure_leagues=["Campionato Inventato"])) == base


def test_a_different_tuning_rescales_the_score_100_without_hard_coded_bounds():
    player = get_player_by_id("jankto")
    doubled = {key: value * 2 for key, value in load_config()["difficulty_weights"].items()}
    config = _config_with(difficulty_weights=doubled)
    # Pesi tutti raddoppiati: il grezzo raddoppia, la scala 0-100 no.
    assert compute_difficulty_score(player, config=config) == pytest.approx(2 * compute_difficulty_score(player))
    assert predict_difficulty(player, config=config)["score"] == predict_difficulty(player)["score"]
