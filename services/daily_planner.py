"""Il planner delle sfide giornaliere (#30): un calendario di 30-90 giorni in un colpo solo.

Prima c'era solo un buffer di pochi giorni (`buffer_days_ahead`) riempito dal job notturno
con un'unica regola, "nessun giocatore ripetuto negli ultimi 60 giorni". Il resto - due
brasiliani di fila, tre giocatori dell'Inter in quattro giorni, una settimana di sole sfide
facili perche' una fascia si era svuotata - lo notava (se lo notava) chi guardava la
dashboard. Qui le regole sono scritte, configurabili e uguali per tutti i punti che creano
una sfida:

- il job notturno e `get_today_challenge` (tramite `daily_generator.ensure_daily_buffer`);
- il bottone "Rigenera" su un giorno (`content_admin.regenerate_daily`);
- il planner della dashboard, che propone un calendario, lo fa rivedere e poi lo scrive.

Le regole, in ordine di importanza:

1. **eleggibilita'**: solo schede selezionabili (`player_pool.get_all_players`: verificate,
   complete, non riservate all'allenamento), non sospese (`/admin_block`) e non escluse dal
   planner (`admin_settings/daily_planner`, con motivo e scadenza facoltativa);
2. **nessun giocatore ripetuto** entro `history_days_no_repeat` giorni, prima **e dopo** il
   giorno (i giorni futuri gia' fissati contano quanto il passato);
3. **fascia di difficolta'** dalla rotazione `difficulty_rotation` (#21), senza superare
   `max_same_band_streak` giorni consecutivi nella stessa fascia;
4. **diversita'**: nessun club in comune entro `club_cooldown_days` e nessuna nazionalita'
   ripetuta entro `nationality_cooldown_days`.

Quando le regole non si possono rispettare tutte insieme (pool piccolo, esclusioni) il
planner non si ferma: allenta nell'ordine inverso (prima nazionalita' e club, poi la fascia,
poi la serie di fasce, per ultimo la ripetizione del giocatore) e **scrive cosa ha
allentato** nell'audit del giorno. Un calendario sempre pieno vale piu' di una regola
perfetta, ma nessun compromesso resta invisibile.

La scelta e' deterministica: stesso stato, stessa data e stessa `variant` danno lo stesso
giocatore. "Rigenera" cambia la `variant`, non il caso.
"""
import logging
import random
import re
from datetime import datetime

from google.api_core.exceptions import GoogleAPICallError

from services import firebase_service
from services.dates import ITALY_TZ, normalize_day, parse_iso, shift_iso, today_iso
from services.difficulty import DIFFICULTY_ORDER, compute_difficulty, predict_difficulty
from services.player_pool import get_all_players, get_answer_aliases, get_player_by_id, load_config

MAX_HORIZON_DAYS = 90

# Valori di ripiego: quelli veri stanno in data/config.json -> daily_planner.
DEFAULT_SETTINGS = {
    "horizon_days": 30,
    "club_cooldown_days": 3,
    "nationality_cooldown_days": 3,
    "max_same_band_streak": 2,
}

MODE_FILL = "fill"        # riempie solo i giorni senza sfida
MODE_REPLAN = "replan"    # ripianifica anche i giorni futuri non bloccati e non scelti a mano

ACTION_CREATE = "crea"
ACTION_REPLACE = "sostituisce"
ACTION_KEEP = "resta"

KEEP_LOCKED = "bloccata"
KEEP_MANUAL = "scelta a mano"
KEEP_IN_PLAY = "in gioco o passata"
KEEP_EXISTING = "gia' programmata"

RELAX_NATIONALITY = "nazionalita'"
RELAX_CLUB = "club"
RELAX_BAND = "fascia"
RELAX_STREAK = "serie di fasce"
RELAX_PLAYER = "ripetizione giocatore"

SOURCE_AUTO = "auto"
SOURCE_PLANNER = "planner"

_PLAYER_ID = re.compile(r"^[a-z0-9_]+$")


class PlannerError(Exception):
    """Errore previsto (nessun giocatore disponibile, parametri non validi): messaggio leggibile."""


def planner_settings(config=None):
    config = config or load_config()
    configured = config.get("daily_planner", {})
    settings: dict = {key: int(configured.get(key, default)) for key, default in DEFAULT_SETTINGS.items()}
    settings["player_cooldown_days"] = int(config.get("history_days_no_repeat", 60))
    settings["rotation"] = list(config.get("difficulty_rotation", DIFFICULTY_ORDER))
    return settings


def target_band(day_iso, config=None):
    """La fascia che la rotazione assegna a un giorno: stabile, dipende solo dalla data."""
    rotation = planner_settings(config)["rotation"]
    return rotation[parse_iso(day_iso).timetuple().tm_yday % len(rotation)]


def _days_between(a, b):
    return abs((parse_iso(a) - parse_iso(b)).days)


# ---------------------------------------------------------------------------
# Esclusioni
# ---------------------------------------------------------------------------

def exclusion_active(exclusion, day_iso):
    """Un'esclusione senza scadenza vale sempre; con scadenza vale fino a quel giorno compreso."""
    until = (exclusion or {}).get("until")
    return not until or day_iso <= until


def load_exclusions():
    """Le esclusioni del planner. Un errore di lettura non deve fermare la sfida del giorno."""
    try:
        return firebase_service.get_planner_exclusions()
    except GoogleAPICallError:
        logging.exception("[PLANNER] Esclusioni non leggibili: procedo senza")
        return {}


def exclude_player(player_id, reason="", until=None):
    player_id = (player_id or "").strip().lower()
    if not _PLAYER_ID.match(player_id) or not get_player_by_id(player_id):
        raise PlannerError(f"Nessun giocatore con id '{player_id}' nel dataset.")
    until = normalize_day(until) if until else None
    if until:
        try:
            parse_iso(until)
        except (TypeError, ValueError):
            raise PlannerError(f"Scadenza '{until}' non valida: serve il formato YYYY-MM-DD.")
    firebase_service.set_planner_exclusion(player_id, {
        "reason": (reason or "").strip(),
        "until": until,
        "excluded_at": datetime.now(ITALY_TZ),
    })
    return player_id


def include_player(player_id):
    player_id = (player_id or "").strip().lower()
    if not _PLAYER_ID.match(player_id):
        raise PlannerError(f"Id '{player_id}' non valido.")
    firebase_service.remove_planner_exclusion(player_id)
    return player_id


# ---------------------------------------------------------------------------
# Pool e contesto
# ---------------------------------------------------------------------------

def _clubs(career):
    return {stop.get("team") for stop in (career or []) if stop.get("team")}


def build_pool(blocked_ids=(), players=None):
    """I candidati, con fascia, club e nazionalita' calcolati una volta sola."""
    blocked = set(blocked_ids or ())
    players = get_all_players(exclude_ids=list(blocked)) if players is None else players
    return [
        {
            "player": player,
            "id": player["id"],
            "band": compute_difficulty(player),
            "clubs": _clubs(player.get("career")),
            "nationality": player.get("nationality"),
        }
        for player in sorted(players, key=lambda p: p["id"])
        if player["id"] not in blocked
    ]


def _entry_from_doc(doc):
    player = get_player_by_id(doc.get("player_id")) if doc.get("player_id") else None
    return {
        "day": normalize_day(doc.get("day")),
        "player_id": doc.get("player_id"),
        "band": doc.get("difficulty"),
        "clubs": _clubs(doc.get("career_path")),
        "nationality": (player or {}).get("nationality"),
    }


def _entry_from_candidate(day_iso, candidate):
    return {
        "day": day_iso,
        "player_id": candidate["id"],
        "band": candidate["band"],
        "clubs": candidate["clubs"],
        "nationality": candidate["nationality"],
    }


def _streak_allows(day_iso, band, assigned, max_streak):
    """Quanti giorni consecutivi nella stessa fascia si avrebbero mettendo `band` in `day_iso`,
    contando i giorni gia' assegnati prima e dopo."""
    length = 1
    for direction in (-1, 1):
        cursor = shift_iso(day_iso, direction)
        while cursor in assigned and assigned[cursor]["band"] == band:
            length += 1
            cursor = shift_iso(cursor, direction)
    return length <= max_streak


def choose_for_day(day_iso, assigned, pool, exclusions=None, config=None, variant=0, avoid_ids=()):
    """Il giocatore per un giorno, dato cio' che e' gia' assegnato intorno.

    `assigned` e' {giorno: voce} per tutti i giorni gia' decisi (passati, futuri fissati, e
    quelli appena pianificati); il giorno stesso non deve esserci. Ritorna (candidato, audit)."""
    settings = planner_settings(config)
    exclusions = exclusions or {}
    avoid = set(avoid_ids or ())

    eligible = [
        c for c in pool
        if c["id"] not in avoid and not (c["id"] in exclusions and exclusion_active(exclusions[c["id"]], day_iso))
    ]
    if not eligible:
        raise PlannerError(
            f"Nessun giocatore disponibile per il {day_iso}: il pool e' vuoto dopo sospensioni ed esclusioni."
        )

    def near(days):
        return [e for d, e in assigned.items() if d != day_iso and _days_between(d, day_iso) <= days]

    recent_players = {e["player_id"] for e in near(settings["player_cooldown_days"])}
    used_anywhere = {e["player_id"] for d, e in assigned.items() if d != day_iso}
    recent_clubs = set().union(*(e["clubs"] for e in near(settings["club_cooldown_days"])))
    recent_nationalities = {e["nationality"] for e in near(settings["nationality_cooldown_days"]) if e["nationality"]}

    after_player = [c for c in eligible if c["id"] not in recent_players]
    after_club = [c for c in after_player if not (c["clubs"] & recent_clubs)]
    after_nationality = [c for c in after_club if c["nationality"] not in recent_nationalities]

    target = target_band(day_iso, config)
    rotation = settings["rotation"]
    start = rotation.index(target) if target in rotation else 0
    # Le altre fasce nell'ordine della rotazione a partire dalla target: con la rotazione
    # standard, dopo 'hard' si prova 'impossible', poi 'easy', poi 'medium'.
    others = [rotation[(start + i) % len(rotation)] for i in range(1, len(rotation))]
    # Poi le fasce fuori dalla rotazione: meglio una fascia inattesa che un buco nel calendario.
    others = list(dict.fromkeys(b for b in others + DIFFICULTY_ORDER if b != target))

    stages = [
        (after_nationality, [target], ()),
        (after_club, [target], (RELAX_NATIONALITY,)),
        (after_player, [target], (RELAX_NATIONALITY, RELAX_CLUB)),
        (after_nationality, others, (RELAX_BAND,)),
        (after_club, others, (RELAX_BAND, RELAX_NATIONALITY)),
        (after_player, others, (RELAX_BAND, RELAX_NATIONALITY, RELAX_CLUB)),
        (after_player, [target] + others, (RELAX_BAND, RELAX_NATIONALITY, RELAX_CLUB, RELAX_STREAK)),
        (eligible, [target] + others, (RELAX_BAND, RELAX_NATIONALITY, RELAX_CLUB, RELAX_STREAK, RELAX_PLAYER)),
    ]
    seed = f"{day_iso}|{variant}"
    for candidates, bands, relaxed in stages:
        for band in bands:
            if RELAX_STREAK not in relaxed and not _streak_allows(day_iso, band, assigned, settings["max_same_band_streak"]):
                continue
            in_band = [c for c in candidates if c["band"] == band]
            if not in_band:
                continue
            # Fra i candidati validi si preferisce chi non compare da nessuna parte nel contesto
            # letto: su un orizzonte di 90 giorni la sola distanza anti-ripetizione (60)
            # lascerebbe tornare un giocatore dentro lo stesso calendario.
            fresh = [c for c in in_band if c["id"] not in used_anywhere] or in_band
            chosen = random.Random(seed).choice(fresh)
            effective = [r for r in relaxed if r != RELAX_BAND or band != target]
            return chosen, {
                "target_band": target,
                "band": band,
                "relaxed": effective,
                "pool": len(pool),
                "eligible": len(eligible),
                "after_player_cooldown": len(after_player),
                "after_club": len(after_club),
                "after_nationality": len(after_nationality),
                "candidates": len(fresh),
                "variant": variant,
            }
    raise PlannerError(f"Nessun giocatore disponibile per il {day_iso}.")  # pragma: no cover - eligible non vuoto


# ---------------------------------------------------------------------------
# Il calendario
# ---------------------------------------------------------------------------

def build_plan(start_day, days, docs, pool, today, exclusions=None, config=None, mode=MODE_FILL, variants=None):
    """La proposta per `days` giorni da `start_day`, senza scrivere niente.

    `docs` sono i documenti `daily_path` gia' esistenti intorno alla finestra (anche prima e
    dopo: contano per le regole di distanza). `variants` e' {giorno: intero} per rigenerare
    un singolo giorno dell'anteprima senza toccare gli altri."""
    if mode not in (MODE_FILL, MODE_REPLAN):
        raise PlannerError(f"Modalita' '{mode}' sconosciuta.")
    if not 1 <= days <= MAX_HORIZON_DAYS:
        raise PlannerError(f"L'orizzonte va da 1 a {MAX_HORIZON_DAYS} giorni.")
    variants = variants or {}
    by_day = {normalize_day(doc.get("day")): doc for doc in docs if doc.get("day")}
    window = [shift_iso(start_day, i) for i in range(days)]

    decisions: dict[str, tuple[str, str | None]] = {}
    for day in window:
        doc = by_day.get(day)
        if not doc:
            decisions[day] = (ACTION_CREATE, None)
        elif doc.get("locked"):
            decisions[day] = (ACTION_KEEP, KEEP_LOCKED)
        elif day <= today:
            decisions[day] = (ACTION_KEEP, KEEP_IN_PLAY)
        elif mode == MODE_FILL:
            decisions[day] = (ACTION_KEEP, KEEP_EXISTING)
        elif doc.get("source") == "manual":
            decisions[day] = (ACTION_KEEP, KEEP_MANUAL)
        else:
            decisions[day] = (ACTION_REPLACE, None)
    # Un giorno passato senza sfida non si crea: nessuno potrebbe piu' giocarlo.
    for day in window:
        if day < today and decisions[day][0] == ACTION_CREATE:
            decisions[day] = (ACTION_KEEP, KEEP_IN_PLAY)

    # I giorni che verranno riscritti non devono vincolare quelli vicini.
    assigned = {
        day: _entry_from_doc(doc)
        for day, doc in by_day.items()
        if decisions.get(day, (ACTION_KEEP,))[0] == ACTION_KEEP
    }

    rows = []
    for day in window:
        action, reason = decisions[day]
        doc = by_day.get(day) or {}
        row = {
            "day": day,
            "action": action,
            "reason": reason,
            "player_id": doc.get("player_id"),
            "player_name": None,
            "band": doc.get("difficulty"),
            "previous_player_id": doc.get("player_id"),
            "audit": doc.get("planner_audit"),
            "locked": bool(doc.get("locked")),
            "source": doc.get("source"),
        }
        if action != ACTION_KEEP:
            candidate, audit = choose_for_day(
                day, assigned, pool, exclusions=exclusions, config=config, variant=variants.get(day, 0),
            )
            assigned[day] = _entry_from_candidate(day, candidate)
            row.update({"player_id": candidate["id"], "band": candidate["band"], "audit": audit})
        player = get_player_by_id(row["player_id"]) if row["player_id"] else None
        row["player_name"] = (player or {}).get("full_name")
        row["nationality"] = (player or {}).get("nationality")
        rows.append(row)

    return {"start": start_day, "end": window[-1], "mode": mode, "days": rows, "summary": summarize(rows)}


def summarize(rows):
    """I numeri per decidere se applicare: cosa cambia, dove si e' dovuto allentare, e come
    risultano distribuite fasce e nazionalita' sull'intero calendario (giorni fissi compresi)."""
    actions = {ACTION_CREATE: 0, ACTION_REPLACE: 0, ACTION_KEEP: 0}
    relaxed: dict[str, int] = {}
    bands = {level: 0 for level in DIFFICULTY_ORDER}
    for row in rows:
        actions[row["action"]] += 1
        if row["band"] in bands:
            bands[row["band"]] += 1
        if row["action"] != ACTION_KEEP:
            for rule in (row["audit"] or {}).get("relaxed", []):
                relaxed[rule] = relaxed.get(rule, 0) + 1
    planned = [row for row in rows if row["player_id"]]
    return {
        "actions": actions,
        "relaxed": relaxed,
        "bands": bands,
        "missing_days": [row["day"] for row in rows if not row["player_id"]],
        "repeated_players": sorted({
            row["player_id"] for row in planned
            if sum(1 for other in planned if other["player_id"] == row["player_id"]) > 1
        }),
        "longest_band_streak": _longest_streak([row["band"] for row in rows]),
    }


def _longest_streak(values):
    best = current = 0
    previous = object()
    for value in values:
        current = current + 1 if value is not None and value == previous else (1 if value is not None else 0)
        previous = value
        best = max(best, current)
    return best


def load_context(start_day, days, today=None, config=None):
    """Legge da Firestore cio' che serve a pianificare: sfide intorno alla finestra, sospesi,
    esclusioni. La finestra letta si allarga della distanza anti-ripetizione in entrambe le
    direzioni, perche' un giorno fissato subito dopo l'orizzonte vincola l'ultimo giorno."""
    config = config or load_config()
    settings = planner_settings(config)
    margin = max(settings["player_cooldown_days"], settings["club_cooldown_days"], settings["nationality_cooldown_days"])
    first, last = shift_iso(start_day, -margin), shift_iso(start_day, days - 1 + margin)
    docs = firebase_service.get_daily_paths_range(first, last, limit=days + 2 * margin + 1)
    try:
        blocked = firebase_service.get_blocked_player_ids()
    except GoogleAPICallError:
        # Un problema nel leggere gli override non deve impedire la generazione della sfida.
        logging.exception("[PLANNER] Giocatori sospesi non leggibili: procedo senza esclusioni")
        blocked = []
    return {"docs": docs, "pool": build_pool(blocked), "exclusions": load_exclusions(), "today": today or today_iso()}


def plan_calendar(days=None, start_day=None, mode=MODE_FILL, today=None, variants=None, config=None):
    config = config or load_config()
    today = today or today_iso()
    days = days or planner_settings(config)["horizon_days"]
    start_day = normalize_day(start_day) if start_day else today
    context = load_context(start_day, days, today=today, config=config)
    if not context["pool"]:
        raise PlannerError("Nessun giocatore valido disponibile nel dataset (data/players.json).")
    return build_plan(
        start_day, days, context["docs"], context["pool"], context["today"],
        exclusions=context["exclusions"], config=config, mode=mode, variants=variants,
    )


# ---------------------------------------------------------------------------
# Scrittura
# ---------------------------------------------------------------------------

def challenge_doc(player, difficulty=None, source=SOURCE_AUTO, keep=None, audit=None):
    """Il documento `daily_path` per un giocatore: unico punto che lo costruisce."""
    keep = keep or {}
    doc = {
        "player_id": player["id"],
        "correct_answers": get_answer_aliases(player),
        "difficulty": difficulty or compute_difficulty(player),
        # La previsione fotografata ora, con la taratura di oggi: e' il termine di paragone
        # per com'e' andata davvero la giornata (services/difficulty_calibration.py, #21).
        "difficulty_prediction": predict_difficulty(player),
        "career_path": player["career"],
        # il bonus gia' assegnato non si riapre da solo cambiando il giocatore: sarebbe un
        # secondo bonus per lo stesso giorno.
        "first_correct_user": bool(keep.get("first_correct_user", False)),
        "generated_at": datetime.now(ITALY_TZ),
        "source": source,
        "locked": bool(keep.get("locked", False)),
    }
    if audit is not None:
        doc["planner_audit"] = dict(audit)
    return doc


def apply_plan(plan, source=SOURCE_PLANNER):
    """Scrive i giorni da creare o sostituire, ricontrollando ognuno subito prima.

    Fra l'anteprima e il click su "Applica" possono passare minuti: se nel frattempo un
    giorno e' stato bloccato, creato o cambiato (da un altro admin o dal job notturno) quel
    giorno si salta e lo si dice, invece di sovrascrivere la modifica di qualcun altro."""
    written, skipped = [], []
    planned_at = datetime.now(ITALY_TZ)
    for row in plan["days"]:
        if row["action"] == ACTION_KEEP:
            continue
        day = row["day"]
        current = firebase_service.get_daily_path(day) or {}
        if current.get("locked"):
            skipped.append({"day": day, "reason": "bloccata nel frattempo"})
            continue
        if row["action"] == ACTION_CREATE and current:
            skipped.append({"day": day, "reason": "creata nel frattempo"})
            continue
        if row["action"] == ACTION_REPLACE and current.get("player_id") != row["previous_player_id"]:
            skipped.append({"day": day, "reason": "modificata nel frattempo"})
            continue
        player = get_player_by_id(row["player_id"])
        if not player:
            skipped.append({"day": day, "reason": "giocatore non piu' nel dataset"})
            continue
        audit = dict(row["audit"] or {}, mode=plan["mode"], planned_at=planned_at)
        doc = challenge_doc(player, difficulty=row["band"], source=source, keep=current, audit=audit)
        firebase_service.save_daily_path(day, doc)
        written.append({"day": day, "player_id": player["id"], "difficulty": doc["difficulty"]})
    logging.info(f"[PLANNER] {plan['start']}..{plan['end']} ({plan['mode']}): {len(written)} scritte, {len(skipped)} saltate")
    return {"written": written, "skipped": skipped}


def choose_single_day(day_iso, avoid_ids=(), variant=0, today=None, config=None):
    """Il giocatore per un solo giorno, con le stesse regole del calendario: e' cio' che usa
    "Rigenera" su una sfida gia' esistente. Il documento attuale del giorno non vincola."""
    config = config or load_config()
    context = load_context(day_iso, 1, today=today, config=config)
    assigned = {
        normalize_day(doc.get("day")): _entry_from_doc(doc)
        for doc in context["docs"]
        if doc.get("day") and normalize_day(doc.get("day")) != day_iso
    }
    if not context["pool"]:
        raise PlannerError("Nessun giocatore valido disponibile nel dataset (data/players.json).")
    candidate, audit = choose_for_day(
        day_iso, assigned, context["pool"], exclusions=context["exclusions"], config=config,
        variant=variant, avoid_ids=avoid_ids,
    )
    return candidate["player"], candidate["band"], audit
