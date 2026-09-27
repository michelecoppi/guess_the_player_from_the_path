"""Creazione manuale degli eventi, comandata da Telegram.

Alcuni eventi non si possono generare in automatico dal dataset dei percorsi: il caso
concreto e' l'evento "coppie padre/figlio", che ha bisogno di una foto e non di una
carriera. Invece di lasciarli come documenti da scrivere a mano su Firestore, qui l'admin
li costruisce dalla chat:

1. manda al bot la foto della coppia con didascalia `/admin_fs_add Maldini, Paolo e Cesare`
   -> la foto resta su Telegram (si salva solo il suo file_id) e le risposte accettate
   finiscono in Firestore;
2. quando ci sono abbastanza coppie, `/admin_event_create coppie_leggendarie` costruisce
   l'evento vero e proprio, un giorno per coppia.

Lo stesso comando serve anche a forzare a mano un evento di un template automatico, quando
si vuole decidere quando parte invece di aspettare la rotazione.
"""
import logging
from datetime import datetime, timedelta

from services import event_config, firebase_service
from services.dates import ITALY_TZ, to_iso
from services.event_generator import build_event_doc, event_doc_base, load_templates, overlapping_event


class ManualEventError(Exception):
    """Errore previsto (dato mancante o regola non rispettata) da mostrare all'admin."""


def parse_answers(text):
    """Trasforma 'Maldini, Paolo e Cesare | maldini' nella lista di risposte accettate."""
    if not text:
        return []
    raw_parts = text.replace("|", ",").split(",")
    answers = []
    for part in raw_parts:
        answer = " ".join(part.strip().lower().split())
        if answer and answer not in answers:
            answers.append(answer)
    return answers


def get_template(template_id):
    for template in load_templates():
        if template["id"] == template_id:
            return template
    raise ManualEventError(
        f"Template '{template_id}' inesistente o non valido. Disponibili: "
        + ", ".join(t["id"] for t in load_templates())
    )


def build_father_son_event(pairs, start_date, template, duration_days=None):
    """Costruisce l'evento padre/figlio: un giorno per coppia, senza mai ripetere una coppia
    nello stesso evento (le coppie disponibili sono poche, ripeterle svelerebbe la risposta)."""
    if not pairs:
        raise ManualEventError(
            "Nessuna coppia padre/figlio salvata. Mandami la foto della coppia con didascalia "
            "/admin_fs_add <risposte accettate separate da virgola>."
        )

    template = event_config.resolved(template)
    requested = duration_days or template["duration_days"]
    days = min(requested, len(pairs))
    dates = [to_iso(start_date + timedelta(days=i)) for i in range(days)]
    points_per_day = template["rewards"]["points_per_day"]

    daily_data = {}
    used_pair_ids = []
    for date_str, pair in zip(dates, pairs):
        answers = pair.get("answers", [])
        if not answers:
            raise ManualEventError(f"La coppia {pair.get('id')} non ha risposte accettate: eliminala e ricreala.")
        daily_data[date_str] = {
            "correct_answers": answers,
            "image_url": pair.get("file_id"),
            "points": points_per_day,
            "first_correct_user": False,
            "pair_id": pair.get("id"),
        }
        if pair.get("hint"):
            daily_data[date_str]["hint"] = pair["hint"]
        used_pair_ids.append(pair.get("id"))

    code = f"{template['id']}_{start_date.strftime('%Y%m%d')}"
    return code, event_doc_base(template, dates, daily_data, "manual"), used_pair_ids


def create_manual_event(template_id, start_date=None, duration_days=None, allow_overlap=False):
    """Crea e salva un evento su richiesta dell'admin. Ritorna un riepilogo per la chat."""
    start_date = start_date or datetime.now(ITALY_TZ)
    template = get_template(template_id)

    if event_config.EVENT_TYPES[template["type"]]["content"] == "father_son_pairs":
        pairs = firebase_service.list_father_son_pairs(only_unused=True)
        code, doc, used_pair_ids = build_father_son_event(pairs, start_date, template, duration_days)
    else:
        code, doc = build_event_doc(template, start_date, source="manual")
        used_pair_ids = []
        if not doc["daily_data"]:
            raise ManualEventError(
                f"Il template '{template_id}' non ha giocatori validi nel dataset con le sue regole."
            )
        if duration_days:
            # taglia o rifiuta: meglio essere espliciti che generare giorni senza contenuto
            raise ManualEventError(
                "La durata personalizzata e' supportata solo per gli eventi manuali padre/figlio; "
                f"'{template_id}' usa la durata del template ({template['duration_days']} giorni)."
            )

    if firebase_service.event_exists(code):
        raise ManualEventError(f"Esiste gia' un evento con codice '{code}' (stesso template e stessa data di inizio).")

    if not allow_overlap:
        overlapping = overlapping_event(doc["dates"], code)
        if overlapping:
            raise ManualEventError(
                f"L'evento si sovrappone a '{overlapping}'. Scegli una data di inizio successiva "
                "(es. /admin_event_create <template> 01/12/26)."
            )

    firebase_service.save_event(code, doc)
    if used_pair_ids:
        firebase_service.mark_father_son_pairs_used(used_pair_ids, code)

    logging.info(f"[MANUAL_EVENT] Evento creato a mano: {code}")
    return {
        "code": code,
        "name": doc["name"],
        "type": doc["type"],
        "dates": doc["dates"],
        "days": len(doc["dates"]),
        "trophy_day": doc["trophy_day"],
    }


def parse_start_date(text):
    """Accetta gg/mm/aa (lo stesso formato usato in tutto il bot) e ritorna una data
    nel fuso italiano; senza argomento, oggi."""
    if not text:
        return datetime.now(ITALY_TZ)
    try:
        naive = datetime.strptime(text.strip(), "%d/%m/%y")
    except ValueError:
        raise ManualEventError(f"Data '{text}' non valida: usa il formato gg/mm/aa (es. 01/12/26).")
    return naive.replace(tzinfo=ITALY_TZ)
