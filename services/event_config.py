"""Lo schema dei template evento (`data/event_templates.json`) e la sua validazione (#31).

Un evento nuovo si crea scrivendo un template, non un ramo di codice: tipo di gioco, filtri
sul pool, regole della partita, premi e calendario stanno tutti nel file. Questo modulo e'
l'unico posto che sa com'e' fatto un template valido, e lo usano:

- `services/event_generator.py` e `services/manual_event_service.py`, che caricano solo i
  template validi (uno sbagliato si salta con un errore nei log, non ferma il job notturno);
- `scripts/dataset_report.py --strict` in CI e `tests/test_event_config.py`, che rifiutano
  un file con anche un solo template sbagliato;
- l'editor della dashboard (`services/event_template_editor.py`), che non salva niente che
  non passi da qui.

Prima di questo schema un filtro scritto male (`"min_team": 6`) veniva ignorato in silenzio
e l'evento usciva con tutto il pool; tentativi, bonus del primo e posti del podio erano
costanti sparse fra chat, mini app e trofei. Ora sono campi del template, copiati sul
documento dell'evento alla creazione: un evento gia' partito resta quello che era anche se
il template cambia.

Il riferimento discorsivo, con un esempio per ogni campo, e' docs/event-templates.md.
"""
import re
from datetime import date

from services.difficulty import DIFFICULTY_ORDER
from services.i18n import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES

SCHEMA_VERSION = 2

TEMPLATE_ID = re.compile(r"^[a-z0-9_]{3,40}$")
MONTH_DAY = re.compile(r"^(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$")
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

# ---------------------------------------------------------------------------
# Tipi di gioco
#
# Il comportamento di un tipo resta nel codice (come si risponde, cosa si mostra): e' cio'
# che un template sceglie, non che definisce. Qui c'e' la tabella che prima era sparsa in
# `if event_type == "career"` fra handler, mini app e generatore.
# ---------------------------------------------------------------------------

EVENT_TYPES: dict[str, dict[str, str | None]] = {
    # si indovina il calciatore dal percorso completo
    "path": {"answer": "player", "content": "dataset", "career_shown": "full"},
    # si indovina il calciatore da un solo trasferimento (l'ultima tappa)
    "transfer_guess": {"answer": "player", "content": "dataset", "career_shown": "last"},
    # si elencano le squadre del calciatore nominato; nessuna immagine del percorso
    "career": {"answer": "teams", "content": "dataset", "career_shown": None},
    # si indovina la coppia padre/figlio da una foto caricata dall'admin
    "father_son": {"answer": "pair", "content": "father_son_pairs", "career_shown": None},
}


def answers_with_player(event_type):
    """La risposta e' un calciatore del dataset: ha senso il confronto dopo un errore."""
    return EVENT_TYPES.get(event_type, {}).get("answer") == "player"


def is_multi_answer(event_type):
    """Si risponde con piu' valori separati da virgola (le squadre di un evento carriera)."""
    return EVENT_TYPES.get(event_type, {}).get("answer") == "teams"


def uses_dataset(event_type):
    return EVENT_TYPES.get(event_type, {}).get("content") == "dataset"


# Tetto di valori per tentativo negli eventi a risposta multipla: e' un limite contro chi
# incolla l'elenco di tutte le squadre di una lega, non una regola di gioco da tarare.
MAX_ANSWERS_PER_ATTEMPT = 5

# ---------------------------------------------------------------------------
# Default: sono i valori che il gioco usava quando erano costanti nel codice.
# ---------------------------------------------------------------------------

DEFAULT_RULES = {"attempts": 3, "min_correct_ratio": 0.5}
DEFAULT_REWARDS = {"points_per_day": 1, "first_correct_bonus": 1, "podium_trophies": 3}
DEFAULT_SCHEDULE: dict = {"mode": "rotation"}

LIMITS = {
    "duration_days": (1, 30),
    "attempts": (1, 10),
    "min_correct_ratio": (0.1, 1.0),
    "points_per_day": (0, 10),
    "first_correct_bonus": (0, 5),
    "podium_trophies": (0, 3),   # i trofei hanno medaglia e colore solo per 1°-3°
}

# ---------------------------------------------------------------------------
# Filtri sul pool: nome -> (tipo atteso, descrizione). Li applica player_pool.filter_players.
# ---------------------------------------------------------------------------

FILTERS = {
    "min_teams": ("int", "almeno N tappe di carriera"),
    "max_teams": ("int", "al massimo N tappe di carriera"),
    "min_popularity": ("popularity", "notorieta' almeno N (1-5)"),
    "max_popularity": ("popularity", "notorieta' al massimo N (1-5)"),
    "nationality_in": ("strings", "nazionalita' fra quelle elencate (come scritte nel dataset)"),
    "leagues_only_top": ("true", "tutte le tappe nei top 5 campionati"),
    "requires_minor_league": ("true", "almeno una tappa fuori dai top 5 campionati"),
}

SCHEDULE_MODES = ("rotation", "fixed", "manual")

TOP_LEVEL_FIELDS = {
    "id", "name", "description", "name_i18n", "description_i18n", "type", "category", "difficulty",
    "duration_days", "filters", "rules", "rewards", "schedule",
}
LEGACY_FIELDS = {
    "rules": None,  # gestito a parte: in v1 "rules" erano i filtri
    "points_per_day": "rewards.points_per_day",
    "min_correct_ratio": "rules.min_correct_ratio",
    "weekend_only": 'schedule.start_weekdays ["fri", "sat", "sun"]',
    "manual_only": 'schedule {"mode": "manual", "reason": ...}',
    "manual_reason": "schedule.reason",
}


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _check_range(errors, path, value, key, integer=True):
    low, high = LIMITS[key]
    ok = _is_int(value) if integer else _is_number(value)
    if not ok or not low <= value <= high:
        kind = "un intero" if integer else "un numero"
        errors.append(f"{path}: deve essere {kind} fra {low} e {high} (trovato {value!r}).")


def _check_i18n(errors, template, field):
    if not isinstance(template.get(field), str) or not template[field].strip():
        errors.append(f"{field}: obbligatorio, testo italiano non vuoto.")
    translations = template.get(f"{field}_i18n")
    if not isinstance(translations, dict):
        errors.append(f"{field}_i18n: obbligatorio, traduzioni per {', '.join(_other_languages())}.")
        return
    for lang in _other_languages():
        if not isinstance(translations.get(lang), str) or not translations[lang].strip():
            errors.append(f"{field}_i18n.{lang}: traduzione mancante.")
    for lang in translations:
        if lang not in SUPPORTED_LANGUAGES:
            errors.append(f"{field}_i18n.{lang}: lingua non supportata.")


def _other_languages():
    return [lang for lang in SUPPORTED_LANGUAGES if lang != DEFAULT_LANGUAGE]


def _check_filters(errors, filters, event_type):
    if not isinstance(filters, dict):
        errors.append("filters: deve essere un oggetto.")
        return
    if filters and not uses_dataset(event_type):
        errors.append(f"filters: il tipo '{event_type}' non pesca dal dataset, i filtri non avrebbero effetto.")
    for key, value in filters.items():
        if key not in FILTERS:
            errors.append(f"filters.{key}: filtro sconosciuto. Disponibili: {', '.join(sorted(FILTERS))}.")
            continue
        kind = FILTERS[key][0]
        if kind == "int" and (not _is_int(value) or value < 1):
            errors.append(f"filters.{key}: deve essere un intero >= 1.")
        elif kind == "popularity" and (not _is_int(value) or not 1 <= value <= 5):
            errors.append(f"filters.{key}: deve essere un intero da 1 a 5.")
        elif kind == "strings" and (
            not isinstance(value, list) or not value or not all(isinstance(v, str) and v.strip() for v in value)
        ):
            errors.append(f"filters.{key}: deve essere una lista non vuota di testi.")
        elif kind == "true" and value is not True:
            errors.append(f"filters.{key}: l'unico valore ammesso e' true (per disattivarlo, toglilo).")
    for low, high in (("min_teams", "max_teams"), ("min_popularity", "max_popularity")):
        if _is_int(filters.get(low)) and _is_int(filters.get(high)) and filters[low] > filters[high]:
            errors.append(f"filters: {low} ({filters[low]}) maggiore di {high} ({filters[high]}): nessun candidato.")
    if filters.get("leagues_only_top") and filters.get("requires_minor_league"):
        errors.append("filters: leagues_only_top e requires_minor_league insieme escludono tutti.")


def _check_rules(errors, rules, event_type):
    if not isinstance(rules, dict):
        errors.append("rules: deve essere un oggetto.")
        return
    for key in rules:
        if key not in DEFAULT_RULES:
            errors.append(f"rules.{key}: regola sconosciuta. Disponibili: {', '.join(DEFAULT_RULES)}.")
    if "attempts" in rules:
        _check_range(errors, "rules.attempts", rules["attempts"], "attempts")
    if "min_correct_ratio" in rules:
        if not is_multi_answer(event_type):
            errors.append(f"rules.min_correct_ratio: vale solo per gli eventi a piu' risposte, non per '{event_type}'.")
        _check_range(errors, "rules.min_correct_ratio", rules["min_correct_ratio"], "min_correct_ratio", integer=False)


def _check_rewards(errors, rewards):
    if not isinstance(rewards, dict):
        errors.append("rewards: deve essere un oggetto.")
        return
    for key, value in rewards.items():
        if key not in DEFAULT_REWARDS:
            errors.append(f"rewards.{key}: premio sconosciuto. Disponibili: {', '.join(DEFAULT_REWARDS)}.")
            continue
        _check_range(errors, f"rewards.{key}", value, key)


def _parse_iso(value):
    try:
        return date.fromisoformat(value) if isinstance(value, str) and len(value) == 10 else None
    except ValueError:
        return None


def _check_schedule(errors, schedule, event_type):
    if not isinstance(schedule, dict):
        errors.append("schedule: deve essere un oggetto.")
        return
    mode = schedule.get("mode")
    if mode not in SCHEDULE_MODES:
        errors.append(f"schedule.mode: deve essere uno fra {', '.join(SCHEDULE_MODES)}.")
        return
    allowed = {
        "rotation": {"mode", "start_weekdays", "window"},
        "fixed": {"mode", "start"},
        "manual": {"mode", "reason"},
    }[mode]
    for key in schedule:
        if key not in allowed:
            errors.append(f"schedule.{key}: non previsto con mode '{mode}'. Ammessi: {', '.join(sorted(allowed))}.")
    if event_type in EVENT_TYPES and not uses_dataset(event_type) and mode != "manual":
        errors.append(f"schedule.mode: il tipo '{event_type}' ha contenuti caricati a mano, serve mode 'manual'.")
    if mode == "manual" and (not isinstance(schedule.get("reason"), str) or not schedule["reason"].strip()):
        errors.append("schedule.reason: obbligatorio con mode 'manual' (perche' non parte da solo).")
    if mode == "fixed" and _parse_iso(schedule.get("start")) is None:
        errors.append("schedule.start: obbligatorio con mode 'fixed', data YYYY-MM-DD.")
    if "start_weekdays" in schedule:
        days = schedule["start_weekdays"]
        if not isinstance(days, list) or not days or any(day not in WEEKDAYS for day in days):
            errors.append(f"schedule.start_weekdays: lista non vuota fra {', '.join(WEEKDAYS)}.")
    if "window" in schedule:
        window = schedule["window"]
        if (
            not isinstance(window, dict) or set(window) != {"from", "to"}
            or not all(isinstance(window[k], str) and MONTH_DAY.match(window[k]) for k in ("from", "to"))
        ):
            errors.append('schedule.window: {"from": "MM-DD", "to": "MM-DD"} (puo\' scavalcare l\'anno).')


def validate_template(template):
    """Gli errori di un template, come frasi leggibili con il percorso del campo. [] = valido."""
    if not isinstance(template, dict):
        return ["il template deve essere un oggetto JSON."]
    errors: list[str] = []
    template_id = template.get("id")
    if not isinstance(template_id, str) or not TEMPLATE_ID.match(template_id):
        errors.append("id: obbligatorio, 3-40 caratteri fra minuscole, cifre e '_'.")

    legacy = [key for key in template if key in LEGACY_FIELDS and key != "rules"]
    for key in legacy:
        errors.append(f"{key}: campo dello schema v1, ora si scrive {LEGACY_FIELDS[key]}.")
    if "rules" in template and isinstance(template["rules"], dict) and set(template["rules"]) & set(FILTERS):
        errors.append("rules: contiene filtri sul pool (schema v1). I filtri vanno in 'filters', 'rules' e' per la partita.")
    for key in template:
        if key not in TOP_LEVEL_FIELDS and key not in LEGACY_FIELDS:
            errors.append(f"{key}: campo sconosciuto.")

    _check_i18n(errors, template, "name")
    _check_i18n(errors, template, "description")

    event_type = template.get("type")
    if event_type not in EVENT_TYPES:
        errors.append(f"type: deve essere uno fra {', '.join(EVENT_TYPES)}.")
    if "category" in template and not isinstance(template["category"], str):
        errors.append("category: deve essere un testo.")
    if template.get("difficulty") not in DIFFICULTY_ORDER:
        errors.append(f"difficulty: deve essere una fra {', '.join(DIFFICULTY_ORDER)}.")
    if "duration_days" not in template:
        errors.append("duration_days: obbligatorio.")
    else:
        _check_range(errors, "duration_days", template["duration_days"], "duration_days")

    _check_filters(errors, template.get("filters", {}), event_type)
    if not ("rules" in template and isinstance(template["rules"], dict) and set(template["rules"]) & set(FILTERS)):
        _check_rules(errors, template.get("rules", {}), event_type)
    _check_rewards(errors, template.get("rewards", {}))
    if "schedule" not in template:
        errors.append('schedule: obbligatorio, ad esempio {"mode": "rotation"}.')
    else:
        _check_schedule(errors, template["schedule"], event_type)
    return errors


def validate_payload(payload):
    """Errori dell'intero file: {id o posizione: [errori]}, con i duplicati. {} = valido."""
    if not isinstance(payload, dict) or not isinstance(payload.get("templates"), list):
        return {"file": ['serve un oggetto con "templates": [...].']}
    problems: dict[str, list[str]] = {}
    if payload.get("schema_version") != SCHEMA_VERSION:
        problems["file"] = [f"schema_version: deve essere {SCHEMA_VERSION}."]
    seen: dict[str, int] = {}
    for index, template in enumerate(payload["templates"]):
        key = str(template["id"]) if isinstance(template, dict) and isinstance(template.get("id"), str) else f"#{index}"
        errors = validate_template(template)
        if key in seen:
            errors.append(f"id: duplicato (gia' usato dal template in posizione {seen[key]}).")
        seen.setdefault(key, index)
        if errors:
            problems.setdefault(key, []).extend(errors)
    return problems


# ---------------------------------------------------------------------------
# Valori risolti
# ---------------------------------------------------------------------------

def resolved(template):
    """Il template con tutti i default espliciti: e' la forma che usano generatore e dashboard."""
    result = dict(template)
    result["filters"] = dict(template.get("filters") or {})
    result["rules"] = {**DEFAULT_RULES, **(template.get("rules") or {})}
    if not is_multi_answer(template.get("type")):
        result["rules"].pop("min_correct_ratio", None)
    result["rewards"] = {**DEFAULT_REWARDS, **(template.get("rewards") or {})}
    result["schedule"] = dict(template.get("schedule") or DEFAULT_SCHEDULE)
    return result


def event_rules(event):
    """Regole della partita per un documento evento; i documenti precedenti a #31 non le hanno."""
    return {**DEFAULT_RULES, **((event or {}).get("rules") or {})}


def event_rewards(event):
    return {**DEFAULT_REWARDS, **((event or {}).get("rewards") or {})}


def is_manual(template):
    return (template.get("schedule") or {}).get("mode") == "manual"


def schedule_label(template):
    """Il calendario in una riga, per la dashboard e il report."""
    schedule = template.get("schedule") or DEFAULT_SCHEDULE
    mode = schedule.get("mode")
    if mode == "manual":
        return f"manuale — {schedule.get('reason', '')}"
    if mode == "fixed":
        return f"data fissa {schedule.get('start')}"
    parts = ["rotazione"]
    if schedule.get("start_weekdays"):
        parts.append("parte di " + "/".join(schedule["start_weekdays"]))
    if schedule.get("window"):
        parts.append(f"dal {schedule['window']['from']} al {schedule['window']['to']}")
    return ", ".join(parts)


def in_window(window, day):
    """`day` (date) dentro una finestra ricorrente MM-DD..MM-DD, anche a cavallo d'anno."""
    if not window:
        return True
    current = day.strftime("%m-%d")
    start, end = window["from"], window["to"]
    return start <= current <= end if start <= end else (current >= start or current <= end)


def rotation_allows_start(template, day):
    """Un template in rotazione puo' partire in questo giorno (giorno della settimana e finestra)."""
    schedule = template.get("schedule") or DEFAULT_SCHEDULE
    if schedule.get("mode") != "rotation":
        return False
    weekdays = schedule.get("start_weekdays")
    if weekdays and WEEKDAYS[day.weekday()] not in weekdays:
        return False
    return in_window(schedule.get("window"), day)
