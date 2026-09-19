"""Euristica condivisa per inferire lo stato di attività di un giocatore dalla carriera.

Usata sia dal flusso di produzione (`approve_candidate`, `career_refresh`) sia dalla
normalizzazione dei candidati (`normalize_candidate`) per popolare `active`/`is_retired`
senza duplicare la logica in più punti.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional


def _safe_year(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return None


def infer_active_status(career: Optional[list[dict]], current_year: Optional[int] = None) -> bool:
    """True se l'ultima tappa di carriera (per start_year) ha end_year nullo o >= anno corrente.

    - career vuota/None -> True (nessuna evidenza di ritiro, meglio un falso positivo di
      "attivo" che perdere un giocatore dal pool).
    - Tappe senza start_year sono ignorate nel trovare l'ultima tappa; se nessuna tappa ha
      uno start_year utilizzabile, si usa l'ultima tappa nell'ordine della lista.
    - end_year None -> attivo.
    - end_year numerico confrontato con current_year (default: anno corrente reale, ma
      iniettabile per testabilità).
    """
    if not career:
        return True

    year_ref = current_year if current_year is not None else datetime.now().year

    last_stop: Optional[dict] = None
    best_start: Optional[int] = None
    for stop in career:
        if not isinstance(stop, dict):
            continue
        start = _safe_year(stop.get("start_year"))
        if start is None:
            continue
        if best_start is None or start >= best_start:
            best_start = start
            last_stop = stop

    if last_stop is None:
        # Nessuna tappa con start_year utilizzabile: fallback sull'ordine della lista.
        for stop in reversed(career):
            if isinstance(stop, dict):
                last_stop = stop
                break

    if last_stop is None:
        return True

    end_year = _safe_year(last_stop.get("end_year"))
    if end_year is None:
        return True

    return end_year >= year_ref
