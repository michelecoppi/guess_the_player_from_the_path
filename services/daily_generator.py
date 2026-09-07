import logging
import random
from datetime import datetime, timedelta

from google.api_core.exceptions import GoogleAPICallError

from services import firebase_service
from services.dates import ITALY_TZ, to_iso
from services.difficulty import DIFFICULTY_ORDER, group_players_by_difficulty
from services.player_pool import get_all_players, get_answer_aliases, load_config


def pick_player_for_date(date_dt, recent_player_ids, rotation_index, blocked_ids=None):
    """Sceglie deterministicamente un giocatore per la data indicata, evitando ripetizioni
    recenti e ruotando la difficolta' target secondo 'difficulty_rotation' in config.json.

    'blocked_ids' sono i giocatori sospesi dall'admin (/admin_block): restano fuori anche
    quando il pool si esaurisce, perche' di solito sono sospesi per un dato sbagliato."""
    config = load_config()
    rotation = config.get("difficulty_rotation", DIFFICULTY_ORDER)
    target_difficulty = rotation[rotation_index % len(rotation)]

    blocked_ids = set(blocked_ids or [])
    players = [p for p in get_all_players() if p["id"] not in blocked_ids]
    available = [p for p in players if p["id"] not in recent_player_ids]
    if not available:
        # Se abbiamo esaurito il pool senza ripetizioni, si riparte accettando ripetizioni
        # (meglio di un errore/blocco della sfida giornaliera).
        available = players
        logging.warning("[GENERATOR] Pool di giocatori esaurito senza ripetizioni: riutilizzo pool completo")

    if not available:
        raise ValueError("Nessun giocatore valido disponibile nel dataset (data/players.json)")

    groups = group_players_by_difficulty(available)

    # Usa il gruppo della difficolta' target; se vuoto, prova le difficolta' vicine.
    ordered_candidates = [target_difficulty] + [d for d in rotation if d != target_difficulty]
    for difficulty in ordered_candidates:
        candidates = groups.get(difficulty, [])
        if candidates:
            # Selezione deterministica ma variata: seed sul giorno cosi' e' riproducibile
            # (utile per rigenerare la stessa scelta in caso di errore, requisito "recupero partita").
            rng = random.Random(date_dt.strftime("%Y-%m-%d"))
            return rng.choice(candidates), difficulty

    raise ValueError("Nessun giocatore disponibile per nessuna fascia di difficolta'")


def build_daily_path_doc(date_dt, recent_player_ids, rotation_index, blocked_ids=None):
    player, difficulty = pick_player_for_date(date_dt, recent_player_ids, rotation_index, blocked_ids)

    return {
        "player_id": player["id"],
        "correct_answers": get_answer_aliases(player),
        "difficulty": difficulty,
        "career_path": player["career"],
        "first_correct_user": False,
        "generated_at": datetime.now(ITALY_TZ),
        "source": "auto",
    }


def ensure_daily_buffer(days_ahead=None):
    """Genera in anticipo le sfide giornaliere mancanti per i prossimi N giorni, cosi' la
    sfida di oggi non dipende da un'esecuzione esatta a mezzanotte (requisito 'generare in
    anticipo i giocatori dei giorni successivi')."""
    config = load_config()
    days_ahead = days_ahead if days_ahead is not None else config.get("buffer_days_ahead", 3)
    history_days = config.get("history_days_no_repeat", 60)

    now_italy = datetime.now(ITALY_TZ)
    generated = []

    try:
        blocked_ids = firebase_service.get_blocked_player_ids()
    except GoogleAPICallError:
        # Un problema nel leggere gli override non deve impedire la generazione della sfida.
        logging.exception("[GENERATOR] Impossibile leggere i giocatori sospesi: procedo senza esclusioni")
        blocked_ids = []

    for offset in range(days_ahead):
        date_dt = now_italy + timedelta(days=offset)
        day_iso = to_iso(date_dt)

        if firebase_service.daily_path_exists(day_iso):
            continue

        recent_ids = set(firebase_service.get_recent_player_ids(history_days))
        # giorno dall'inizio dell'anno come indice di rotazione difficolta', stabile e deterministico
        rotation_index = date_dt.timetuple().tm_yday
        doc = build_daily_path_doc(date_dt, recent_ids, rotation_index, blocked_ids)
        firebase_service.save_daily_path(day_iso, doc)
        generated.append({"day": day_iso, "player_id": doc["player_id"], "difficulty": doc["difficulty"]})

    return generated
