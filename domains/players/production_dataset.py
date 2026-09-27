"""Funzioni standalone per leggere/scrivere/backuppare `data/players.json` in sicurezza.

Estratte da `CandidateReviewService` (domains/players/candidates/review.py) per essere
riusabili anche fuori dal flusso di review (backfill, refresh carriera). Nessuna logica di
dominio qui: solo I/O sicuro (fail-closed sulla lettura, scrittura atomica, backup con nome
collision-free). Il chiamante resta responsabile del locking (`ProcessFileLock`) attorno alle
sezioni critiche multi-step.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from services import observability


def load_production_players_strict(players_path: Path) -> tuple[Optional[list[dict[str, Any]]], Optional[str]]:
    """Carica il dataset di produzione con semantica FAIL-CLOSED per mutazioni.

    Ritorna (players, None) in caso di successo, oppure (None, error_message) se il
    dataset è mancante, illeggibile o strutturalmente non valido.
    """
    players_path = Path(players_path)
    if not players_path.is_file():
        observability.log_event("candidate.dataset.unreadable", logging.ERROR, reason="missing")
        return None, "Dataset di produzione mancante o non accessibile."
    try:
        with open(players_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as err:
        observability.log_event("candidate.dataset.unreadable", logging.ERROR, exc_info=err, reason="invalid_json")
        return None, "Dataset di produzione non valido o corrotto."

    if not isinstance(data, dict) or "players" not in data or not isinstance(data["players"], list):
        observability.log_event("candidate.dataset.unreadable", logging.ERROR, reason="invalid_structure")
        return None, "Struttura del dataset di produzione inattesa o non conforme."

    return list(data["players"]), None


def atomic_write_production_dataset(players_path: Path, players: list[dict[str, Any]]) -> None:
    """Scrittura atomica sicura del dataset di produzione con fsync e replace."""
    players_path = Path(players_path)
    comment = (
        "Dataset locale curato di carriere calcistiche. 'verified': true = dati controllati e pronti "
        "per la selezione automatica."
    )
    if players_path.is_file():
        try:
            with open(players_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
                comment = existing.get("_comment", comment)
        except Exception:
            pass

    payload = {
        "_comment": comment,
        "players": players,
    }

    parent_dir = players_path.parent
    parent_dir.mkdir(parents=True, exist_ok=True)

    handle, tmp_path_str = tempfile.mkstemp(dir=str(parent_dir), prefix=".tmp_players_", suffix=".json")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path_str, str(players_path))
    except Exception:
        if os.path.exists(tmp_path_str):
            try:
                os.remove(tmp_path_str)
            except OSError:
                pass
        raise


def backup_production_dataset(players_path: Path, backup_dir: Path, tag: str) -> tuple[str, Path]:
    """Crea una copia di backup con identificatore univoco e sicuro (collision-free)."""
    players_path = Path(players_path)
    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    clean_tag = re.sub(r"[^a-zA-Z0-9]+", "_", str(tag)).strip("_")[:20] or "snap"
    random_suffix = uuid.uuid4().hex[:8]
    filename = f"players-review-{stamp}_{clean_tag}_{random_suffix}.json"
    dest = backup_dir / filename

    if players_path.is_file():
        shutil.copy2(str(players_path), str(dest))
    return filename, dest
