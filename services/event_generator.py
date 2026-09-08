import json
import logging
import math
import os
import random
from datetime import datetime, timedelta

from services import firebase_service
from services.dates import ITALY_TZ, to_iso
from services.player_pool import filter_players, get_all_players, get_answer_aliases, load_config

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TEMPLATES_PATH = os.path.join(_BASE_DIR, "data", "event_templates.json")

_templates_cache = None


def load_templates():
    global _templates_cache
    if _templates_cache is None:
        with open(_TEMPLATES_PATH, "r", encoding="utf-8") as f:
            _templates_cache = json.load(f).get("templates", [])
    return _templates_cache


def _is_eligible(template, now_italy, recent_template_ids, min_gap_ok):
    if template.get("manual_only"):
        return False
    if template["id"] in recent_template_ids:
        return False
    if not min_gap_ok:
        return False
    if template.get("weekend_only") and now_italy.weekday() not in (4, 5, 6):  # ven/sab/dom
        return False
    return True


def pick_event_template(now_italy=None):
    now_italy = now_italy or datetime.now(ITALY_TZ)
    config = load_config()
    templates = load_templates()

    recent_template_ids = set(
        firebase_service.get_recent_event_template_ids(config.get("event_history_no_repeat_templates", 3))
    )

    last_end = firebase_service.get_last_event_end_date()
    min_gap_days = config.get("event_min_gap_days", 10)
    min_gap_ok = last_end is None or (now_italy.replace(tzinfo=None) - last_end).days >= min_gap_days

    eligible = [t for t in templates if _is_eligible(t, now_italy, recent_template_ids, min_gap_ok)]
    if not eligible:
        return None

    rng = random.Random(now_italy.strftime("%Y-%W"))
    return rng.choice(eligible)


def _build_daily_data_for_type(event_type, dates, rules, points_per_day, min_correct_ratio):
    players = filter_players(get_all_players(), rules)
    if len(players) < len(dates):
        logging.warning(
            f"[EVENT_GENERATOR] Pool insufficiente per il tipo '{event_type}' "
            f"({len(players)} giocatori validi per {len(dates)} giorni): alcuni giorni potrebbero ripetersi."
        )

    rng = random.Random(dates[0] if dates else "seed")
    daily_data = {}

    for i, date_str in enumerate(dates):
        if not players:
            break
        player = rng.choice(players)

        if event_type == "career":
            team_names = [stop["team"] for stop in player["career"]]
            min_correct = max(1, math.ceil(len(team_names) * min_correct_ratio))
            daily_data[date_str] = {
                "correct_answers": team_names,
                "min_correct": min_correct,
                "player_name": player["full_name"],
                "points": points_per_day,
                "first_correct_user": False,
            }
        else:  # "path" o "transfer_guess": si indovina il nome del calciatore
            career = player["career"]
            if event_type == "transfer_guess" and len(career) > 1:
                career_shown = [career[-1]]
            else:
                career_shown = career
            daily_data[date_str] = {
                "correct_answers": get_answer_aliases(player),
                "career_path": career_shown,
                "points": points_per_day,
                "first_correct_user": False,
            }

    return daily_data


def build_event_doc(template, start_date=None):
    start_date = start_date or datetime.now(ITALY_TZ)
    duration_days = template.get("duration_days", 5)
    dates = [to_iso(start_date + timedelta(days=i)) for i in range(duration_days)]

    daily_data = _build_daily_data_for_type(
        template["type"],
        dates,
        template.get("rules", {}),
        template.get("points_per_day", 1),
        template.get("min_correct_ratio", 0.5),
    )

    code = f"{template['id']}_{start_date.strftime('%Y%m%d')}"

    return code, {
        "template_id": template["id"],
        "name": template["name"],
        "description": template["description"],
        # Le traduzioni si copiano sul documento come il nome: un evento gia' generato deve
        # restare quello che era anche se il template cambia sotto.
        "name_i18n": template.get("name_i18n", {}),
        "description_i18n": template.get("description_i18n", {}),
        "type": template["type"],
        "category": template.get("category"),
        "difficulty": template.get("difficulty"),
        "dates": dates,
        "daily_data": daily_data,
        "trophy_day": dates[-1] if dates else None,
        "generated_at": datetime.now(ITALY_TZ),
        "source": "auto",
        "active": True,
    }


def maybe_generate_event(now_italy=None):
    """Se non c'e' un evento attivo/programmato di recente e le regole di rotazione lo
    consentono, ne genera uno nuovo. Ritorna il codice evento creato, oppure None."""
    now_italy = now_italy or datetime.now(ITALY_TZ)

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
