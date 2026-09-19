"""Risolutore di adapter standard per source_name/source_id (#15, #26).

Estratto da `_default_adapter_resolver` in `domains/players/candidates/review.py` per essere
riusabile anche fuori dal servizio di review (refresh carriera, backfill, admin UI).
"""
from __future__ import annotations

from typing import Optional

from domains.players.adapters.base import AdapterResult


def resolve_adapter_result(source: str, source_id: str) -> Optional[AdapterResult]:
    """Risolve un `AdapterResult` fresco per la coppia (source, source_id) data.

    Ritorna None se la fonte non è supportata (nessun adapter registrato).
    """
    src = str(source).strip().lower()
    if src == "wikipedia":
        from domains.players.adapters.wikipedia import WikipediaAdapter

        return WikipediaAdapter().fetch_player(source_id)
    elif src == "wikidata":
        from domains.players.adapters.wikidata import WikidataAdapter

        return WikidataAdapter().fetch_player(source_id)
    return None
