"""Creazione e modifica dei template evento (`data/event_templates.json`) dalla dashboard (#31).

Stesso schema di `domains/shop/editor.py` e `services/dataset_editor.py`: la dashboard
raccoglie il JSON del template, qui ci sono le regole. Niente arriva nel file se non passa
la validazione di `services/event_config.py`, e prima di salvare si vede cosa produrrebbe il
template: quanti candidati ha, un evento d'esempio, quando puo' partire.

Scrittura: copia di sicurezza in `backup/`, riscrittura atomica, cache dei template svuotata.
Come per gli altri file in `data/`, la modifica vale per questa copia locale del repository:
per portarla in produzione va committata e rilasciata.
"""
import json
import os
import shutil
import tempfile
from datetime import datetime, timedelta

from services import event_config, event_generator
from services.dates import ITALY_TZ, to_iso
from services.event_rules import order_teams
from services.player_pool import get_all_players

BACKUP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backup")

SCHEDULE_PREVIEW_DAYS = 120


class TemplateEditError(Exception):
    """Errore previsto (JSON o template non validi) da mostrare cosi' com'e' nella dashboard."""


def blank_template():
    """Lo scheletro di un template nuovo: valido nella forma, da riempire nei testi."""
    return {
        "id": "nuovo_evento",
        "name": "",
        "description": "",
        "name_i18n": {lang: "" for lang in event_config._other_languages()},
        "description_i18n": {lang: "" for lang in event_config._other_languages()},
        "type": "path",
        "category": "",
        "difficulty": "medium",
        "duration_days": 5,
        "filters": {},
        "rules": {"attempts": event_config.DEFAULT_RULES["attempts"]},
        "rewards": dict(event_config.DEFAULT_REWARDS),
        "schedule": {"mode": "manual", "reason": "in preparazione"},
    }


def list_templates():
    """Tutti i template del file, anche quelli non validi (con i loro errori)."""
    selectable = get_all_players()
    rows = []
    for template in event_generator.load_payload().get("templates", []):
        errors = event_config.validate_template(template)
        row = {
            "id": template.get("id"),
            "name": template.get("name"),
            "type": template.get("type"),
            "errors": errors,
            "valid": not errors,
            "schedule": event_config.schedule_label(template) if isinstance(template.get("schedule"), dict) else "?",
            "duration_days": template.get("duration_days"),
            "candidates": None,
        }
        if not errors:
            resolved = event_config.resolved(template)
            row["points_per_day"] = resolved["rewards"]["points_per_day"]
            if event_config.uses_dataset(resolved["type"]):
                players = event_generator.eligible_players(resolved, selectable)
                row["candidates"] = len(event_generator.link_pairs(players)) if resolved["type"] == "link_club" else len(players)
        rows.append(row)
    return rows


def template_text(template_id=None):
    """Il JSON da mettere nell'editor: quello del template esistente, o lo scheletro."""
    if template_id is None:
        template = blank_template()
    else:
        template = _find(event_generator.load_payload(), template_id)
        if template is None:
            raise TemplateEditError(f"Nessun template con id '{template_id}'.")
    return json.dumps(template, indent=2, ensure_ascii=False)


def parse_template(text):
    try:
        template = json.loads(text)
    except json.JSONDecodeError as e:
        raise TemplateEditError(f"JSON non valido alla riga {e.lineno}, colonna {e.colno}: {e.msg}.")
    if not isinstance(template, dict):
        raise TemplateEditError("Il template deve essere un oggetto JSON ({...}).")
    return template


def _find(payload, template_id):
    return next((t for t in payload.get("templates", []) if t.get("id") == template_id), None)


def _save_errors(template, original_id, payload):
    errors = list(event_config.validate_template(template))
    new_id = template.get("id")
    if original_id is None:
        if _find(payload, new_id) is not None:
            errors.append(f"id: esiste gia' un template '{new_id}' (per modificarlo, sceglilo dall'elenco).")
    elif new_id != original_id:
        errors.append(
            f"id: non si cambia ('{original_id}' -> '{new_id}'): i trofei degli eventi passati mostrano il nome "
            "leggendolo dal template con quell'id. Per un evento diverso crea un template nuovo."
        )
    return errors


def next_starts(template, today=None, limit=5):
    """Quando potrebbe partire, secondo il suo calendario (senza contare gli altri eventi)."""
    template = event_config.resolved(template)
    schedule = template["schedule"]
    if schedule["mode"] == "manual":
        return []
    if schedule["mode"] == "fixed":
        return [schedule["start"]]
    today = today or datetime.now(ITALY_TZ)
    starts = []
    for offset in range(SCHEDULE_PREVIEW_DAYS):
        day = today + timedelta(days=offset)
        if event_config.rotation_allows_start(template, day.date()):
            starts.append(to_iso(day))
            if len(starts) >= limit:
                break
    return starts


def preview_template(template, original_id=None, today=None):
    """Cosa succederebbe salvando: errori, oppure candidati, evento d'esempio e date di partenza."""
    errors = _save_errors(template, original_id, event_generator.load_payload())
    if errors:
        return {"valid": False, "errors": errors}
    resolved = event_config.resolved(template)
    today = today or datetime.now(ITALY_TZ)
    starts = next_starts(resolved, today=today)
    sample_start = datetime.fromisoformat(starts[0]).replace(tzinfo=ITALY_TZ) if starts else today
    result = {
        "valid": True,
        "errors": [],
        "resolved": resolved,
        "next_starts": starts,
        "candidates": None,
        "sample_days": [],
        "warnings": [],
    }
    if event_config.uses_dataset(resolved["type"]):
        candidates = event_generator.eligible_players(resolved)
        if resolved["type"] == "link_club":
            candidates = event_generator.link_pairs(candidates)
        result["candidates"] = len(candidates)
        if len(candidates) < resolved["duration_days"]:
            result["warnings"].append(
                f"{len(candidates)} candidati per {resolved['duration_days']} giorni: alcuni giorni si ripeteranno."
            )
        if candidates:
            _, doc = event_generator.build_event_doc(resolved, sample_start)
            result["sample_days"] = [
                {
                    "day": day,
                    "content": _sample_content(data),
                    "answer": _sample_answer(data),
                    # un giorno "order_career" ha una sola risposta: l'ordine intero
                    "answers": 1 if data.get("order_stop_ids") else len(data.get("correct_answers") or []),
                    "min_correct": data.get("min_correct"),
                    "points": data.get("points"),
                    "stops_shown": len(data.get("career_path") or []),
                }
                for day, data in doc["daily_data"].items()
            ]
    if resolved["schedule"]["mode"] == "rotation" and not starts:
        result["warnings"].append(
            f"Con questo calendario non puo' partire nei prossimi {SCHEDULE_PREVIEW_DAYS} giorni."
        )
    return result


def _sample_content(data):
    """Cosa vede chi gioca quel giorno, in una riga."""
    if data.get("player_names"):
        return " + ".join(data["player_names"])
    return data.get("player_name") or f"{len(data.get('career_path') or [])} tappe"


def _sample_answer(data):
    if data.get("order_stop_ids"):
        return " → ".join(order_teams(data))
    if data.get("player_names") or not data.get("player_name"):
        return (data.get("correct_answers") or ["?"])[-1]
    return data["player_name"]


def save_template(template, original_id=None):
    """Aggiunge (original_id=None) o sostituisce un template; ritorna id e copia di sicurezza."""
    payload = event_generator.load_payload()
    errors = _save_errors(template, original_id, payload)
    if errors:
        raise TemplateEditError("Template non valido:\n- " + "\n- ".join(errors))

    templates = list(payload.get("templates", []))
    if original_id is None:
        templates.append(template)
    else:
        templates = [template if t.get("id") == original_id else t for t in templates]
    new_payload = dict(payload, schema_version=event_config.SCHEMA_VERSION, templates=templates)

    problems = event_config.validate_payload(new_payload)
    if problems:
        details = "; ".join(f"{key}: {', '.join(errs)}" for key, errs in problems.items())
        raise TemplateEditError(f"Il file risultante non sarebbe valido: {details}")
    if original_id is not None and _find(payload, original_id) == template:
        raise TemplateEditError("Nessuna modifica da salvare.")

    backup_path = _backup(event_generator.TEMPLATES_PATH)
    _write_json(event_generator.TEMPLATES_PATH, new_payload)
    event_generator.reload_templates()
    return {"id": template["id"], "backup": backup_path, "created": original_id is None}


def _backup(path):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    destination = os.path.join(BACKUP_DIR, f"event_templates-{stamp}.json")
    shutil.copy2(path, destination)
    return destination


def _write_json(path, payload):
    """Riscrittura atomica: o c'e' il file nuovo o c'e' quello vecchio, mai mezzo file."""
    directory = os.path.dirname(path)
    fd, temp_path = tempfile.mkstemp(dir=directory, prefix=".event_templates-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(temp_path, path)
    except BaseException:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise
