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


def _failure(player_id: str, message: str) -> CareerRefreshResult:
    return CareerRefreshResult(player_id=player_id, success=False, changed=False, message=message)


def _fetch_failure_message(source: str, result: Optional[AdapterResult]) -> str:
    if result is None:
        return f"Impossibile aggiornare da '{source}' (fonte non supportata)."
    detail = "; ".join(err.message for err in result.errors if getattr(err, "message", None))
    suffix = f": {detail}" if detail else ""
    return f"Impossibile aggiornare da '{source}' (recupero fallito){suffix}."


def _is_retryable_failure(result: Optional[AdapterResult]) -> bool:
    return result is not None and not result.success and any(err.retryable for err in result.errors)


def _resolve_safely(
    adapter_resolver: Callable[[str, str], Optional[AdapterResult]],
    source: str,
    source_id: str,
) -> tuple[Optional[AdapterResult], Optional[str]]:
    """(risultato, messaggio_di_errore): un'eccezione di rete non deve mai propagare."""
    try:
        return adapter_resolver(source, source_id), None
    except Exception as err:  # noqa: BLE001 - errore di rete/adapter
        return None, f"Errore durante il recupero dalla fonte '{source}': {type(err).__name__}: {err}"


def _apply_source_result(
    player: dict[str, Any],
    result: AdapterResult,
    current_year: Optional[int],
) -> tuple[bool, dict[str, Any]]:
    """Applica al giocatore (in place) il risultato fresco della fonte. Ritorna (changed, diff)."""
    existing_career = list(player.get("career", []))
    fresh_career = [dict(c) for c in result.career]
    diff = _diff_career(existing_career, fresh_career)

    merged_career = _merge_career(existing_career, fresh_career) if fresh_career else existing_career

    if fresh_career:
        new_active = infer_active_status(
            merged_career,
            current_year,
            career_end=result.source_metadata.get("career_end"),
        )
        old_active = player.get("active")
        if old_active != new_active:
            diff["active_changed"] = {"previous": old_active, "new": new_active}
        player["active"] = new_active

    changed = bool(diff)

    player["career"] = merged_career
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
    return changed, diff


def _success(player_id: str, changed: bool, diff: dict[str, Any]) -> CareerRefreshResult:
    message = (
        "Carriera aggiornata con modifiche."
        if changed
        else "Nessuna modifica rilevata (fonte già allineata)."
    )
    return CareerRefreshResult(player_id=player_id, success=True, changed=changed, message=message, diff=diff)


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
            return _failure(player_id, load_err or "Dataset di produzione non accessibile.")

        idx = next((i for i, p in enumerate(players) if p.get("id") == player_id), None)
        if idx is None:
            return _failure(player_id, f"Giocatore '{player_id}' non trovato nel dataset di produzione.")

        player = players[idx]
        source = player.get("source")
        source_id = player.get("source_id")
        if not source or not source_id:
            return _failure(
                player_id, "Nessuna fonte collegata: impossibile aggiornare la carriera automaticamente."
            )

        result, error_message = _resolve_safely(adapter_resolver, source, source_id)
        if error_message:
            return _failure(player_id, error_message)
        if result is None or not getattr(result, "success", False):
            return _failure(player_id, _fetch_failure_message(source, result))

        current_year = current_year_provider() if current_year_provider else None
        changed, diff = _apply_source_result(player, result, current_year)
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
            return _failure(
                player_id,
                f"Errore durante la scrittura del dataset di produzione: {type(err).__name__}: {err}",
            )

        diff["backup_snapshot"] = snapshot_name

    _append_audit_log(player_id, diff, log_path)
    return _success(player_id, changed, diff)


ProgressCallback = Callable[[int, int, CareerRefreshResult], None]


def refresh_players(
    player_ids: list[str],
    *,
    players_path: Path,
    backup_dir: Path,
    chunk_size: int = 20,
    delay_seconds: float = 1.5,
    dry_run: bool = False,
    adapter_resolver: Callable[[str, str], Optional[AdapterResult]] = resolve_adapter_result,
    wikipedia_adapter_factory: Optional[Callable[[], Any]] = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    current_year_provider: Optional[Callable[[], int]] = None,
    log_path: Optional[Path] = None,
    progress_callback: Optional[ProgressCallback] = None,
    max_unreachable_chunks: int = 2,
) -> list[CareerRefreshResult]:
    """Aggiorna la carriera dei giocatori indicati, un blocco alla volta.

    Per ogni blocco: le pagine Wikipedia si scaricano con una richiesta bulk, poi il
    dataset viene caricato, aggiornato e scritto **una sola volta** sotto lock. Un'
    interruzione (timeout, Ctrl+C, crash) lascia quindi salvato tutto il lavoro dei blocchi
    gia' completati, e un nuovo run riparte da li'. Il backup del dataset si fa una volta
    per run, prima della prima scrittura.

    Un risultato bulk fallito per un errore transitorio (timeout, 429, 5xx) viene
    ritentato con la richiesta singola prima di arrendersi. Se per
    `max_unreachable_chunks` blocchi consecutivi la fonte non restituisce nulla (Wikipedia
    giu' o in rate limit), il run si ferma e i giocatori rimasti tornano come falliti
    "non tentati", da rilanciare piu' tardi (0 disattiva l'interruzione).
    """
    players_path = Path(players_path)
    backup_dir = Path(backup_dir)
    log_path = Path(log_path) if log_path is not None else _default_log_path()
    lock_path = players_path.with_suffix(".lock")
    current_year = current_year_provider() if current_year_provider else None
    ordered_ids = list(dict.fromkeys(player_ids))
    total = len(ordered_ids)
    size = max(1, int(chunk_size))

    use_bulk = wikipedia_adapter_factory is not None or adapter_resolver is resolve_adapter_result
    if use_bulk and wikipedia_adapter_factory is None:
        from domains.players.adapters.wikipedia import WikipediaAdapter

        wikipedia_adapter_factory = WikipediaAdapter
    wikipedia_adapter = None

    results: list[CareerRefreshResult] = []
    snapshot_name: Optional[str] = None
    done = 0
    unreachable_chunks = 0

    def _report(result: CareerRefreshResult) -> None:
        nonlocal done
        done += 1
        results.append(result)
        if progress_callback is not None:
            try:
                progress_callback(done, total, result)
            except Exception:  # noqa: BLE001 - la UI non deve interrompere il batch
                pass

    for offset in range(0, total, size):
        chunk_ids = ordered_ids[offset : offset + size]
        players, load_err = load_production_players_strict(players_path)
        if players is None:
            for player_id in chunk_ids:
                _report(_failure(player_id, load_err or "Dataset di produzione non accessibile."))
            continue
        by_id = {p.get("id"): p for p in players}

        # 1. Rete, fuori dal lock: nessuno resta bloccato mentre Wikipedia risponde.
        fetched: dict[str, tuple[Optional[AdapterResult], Optional[str]]] = {}
        sources: dict[str, tuple[str, str]] = {}
        for player_id in chunk_ids:
            player = by_id.get(player_id)
            if player is not None and player.get("source") and player.get("source_id"):
                sources[player_id] = (str(player["source"]), str(player["source_id"]))

        bulk: dict[str, AdapterResult] = {}
        wikipedia_ids = [sid for src, sid in sources.values() if src == "wikipedia"]
        if use_bulk and wikipedia_ids and wikipedia_adapter_factory is not None:
            try:
                if wikipedia_adapter is None:
                    wikipedia_adapter = wikipedia_adapter_factory()
                bulk = wikipedia_adapter.fetch_players(wikipedia_ids)
            except Exception as err:  # noqa: BLE001 - fallback al resolver sequenziale
                _logger.warning("Prefetch Wikipedia batch non riuscito: %s", err)

        # Il fallback sequenziale ha senso solo se la fonte risponde: se l'intero bulk e'
        # fallito, altre N richieste singole con retry costerebbero ore senza risultato.
        bulk_alive = any(r.success for r in bulk.values())
        sequential_calls = 0
        for player_id, (source, source_id) in sources.items():
            prefetched = bulk.get(source_id) if source == "wikipedia" else None
            if prefetched is not None and (bulk_alive is False or not _is_retryable_failure(prefetched)):
                fetched[player_id] = (prefetched, None)
                continue
            if sequential_calls and delay_seconds > 0:
                sleep_fn(delay_seconds)
            sequential_calls += 1
            fetched[player_id] = _resolve_safely(adapter_resolver, source, source_id)

        if fetched and all(
            error_message is not None or _is_retryable_failure(result)
            for result, error_message in fetched.values()
        ):
            unreachable_chunks += 1
        else:
            unreachable_chunks = 0

        # 2. Applicazione e scrittura unica del blocco, sotto lock sul dataset piu' recente.
        chunk_results: list[CareerRefreshResult] = []
        audit: list[tuple[str, dict[str, Any]]] = []
        with ProcessFileLock(lock_path):
            players, load_err = load_production_players_strict(players_path)
            if players is None:
                chunk_results = [
                    _failure(pid, load_err or "Dataset di produzione non accessibile.") for pid in chunk_ids
                ]
            else:
                index_by_id = {p.get("id"): i for i, p in enumerate(players)}
                touched = False
                for player_id in chunk_ids:
                    idx = index_by_id.get(player_id)
                    if idx is None:
                        chunk_results.append(
                            _failure(player_id, f"Giocatore '{player_id}' non trovato nel dataset di produzione.")
                        )
                        continue
                    player = players[idx]
                    if player_id not in sources or (
                        (str(player.get("source")), str(player.get("source_id"))) != sources[player_id]
                    ):
                        chunk_results.append(
                            _failure(
                                player_id,
                                "Nessuna fonte collegata: impossibile aggiornare la carriera automaticamente."
                                if not player.get("source_id")
                                else "Fonte cambiata durante il refresh: rilancia il giocatore.",
                            )
                        )
                        continue
                    result, error_message = fetched[player_id]
                    if error_message:
                        chunk_results.append(_failure(player_id, error_message))
                        continue
                    if result is None or not getattr(result, "success", False):
                        chunk_results.append(
                            _failure(player_id, _fetch_failure_message(sources[player_id][0], result))
                        )
                        continue
                    changed, diff = _apply_source_result(player, result, current_year)
                    touched = True
                    chunk_results.append(_success(player_id, changed, diff))
                    audit.append((player_id, diff))

                if touched and not dry_run:
                    try:
                        if snapshot_name is None:
                            snapshot_name, _ = backup_production_dataset(players_path, backup_dir, "career_refresh")
                        atomic_write_production_dataset(players_path, players)
                    except Exception as err:
                        message = (
                            f"Errore durante la scrittura del dataset di produzione: {type(err).__name__}: {err}"
                        )
                        chunk_results = [
                            _failure(r.player_id, message) if r.success else r for r in chunk_results
                        ]
                        audit = []
                    else:
                        for r in chunk_results:
                            if r.success:
                                r.diff["backup_snapshot"] = snapshot_name

        if not dry_run:
            for player_id, diff in audit:
                _append_audit_log(player_id, diff, log_path)
        for chunk_result in chunk_results:
            _report(chunk_result)

        if max_unreachable_chunks and unreachable_chunks >= max_unreachable_chunks:
            _logger.warning("Refresh carriera interrotto: fonte non raggiungibile per %s blocchi", unreachable_chunks)
            for player_id in ordered_ids[offset + size :]:
                _report(
                    _failure(
                        player_id,
                        "Non tentato: la fonte non risponde (timeout/limiti di richieste). "
                        "Riprova più tardi.",
                    )
                )
            break

        if offset + size < total and delay_seconds > 0:
            sleep_fn(delay_seconds)

    return results


def select_players_for_refresh(
    players: list[dict[str, Any]],
    *,
    include_inactive: bool = False,
    checked_before: Optional[str] = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(giocatori_da_aggiornare, giocatori_senza_fonte) per un refresh massivo.

    `active` assente vale come attivo (stato sconosciuto). `checked_before` (ISO UTC)
    esclude chi e' gia' stato controllato da quel momento in poi: serve a riprendere un
    run interrotto senza ricontattare i giocatori gia' aggiornati.
    """
    pool = [p for p in players if include_inactive or p.get("active", True)]
    if checked_before:
        pool = [p for p in pool if str(p.get("career_last_checked_at") or "") < checked_before]
    with_source = [p for p in pool if p.get("source_id")]
    without_source = [p for p in pool if not p.get("source_id")]
    return with_source, without_source


def refresh_all_active_players(
    *,
    players_path: Path,
    backup_dir: Path,
    delay_seconds: float = 1.5,
    adapter_resolver: Callable[[str, str], Optional[AdapterResult]] = resolve_adapter_result,
    wikipedia_adapter_factory: Optional[Callable[[], Any]] = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    log_path: Optional[Path] = None,
    include_inactive: bool = False,
    checked_before: Optional[str] = None,
    chunk_size: int = 20,
    progress_callback: Optional[ProgressCallback] = None,
) -> tuple[list[CareerRefreshResult], list[dict[str, Any]]]:
    """Aggiorna la carriera di tutti i giocatori attivi con una fonte collegata.

    Ritorna (risultati, giocatori_senza_source_id).
    """
    players, _ = load_production_players_strict(Path(players_path))
    if players is None:
        return [], []

    with_source, without_source = select_players_for_refresh(
        players, include_inactive=include_inactive, checked_before=checked_before
    )
    results = refresh_players(
        [p["id"] for p in with_source],
        players_path=players_path,
        backup_dir=backup_dir,
        chunk_size=chunk_size,
        delay_seconds=delay_seconds,
        adapter_resolver=adapter_resolver,
        wikipedia_adapter_factory=wikipedia_adapter_factory,
        sleep_fn=sleep_fn,
        log_path=log_path,
        progress_callback=progress_callback,
    )
    return results, without_source
