"""Stato di salute del dataset calciatori.

Serve a rispondere alla domanda pratica "il pool basta ancora?" senza aprire il database:
quanti giocatori sono realmente selezionabili, per quanti giorni il bot puo' andare avanti
senza ripetere nessuno, quali fasce di difficolta' sono scoperte e quali eventi tematici
non hanno abbastanza candidati.

Usato da `scripts/dataset_report.py` (CI e riga di comando) e dal comando Telegram /admin_pool.
"""
from services.difficulty import DIFFICULTY_ORDER, compute_difficulty
from services.player_pool import (
    _load_raw_players,
    filter_players,
    get_all_players,
    is_practice_only,
    load_config,
    validate_dataset,
)


def _load_templates():
    # import locale: event_generator importa firebase_service, che non serve per il report
    from services.event_generator import load_templates

    return load_templates()


def build_report(exclude_ids=None):
    config = load_config()
    raw_players = _load_raw_players()
    selectable = get_all_players(exclude_ids=exclude_ids)
    history_days = config.get("history_days_no_repeat", 60)

    by_difficulty = {level: 0 for level in DIFFICULTY_ORDER}
    for player in selectable:
        by_difficulty[compute_difficulty(player)] += 1

    rotation = config.get("difficulty_rotation", DIFFICULTY_ORDER)
    # Con la rotazione delle difficolta', la fascia piu' povera e' quella che determina
    # quando il generatore inizia a "ripiegare" su un'altra difficolta'.
    rotation_counts = {level: by_difficulty.get(level, 0) for level in rotation}

    templates = []
    for template in _load_templates():
        candidates = filter_players(selectable, template.get("rules", {}))
        duration = template.get("duration_days", config.get("event_default_duration_days", 5))
        templates.append({
            "id": template["id"],
            "name": template["name"],
            "manual_only": bool(template.get("manual_only")),
            "candidates": len(candidates),
            "duration_days": duration,
            "ok": template.get("manual_only") or len(candidates) >= duration,
        })

    dataset_problems = validate_dataset(raw_players)

    warnings = []
    if len(selectable) <= history_days:
        warnings.append(
            f"Solo {len(selectable)} giocatori selezionabili contro {history_days} giorni di "
            f"anti-ripetizione: il pool si esaurisce e il bot dovra' riproporre giocatori gia' usati."
        )
    elif len(selectable) < history_days * 1.5:
        warnings.append(
            f"Margine ridotto: {len(selectable)} giocatori selezionabili per {history_days} giorni "
            f"di anti-ripetizione. Conviene ampliare il dataset."
        )
    for level, count in rotation_counts.items():
        if count == 0:
            warnings.append(f"Nessun giocatore nella fascia di difficolta' '{level}': la rotazione ripieghera' su altre fasce.")
        elif count < 5:
            warnings.append(f"Solo {count} giocatori nella fascia '{level}': ripetizioni probabili.")
    for template in templates:
        if not template["ok"]:
            warnings.append(
                f"Evento '{template['id']}': {template['candidates']} candidati per {template['duration_days']} "
                f"giorni di evento, i giorni si ripeteranno."
            )
    if dataset_problems:
        warnings.append(f"{len(dataset_problems)} problemi di integrita' nel dataset (vedi /admin_review o scripts/dataset_report.py).")

    return {
        "total": len(raw_players),
        "verified": sum(1 for p in raw_players if p.get("verified")),
        "selectable": len(selectable),
        # Riservati e scartati vanno contati separatamente: i primi sono una scelta (fanno
        # da materiale per l'allenamento), i secondi un problema da guardare.
        "practice_reserved": sum(1 for p in raw_players if is_practice_only(p)),
        "excluded": len(raw_players) - len(selectable) - sum(1 for p in raw_players if is_practice_only(p)),
        "history_days_no_repeat": history_days,
        "autonomy_days": len(selectable),
        "by_difficulty": by_difficulty,
        "templates": templates,
        "dataset_problems": dataset_problems,
        "warnings": warnings,
    }


def format_report_text(report):
    lines = [
        f"Giocatori nel dataset: {report['total']}",
        f"  verificati: {report['verified']}",
        f"  selezionabili in automatico: {report['selectable']}",
        f"  riservati all'allenamento (mai come sfida del giorno): {report['practice_reserved']}",
        f"  esclusi (non verificati o dati incompleti): {report['excluded']}",
        "",
        f"Autonomia senza ripetizioni: {report['autonomy_days']} giorni "
        f"(anti-ripetizione configurata su {report['history_days_no_repeat']} giorni)",
        "",
        "Per difficolta':",
    ]
    for level in DIFFICULTY_ORDER:
        lines.append(f"  {level}: {report['by_difficulty'].get(level, 0)}")

    lines.append("")
    lines.append("Eventi tematici:")
    for template in report["templates"]:
        flag = "manuale" if template["manual_only"] else ("ok" if template["ok"] else "POCHI CANDIDATI")
        lines.append(f"  {template['id']}: {template['candidates']} candidati / {template['duration_days']} giorni [{flag}]")

    if report["warnings"]:
        lines.append("")
        lines.append("Avvisi:")
        for warning in report["warnings"]:
            lines.append(f"  - {warning}")

    if report["dataset_problems"]:
        lines.append("")
        lines.append("Problemi di integrita':")
        for problem in report["dataset_problems"]:
            lines.append(f"  - {problem}")

    return "\n".join(lines)
