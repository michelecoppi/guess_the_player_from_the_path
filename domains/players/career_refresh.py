"""Refresh mirato della carriera dei giocatori già in produzione, a partire dalla fonte
collegata (`source`/`source_id`).

Riusa lo stesso pattern di sicurezza di `approve_candidate` in
`domains/players/candidates/review.py`: lock di processo, backup prima della scrittura,
scrittura atomica, rollback su fallimento. Non tocca la coda dei candidati: opera
direttamente su `data/players.json`.
"""

from __future__ import annotations

import json
import logging
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from domains.players.adapters.base import AdapterResult
from domains.players.adapters.resolver import resolve_adapter_result
from domains.players.career_status import infer_active_status
from domains.players.production_dataset import (
    atomic_write_production_dataset,
    backup_production_dataset,
    load_production_players_strict,
)
from services.career_order import order_career
from services.repos.file_lock import ProcessFileLock

observability: Any
try:
    from services import observability
except Exception:  # pragma: no cover - fallback difensivo
    observability = None

_logger = logging.getLogger(__name__)

_CAREER_FIELDS = ("team", "country", "league", "start_year", "end_year", "loan", "apps", "goals")


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class CareerRefreshResult:
    player_id: str
    success: bool
    changed: bool
    message: str
    diff: dict[str, Any] = field(default_factory=dict)


def _clean_career_entry(stop: dict[str, Any]) -> dict[str, Any]:
    return {k: stop[k] for k in _CAREER_FIELDS if k in stop and stop[k] is not None}


def _team_key(stop: dict[str, Any]) -> str:
    return str(stop.get("team", "")).strip().lower()


def _diff_career(existing: list[dict[str, Any]], fresh: list[dict[str, Any]]) -> dict[str, Any]:
    """Confronta la carriera esistente con quella appena recuperata dalla fonte.

    Struttura del diff: liste leggibili di aggiunte, trasferimenti (end_year cambiato su
    una tappa esistente) e aggiornamenti di statistiche (apps/goals).
    """
    existing_by_team: dict[str, dict[str, Any]] = {_team_key(s): s for s in existing if s.get("team")}

    new_teams: list[str] = []
    transfers: list[dict[str, Any]] = []
    stat_changes: list[dict[str, Any]] = []

    for fresh_stop in fresh:
        key = _team_key(fresh_stop)
        if not key:
            continue
        prev = existing_by_team.get(key)
        if prev is None:
            new_teams.append(fresh_stop.get("team", key))
            continue

        prev_end = prev.get("end_year")
        fresh_end = fresh_stop.get("end_year")
        if prev_end != fresh_end:
            transfers.append(
                {
                    "team": fresh_stop.get("team", key),
                    "previous_end_year": prev_end,
                    "new_end_year": fresh_end,
                }
            )

        for stat in ("apps", "goals"):
            prev_val = prev.get(stat)
            fresh_val = fresh_stop.get(stat)
            if fresh_val is not None and fresh_val != prev_val:
                stat_changes.append(
                    {
                        "team": fresh_stop.get("team", key),
                        "field": stat,
                        "previous": prev_val,
                        "new": fresh_val,
                    }
                )

    diff: dict[str, Any] = {}
    if new_teams:
        diff["new_teams"] = new_teams
    if transfers:
        diff["team_changes"] = transfers
    if stat_changes:
        diff["stat_changes"] = stat_changes
    return diff


def _merge_career(existing: list[dict[str, Any]], fresh: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Applica le tappe fresche sulla carriera esistente: arricchisce/aggiorna quelle note,
    aggiunge quelle nuove. Non elimina mai tappe presenti solo nella carriera esistente."""
    merged: list[dict[str, Any]] = [dict(s) for s in existing]
    merged_by_team = {_team_key(s): s for s in merged if s.get("team")}

    for fresh_stop in fresh:
        clean_fresh = _clean_career_entry(fresh_stop)
        key = _team_key(clean_fresh)
        if not key:
            continue
        if key in merged_by_team:
            merged_by_team[key].update(clean_fresh)
        else:
            merged.append(clean_fresh)
            merged_by_team[key] = clean_fresh

    return order_career(merged)


def _default_log_path() -> Path:
    base_dir = Path(__file__).resolve().parents[2]
    return base_dir / "data" / "logs" / "career_refresh.log"


def _append_audit_log(player_id: str, diff: dict[str, Any], log_path: Path) -> None:
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {"player_id": player_id, "timestamp": _now_utc_iso(), "diff": diff}
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as err:  # noqa: BLE001 - il logging non deve mai far fallire il refresh
        if observability is not None:
            try:
                observability.log_event(
                    "career_refresh.audit_log_failed",
                    logging.WARNING,
                    exc_info=err,
                    error_type=type(err).__name__,
                )
                return
            except Exception:
                pass
        _logger.warning("Impossibile scrivere career_refresh.log per %s: %s", player_id, err)


def refresh_player_career(
    player_id: str,
    *,
    players_path: Path,
    backup_dir: Path,
    adapter_resolver: Callable[[str, str], Optional[AdapterResult]] = resolve_adapter_result,
    current_year_provider: Optional[Callable[[], int]] = None,
    log_path: Optional[Path] = None,
) -> CareerRefreshResult:
    """Ricontrolla la fonte collegata di un giocatore e aggiorna carriera/attivita' se serve."""
    players_path = Path(players_path)
    backup_dir = Path(backup_dir)
    log_path = Path(log_path) if log_path is not None else _default_log_path()
    lock_path = players_path.with_suffix(".lock")

    with ProcessFileLock(lock_path):
        players, load_err = load_production_players_strict(players_path)
        if players is None:
            return CareerRefreshResult(
                player_id=player_id,
                success=False,
                changed=False,
                message=load_err or "Dataset di produzione non accessibile.",
            )

        idx = next((i for i, p in enumerate(players) if p.get("id") == player_id), None)
        if idx is None:
            return CareerRefreshResult(
                player_id=player_id,
                success=False,
                changed=False,
                message=f"Giocatore '{player_id}' non trovato nel dataset di produzione.",
            )

        player = players[idx]
        source = player.get("source")
        source_id = player.get("source_id")
        if not source or not source_id:
            return CareerRefreshResult(
                player_id=player_id,
                success=False,
                changed=False,
                message="Nessuna fonte collegata: impossibile aggiornare la carriera automaticamente.",
            )

        try:
            result = adapter_resolver(source, source_id)
        except Exception as err:  # noqa: BLE001 - errore di rete/adapter, non deve propagare
            return CareerRefreshResult(
                player_id=player_id,
                success=False,
                changed=False,
                message=f"Errore durante il recupero dalla fonte '{source}': {type(err).__name__}: {err}",
            )

        if result is None or not getattr(result, "success", False):
            reason = "fonte non supportata" if result is None else "recupero fallito"
            return CareerRefreshResult(
                player_id=player_id,
                success=False,
                changed=False,
                message=f"Impossibile aggiornare da '{source}' ({reason}).",
            )

        existing_career = list(player.get("career", []))
        fresh_career = [dict(c) for c in result.career]
        diff = _diff_career(existing_career, fresh_career)

        merged_career = _merge_career(existing_career, fresh_career) if fresh_career else existing_career

        old_active = player.get("active")
        if fresh_career:
            year_provider = current_year_provider() if current_year_provider else None
            new_active = infer_active_status(
                merged_career,
                year_provider,
                career_end=result.source_metadata.get("career_end"),
            )
            if old_active != new_active:
                diff["active_changed"] = {"previous": old_active, "new": new_active}

        changed = bool(diff)

        player["career"] = merged_career
        if fresh_career:
            player["active"] = new_active
        player["career_last_checked_at"] = _now_utc_iso()
        revision_id = result.source_metadata.get("revision_id")
        wikidata_id = result.source_metadata.get("wikidata_id")
        if revision_id is not None:
            player["source_revision_id"] = revision_id
        if wikidata_id:
            player["wikidata_id"] = wikidata_id
        career_end = result.source_metadata.get("career_end")
        if career_end:
            player["source_career_end"] = career_end
        players[idx] = player

        snapshot_name, snapshot_dest = backup_production_dataset(players_path, backup_dir, player_id)
        try:
            atomic_write_production_dataset(players_path, players)
        except Exception as err:
            try:
                if snapshot_dest.is_file():
                    shutil.copy2(str(snapshot_dest), str(players_path))
            except Exception:
                pass
            return CareerRefreshResult(
                player_id=player_id,
                success=False,
                changed=False,
                message=f"Errore durante la scrittura del dataset di produzione: {type(err).__name__}: {err}",
            )

        diff["backup_snapshot"] = snapshot_name

    _append_audit_log(player_id, diff, log_path)

    message = (
        "Carriera aggiornata con modifiche."
        if changed
        else "Nessuna modifica rilevata (fonte già allineata)."
    )
    return CareerRefreshResult(player_id=player_id, success=True, changed=changed, message=message, diff=diff)


def refresh_all_active_players(
    *,
    players_path: Path,
    backup_dir: Path,
    delay_seconds: float = 1.5,
    adapter_resolver: Callable[[str, str], Optional[AdapterResult]] = resolve_adapter_result,
    wikipedia_adapter_factory: Optional[Callable[[], Any]] = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    log_path: Optional[Path] = None,
) -> tuple[list[CareerRefreshResult], list[dict[str, Any]]]:
    """Aggiorna la carriera di tutti i giocatori attivi con una fonte collegata.

    Ritorna (risultati, giocatori_senza_source_id).
    """
    players_path = Path(players_path)
    players, load_err = load_production_players_strict(players_path)
    if players is None:
        return [], []

    active_players = [p for p in players if p.get("active", True)]
    with_source = [p for p in active_players if p.get("source_id")]
    without_source = [p for p in active_players if not p.get("source_id")]

    prefetched_wikipedia: dict[str, AdapterResult] = {}
    wikipedia_ids = [
        str(player["source_id"]) for player in with_source if player.get("source") == "wikipedia"
    ]
    if wikipedia_ids and (
        wikipedia_adapter_factory is not None or adapter_resolver is resolve_adapter_result
    ):
        if wikipedia_adapter_factory is None:
            from domains.players.adapters.wikipedia import WikipediaAdapter

            wikipedia_adapter_factory = WikipediaAdapter
        try:
            prefetched_wikipedia = wikipedia_adapter_factory().fetch_players(wikipedia_ids)
        except Exception as err:  # noqa: BLE001 - fallback al resolver sequenziale
            _logger.warning("Prefetch Wikipedia batch non riuscito: %s", err)

    results: list[CareerRefreshResult] = []
    for i, player in enumerate(with_source):
        source = str(player.get("source") or "")
        source_id = str(player.get("source_id") or "")
        prefetched = prefetched_wikipedia.get(source_id)

        def player_resolver(
            requested_source: str,
            requested_id: str,
            *,
            _prefetched: Optional[AdapterResult] = prefetched,
        ) -> Optional[AdapterResult]:
            if requested_source == "wikipedia" and _prefetched is not None:
                return _prefetched
            return adapter_resolver(requested_source, requested_id)

        results.append(
            refresh_player_career(
                player["id"],
                players_path=players_path,
                backup_dir=backup_dir,
                adapter_resolver=player_resolver,
                log_path=log_path,
            )
        )
        used_sequential_request = not (source == "wikipedia" and source_id in prefetched_wikipedia)
        if used_sequential_request and i < len(with_source) - 1 and delay_seconds > 0:
            sleep_fn(delay_seconds)

    return results, without_source
