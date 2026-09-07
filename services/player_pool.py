import json
import os

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PLAYERS_PATH = os.path.join(_BASE_DIR, "data", "players.json")
_CONFIG_PATH = os.path.join(_BASE_DIR, "data", "config.json")

_players_cache = None
_config_cache = None


def load_config():
    global _config_cache
    if _config_cache is None:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            _config_cache = json.load(f)
    return _config_cache


def _load_raw_players():
    global _players_cache
    if _players_cache is None:
        with open(_PLAYERS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        _players_cache = data.get("players", [])
    return _players_cache


def validate_player(player, min_teams=2):
    """Ritorna una lista di problemi trovati sui dati del giocatore (vuota se ok)."""
    problems = []
    required_fields = ["id", "full_name", "aliases", "nationality", "career"]
    for field in required_fields:
        if not player.get(field):
            problems.append(f"campo mancante o vuoto: {field}")

    career = player.get("career", [])
    if len(career) < min_teams:
        problems.append(f"percorso troppo corto ({len(career)} squadre, minimo {min_teams})")

    for entry in career:
        for key in ("team", "country", "league", "start_year"):
            if entry.get(key) in (None, ""):
                problems.append(f"tappa carriera incompleta ({entry.get('team', '?')}): manca '{key}'")

    return problems


def get_all_players(include_unverified=None):
    """Carica tutti i giocatori dal dataset locale, filtrando quelli con dati incompleti
    e (di default) quelli non verificati, secondo 'auto_include_unverified_players' in config.json."""
    config = load_config()
    if include_unverified is None:
        include_unverified = config.get("auto_include_unverified_players", False)
    min_teams = config.get("min_teams_in_career", 2)

    valid_players = []
    for player in _load_raw_players():
        if not include_unverified and not player.get("verified", False):
            continue
        if validate_player(player, min_teams=min_teams):
            continue
        valid_players.append(player)

    return valid_players


def get_incomplete_or_unverified_players():
    """Utile per l'area admin: elenca i giocatori scartati dalla selezione automatica e il motivo."""
    config = load_config()
    min_teams = config.get("min_teams_in_career", 2)
    report = []
    for player in _load_raw_players():
        problems = validate_player(player, min_teams=min_teams)
        if not player.get("verified", False):
            problems = ["dati non verificati (verified=false)"] + problems
        if problems:
            report.append({"id": player.get("id"), "full_name": player.get("full_name"), "problems": problems})
    return report


def get_player_by_id(player_id):
    for player in _load_raw_players():
        if player.get("id") == player_id:
            return player
    return None


def get_answer_aliases(player):
    aliases = set(a.strip().lower() for a in player.get("aliases", []) if a.strip())
    if player.get("full_name"):
        aliases.add(player["full_name"].strip().lower())
    return sorted(aliases)


def filter_players(players, rules):
    """Applica le regole di un template evento (data/event_templates.json) a un elenco di giocatori."""
    config = load_config()
    top_leagues = set(config.get("top_leagues", []))
    result = []

    for player in players:
        career = player.get("career", [])
        teams_count = len(career)

        if "min_teams" in rules and teams_count < rules["min_teams"]:
            continue
        if "max_teams" in rules and teams_count > rules["max_teams"]:
            continue
        if "max_popularity" in rules and player.get("popularity", 3) > rules["max_popularity"]:
            continue
        if "min_popularity" in rules and player.get("popularity", 3) < rules["min_popularity"]:
            continue
        if "nationality_in" in rules and player.get("nationality") not in rules["nationality_in"]:
            continue
        if rules.get("leagues_only_top") and any(entry.get("league") not in top_leagues for entry in career):
            continue
        if rules.get("requires_minor_league") and not any(entry.get("league") not in top_leagues for entry in career):
            continue

        result.append(player)

    return result
