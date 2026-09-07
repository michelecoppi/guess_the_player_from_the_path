from services.player_pool import load_config

DIFFICULTY_ORDER = ["easy", "medium", "hard", "impossible"]


def compute_difficulty_score(player):
    """Punteggio piu' alto = piu' difficile da indovinare.
    Fattori: numero squadre, numero campionati/paesi diversi, tappe in campionati minori,
    popolarita' del giocatore (meno popolare = piu' difficile)."""
    config = load_config()
    top_leagues = set(config.get("top_leagues", []))
    career = player.get("career", [])

    teams_count = len(career)
    countries = {entry.get("country") for entry in career if entry.get("country")}
    minor_league_stops = sum(1 for entry in career if entry.get("league") not in top_leagues)
    popularity = player.get("popularity", 3)

    score = (
        teams_count * 1.0
        + len(countries) * 1.5
        + minor_league_stops * 2.0
        + (6 - popularity) * 2.0
    )
    return score


def bucket_for_score(score, thresholds=None):
    config = load_config()
    thresholds = thresholds or config.get("difficulty_thresholds", {"easy": 5, "medium": 9, "hard": 13})

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
