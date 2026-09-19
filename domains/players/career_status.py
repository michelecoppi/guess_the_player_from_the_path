"""Euristica condivisa per inferire lo stato di attività di un giocatore dalla carriera.

Usata sia dal flusso di produzione (`approve_candidate`, `career_refresh`) sia dalla
normalizzazione dei candidati (`normalize_candidate`) per popolare `active`/`is_retired`
senza duplicare la logica in più punti.
"""
from __future__ import annotations

import re
from datetime import date
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


_ITALIAN_MONTHS = {
    "gennaio": 1,
    "febbraio": 2,
    "marzo": 3,
    "aprile": 4,
    "maggio": 5,
    "giugno": 6,
    "luglio": 7,
    "agosto": 8,
    "settembre": 9,
    "ottobre": 10,
    "novembre": 11,
    "dicembre": 12,
}


def _career_end_state(value: Any, today: date) -> Optional[bool]:
    """Return True when an explicit source career-end marker has passed."""
    text = " ".join(str(value or "").strip().lower().split())
    if not text:
        return None
    if any(marker in text for marker in ("in attività", "in attivita", "attivo")):
        return False

    full_date = re.search(r"\b(\d{1,2})\s+([a-zà]+)\s+(\d{4})\b", text)
    if full_date and full_date.group(2) in _ITALIAN_MONTHS:
        parsed = date(
            int(full_date.group(3)),
            _ITALIAN_MONTHS[full_date.group(2)],
            int(full_date.group(1)),
        )
        return parsed <= today

    year = re.search(r"\b(\d{4})\b", text)
    if year:
        parsed_year = int(year.group(1))
        if parsed_year != today.year:
            return parsed_year < today.year
        return None

    # A populated ``terminecarriera`` field is itself an explicit retirement signal.
    return True


def infer_active_status(
    career: Optional[list[dict]],
    current_year: Optional[int] = None,
    *,
    career_end: Any = None,
    current_date: Optional[date] = None,
) -> bool:
    """True se l'ultima tappa di carriera (per start_year) ha end_year nullo o >= anno corrente.

    - career vuota/None -> True (nessuna evidenza di ritiro, meglio un falso positivo di
      "attivo" che perdere un giocatore dal pool).
    - Tappe senza start_year sono ignorate nel trovare l'ultima tappa; se nessuna tappa ha
      uno start_year utilizzabile, si usa l'ultima tappa nell'ordine della lista.
    - end_year None -> attivo.
    - end_year numerico confrontato con current_year (default: anno corrente reale, ma
      iniettabile per testabilità).
    """
    today = current_date or date.today()
    explicit_end = _career_end_state(career_end, today)
    if explicit_end is not None:
        return not explicit_end

    if not career:
        return True

    year_ref = current_year if current_year is not None else today.year

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
