from services.player_pool import load_config

DIFFICULTY_ORDER = ["easy", "medium", "hard", "impossible"]


def compute_difficulty_score(player):
    """Punteggio piu' alto = piu' difficile da indovinare.

    Il fattore dominante e' la notorieta' del calciatore (popularity 1-5): un percorso lungo
    di un giocatore famosissimo resta facile, mentre poche tappe in campionati poco seguiti
    sono difficili. Gli altri fattori pesano come "modificatori" e sono normalizzati sulla
    lunghezza della carriera, altrimenti il punteggio cresce solo perche' un calciatore ha
    cambiato molte squadre.
    """
    config = load_config()
    top_leagues = set(config.get("top_leagues", []))
    weights = config.get("difficulty_weights", {})
    career = player.get("career", [])

    teams_count = len(career)
    if teams_count == 0:
        return 0.0

    countries = {entry.get("country") for entry in career if entry.get("country")}
    minor_league_ratio = sum(1 for entry in career if entry.get("league") not in top_leagues) / teams_count
    popularity = player.get("popularity", 3)

    score = (
        (6 - popularity) * weights.get("popularity", 3.0)
        + minor_league_ratio * weights.get("minor_leagues", 4.0)
        + min(max(len(countries) - 2, 0), 3) * weights.get("extra_countries", 1.0)
        + min(max(teams_count - 4, 0), 4) * weights.get("extra_teams", 0.5)
    )
    return score


def bucket_for_score(score, thresholds=None):
    config = load_config()
    thresholds = thresholds or config.get("difficulty_thresholds", {"easy": 8.5, "medium": 12, "hard": 15})

    if score < thresholds["easy"]:
        return "easy"
    if score < thresholds["medium"]:
        return "medium"
    if score < thresholds["hard"]:
        return "hard"
    return "impossible"


def compute_difficulty(player):
    return bucket_for_score(compute_difficulty_score(player))


def group_players_by_difficulty(players):
    groups = {level: [] for level in DIFFICULTY_ORDER}
    for player in players:
        groups[compute_difficulty(player)].append(player)
    return groups


def points_for_difficulty(difficulty):
    return {"easy": 1, "medium": 2, "hard": 3, "impossible": 4}.get(difficulty, 0)
