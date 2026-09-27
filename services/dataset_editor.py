"""Modifiche al dataset locale (`data/players.json`) e alla taratura (`data/config.json`).

E' il livello che sta sotto la sezione *Dataset* della dashboard (`admin_ui.py`), come
`services/content_admin.py` lo e' per sfide ed eventi: la dashboard mostra la tabella e
raccoglie le modifiche, qui ci sono le regole.

Serve perche' correggere una difficolta' che non convince **non** vuol dire scrivere la
difficolta' da qualche parte: la difficolta' e' calcolata (vedi `docs/difficolta.md`), e le
leve vere sono tre, in quest'ordine:

1. la **notorieta'** (`popularity` 1-5) della scheda: e' il caso di gran lunga piu' frequente;
2. il **campionato** di una tappa scritto male, che pesa 1.0 invece di 0.5;
3. la **taratura globale** (pesi e soglie), da toccare solo guardando l'intero dataset.

Le prime due si correggono giocatore per giocatore con `apply_player_changes`, la terza con
`update_difficulty_settings`. In tutti i casi:

- si scrive **una copia di sicurezza** in `backup/` prima di toccare il file;
- si rifiuta la modifica se introduce un problema nuovo nel dataset (alias ambiguo,
  notorieta' fuori scala, tappa incoerente), confrontando i problemi prima e dopo invece di
  pretendere un dataset gia' perfetto;
- il file viene riscritto in modo atomico e con lo stesso formato di
  `scripts/import_players.py` (indent 2, niente escape unicode), cosi' il diff in git
  contiene solo le righe cambiate davvero;
- le cache in memoria di `services/player_pool.py` vengono svuotate, altrimenti il bot e la
  dashboard continuerebbero a vedere i valori vecchi.

Le funzioni che modificano qualcosa alzano `DatasetEditError` con un messaggio gia'
leggibile: la dashboard lo mostra cosi' com'e'.
"""
import json
import os
import shutil
import tempfile
from datetime import datetime

from services.difficulty import DIFFICULTY_ORDER, compute_difficulty, explain_difficulty, league_tier_weight
from services.player_pool import (
    _CONFIG_PATH,
    _PLAYERS_PATH,
    _load_raw_players,
    load_config,
    reload_dataset,
    validate_dataset,
    validate_player,
)

BACKUP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backup")

POPULARITY_VALUES = (1, 2, 3, 4, 5)

# I campi che la dashboard puo' cambiare. Sono pochi di proposito: sono le leve della
# difficolta' piu' i due interruttori che decidono se una scheda entra in gioco
# (`verified`) e in quale meta' del dataset (`practice_only`). Nome, alias e carriera si
# scrivono nel file o si importano con scripts/import_players.py, dove un errore si vede.
EDITABLE_FIELDS = ("popularity", "verified", "practice_only", "one_club_career")

FLAG_FIELDS = ("verified", "practice_only", "one_club_career")

# Questi due valgono "false" quando mancano e nel dataset le schede normali non li hanno:
# toglierli invece di scrivere false tiene il file leggibile e il diff piccolo. `verified`
# no: sta scritto in tutte le schede, ed e' l'unico modo per distinguere "rivista e
# bocciata" da "mai guardata".
REMOVABLE_FLAGS = ("practice_only", "one_club_career")

CONFIG_WEIGHT_KEYS = ("popularity", "minor_leagues", "extra_countries", "extra_teams")
CONFIG_THRESHOLD_KEYS = ("easy", "medium", "hard")

# Stato di una scheda rispetto alla selezione automatica, in ordine di precedenza: e' la
# colonna che spiega perche' un giocatore non esce mai come sfida del giorno.
STATUS_SELECTABLE = "selezionabile"
STATUS_PRACTICE = "solo allenamento"
STATUS_BLOCKED = "sospeso"
STATUS_UNVERIFIED = "non verificato"
STATUS_INCOMPLETE = "dati incompleti"


class DatasetEditError(Exception):
    """Errore previsto (valore non valido o modifica che romperebbe il dataset)."""


# ---------------------------------------------------------------------------
# Lettura
# ---------------------------------------------------------------------------

def player_status(player, problems, blocked_ids=()):
    if problems:
        return STATUS_INCOMPLETE
    if not player.get("verified"):
        return STATUS_UNVERIFIED
    if player.get("id") in blocked_ids:
        return STATUS_BLOCKED
    if player.get("practice_only"):
        return STATUS_PRACTICE
    return STATUS_SELECTABLE


def list_players(blocked_ids=(), config=None):
    """Tutte le schede del dataset con difficolta', punteggio scomposto e stato.

    Volutamente **tutte**, non solo quelle selezionabili: chi cerca la scheda che non
    convince non sa in anticipo se e' finita fuori dalla selezione, e la riga che dice
    "non verificato" o "dati incompleti" e' meta' della risposta.
    """
    blocked_ids = set(blocked_ids or ())
    min_teams = load_config().get("min_teams_in_career", 2)
    rows = []
    for player in _load_raw_players():
        problems = validate_player(player, min_teams=min_teams)
        explained = explain_difficulty(player, config=config)
        career = player.get("career", [])
        rows.append({
            "id": player.get("id"),
            "full_name": player.get("full_name"),
            "difficulty": explained["difficulty"] if career else None,
            "score": round(explained["score"], 2) if career else None,
            "from_popularity": round(explained["components"]["popularity"], 2),
            "from_path": round(explained["score"] - explained["components"]["popularity"], 2),
            "popularity": player.get("popularity"),
            "verified": bool(player.get("verified")),
            "practice_only": bool(player.get("practice_only")),
            "one_club_career": bool(player.get("one_club_career")),
            "teams": len(career),
            "countries": explained["countries"],
            "nationality": player.get("nationality"),
            "birth_year": player.get("birth_year"),
            "status": player_status(player, problems, blocked_ids),
            "problems": problems,
        })
    return rows


def career_with_weights(player, config=None):
    """Le tappe con il peso che ognuna porta al punteggio.

    E' la seconda causa di una difficolta' sbagliata (`docs/difficolta.md`, sezione 5): un
    campionato scritto in un modo che non e' in lista pesa 1.0 invece di 0.5, e nella
    tabella si vede subito quale tappa e'.
    """
    config = config or load_config()
    top_leagues = set(config.get("top_leagues", []))
    known_leagues = set(config.get("known_leagues", []))
    rows = []
    for index, stop in enumerate(player.get("career", [])):
        weight = league_tier_weight(stop.get("league"), top_leagues, known_leagues)
        rows.append({
            "index": index,
            "team": stop.get("team"),
            "country": stop.get("country"),
            "league": stop.get("league"),
            "start_year": stop.get("start_year"),
            "end_year": stop.get("end_year"),
            "weight": weight,
            "tier": "top" if weight == 0.0 else ("noto" if weight == 0.5 else "oscuro"),
        })
    return rows


def known_league_names(config=None):
    """I nomi di campionato accettabili: le due liste di config piu' quelli gia' in uso.

    Quelli gia' nel dataset ci sono perche' un campionato fuori lista non e' per forza un
    errore (la J1 League pesa 1.0 di proposito): serve poterlo riscegliere senza ribattere
    il nome, che e' il modo in cui nascono i refusi.
    """
    config = config or load_config()
    names = set(config.get("top_leagues", [])) | set(config.get("known_leagues", []))
    for player in _load_raw_players():
        for stop in player.get("career", []):
            if stop.get("league"):
                names.add(stop["league"])
    return sorted(names)


def difficulty_settings(config=None):
    config = config or load_config()
    thresholds = config.get("difficulty_thresholds", {"easy": 5, "medium": 9, "hard": 13})
    weights = config.get("difficulty_weights", {})
    defaults = dict(zip(CONFIG_WEIGHT_KEYS, (4.0, 3.0, 0.5, 0.2)))
    return {
        "thresholds": {key: float(thresholds.get(key, default))
                       for key, default in zip(CONFIG_THRESHOLD_KEYS, (5, 9, 13))},
        "weights": {key: float(weights.get(key, defaults[key])) for key in CONFIG_WEIGHT_KEYS},
    }


# ---------------------------------------------------------------------------
# Modifica delle schede
# ---------------------------------------------------------------------------

def _normalize_field(field, value):
    if field == "popularity":
        try:
            value = int(value)
        except (TypeError, ValueError):
            raise DatasetEditError(f"Notorieta' non valida ({value!r}): serve un intero da 1 a 5.")
        if value not in POPULARITY_VALUES:
            raise DatasetEditError(f"Notorieta' non valida ({value}): serve un intero da 1 a 5.")
        return value
    if field in FLAG_FIELDS:
        return bool(value)
    raise DatasetEditError(f"Campo non modificabile da qui: '{field}'.")


def _apply_to_player(player, fields, career_leagues=None):
    """Scrive i campi sulla scheda (copia) e ritorna l'elenco delle modifiche fatte."""
    changes = []
    for field, raw_value in fields.items():
        value = _normalize_field(field, raw_value)
        if field in FLAG_FIELDS:
            before = bool(player.get(field))
            if before == value:
                continue
            if not value and field in REMOVABLE_FLAGS:
                player.pop(field, None)
            else:
                player[field] = value
        else:
            before = player.get(field)
            if before == value:
                continue
            player[field] = value
        changes.append({"id": player.get("id"), "field": field, "before": before, "after": value})

    for index, league in (career_leagues or {}).items():
        career = player.get("career", [])
        if not 0 <= index < len(career):
            raise DatasetEditError(f"{player.get('id')}: tappa numero {index + 1} inesistente.")
        league = str(league).strip()
        if not league:
            raise DatasetEditError(f"{player.get('id')}: il campionato della tappa {index + 1} non puo' essere vuoto.")
        before = career[index].get("league")
        if before == league:
            continue
        career[index]["league"] = league
        changes.append({
            "id": player.get("id"),
            "field": f"career[{index + 1}].league",
            "before": before,
            "after": league,
        })
    return changes


def preview_player_changes(changes, career_changes=None):
    """Cosa succederebbe salvando: le modifiche riga per riga e i cambi di fascia.

    Si chiama prima di `apply_player_changes` per mostrare l'effetto (una notorieta' alzata
    di uno **di solito** sposta la fascia, ma non sempre: dipende dal percorso) senza
    scrivere niente.
    """
    players, detail = _players_with_changes(changes, career_changes)
    after_by_id = {player.get("id"): player for player in players}
    before_by_id = {player.get("id"): player for player in _load_raw_players()}

    moves = []
    for player_id in sorted({item["id"] for item in detail}):
        before, after = before_by_id.get(player_id), after_by_id.get(player_id)
        if not before or not after or not after.get("career"):
            continue
        before_bucket, after_bucket = compute_difficulty(before), compute_difficulty(after)
        if before_bucket != after_bucket:
            moves.append({
                "id": player_id,
                "full_name": after.get("full_name"),
                "before": before_bucket,
                "after": after_bucket,
            })
    return {"changes": detail, "moves": moves}


def _players_with_changes(changes, career_changes=None):
    """Copia del dataset con le modifiche applicate, piu' l'elenco di cosa e' cambiato."""
    changes = changes or {}
    career_changes = career_changes or {}
    unknown = (set(changes) | set(career_changes)) - {p.get("id") for p in _load_raw_players()}
    if unknown:
        raise DatasetEditError(f"Id non presenti nel dataset: {', '.join(sorted(unknown))}.")

    players = json.loads(json.dumps(_load_raw_players()))
    applied = []
    for player in players:
        player_id = player.get("id")
        fields = changes.get(player_id) or {}
        careers = career_changes.get(player_id) or {}
        if fields or careers:
            applied.extend(_apply_to_player(player, fields, careers))
    return players, applied


def _new_problems(before_players, after_players):
    """I problemi introdotti dalla modifica, ignorando quelli che c'erano gia'.

    Il dataset contiene per costruzione schede imperfette (in attesa di verifica, o
    incomplete): pretendere zero problemi bloccherebbe qualunque correzione. Quello che va
    impedito e' **peggiorare**.
    """
    before = set(validate_dataset(before_players))
    return [problem for problem in validate_dataset(after_players) if problem not in before]


def _backup(path, prefix):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    destination = os.path.join(BACKUP_DIR, f"{prefix}-{stamp}.json")
    shutil.copy2(path, destination)
    return destination


def _write_json(path, payload):
    """Riscrittura atomica: o c'e' il file nuovo o c'e' quello vecchio, mai mezzo file.

    Stesso formato di scripts/import_players.py, cosi' i due modi di modificare il dataset
    non si rincorrono a vicenda con diff di formattazione.
    """
    directory = os.path.dirname(path)
    handle, temp_path = tempfile.mkstemp(dir=directory, prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(temp_path, path)
    except BaseException:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise


def apply_player_changes(changes, career_changes=None):
    """Salva le modifiche alle schede in data/players.json.

    `changes`: {id_giocatore: {campo: valore}} con i campi di EDITABLE_FIELDS.
    `career_changes`: {id_giocatore: {indice_tappa: nome_campionato}}.
    """
    before_players = _load_raw_players()
    players, applied = _players_with_changes(changes, career_changes)
    if not applied:
        raise DatasetEditError("Nessuna modifica da salvare.")

    problems = _new_problems(before_players, players)
    if problems:
        raise DatasetEditError(
            "La modifica renderebbe il dataset incoerente, non l'ho salvata:\n\n- "
            + "\n- ".join(problems)
        )

    with open(_PLAYERS_PATH, "r", encoding="utf-8") as f:
        dataset = json.load(f)
    dataset["players"] = players

    backup_path = _backup(_PLAYERS_PATH, "players")
    _write_json(_PLAYERS_PATH, dataset)
    reload_dataset()
    return {"changes": applied, "backup": backup_path}


# ---------------------------------------------------------------------------
# Taratura globale
# ---------------------------------------------------------------------------

def _tidy_number(value):
    """5.0 torna 5: in data/config.json le soglie sono scritte come interi e devono
    restare tali, altrimenti ogni salvataggio produce un diff finto."""
    value = float(value)
    return int(value) if value.is_integer() else round(value, 3)


def _validated_settings(thresholds, weights):
    try:
        thresholds = {key: _tidy_number(thresholds[key]) for key in CONFIG_THRESHOLD_KEYS}
        weights = {key: _tidy_number(weights[key]) for key in CONFIG_WEIGHT_KEYS}
    except (KeyError, TypeError, ValueError) as e:
        raise DatasetEditError(f"Taratura incompleta o non numerica: {e}")

    if not thresholds["easy"] < thresholds["medium"] < thresholds["hard"]:
        raise DatasetEditError(
            "Le soglie devono crescere: easy < medium < hard "
            f"(ricevute {thresholds['easy']}, {thresholds['medium']}, {thresholds['hard']})."
        )
    if thresholds["easy"] <= 0:
        raise DatasetEditError("La soglia 'easy' deve essere maggiore di zero, altrimenti nessuno e' facile.")
    negative = [key for key, value in weights.items() if value < 0]
    if negative:
        raise DatasetEditError(f"I pesi non possono essere negativi: {', '.join(negative)}.")
    return thresholds, weights


def preview_difficulty_settings(thresholds, weights, blocked_ids=()):
    """Distribuzione delle fasce con la taratura proposta, senza salvarla.

    E' la richiesta esplicita di docs/difficolta.md: le soglie non si spostano per
    sistemare un giocatore, si spostano guardando come si ridistribuisce tutto il dataset.
    """
    thresholds, weights = _validated_settings(thresholds, weights)
    config = dict(load_config())
    config["difficulty_thresholds"] = thresholds
    config["difficulty_weights"] = weights

    blocked_ids = set(blocked_ids or ())
    by_id = {player.get("id"): player for player in _load_raw_players()}
    before_counts = {level: 0 for level in DIFFICULTY_ORDER}
    after_counts = {level: 0 for level in DIFFICULTY_ORDER}
    moves = []
    for row in list_players(blocked_ids=blocked_ids):
        if row["status"] != STATUS_SELECTABLE:
            continue
        player = by_id[row["id"]]
        before = compute_difficulty(player)
        after = compute_difficulty(player, config=config)
        before_counts[before] += 1
        after_counts[after] += 1
        if before != after:
            moves.append({
                "id": row["id"],
                "full_name": row["full_name"],
                "before": before,
                "after": after,
                "score": row["score"],
            })
    return {
        "before": before_counts,
        "after": after_counts,
        "moves": sorted(moves, key=lambda m: (m["after"], m["id"])),
    }


def update_difficulty_settings(thresholds, weights):
    """Salva pesi e soglie in data/config.json (il resto della config resta com'e')."""
    thresholds, weights = _validated_settings(thresholds, weights)
    current = difficulty_settings()
    unchanged = all(current["thresholds"][key] == thresholds[key] for key in CONFIG_THRESHOLD_KEYS)
    unchanged = unchanged and all(current["weights"][key] == weights[key] for key in CONFIG_WEIGHT_KEYS)
    if unchanged:
        raise DatasetEditError("Nessuna modifica da salvare.")

    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)
    config["difficulty_thresholds"] = thresholds
    config["difficulty_weights"] = weights

    backup_path = _backup(_CONFIG_PATH, "config")
    _write_json(_CONFIG_PATH, config)
    reload_dataset()
    return {"thresholds": thresholds, "weights": weights, "backup": backup_path}
