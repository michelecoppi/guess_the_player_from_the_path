import json
import os

from services.matching import find_match, normalize

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PLAYERS_PATH = os.path.join(_BASE_DIR, "data", "players.json")
_CONFIG_PATH = os.path.join(_BASE_DIR, "data", "config.json")

_players_cache = None
_config_cache = None
_alias_index_cache = None

# Anno minimo plausibile per una tappa di carriera: sotto questa soglia il dato e' quasi
# sicuramente un errore di battitura (es. 199 invece di 1990).
_MIN_PLAUSIBLE_YEAR = 1900
_MAX_PLAUSIBLE_YEAR = 2100


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


def reload_dataset():
    """Svuota le cache in memoria: usato dagli script di import e dai test dopo aver
    riscritto data/players.json."""
    global _players_cache, _config_cache, _alias_index_cache
    _players_cache = None
    _config_cache = None
    _alias_index_cache = None


def validate_player(player, min_teams=2):
    """Ritorna una lista di problemi trovati sui dati del giocatore (vuota se ok).

    Oltre ai campi obbligatori controlla la coerenza cronologica della carriera: sono gli
    errori piu' frequenti quando si amplia il dataset a mano (anni invertiti, tappe non in
    ordine, anno di nascita incompatibile con l'esordio)."""
    problems = []
    required_fields = ["id", "full_name", "aliases", "nationality", "career"]
    for field in required_fields:
        if not player.get(field):
            problems.append(f"campo mancante o vuoto: {field}")

    career = player.get("career", [])
    # Un percorso di una sola squadra e' valido solo se marcato esplicitamente come
    # "bandiera" (one_club_career): serve a distinguere una carriera davvero monoclub
    # (Totti, Maldini, Puyol) da una scheda incompleta.
    if len(career) < min_teams and not player.get("one_club_career"):
        problems.append(
            f"percorso troppo corto ({len(career)} squadre, minimo {min_teams}): "
            "se e' davvero una carriera in un solo club aggiungi \"one_club_career\": true"
        )
    if player.get("one_club_career") and len(career) > 1:
        problems.append("marcato one_club_career ma la carriera ha piu' di una squadra")

    popularity = player.get("popularity", 3)
    if not isinstance(popularity, int) or not 1 <= popularity <= 5:
        problems.append(f"popolarita' non valida ({popularity}): deve essere un intero 1-5")

    birth_year = player.get("birth_year")
    if birth_year is not None and not (_MIN_PLAUSIBLE_YEAR <= birth_year <= _MAX_PLAUSIBLE_YEAR):
        problems.append(f"anno di nascita non plausibile: {birth_year}")

    previous_start = None
    for entry in career:
        team_label = entry.get("team", "?")
        for key in ("team", "country", "league", "start_year"):
            if entry.get(key) in (None, ""):
                problems.append(f"tappa carriera incompleta ({team_label}): manca '{key}'")

        if "loan" in entry and not isinstance(entry["loan"], bool):
            problems.append(f"tappa {team_label}: 'loan' deve essere true/false ({entry['loan']})")

        # Presenze e gol sono facoltativi (non tutte le schede li hanno), ma se ci sono
        # devono essere numeri non negativi: finiscono disegnati nell'immagine.
        for key in ("apps", "goals"):
            value = entry.get(key)
            if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
                problems.append(f"tappa {team_label}: '{key}' deve essere un intero >= 0 ({value})")

        start_year = entry.get("start_year")
        end_year = entry.get("end_year")

        if isinstance(start_year, int):
            if not _MIN_PLAUSIBLE_YEAR <= start_year <= _MAX_PLAUSIBLE_YEAR:
                problems.append(f"tappa {team_label}: anno di inizio non plausibile ({start_year})")
            if birth_year and start_year - birth_year < 14:
                problems.append(
                    f"tappa {team_label}: inizio {start_year} incompatibile con l'anno di nascita {birth_year}"
                )
            if previous_start is not None and start_year < previous_start:
                problems.append(
                    f"tappa {team_label}: le tappe non sono in ordine cronologico ({start_year} dopo {previous_start})"
                )
            previous_start = start_year
        elif start_year is not None:
            problems.append(f"tappa {team_label}: 'start_year' non e' un numero ({start_year})")

        if end_year is not None:
            if not isinstance(end_year, int):
                problems.append(f"tappa {team_label}: 'end_year' non e' un numero ({end_year})")
            elif isinstance(start_year, int) and end_year < start_year:
                problems.append(f"tappa {team_label}: fine ({end_year}) precedente all'inizio ({start_year})")

    return problems


def validate_dataset(players=None, min_teams=None):
    """Controlli che hanno senso solo sull'intero dataset (non sul singolo giocatore):
    id duplicati e alias condivisi fra giocatori diversi.

    Un alias condiviso e' il bug piu' insidioso del gioco: la risposta "ronaldo" sarebbe
    corretta per due calciatori diversi, ma il bot ne accetta solo uno."""
    if players is None:
        players = _load_raw_players()
    if min_teams is None:
        min_teams = load_config().get("min_teams_in_career", 2)

    problems = []

    seen_ids = {}
    for index, player in enumerate(players):
        player_id = player.get("id")
        if not player_id:
            problems.append(f"giocatore in posizione {index}: campo 'id' mancante")
            continue
        if player_id in seen_ids:
            problems.append(f"id duplicato: '{player_id}'")
        seen_ids[player_id] = index

    alias_owner: dict[str, str] = {}
    for player in players:
        for alias in get_answer_aliases(player):
            owner = alias_owner.get(alias)
            if owner and owner != player.get("id"):
                problems.append(
                    f"alias ambiguo '{alias}': usato sia da '{owner}' sia da '{player.get('id')}'"
                )
            else:
                alias_owner[alias] = player.get("id")

    for player in players:
        for problem in validate_player(player, min_teams=min_teams):
            problems.append(f"{player.get('id', '?')}: {problem}")

    return problems


def is_practice_only(player):
    """Riservato all'allenamento: non esce mai come sfida del giorno ne' dentro un evento.

    E' la regola che rende allenamento e round di gruppo materiale infinito **senza
    spoiler**: chi si allena su queste schede non vedra' mai lo stesso percorso arrivare
    come sfida del giorno, perche' per costruzione non ci puo' arrivare. La fetta e' scritta
    nel dataset (`"practice_only": true`) e non calcolata a runtime: se cambiasse da sola,
    un giocatore potrebbe passare da una parte all'altra e lo spoiler tornerebbe."""
    return bool(player.get("practice_only"))


def get_all_players(include_unverified=None, exclude_ids=None, practice_only=False):
    """Carica tutti i giocatori dal dataset locale, filtrando quelli con dati incompleti
    e (di default) quelli non verificati, secondo 'auto_include_unverified_players' in config.json.

    'exclude_ids' permette all'admin di sospendere al volo un giocatore (dato sbagliato
    segnalato dagli utenti) senza dover ridistribuire il bot.

    'practice_only' sceglie **quale delle due meta'** del dataset si vuole: di default
    quella che alimenta il gioco vero (sfida del giorno ed eventi), con True quella
    riservata all'allenamento. Le due non si incontrano mai."""
    config = load_config()
    if include_unverified is None:
        include_unverified = config.get("auto_include_unverified_players", False)
    min_teams = config.get("min_teams_in_career", 2)
    exclude_ids = set(exclude_ids or [])

    valid_players = []
    for player in _load_raw_players():
        if player.get("id") in exclude_ids:
            continue
        if is_practice_only(player) != practice_only:
            continue
        if not include_unverified and not player.get("verified", False):
            continue
        if validate_player(player, min_teams=min_teams):
            continue
        valid_players.append(player)

    return valid_players


def get_practice_players(exclude_ids=None):
    """La fetta riservata all'allenamento: stessi controlli di validita' del resto, perche'
    una scheda sbagliata mostrata in allenamento e' sbagliata uguale."""
    return get_all_players(exclude_ids=exclude_ids, practice_only=True)


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
    aliases = set(a.strip().lower() for a in player.get("aliases", []) if a and a.strip())
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


def _alias_index():
    """Indice alias normalizzato -> scheda, costruito una volta sola.

    Serve al confronto dopo un tentativo sbagliato (services/guess_feedback.py): li' non
    basta sapere che la risposta e' sbagliata, serve **quale** calciatore ha scritto
    l'utente. Gli alias ambigui sono gia' vietati da validate_dataset(), quindi la mappa
    non puo' avere due proprietari per la stessa chiave."""
    global _alias_index_cache
    if _alias_index_cache is None:
        index: dict[str, dict] = {}
        for player in _load_raw_players():
            for alias in get_answer_aliases(player):
                index.setdefault(normalize(alias), player)
        _alias_index_cache = index
    return _alias_index_cache


def find_player_by_answer(text):
    """La scheda del calciatore che l'utente ha scritto, None se non e' nel dataset.

    Cerca fra **tutte** le schede, anche quelle non verificate: qui non si sta scegliendo
    la sfida del giorno, si sta solo capendo di chi parla l'utente, e una scheda in attesa
    di revisione ha comunque nazionalita' e ruolo giusti (quello che si sbaglia sono le
    date della carriera).

    La tolleranza ai refusi e' la stessa delle risposte (services/matching.py): chi scrive
    "Ibrahimovich" merita il confronto come chi lo scrive giusto."""
    index = _alias_index()
    match = find_match(text, index.keys())
    if not match:
        return None
    return index.get(match["answer"])
