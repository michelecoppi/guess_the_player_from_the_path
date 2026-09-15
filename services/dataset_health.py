"""Stato di salute del dataset calciatori.

Il report statico e' condiviso da CLI/CI, Telegram Admin e dashboard. Le anomalie di
utilizzo (mai usato / usato troppo recentemente) vengono invece calcolate solo quando il
chiamante fornisce uno storico Daily: in questo modo la CI resta deterministica e non ha
mai bisogno di Firestore.
"""
from services.dates import shift_iso, today_iso
from services.difficulty import DIFFICULTY_ORDER, compute_difficulty
from services.player_pool import (
    _load_raw_players,
    filter_players,
    get_all_players,
    is_practice_only,
    load_config,
    normalize_league,
    validate_dataset,
)

SEVERITY_ORDER = ("error", "warning", "info")


def _load_templates():
    # import locale: event_generator importa firebase_service, che non serve per il report
    from services.event_generator import load_templates

    return load_templates()


def unclassified_leagues(players, config):
    """Campionati abbastanza frequenti da meritare una classificazione esplicita."""
    minimum = config.get("unclassified_league_warning_min", 20)
    classified = (
        set(config.get("top_leagues", []))
        | set(config.get("known_leagues", []))
        | set(config.get("obscure_leagues", []))
    )
    counts: dict[str, int] = {}
    for player in players:
        for stop in player.get("career", []):
            league = stop.get("league")
            if league and league not in classified:
                counts[league] = counts.get(league, 0) + 1
    return sorted(
        ((league, stints) for league, stints in counts.items() if stints >= minimum),
        key=lambda item: (-item[1], item[0]),
    )


def _anomaly(*, severity, category, cause, action, player_id=None, source="dataset", **extra):
    item = {
        "severity": severity,
        "category": category,
        "player_id": player_id,
        "cause": cause,
        "action": action,
        "source": source,
    }
    item.update(extra)
    return item


def classify_dataset_problem(problem, player_ids=()):
    """Trasforma il testo storico di ``validate_dataset`` in un record azionabile.

    ``validate_dataset`` resta la source of truth del gate CI; qui aggiungiamo solo
    struttura per Admin/diagnostica, senza duplicare le regole di validazione.
    """
    player_id = None
    cause = problem
    prefix, separator, remainder = problem.partition(": ")
    if separator and prefix in set(player_ids):
        player_id = prefix
        cause = remainder

    lowered = cause.lower()
    if "alias ambiguo" in lowered or "id duplicato" in lowered:
        category = "identity"
        action = "Rendere univoci id e alias prima di pubblicare il dataset."
    elif "traduz" in lowered:
        category = "translation"
        action = "Aggiungere o correggere la traduzione nel catalogo i18n e rieseguire il dataset check."
    elif "club '" in lowered or lowered.startswith("club "):
        category = "club"
        action = "Correggere la tappa o dichiarare esplicitamente l'eccezione di club nel config."
    elif "campionato" in lowered or "lega" in lowered:
        category = "league"
        action = "Canonicalizzare il nome del campionato e la sua classificazione in data/config.json."
    elif "tappa" in lowered or "carriera" in lowered:
        category = "career"
        action = "Completare o correggere la carriera del giocatore e rivalidare la scheda."
    else:
        category = "metadata"
        action = "Correggere i metadati della scheda e rieseguire scripts/dataset_report.py --strict."

    return _anomaly(
        severity="error",
        category=category,
        player_id=player_id,
        cause=cause,
        action=action,
    )


def club_spelling_anomalies(players):
    """Grafie diverse dello stesso club normalizzato, senza promuoverle a errore CI.

    E' intenzionalmente un warning: punteggiatura/abbreviazioni possono avere casi legittimi,
    ma in Admin devono essere visibili per evitare duplicati silenziosi nel dataset.
    """
    spellings: dict[str, dict[str, int]] = {}
    for player in players:
        for stop in player.get("career", []):
            team = stop.get("team")
            if not team:
                continue
            bucket = spellings.setdefault(normalize_league(team), {})
            bucket[team] = bucket.get(team, 0) + 1

    anomalies = []
    for variants in spellings.values():
        if len(variants) <= 1:
            continue
        detail = ", ".join(f"'{name}' ({count} tappe)" for name, count in sorted(variants.items()))
        anomalies.append(
            _anomaly(
                severity="warning",
                category="club",
                cause=f"Possibile club duplicato con grafie diverse: {detail}.",
                action="Verificare se e' lo stesso club; se si', scegliere una grafia canonica in tutte le carriere.",
            )
        )
    return anomalies


def build_usage_health(players, daily_paths, recent_days, today=None):
    """Analizza lo storico Daily gia' letto dal chiamante, senza accedere a Firestore."""
    today = today or today_iso()
    recent_days = max(1, int(recent_days))
    recent_cutoff = shift_iso(today, -(recent_days - 1))

    last_used: dict[str, str] = {}
    use_counts: dict[str, int] = {}
    for row in daily_paths or ():
        player_id = row.get("player_id")
        day = row.get("day")
        if not player_id or not day or day > today:
            continue
        use_counts[player_id] = use_counts.get(player_id, 0) + 1
        if player_id not in last_used or day > last_used[player_id]:
            last_used[player_id] = day

    anomalies = []
    selectable_ids = []
    for player in players:
        player_id = player.get("id")
        if not player_id:
            continue
        selectable_ids.append(player_id)
        last_day = last_used.get(player_id)
        if last_day is None:
            anomalies.append(
                _anomaly(
                    severity="info",
                    category="usage",
                    player_id=player_id,
                    cause="Mai usato in una Daily presente nello storico disponibile.",
                    action="Valutarlo come candidato prioritario nel planner se resta eleggibile e coerente con la difficolta'.",
                    source="daily_history",
                    usage_status="never_used",
                    last_used=None,
                )
            )
        elif last_day >= recent_cutoff:
            anomalies.append(
                _anomaly(
                    severity="warning",
                    category="usage",
                    player_id=player_id,
                    cause=f"Usato il {last_day}, dentro la finestra anti-ripetizione di {recent_days} giorni.",
                    action=f"Non riproporlo prima del {shift_iso(last_day, recent_days)}.",
                    source="daily_history",
                    usage_status="recently_used",
                    last_used=last_day,
                )
            )

    never_used = sum(1 for item in anomalies if item.get("usage_status") == "never_used")
    recently_used = sum(1 for item in anomalies if item.get("usage_status") == "recently_used")
    used_selectable = sum(1 for player_id in selectable_ids if player_id in last_used)
    return {
        "available": True,
        "history_rows": sum(use_counts.values()),
        "used_selectable": used_selectable,
        "never_used": never_used,
        "recently_used": recently_used,
        "recent_days": recent_days,
        "anomalies": anomalies,
    }


def _count_anomalies(anomalies):
    by_severity = {severity: 0 for severity in SEVERITY_ORDER}
    by_category: dict[str, int] = {}
    for item in anomalies:
        severity = item.get("severity", "info")
        by_severity[severity] = by_severity.get(severity, 0) + 1
        category = item.get("category", "other")
        by_category[category] = by_category.get(category, 0) + 1
    return {"by_severity": by_severity, "by_category": by_category, "total": len(anomalies)}


def attach_usage_health(report, daily_paths, today=None):
    """Arricchisce un report statico con lo storico Daily gia' recuperato dall'Admin."""
    usage = build_usage_health(
        report["selectable_players"],
        daily_paths,
        report["history_days_no_repeat"],
        today=today,
    )
    report = dict(report)
    report["usage_health"] = usage
    report["anomalies"] = list(report["anomalies"]) + usage["anomalies"]
    report["anomaly_counts"] = _count_anomalies(report["anomalies"])
    # Dettaglio interno utile solo all'aggancio; non deve diventare parte del contratto UI.
    report.pop("selectable_players", None)
    return report


def build_report(exclude_ids=None):
    config = load_config()
    raw_players = _load_raw_players()
    selectable = get_all_players(exclude_ids=exclude_ids)
    history_days = config.get("history_days_no_repeat", 60)

    by_difficulty = {level: 0 for level in DIFFICULTY_ORDER}
    for player in selectable:
        by_difficulty[compute_difficulty(player)] += 1

    rotation = config.get("difficulty_rotation", DIFFICULTY_ORDER)
    rotation_counts = {level: by_difficulty.get(level, 0) for level in rotation}

    templates = []
    for template in _load_templates():
        candidates = filter_players(selectable, template.get("rules", {}))
        duration = template.get("duration_days", config.get("event_default_duration_days", 5))
        templates.append(
            {
                "id": template["id"],
                "name": template["name"],
                "manual_only": bool(template.get("manual_only")),
                "candidates": len(candidates),
                "duration_days": duration,
                "ok": template.get("manual_only") or len(candidates) >= duration,
            }
        )

    dataset_problems = validate_dataset(raw_players, config=config)
    player_ids = {player.get("id") for player in raw_players if player.get("id")}
    anomalies = [classify_dataset_problem(problem, player_ids) for problem in dataset_problems]
    anomalies.extend(club_spelling_anomalies(raw_players))

    unclassified = unclassified_leagues(raw_players, config)
    for league, stints in unclassified:
        anomalies.append(
            _anomaly(
                severity="warning",
                category="league",
                cause=f"Campionato '{league}' non classificato ({stints} tappe).",
                action="Classificarlo in top_leagues, known_leagues o obscure_leagues in data/config.json.",
            )
        )

    warnings = []
    if unclassified:
        elenco = ", ".join(f"{league} ({stints})" for league, stints in unclassified)
        warnings.append(
            f"Campionati non classificati in data/config.json, con il numero di tappe: {elenco}. "
            "Classificali esplicitamente invece di lasciare il peso di ripiego."
        )
    if len(selectable) <= history_days:
        warnings.append(
            f"Solo {len(selectable)} giocatori selezionabili contro {history_days} giorni di "
            "anti-ripetizione: il pool si esaurisce e il bot dovra' riproporre giocatori gia' usati."
        )
    elif len(selectable) < history_days * 1.5:
        warnings.append(
            f"Margine ridotto: {len(selectable)} giocatori selezionabili per {history_days} giorni "
            "di anti-ripetizione. Conviene ampliare il dataset."
        )
    for level, count in rotation_counts.items():
        if count == 0:
            warnings.append(
                f"Nessun giocatore nella fascia di difficolta' '{level}': la rotazione ripieghera' su altre fasce."
            )
        elif count < 5:
            warnings.append(f"Solo {count} giocatori nella fascia '{level}': ripetizioni probabili.")
    for template in templates:
        if not template["ok"]:
            warnings.append(
                f"Evento '{template['id']}': {template['candidates']} candidati per {template['duration_days']} "
                "giorni di evento, i giorni si ripeteranno."
            )
    if dataset_problems:
        warnings.append(
            f"{len(dataset_problems)} problemi di integrita' nel dataset "
            "(vedi /admin_review o scripts/dataset_report.py)."
        )

    practice_reserved = sum(1 for player in raw_players if is_practice_only(player))
    return {
        "total": len(raw_players),
        "verified": sum(1 for player in raw_players if player.get("verified")),
        "selectable": len(selectable),
        "practice_reserved": practice_reserved,
        "excluded": len(raw_players) - len(selectable) - practice_reserved,
        "history_days_no_repeat": history_days,
        "autonomy_days": len(selectable),
        "by_difficulty": by_difficulty,
        "templates": templates,
        "dataset_problems": dataset_problems,
        "warnings": warnings,
        "anomalies": anomalies,
        "anomaly_counts": _count_anomalies(anomalies),
        "usage_health": {"available": False},
        # Campo interno: attach_usage_health lo consuma e lo rimuove prima dell'uso in Admin.
        "selectable_players": selectable,
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

    lines.extend(("", "Eventi tematici:"))
    for template in report["templates"]:
        flag = "manuale" if template["manual_only"] else ("ok" if template["ok"] else "POCHI CANDIDATI")
        lines.append(
            f"  {template['id']}: {template['candidates']} candidati / "
            f"{template['duration_days']} giorni [{flag}]"
        )

    if report["warnings"]:
        lines.extend(("", "Avvisi:"))
        for warning in report["warnings"]:
            lines.append(f"  - {warning}")

    if report["dataset_problems"]:
        lines.extend(("", "Problemi di integrita':"))
        for problem in report["dataset_problems"]:
            lines.append(f"  - {problem}")

    return "\n".join(lines)
