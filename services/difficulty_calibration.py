"""Difficolta' prevista contro difficolta' osservata (#21).

`services/difficulty.py` **prevede** quanto e' difficile un giocatore guardando la scheda;
questo modulo guarda com'e' andata davvero ogni giornata e mette le due cose una accanto
all'altra. Serve a rispondere, con i numeri invece che a sensazione, a due domande:

1. **la formula ordina bene le giornate?** Una sfida prevista piu' difficile deve essere
   indovinata da meno persone e con piu' tentativi. Lo dice la correlazione di rango fra
   previsto e osservato, e la tabella per fascia (le fasce devono salire in ordine);
2. **dove sbaglia, sbaglia sempre allo stesso modo?** Uno scarto isolato e' rumore (un
   giocatore in tendenza quel giorno); uno scarto che si ripete su tutti i giocatori con
   8 squadre, o su tutti i ritirati da 15 anni, e' una taratura da rivedere.

La risposta non modifica niente da sola: la taratura resta in `data/config.json` e si cambia
dalla dashboard (Dataset -> Taratura difficolta'), guardando la ridistribuzione. Qui si
decide solo **se** e **dove** vale la pena toccarla. Procedura in docs/difficolta.md, sezione 6.

Le due scale non sono la stessa scala: il previsto e' un punteggio della formula, l'osservato
una misura di quanti hanno fallito e quanti tentativi sono serviti. Per questo lo scarto di
ogni giornata si calcola sui **percentili** (in che punto della classifica di difficolta' sta
la giornata secondo la formula, e in che punto secondo i giocatori), non sui valori grezzi.
"""
import math

from services import firebase_service
from services.daily_challenge import MAX_ATTEMPTS
from services.dates import shift_iso, today_iso
from services.difficulty import DIFFICULTY_ORDER, league_tier_weight, model_fingerprint, predict_difficulty
from services.player_pool import get_player_by_id, load_config

# Valori di ripiego: quelli veri stanno in data/config.json -> difficulty_calibration.
DEFAULT_SETTINGS = {
    # Sotto questo numero di partecipanti la giornata non entra nel confronto: con 4 giocatori
    # un solo errore vale il 25%.
    "min_players": 10,
    # Come si compone il punteggio osservato 0-100: quota di chi non ha indovinato e tentativi
    # medi di chi ha indovinato. Il fallimento pesa di piu' perche' e' il segnale piu' forte.
    "failure_weight": 0.7,
    "attempts_weight": 0.3,
    # Scarto (in punti percentile) oltre il quale una giornata e' "fuori previsione".
    "mismatch_tolerance": 25,
}

VERDICT_HARDER = "piu' difficile del previsto"
VERDICT_EASIER = "piu' facile del previsto"
VERDICT_IN_LINE = "in linea"

SOURCE_SNAPSHOT = "snapshot"
SOURCE_RECOMPUTED = "ricalcolata"


def calibration_settings(config=None):
    config = config or load_config()
    configured = config.get("difficulty_calibration", {})
    return {key: configured.get(key, default) for key, default in DEFAULT_SETTINGS.items()}


def observed_difficulty(doc, config=None, max_attempts=MAX_ATTEMPTS):
    """Com'e' andata una giornata, dai contatori sul documento `daily_path`.

    `score` e' 0-100 (100 = nessuno l'ha indovinata) oppure None quando i partecipanti sono
    troppo pochi per dire qualcosa. Le giornate precedenti ai contatori dei tentativi hanno
    solo la percentuale: il punteggio usa allora solo quella, e `avg_attempts` resta None."""
    settings = calibration_settings(config)
    players = int(doc.get("players_count") or 0)
    solved = min(int(doc.get("solved_count") or 0), players)
    has_attempts = solved > 0 and "solved_attempts_total" in doc
    avg_attempts = doc["solved_attempts_total"] / solved if has_attempts else None
    avg_hints = doc["solved_hints_total"] / solved if solved > 0 and "solved_hints_total" in doc else None

    result = {
        "players": players,
        "solved": solved,
        "completion_rate": round(100 * solved / players, 1) if players else None,
        "avg_attempts": round(avg_attempts, 2) if avg_attempts is not None else None,
        "avg_hints": round(avg_hints, 2) if avg_hints is not None else None,
        "enough_data": players >= settings["min_players"],
        "score": None,
    }
    if not result["enough_data"]:
        return result

    failure = 1 - solved / players
    failure_weight = float(settings["failure_weight"])
    attempts_weight = float(settings["attempts_weight"])
    if avg_attempts is None or max_attempts <= 1 or failure_weight + attempts_weight <= 0:
        score = failure
    else:
        extra_attempts = min(max((avg_attempts - 1) / (max_attempts - 1), 0.0), 1.0)
        score = (failure_weight * failure + attempts_weight * extra_attempts) / (failure_weight + attempts_weight)
    result["score"] = round(100 * score, 1)
    return result


def predicted_difficulty(doc, config=None, player=None):
    """La previsione di una giornata: quella fotografata alla generazione se c'e', altrimenti
    ricalcolata dalla scheda di oggi (e marcata come tale, perche' non e' la stessa cosa)."""
    snapshot = doc.get("difficulty_prediction")
    if isinstance(snapshot, dict) and snapshot.get("score") is not None:
        return {
            "score": float(snapshot["score"]),
            "band": snapshot.get("band"),
            "model": snapshot.get("model"),
            "source": SOURCE_SNAPSHOT,
        }
    if player is None:
        return None
    prediction = predict_difficulty(player, config=config)
    return {
        "score": prediction["score"],
        "band": prediction["band"],
        "model": prediction["model"],
        "source": SOURCE_RECOMPUTED,
    }


# ---------------------------------------------------------------------------
# Segnali: le dimensioni su cui si cercano scarti ricorrenti
# ---------------------------------------------------------------------------

def _signal_groups(player, day_iso, config):
    """In che gruppo cade la giornata per ogni dimensione valutata da #21.

    Alcune dimensioni sono gia' nella formula (notorieta', campionati, squadre, paesi), altre
    no (durata e distanza nel tempo della carriera): guardare lo scarto medio per gruppo dice
    sia se un peso esistente e' tarato male sia se una dimensione assente meriterebbe di
    entrare. Tutte si calcolano dalla sola scheda e dalla data, mai dal resto del dataset."""
    career = player.get("career") or []
    day_year = int(day_iso[:4])
    top = set(config.get("top_leagues", []))
    known = set(config.get("known_leagues", []))
    teams = len(career)
    countries = len({stop.get("country") for stop in career if stop.get("country")})
    obscurity = (
        sum(league_tier_weight(stop.get("league"), top, known) for stop in career) / teams if teams else 0.0
    )
    start = min((stop.get("start_year") for stop in career if stop.get("start_year")), default=None)
    # In attivita' = l'ultima tappa non ha fine (un prestito a meta' carriera senza fine e' un
    # buco nel dato, non una carriera aperta). Per chi gioca ancora la carriera "finisce" il
    # giorno della sfida.
    active = bool(career) and not career[-1].get("end_year")
    end = day_year if active else max((stop.get("end_year") or 0 for stop in career), default=day_year)
    length = (end - start) if start else None
    since_end = day_year - end

    def bucket(value, edges, labels):
        for edge, label in zip(edges, labels):
            if value <= edge:
                return label
        return labels[-1]

    return {
        "notorietà": str(player.get("popularity", "?")),
        "squadre": bucket(teams, (3, 5, 7), ("2-3", "4-5", "6-7", "8+")),
        "paesi": bucket(countries, (1, 2, 3), ("1", "2", "3", "4+")),
        "campionati": "solo top 5" if obscurity == 0 else ("misti (≤ 0.5)" if obscurity <= 0.5 else "poco noti (> 0.5)"),
        "durata carriera": "?" if length is None else bucket(length, (8, 14), ("≤ 8 anni", "9-14 anni", "15+ anni")),
        "fine carriera": "in attività" if active else bucket(since_end, (5, 15), ("≤ 5 anni fa", "6-15 anni fa", "> 15 anni fa")),
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _average_ranks(values):
    """Ranghi 1..n, con la media dei ranghi per i valori uguali (come la Spearman standard)."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        rank = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = rank
        i = j + 1
    return ranks


def spearman(xs, ys):
    """Correlazione di rango fra -1 e 1, None se non calcolabile (meno di 3 punti o valori tutti uguali)."""
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    rx, ry = _average_ranks(xs), _average_ranks(ys)
    mean_x, mean_y = sum(rx) / len(rx), sum(ry) / len(ry)
    cov = sum((a - mean_x) * (b - mean_y) for a, b in zip(rx, ry))
    var_x = sum((a - mean_x) ** 2 for a in rx)
    var_y = sum((b - mean_y) ** 2 for b in ry)
    if var_x == 0 or var_y == 0:
        return None
    return round(cov / math.sqrt(var_x * var_y), 3)


def _percentiles(values):
    if len(values) == 1:
        return [50.0]
    return [100 * (rank - 1) / (len(values) - 1) for rank in _average_ranks(values)]


def _mean(values):
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 2) if values else None


def build_report(docs, config=None, player_lookup=get_player_by_id):
    """Il confronto su un insieme di giornate gia' chiuse (documenti `daily_path`)."""
    config = config or load_config()
    settings = calibration_settings(config)
    tolerance = float(settings["mismatch_tolerance"])

    rows = []
    for doc in sorted(docs, key=lambda d: d.get("day", "")):
        day = doc.get("day")
        if not day:
            continue
        player = player_lookup(doc.get("player_id")) if doc.get("player_id") else None
        rows.append({
            "day": day,
            "player_id": doc.get("player_id"),
            "player_name": (player or {}).get("full_name"),
            "played_band": doc.get("difficulty"),
            "predicted": predicted_difficulty(doc, config=config, player=player),
            "observed": observed_difficulty(doc, config=config),
            "signals": _signal_groups(player, day, config) if player else {},
            "predicted_pct": None,
            "observed_pct": None,
            "delta": None,
            "verdict": None,
        })

    comparable = [row for row in rows if row["predicted"] and row["observed"]["score"] is not None]
    predicted_scores = [row["predicted"]["score"] for row in comparable]
    observed_scores = [row["observed"]["score"] for row in comparable]
    for row, predicted_pct, observed_pct in zip(
        comparable, _percentiles(predicted_scores), _percentiles(observed_scores)
    ):
        delta = round(observed_pct - predicted_pct, 1)
        row.update({
            "predicted_pct": round(predicted_pct, 1),
            "observed_pct": round(observed_pct, 1),
            "delta": delta,
            "verdict": VERDICT_HARDER if delta >= tolerance else VERDICT_EASIER if delta <= -tolerance else VERDICT_IN_LINE,
        })

    by_band = []
    for band in DIFFICULTY_ORDER:
        in_band = [row for row in comparable if row["predicted"]["band"] == band]
        by_band.append({
            "band": band,
            "days": len(in_band),
            "completion_rate": _mean([row["observed"]["completion_rate"] for row in in_band]),
            "avg_attempts": _mean([row["observed"]["avg_attempts"] for row in in_band]),
            "observed_score": _mean([row["observed"]["score"] for row in in_band]),
        })
    band_scores = [entry["observed_score"] for entry in by_band if entry["observed_score"] is not None]
    bands_in_order = all(a <= b for a, b in zip(band_scores, band_scores[1:])) if len(band_scores) > 1 else None

    by_signal: dict[str, dict[str, list]] = {}
    for row in comparable:
        for signal, group in row["signals"].items():
            by_signal.setdefault(signal, {}).setdefault(group, []).append(row["delta"])
    by_signal_rows = {
        signal: sorted(
            ({"group": group, "days": len(deltas), "avg_delta": _mean(deltas)} for group, deltas in groups.items()),
            key=lambda entry: entry["group"],
        )
        for signal, groups in by_signal.items()
    }

    models: dict[str, int] = {}
    for row in rows:
        if row["predicted"]:
            key = row["predicted"]["model"] or "?"
            models[key] = models.get(key, 0) + 1

    return {
        "settings": settings,
        "current_model": model_fingerprint(config),
        "models": models,
        "days": len(rows),
        "comparable_days": len(comparable),
        "snapshot_days": sum(1 for row in rows if row["predicted"] and row["predicted"]["source"] == SOURCE_SNAPSHOT),
        "spearman": spearman(predicted_scores, observed_scores),
        "by_band": by_band,
        "bands_in_order": bands_in_order,
        "by_signal": by_signal_rows,
        "mismatches": sorted(
            (row for row in comparable if row["verdict"] != VERDICT_IN_LINE),
            key=lambda row: (-abs(row["delta"]), row["day"]),
        ),
        "rows": rows,
    }


def load_report(days, today=None):
    """Il report sulle ultime `days` giornate chiuse (oggi escluso: e' ancora in corso)."""
    today = today or today_iso()
    docs = firebase_service.get_daily_paths_range(shift_iso(today, -days), shift_iso(today, -1), limit=days)
    return build_report(docs)
