"""Lettura dettagliata e modifica dei contenuti gia' programmati (sfide ed eventi).

E' il livello che sta sotto la dashboard locale (`admin_ui.py`): la dashboard mostra e
raccoglie i click, qui c'e' la logica. Serve perche' le correzioni che servono davvero non
sono scritture "grezze" su Firestore:

- sostituire il giocatore di un giorno vuol dire ricalcolare risposte accettate e
  difficolta' dal dataset, non solo cambiare un campo;
- rigenerare un giorno deve rispettare le stesse regole del generatore automatico
  (anti-ripetizione, giocatori sospesi, rotazione della difficolta');
- spostare un evento vuol dire rimappare le date **e** le chiavi di `daily_data`, che sono
  date a loro volta: farlo a mano dalla console e' il modo piu' rapido per rompere un evento;
- il flag "bonus del primo ancora libero" va trattato come uno stato del gioco, non come un
  booleano qualsiasi: si tocca solo di proposito.

Le funzioni che modificano qualcosa alzano `ContentAdminError` con un messaggio gia'
leggibile: la dashboard lo mostra cosi' com'e'.
"""
import logging
from datetime import datetime, timedelta

from services import firebase_service
from services.daily_challenge import challenge_number
from services.daily_generator import pick_player_for_date
from services.dates import ITALY_TZ, normalize_day, parse_iso, shift_iso, to_display, to_iso, today_iso
from services.difficulty import (
    DIFFICULTY_ORDER,
    compute_difficulty,
    compute_difficulty_score,
    points_for_difficulty,
)
from services.player_pool import get_answer_aliases, get_player_by_id, load_config

WEEKDAYS_IT = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]

STATUS_PAST = "passata"
STATUS_TODAY = "oggi"
STATUS_PLANNED = "programmata"
STATUS_MISSING = "mancante"

EVENT_STATUS_ENDED = "concluso"
EVENT_STATUS_RUNNING = "in corso"
EVENT_STATUS_PLANNED = "programmato"


class ContentAdminError(Exception):
    """Errore previsto (dato mancante o modifica non permessa) da mostrare all'admin."""


def _require_iso(day_iso):
    try:
        parse_iso(day_iso)
    except (ValueError, TypeError):
        raise ContentAdminError(f"Data '{day_iso}' non valida: serve il formato YYYY-MM-DD.")
    return day_iso


def _weekday_label(day_iso):
    return WEEKDAYS_IT[parse_iso(day_iso).weekday()]


def day_status(day_iso, today=None):
    today = today or today_iso()
    if day_iso < today:
        return STATUS_PAST
    if day_iso == today:
        return STATUS_TODAY
    return STATUS_PLANNED


# ---------------------------------------------------------------------------
# Sfide giornaliere
# ---------------------------------------------------------------------------

def describe_daily(day_iso, doc, today=None):
    """Tutte le informazioni di una sfida in un dizionario piatto, pronto da mostrare.

    Il documento su Firestore contiene solo l'essenziale (il generatore scrive percorso,
    risposte e difficolta'): il resto - nome del giocatore, punteggio di difficolta',
    numero della sfida - si ricava da dataset e configurazione, quindi resta coerente anche
    con le sfide generate mesi fa."""
    day_iso = normalize_day(day_iso)

    info = {
        "day": day_iso,
        "day_display": to_display(day_iso),
        "weekday": _weekday_label(day_iso),
        "challenge_number": challenge_number(day_iso),
        "status": day_status(day_iso, today) if doc else STATUS_MISSING,
        "exists": bool(doc),
        "player_id": None,
        "player_name": None,
        "player_in_dataset": False,
        "verified": None,
        "answers": [],
        "difficulty": None,
        "difficulty_score": None,
        "points": None,
        "career": [],
        "teams_count": 0,
        "source": None,
        "generated_at": None,
        "first_correct_taken": None,
    }
    if not doc:
        return info

    player_id = doc.get("player_id")
    player = get_player_by_id(player_id) if player_id else None
    difficulty = doc.get("difficulty")
    career = doc.get("career_path") or []

    info.update({
        "player_id": player_id,
        "player_name": (player or {}).get("full_name"),
        "player_in_dataset": player is not None,
        "verified": (player or {}).get("verified"),
        "answers": doc.get("correct_answers") or [],
        "difficulty": difficulty,
        "difficulty_score": round(compute_difficulty_score(player), 2) if player else None,
        "points": points_for_difficulty(difficulty),
        "career": career,
        "teams_count": len(career),
        "source": doc.get("source", "auto"),
        "generated_at": doc.get("generated_at"),
        "first_correct_taken": bool(doc.get("first_correct_user")),
    })
    return info


def list_daily_window(days_back=3, days_ahead=14, today=None):
    """La finestra di giorni intorno a oggi, **buchi compresi**.

    I giorni senza documento sono la cosa piu' importante da vedere in una dashboard di
    pianificazione, e una semplice lista di documenti non li mostrerebbe: qui si costruisce
    l'intervallo completo di date e si segna come 'mancante' cio' che non c'e'."""
    today = today or today_iso()
    start = shift_iso(today, -abs(days_back))
    end = shift_iso(today, abs(days_ahead))

    docs = {normalize_day(d.get("day")): d for d in firebase_service.get_daily_paths_range(start, end)}

    rows = []
    current = start
    while current <= end:
        rows.append(describe_daily(current, docs.get(current), today=today))
        current = shift_iso(current, 1)
    return rows


def buffer_health(today=None):
    """Fino a che giorno il gioco e' coperto senza buchi, a partire da oggi."""
    today = today or today_iso()
    config = load_config()
    rows = {row["day"]: row for row in list_daily_window(0, 30, today=today)}

    covered = 0
    day = today
    while rows.get(day, {}).get("exists"):
        covered += 1
        day = shift_iso(day, 1)

    return {
        "covered_days": covered,
        "last_covered_day": shift_iso(today, covered - 1) if covered else None,
        "target_days": config.get("buffer_days_ahead", 3),
        "missing_days": [d for d, row in sorted(rows.items()) if not row["exists"]],
    }


def _daily_doc_for_player(player, difficulty=None, source="manual", keep=None):
    keep = keep or {}
    return {
        "player_id": player["id"],
        "correct_answers": get_answer_aliases(player),
        "difficulty": difficulty or compute_difficulty(player),
        "career_path": player["career"],
        # il bonus gia' assegnato non si riapre da solo cambiando il giocatore: sarebbe un
        # secondo bonus per lo stesso giorno.
        "first_correct_user": bool(keep.get("first_correct_user", False)),
        "generated_at": datetime.now(ITALY_TZ),
        "source": source,
    }


def set_daily_player(day_iso, player_id):
    """Sostituisce (o crea) la sfida di un giorno con un giocatore scelto a mano."""
    day_iso = _require_iso(normalize_day(day_iso))
    player = get_player_by_id((player_id or "").strip().lower())
    if not player:
        raise ContentAdminError(f"Nessun giocatore con id '{player_id}' in data/players.json.")
    if len(player.get("career") or []) < load_config().get("min_teams_in_career", 2):
        raise ContentAdminError(
            f"'{player['id']}' ha meno tappe di carriera del minimo richiesto: correggi il dataset."
        )

    existing = firebase_service.get_daily_path(day_iso) or {}
    doc = _daily_doc_for_player(player, source="manual", keep=existing)
    firebase_service.save_daily_path(day_iso, doc)
    logging.info(f"[ADMIN] Sfida del {day_iso} impostata a mano su '{player['id']}'")
    return describe_daily(day_iso, doc)


def regenerate_daily(day_iso, avoid_current=True):
    """Rigenera un giorno con le stesse regole del generatore automatico.

    La scelta e' deterministica sulla data: senza escludere il giocatore attuale si
    rigenererebbe sempre lo stesso. Per questo `avoid_current` e' il comportamento di
    default - chi clicca "rigenera" vuole un'altra sfida."""
    day_iso = _require_iso(normalize_day(day_iso))
    config = load_config()

    recent = set(firebase_service.get_recent_player_ids(config.get("history_days_no_repeat", 60)))
    existing = firebase_service.get_daily_path(day_iso) or {}
    if avoid_current and existing.get("player_id"):
        recent.add(existing["player_id"])

    date_dt = parse_iso(day_iso)
    try:
        player, difficulty = pick_player_for_date(
            date_dt,
            recent,
            rotation_index=date_dt.timetuple().tm_yday,
            blocked_ids=firebase_service.get_blocked_player_ids(),
        )
    except ValueError as e:
        raise ContentAdminError(str(e))

    doc = _daily_doc_for_player(player, difficulty=difficulty, source="auto", keep=existing)
    firebase_service.save_daily_path(day_iso, doc)
    logging.info(f"[ADMIN] Sfida del {day_iso} rigenerata su '{player['id']}'")
    return describe_daily(day_iso, doc)


def parse_answers_list(text):
    """'Messi, leo messi' -> ['messi', 'leo messi']. Le risposte si confrontano in
    minuscolo (services/matching.py), quindi si salvano gia' normalizzate."""
    if not text:
        return []
    answers = []
    for part in text.replace("|", ",").split(","):
        answer = " ".join(part.strip().lower().split())
        if answer and answer not in answers:
            answers.append(answer)
    return answers


def update_daily_answers(day_iso, answers):
    day_iso = _require_iso(normalize_day(day_iso))
    if not answers:
        raise ContentAdminError("Serve almeno una risposta accettata.")
    if not firebase_service.get_daily_path(day_iso):
        raise ContentAdminError(f"Non c'e' nessuna sfida per il {to_display(day_iso)}.")
    firebase_service.update_daily_path(day_iso, {"correct_answers": list(answers)})
    return answers


def update_daily_difficulty(day_iso, difficulty):
    day_iso = _require_iso(normalize_day(day_iso))
    if difficulty not in DIFFICULTY_ORDER:
        raise ContentAdminError(f"Difficolta' '{difficulty}' sconosciuta: usa {', '.join(DIFFICULTY_ORDER)}.")
    if not firebase_service.get_daily_path(day_iso):
        raise ContentAdminError(f"Non c'e' nessuna sfida per il {to_display(day_iso)}.")
    firebase_service.update_daily_path(day_iso, {"difficulty": difficulty})
    return difficulty


def set_daily_first_correct(day_iso, taken):
    """Riapre (o chiude) il bonus del primo che indovina. Riaprirlo su un giorno passato
    non toglie il bonus a chi l'ha gia' preso: serve solo quando la sfida e' stata
    sostituita in corsa e nessuno l'ha ancora indovinata davvero."""
    day_iso = _require_iso(normalize_day(day_iso))
    if not firebase_service.get_daily_path(day_iso):
        raise ContentAdminError(f"Non c'e' nessuna sfida per il {to_display(day_iso)}.")
    firebase_service.update_daily_path(day_iso, {"first_correct_user": bool(taken)})
    return bool(taken)


def delete_daily(day_iso, today=None):
    """Elimina la sfida di un giorno. Quella di oggi no: il gioco la sta usando e la
    rigenerazione al volo (services/daily_challenge.py) ne creerebbe un'altra a meta'
    giornata, con gli utenti che hanno gia' speso i tentativi sulla precedente."""
    day_iso = _require_iso(normalize_day(day_iso))
    if day_status(day_iso, today) == STATUS_TODAY:
        raise ContentAdminError(
            "La sfida di oggi non si elimina: e' in gioco. Se il contenuto e' sbagliato, "
            "sostituisci il giocatore o rigenerala."
        )
    if not firebase_service.delete_daily_path(day_iso):
        raise ContentAdminError(f"Non c'e' nessuna sfida per il {to_display(day_iso)}.")
    return True


# ---------------------------------------------------------------------------
# Eventi
# ---------------------------------------------------------------------------

def event_status(event, today=None):
    today = today or today_iso()
    dates = [normalize_day(d) for d in (event.get("dates") or [])]
    if not dates:
        return EVENT_STATUS_ENDED
    if today < dates[0]:
        return EVENT_STATUS_PLANNED
    if today > dates[-1]:
        return EVENT_STATUS_ENDED
    return EVENT_STATUS_RUNNING


def describe_event(event, today=None):
    """Lo stato completo di un evento: dove si trova nel calendario, cosa contiene ogni
    giorno e se il bonus di giornata e' ancora libero."""
    today = today or today_iso()
    dates = [normalize_day(d) for d in (event.get("dates") or [])]
    daily_data = event.get("daily_data") or {}
    status = event_status(event, today)

    days = []
    for index, day_iso in enumerate(dates, start=1):
        data = daily_data.get(day_iso) or daily_data.get(to_display(day_iso)) or {}
        days.append({
            "index": index,
            "day": day_iso,
            "day_display": to_display(day_iso),
            "weekday": _weekday_label(day_iso) if day_iso else "",
            "status": day_status(day_iso, today),
            "has_content": bool(data),
            "answers": data.get("correct_answers") or [],
            "min_correct": data.get("min_correct"),
            "points": data.get("points"),
            "player_name": data.get("player_name"),
            "pair_id": data.get("pair_id"),
            "image_url": data.get("image_url"),
            "career": data.get("career_path") or [],
            "first_correct_taken": bool(data.get("first_correct_user")),
        })

    current_index = next((d["index"] for d in days if d["day"] == today), None)
    missing = [d["day_display"] for d in days if not d["has_content"]]

    return {
        "code": event.get("code"),
        "name": event.get("name"),
        "description": event.get("description"),
        "template_id": event.get("template_id"),
        "type": event.get("type"),
        "category": event.get("category"),
        "difficulty": event.get("difficulty"),
        "source": event.get("source", "auto"),
        "active": event.get("active", True),
        "status": status,
        "start_day": dates[0] if dates else None,
        "end_day": dates[-1] if dates else None,
        "period": f"{to_display(dates[0])} → {to_display(dates[-1])}" if dates else "date non disponibili",
        "days_total": len(dates),
        "current_index": current_index,
        "trophy_day": normalize_day(event.get("trophy_day")),
        "trophy_assigned": bool(event.get("trophies_assigned")),
        "generated_at": event.get("generated_at"),
        "participants_count": event.get("participants_count"),
        "days": days,
        "days_without_content": missing,
    }


def _event_or_error(event_code):
    event = firebase_service.get_event(event_code)
    if not event:
        raise ContentAdminError(f"Nessun evento con codice '{event_code}'.")
    return event


def set_event_active(event_code, active):
    _event_or_error(event_code)
    firebase_service.update_event(event_code, {"active": bool(active)})
    return bool(active)


def update_event_day_answers(event_code, day_iso, answers):
    """Corregge le risposte accettate di un singolo giorno dell'evento."""
    event = _event_or_error(event_code)
    day_iso = normalize_day(day_iso)
    if day_iso not in [normalize_day(d) for d in (event.get("dates") or [])]:
        raise ContentAdminError(f"Il {to_display(day_iso)} non fa parte dell'evento '{event_code}'.")
    if not answers:
        raise ContentAdminError("Serve almeno una risposta accettata.")
    firebase_service.update_event(event_code, {f"daily_data.{day_iso}.correct_answers": list(answers)})
    return answers


def set_event_day_first_correct(event_code, day_iso, taken):
    event = _event_or_error(event_code)
    day_iso = normalize_day(day_iso)
    if day_iso not in [normalize_day(d) for d in (event.get("dates") or [])]:
        raise ContentAdminError(f"Il {to_display(day_iso)} non fa parte dell'evento '{event_code}'.")
    firebase_service.update_event(event_code, {f"daily_data.{day_iso}.first_correct_user": bool(taken)})
    return bool(taken)


def shift_event(event_code, new_start_day, today=None):
    """Sposta un evento a un'altra data di inizio.

    Le date non sono solo il campo `dates`: sono anche le **chiavi** di `daily_data` e il
    valore di `trophy_day`. Rimappare tutto insieme e' l'unico modo per non ritrovarsi un
    evento con giorni senza contenuto (e' l'errore tipico quando si sposta un evento dalla
    console di Firestore)."""
    today = today or today_iso()
    event = _event_or_error(event_code)
    new_start_day = _require_iso(normalize_day(new_start_day))

    if event_status(event, today) == EVENT_STATUS_ENDED:
        raise ContentAdminError("L'evento e' gia' concluso: spostarlo riaprirebbe una classifica chiusa.")

    old_dates = [normalize_day(d) for d in (event.get("dates") or [])]
    if not old_dates:
        raise ContentAdminError("L'evento non ha date: va ricreato.")

    daily_data = event.get("daily_data") or {}
    start_dt = parse_iso(new_start_day)
    new_dates = [to_iso(start_dt + timedelta(days=i)) for i in range(len(old_dates))]

    overlapping = _overlapping_event_name(new_dates, event_code)
    if overlapping:
        raise ContentAdminError(f"Le nuove date si sovrappongono all'evento '{overlapping}'.")

    new_daily = {}
    for old_day, new_day in zip(old_dates, new_dates):
        content = daily_data.get(old_day) or daily_data.get(to_display(old_day))
        if content is not None:
            new_daily[new_day] = content

    firebase_service.update_event(event_code, {
        "dates": new_dates,
        "daily_data": new_daily,
        "trophy_day": new_dates[-1],
    })
    logging.info(f"[ADMIN] Evento {event_code} spostato: {old_dates[0]} -> {new_dates[0]}")
    return {"dates": new_dates, "trophy_day": new_dates[-1]}


def _overlapping_event_name(dates, own_code):
    for day in dates:
        for event in firebase_service.get_active_events(day):
            if event.get("code") != own_code:
                return event.get("name") or event.get("code")
    return None


def delete_event(event_code, today=None):
    """Elimina un evento e i suoi partecipanti. Non quello in corso: sparirebbe la
    classifica a meta' gara. Per fermarlo si usa 'disattiva'."""
    event = _event_or_error(event_code)
    if event_status(event, today) == EVENT_STATUS_RUNNING:
        raise ContentAdminError(
            "L'evento e' in corso: disattivalo invece di eliminarlo, oppure aspetta che finisca."
        )
    firebase_service.delete_event(event_code)
    return True
