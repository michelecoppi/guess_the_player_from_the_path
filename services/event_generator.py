"""Generazione degli eventi tematici dai template di `data/event_templates.json`.

Cosa rende un evento diverso da un altro sta nel template (schema e validazione in
services/event_config.py, riferimento in docs/event-templates.md); qui c'e' solo il motore:
decidere **se** e **quale** evento parte oggi, e costruirne il documento.
"""
import json
import logging
import math
import os
import random
from datetime import datetime, timedelta

from services import event_config, firebase_service
from services.career_order import order_career
from services.dates import ITALY_TZ, to_iso
from services.player_pool import filter_players, get_all_players, get_answer_aliases, load_config

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_PATH = os.path.join(_BASE_DIR, "data", "event_templates.json")

_templates_cache = None


def load_payload():
    """Il file cosi' com'e' (per l'editor e la validazione)."""
    with open(TEMPLATES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_templates():
    """I template **validi**, con i default espliciti.

    Un template sbagliato si salta con un errore nei log invece di far fallire il job
    notturno: la CI (`scripts/dataset_report.py --strict`) e l'editor della dashboard
    impediscono che ci arrivi, questo e' solo l'ultimo paracadute."""
    global _templates_cache
    if _templates_cache is None:
        templates = []
        for template in load_payload().get("templates", []):
            errors = event_config.validate_template(template)
            if errors:
                logging.error(f"[EVENT_GENERATOR] Template '{template.get('id')}' non valido, ignorato: {errors}")
                continue
            templates.append(event_config.resolved(template))
        _templates_cache = templates
    return _templates_cache


def reload_templates():
    global _templates_cache
    _templates_cache = None


def _event_dates(start_date, duration_days):
    return [to_iso(start_date + timedelta(days=i)) for i in range(duration_days)]


def overlapping_event(dates, own_code=None):
    """Due eventi contemporaneamente attivi si contenderebbero /events: si controlla la
    sovrapposizione sulle date del nuovo evento, non solo su oggi, cosi' si puo' programmare
    un evento futuro mentre uno e' in corso."""
    for day in dates:
        for event in firebase_service.get_active_events(day):
            if event.get("code") != own_code:
                return event.get("name") or event.get("code")
    return None


# Un evento a data fissa si crea con qualche giorno d'anticipo: se la notte giusta il job non
# gira, o se quel giorno c'e' ancora un evento in coda, c'e' tempo per accorgersene.
FIXED_LOOKAHEAD_DAYS = 7


def fixed_templates_due(now_italy, templates=None):
    """I template a data fissa che partono fra oggi e FIXED_LOOKAHEAD_DAYS giorni."""
    templates = load_templates() if templates is None else templates
    first, last = to_iso(now_italy), to_iso(now_italy + timedelta(days=FIXED_LOOKAHEAD_DAYS))
    return [
        t for t in templates
        if t["schedule"]["mode"] == "fixed" and first <= t["schedule"]["start"] <= last
    ]


def _collides_with_fixed(template, start_date, templates):
    """Un evento in rotazione non deve occupare i giorni in cui parte un evento a data fissa."""
    dates = set(_event_dates(start_date, template["duration_days"]))
    for fixed in templates:
        if fixed["schedule"]["mode"] != "fixed":
            continue
        fixed_start = datetime.fromisoformat(fixed["schedule"]["start"])
        if dates & set(_event_dates(fixed_start, fixed["duration_days"])):
            return True
    return False


def pick_event_template(now_italy=None):
    now_italy = now_italy or datetime.now(ITALY_TZ)
    config = load_config()
    templates = load_templates()

    recent_template_ids = set(
        firebase_service.get_recent_event_template_ids(config.get("event_history_no_repeat_templates", 3))
    )

    last_end = firebase_service.get_last_event_end_date()
    min_gap_days = config.get("event_min_gap_days", 10)
    if last_end is not None and (now_italy.replace(tzinfo=None) - last_end).days < min_gap_days:
        return None

    eligible = [
        t for t in templates
        if event_config.rotation_allows_start(t, now_italy.date())
        and t["id"] not in recent_template_ids
        and not _collides_with_fixed(t, now_italy, templates)
    ]
    if not eligible:
        return None

    rng = random.Random(now_italy.strftime("%Y-%W"))
    return rng.choice(eligible)


def eligible_players(template, players=None):
    """Return the same candidate pool for generation and dashboard previews."""
    candidates = filter_players(get_all_players() if players is None else players, template["filters"])
    if template["type"] == "blind_path":
        # Repeated clubs in the five-stop puzzle would feel like a duplicate reveal.
        candidates = [player for player in candidates if len({stop["team"] for stop in order_career(player["career"])[-5:]}) == 5]
    return candidates


def link_pairs(players):
    """Pairs with exactly one shared club; a displayed pair has one valid answer."""
    clubs: dict[str, list[dict]] = {}
    for player in players:
        for club in {stop["team"] for stop in player["career"]}:
            clubs.setdefault(club, []).append(player)
    pairs = []
    seen = set()
    for club, members in clubs.items():
        for left_index, left in enumerate(members):
            for right in members[left_index + 1:]:
                key = tuple(sorted((left["id"], right["id"])))
                if key in seen:
                    continue
                seen.add(key)
                if len({stop["team"] for stop in left["career"]} &
                       {stop["team"] for stop in right["career"]}) == 1:
                    pairs.append((left, right, club))
    return pairs


def _build_daily_data(template, dates):
    event_type = template["type"]
    players = eligible_players(template)
    pairs = link_pairs(players) if event_type == "link_club" else []
    if len(players) < len(dates):
        logging.warning(
            f"[EVENT_GENERATOR] Pool insufficiente per '{template['id']}' "
            f"({len(players)} giocatori validi per {len(dates)} giorni): alcuni giorni potrebbero ripetersi."
        )

    rng = random.Random(dates[0] if dates else "seed")
    points_per_day = template["rewards"]["points_per_day"]
    shown = event_config.EVENT_TYPES[event_type]["career_shown"]
    daily_data = {}

    for date_str in dates:
        if not players or (event_type == "link_club" and not pairs):
            break
        if event_type == "link_club":
            left, right, club = rng.choice(pairs)
            if len(pairs) > 1:
                pairs.remove((left, right, club))
            daily_data[date_str] = {
                "player_names": [left["full_name"], right["full_name"]],
                "correct_answers": [club],
                "points": points_per_day,
                "first_correct_user": False,
            }
            continue
        player = rng.choice(players)
        if event_type == "blind_path" and len(players) > 1:
            players.remove(player)

        if event_config.is_multi_answer(event_type):
            team_names = [stop["team"] for stop in player["career"]]
            ratio = template["rules"]["min_correct_ratio"]
            daily_data[date_str] = {
                "correct_answers": team_names,
                "min_correct": max(1, math.ceil(len(team_names) * ratio)),
                "player_name": player["full_name"],
                "points": points_per_day,
                "first_correct_user": False,
            }
        else:  # la risposta e' il calciatore
            career = player["career"]
            visible_career = order_career(career)[-5:] if shown == "blind" else career
            daily_data[date_str] = {
                "correct_answers": get_answer_aliases(player),
                "career_path": [career[-1]] if shown == "last" and len(career) > 1 else visible_career,
                # Serve al confronto dopo un tentativo sbagliato, come nella sfida del
                # giorno: senza l'id non si sa **chi** era e non si puo' confrontare niente.
                "player_id": player["id"],
                "points": points_per_day,
                "first_correct_user": False,
            }

    return daily_data


def event_doc_base(template, dates, daily_data, source):
    """I campi comuni a ogni evento, automatico o manuale: il template si copia sul documento
    (testi, traduzioni, regole e premi) perche' un evento gia' partito deve restare quello che
    era anche se il template cambia sotto."""
    return {
        "template_id": template["id"],
        "name": template["name"],
        "description": template["description"],
        "name_i18n": template.get("name_i18n", {}),
        "description_i18n": template.get("description_i18n", {}),
        "type": template["type"],
        "category": template.get("category"),
        "difficulty": template.get("difficulty"),
        "rules": dict(template["rules"]),
        "rewards": dict(template["rewards"]),
        "dates": dates,
        "daily_data": daily_data,
        "trophy_day": dates[-1] if dates else None,
        "generated_at": datetime.now(ITALY_TZ),
        "source": source,
        "active": True,
    }


def build_event_doc(template, start_date=None, source="auto"):
    template = event_config.resolved(template)
    start_date = start_date or datetime.now(ITALY_TZ)
    dates = _event_dates(start_date, template["duration_days"])
    code = f"{template['id']}_{start_date.strftime('%Y%m%d')}"
    return code, event_doc_base(template, dates, _build_daily_data(template, dates), source)


def _create_fixed_events(now_italy):
    created = []
    for template in fixed_templates_due(now_italy):
        start = datetime.fromisoformat(template["schedule"]["start"]).replace(tzinfo=ITALY_TZ)
        code, doc = build_event_doc(template, start)
        if firebase_service.event_exists(code):
            continue
        overlapping = overlapping_event(doc["dates"], code)
        if overlapping:
            logging.error(
                f"[EVENT_GENERATOR] Evento a data fissa '{template['id']}' non creato: si sovrappone a '{overlapping}'"
            )
            continue
        if not doc["daily_data"]:
            logging.warning(f"[EVENT_GENERATOR] Template '{template['id']}' senza giocatori validi: evento non creato")
            continue
        firebase_service.save_event(code, doc)
        created.append(code)
    return created


def maybe_generate_event(now_italy=None):
    """Genera gli eventi che il calendario dei template prevede. Ritorna il codice del primo
    evento creato, oppure None.

    Prima gli eventi a data fissa, creati in anticipo (sono un impegno preso nel calendario:
    non aspettano la distanza minima dall'ultimo evento e la rotazione non puo' occupare i
    loro giorni), poi la rotazione, solo se oggi non c'e' gia' un evento."""
    now_italy = now_italy or datetime.now(ITALY_TZ)

    fixed = _create_fixed_events(now_italy)
    if fixed:
        return fixed[0]

    if firebase_service.get_active_events():
        return None

    template = pick_event_template(now_italy)
    if not template:
        return None

    code, doc = build_event_doc(template, now_italy)
    if not doc["daily_data"]:
        logging.warning(f"[EVENT_GENERATOR] Template '{template['id']}' senza giocatori validi: evento non creato")
        return None

    firebase_service.save_event(code, doc)
    return code
