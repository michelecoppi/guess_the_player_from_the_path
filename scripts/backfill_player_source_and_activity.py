"""Backfill di `source`/`source_id`/`active` sui giocatori di
produzione (`data/players.json`) che non hanno ancora una fonte collegata.

Step 1 del piano di rilevamento fine-mercato: SOLO flagging (fonte + stato attivita').
Non tocca mai `career`: quello e' compito dello step 2 (`domains/players/career_refresh.py`).

Uso:
    python scripts/backfill_player_source_and_activity.py [--dry-run] [--delay SECONDI]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from domains.players.adapters.base import AdapterErrorType, AdapterResult, AdapterSearchResult  # noqa: E402
from domains.players.career_status import infer_active_status  # noqa: E402
from domains.players.production_dataset import (  # noqa: E402
    atomic_write_production_dataset,
    load_production_players_strict,
)

_logger = logging.getLogger("backfill_player_source")

_BASE_DIR = Path(__file__).resolve().parents[1]
_PLAYERS_PATH = _BASE_DIR / "data" / "players.json"
_LOGS_DIR = _BASE_DIR / "data" / "logs"


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clean_name(name: str) -> str:
    return " ".join(str(name or "").strip().lower().split())


def find_high_confidence_match(
    player: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> Optional[dict[str, Any]]:
    """Sceglie, tra una lista di risultati candidati {"identifier", "name", "birth_year"},
    quello ad "alta confidenza" per il player dato, oppure None se ambiguo.

    Regole:
    - Un solo candidato compatibile per birth_year (quando entrambi lo espongono) -> match.
    - Se non e' possibile confrontare i birth_year, match SOLO se c'e' un unico candidato con
      nome quasi identico (case-insensitive, dopo pulizia spazi) al player.
    """
    if not candidates:
        return None

    player_birth_year = player.get("birth_year")
    player_name = _clean_name(player.get("full_name", ""))

    if player_birth_year is not None:
        birth_matches = [
            c
            for c in candidates
            if c.get("birth_year") is not None and c.get("birth_year") == player_birth_year
        ]
        if len(birth_matches) == 1:
            return birth_matches[0]
        if len(birth_matches) > 1:
            return None  # ambiguo
        # Se conosciamo l'anno del record locale, un nome uguale non basta: pagine di
        # disambiguazione e redirect di omonimi possono avere lo stesso display name.
        return None

    name_matches = [c for c in candidates if _clean_name(c.get("name", "")) == player_name]
    if len(name_matches) == 1:
        return name_matches[0]

    return None


def _has_retryable_errors(result: AdapterResult | AdapterSearchResult) -> bool:
    return any(
        getattr(error, "retryable", False)
        or getattr(error, "error_type", None) == AdapterErrorType.RATE_LIMIT
        for error in (result.errors or [])
    )


def _fetch_with_backoff(
    adapter,
    identifier: str,
    *,
    max_retries: int = 3,
    base_delay: float = 5.0,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> AdapterResult:
    """Fetcha un player con backoff esponenziale sui 429 (rate limit).

    Wikipedia/Wikidata applicano throttling aggressivo su burst di richieste: senza
    questo backoff un run su centinaia di player finisce per essere quasi tutto
    rate-limited dopo i primi ~40 giocatori.
    """
    attempt = 0
    while True:
        try:
            fetched = adapter.fetch_player(identifier)
        except Exception as err:  # noqa: BLE001
            _logger.warning("Errore fetch %s/%s: %s", adapter.source_name, identifier, err)
            raise
        if fetched.success or not _has_retryable_errors(fetched) or attempt >= max_retries:
            return fetched
        wait = base_delay * (2**attempt)
        _logger.info(
            "Rate limited su %s/%s, retry tra %.1fs (tentativo %d)",
            adapter.source_name,
            identifier,
            wait,
            attempt + 1,
        )
        sleep_fn(wait)
        attempt += 1


_DEFAULT_MAX_CANDIDATES_PER_SOURCE = 2


def _try_source(
    player: dict[str, Any],
    adapter,
    identifiers: list[str],
    *,
    max_candidates: int = _DEFAULT_MAX_CANDIDATES_PER_SOURCE,
    sleep_fn: Callable[[float], None] = time.sleep,
    request_delay: float = 0.5,
) -> tuple[Optional[dict[str, Any]], bool]:
    """Fetcha al massimo `max_candidates` risultati di ricerca (invece di tutti e 5 come in
    origine) e applica `find_high_confidence_match` sull'insieme raccolto.

    NON decide dopo il primo fetch riuscito: due pagine diverse potrebbero condividere nome e
    anno di nascita, e l'ambiguita' si rileva solo confrontando ALMENO due candidati. Il taglio
    a `max_candidates` (default 2, invece di 5) e' gia' sufficiente a ridurre drasticamente il
    volume di richieste verso Wikipedia/Wikidata e il rischio di rate limiting (429) su run
    massivi, senza perdere la capacita' di rilevare un'ambiguita' a due candidati.

    Ritorna (match_o_None, rate_limited).
    """
    capped = identifiers[:max_candidates]
    seen: list[dict[str, Any]] = []
    hit_rate_limit = False
    for i, identifier in enumerate(capped):
        try:
            fetched: AdapterResult = _fetch_with_backoff(adapter, identifier, sleep_fn=sleep_fn)
        except Exception:
            continue
        if i < len(capped) - 1 and request_delay > 0:
            sleep_fn(request_delay)
        if not fetched.success:
            if _has_retryable_errors(fetched):
                hit_rate_limit = True
            continue
        if not fetched.player_name:
            continue
        seen.append(
            {
                "identifier": identifier,
                "name": fetched.player_name,
                "birth_year": fetched.birth_year,
                "source": adapter.source_name,
                "result": fetched,
            }
        )
    return find_high_confidence_match(player, seen), hit_rate_limit


def _resolve_source_for_player(
    player: dict[str, Any],
    *,
    wikipedia_adapter,
    wikidata_adapter,
    sleep_fn: Callable[[float], None] = time.sleep,
    max_candidates_per_source: int = _DEFAULT_MAX_CANDIDATES_PER_SOURCE,
) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """Ritorna (match, None) oppure (None, motivo) — motivo None significa 'nessun match'."""
    full_name = player.get("full_name")
    if not full_name:
        return None, "full_name mancante"

    temporary_failure = False
    wiki_search: AdapterSearchResult = wikipedia_adapter.search_player(
        full_name, limit=max_candidates_per_source
    )
    if wiki_search.success and wiki_search.identifiers:
        match, retryable = _try_source(
            player,
            wikipedia_adapter,
            wiki_search.identifiers,
            max_candidates=max_candidates_per_source,
            sleep_fn=sleep_fn,
        )
        temporary_failure = temporary_failure or retryable
        if match:
            return match, None
    elif not wiki_search.success:
        temporary_failure = temporary_failure or _has_retryable_errors(wiki_search)

    wikidata_search: AdapterSearchResult = wikidata_adapter.search_player(
        full_name, limit=max_candidates_per_source
    )
    if wikidata_search.success and wikidata_search.identifiers:
        match, retryable = _try_source(
            player,
            wikidata_adapter,
            wikidata_search.identifiers,
            max_candidates=max_candidates_per_source,
            sleep_fn=sleep_fn,
        )
        temporary_failure = temporary_failure or retryable
        if match:
            return match, None
    elif not wikidata_search.success:
        temporary_failure = temporary_failure or _has_retryable_errors(wikidata_search)

    if temporary_failure:
        return None, "errore temporaneo/rate limit: da ricontrollare in un run successivo"

    return None, "nessun match ad alta confidenza"


def _bulk_wikipedia_matches(
    players: list[dict[str, Any]],
    wikipedia_adapter: Any,
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Resolve exact Wikipedia titles in batched API calls when supported.

    Older test doubles and alternative adapters may only implement ``fetch_player``;
    those callers transparently retain the sequential search path.
    """
    fetch_many = getattr(wikipedia_adapter, "fetch_players", None)
    if not callable(fetch_many):
        return {}, {}

    names = [str(player.get("full_name") or "").strip() for player in players]
    names = [name for name in names if name]
    if not names:
        return {}, {}

    fetched_by_name = fetch_many(names)
    matches: dict[str, dict[str, Any]] = {}
    temporary_failures: dict[str, str] = {}
    for player in players:
        player_id = str(player.get("id") or "")
        full_name = str(player.get("full_name") or "").strip()
        result = fetched_by_name.get(full_name)
        if result is None:
            continue
        if not result.success:
            if _has_retryable_errors(result):
                temporary_failures[player_id] = (
                    "errore temporaneo/rate limit nel recupero Wikipedia batch: "
                    "da ricontrollare in un run successivo"
                )
            continue

        identifier = str(result.source_metadata.get("canonical_title") or result.source_id)
        candidate = {
            "identifier": identifier,
            "name": result.player_name,
            "birth_year": result.birth_year,
            "source": wikipedia_adapter.source_name,
            "result": result,
        }
        if find_high_confidence_match(player, [candidate]) is not None:
            matches[player_id] = candidate

    return matches, temporary_failures


def _apply_match(player: dict[str, Any], match: dict[str, Any]) -> None:
    """Persist provenance and activity without overwriting the local career."""
    result: AdapterResult = match["result"]
    player["source"] = match["source"]
    player["source_id"] = match["identifier"]

    if result.career:
        player["active"] = infer_active_status(
            result.career, career_end=result.source_metadata.get("career_end")
        )
    else:
        # No fresh career means the activity state is unknown, never inactive by default.
        player.pop("active", None)
    player["activity_checked_at"] = _now_utc_iso()

    revision_id = result.source_metadata.get("revision_id")
    wikidata_id = result.source_metadata.get("wikidata_id")
    if revision_id is not None:
        player["source_revision_id"] = revision_id
    if wikidata_id:
        player["wikidata_id"] = wikidata_id
    career_end = result.source_metadata.get("career_end")
    if career_end:
        player["source_career_end"] = career_end


def run_backfill(
    *,
    players_path: Path = _PLAYERS_PATH,
    logs_dir: Path = _LOGS_DIR,
    dry_run: bool = False,
    delay: float = 1.5,
    max_candidates_per_source: int = _DEFAULT_MAX_CANDIDATES_PER_SOURCE,
    wikipedia_adapter_factory: Optional[Callable[[], Any]] = None,
    wikidata_adapter_factory: Optional[Callable[[], Any]] = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Esegue il backfill. Estratta come funzione per essere testabile senza rete."""
    if wikipedia_adapter_factory is None:
        from domains.players.adapters.wikipedia import WikipediaAdapter

        wikipedia_adapter_factory = WikipediaAdapter
    if wikidata_adapter_factory is None:
        from domains.players.adapters.wikidata import WikidataAdapter

        wikidata_adapter_factory = WikidataAdapter

    wikipedia_adapter = wikipedia_adapter_factory()
    wikidata_adapter = wikidata_adapter_factory()

    players, load_err = load_production_players_strict(players_path)
    if players is None:
        raise RuntimeError(load_err or "Dataset di produzione non accessibile.")

    updated_count = 0
    error_count = 0
    needs_review: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    targets = [p for p in players if not p.get("source_id")]
    total = len(targets)
    bulk_matches, bulk_temporary_failures = _bulk_wikipedia_matches(targets, wikipedia_adapter)

    for i, player in enumerate(targets):
        player_id = str(player.get("id") or "")
        match = bulk_matches.get(player_id)
        used_search_path = match is None and player_id not in bulk_temporary_failures
        try:
            if match is not None:
                reason = None
            elif player_id in bulk_temporary_failures:
                reason = bulk_temporary_failures[player_id]
            else:
                match, reason = _resolve_source_for_player(
                    player,
                    wikipedia_adapter=wikipedia_adapter,
                    wikidata_adapter=wikidata_adapter,
                    sleep_fn=sleep_fn,
                    max_candidates_per_source=max_candidates_per_source,
                )
        except Exception as err:  # noqa: BLE001 - un player non deve interrompere il ciclo
            _logger.exception("Errore imprevisto su '%s'", player.get("id"))
            errors.append({"id": player.get("id"), "full_name": player.get("full_name"), "error": str(err)})
            error_count += 1
            if used_search_path and i < total - 1 and delay > 0:
                sleep_fn(delay)
            continue

        if match is None:
            needs_review.append(
                {"id": player.get("id"), "full_name": player.get("full_name"), "reason": reason}
            )
        else:
            _apply_match(player, match)
            updated_count += 1
            if not dry_run and updated_count % 10 == 0:
                atomic_write_production_dataset(players_path, players)

        if used_search_path and i < total - 1 and delay > 0:
            sleep_fn(delay)

    if not dry_run and updated_count > 0:
        atomic_write_production_dataset(players_path, players)

    review_log_path = None
    if needs_review and not dry_run:
        logs_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        review_log_path = logs_dir / f"source_backfill_review_{stamp}.json"
        with open(review_log_path, "w", encoding="utf-8") as f:
            json.dump(needs_review, f, ensure_ascii=False, indent=2)

    summary = {
        "total_candidates": total,
        "updated": updated_count,
        "needs_review": len(needs_review),
        "errors": error_count,
        "dry_run": dry_run,
        "review_log_path": str(review_log_path) if review_log_path else None,
    }
    return {"summary": summary, "needs_review": needs_review, "errors": errors}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", default=False)
    parser.add_argument(
        "--delay", type=float, default=5.0, help="Pausa (secondi) tra un giocatore e il successivo."
    )
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=_DEFAULT_MAX_CANDIDATES_PER_SOURCE,
        help="Quanti risultati di ricerca fetchare al massimo per fonte prima di rinunciare "
        "(default 2 — necessario per rilevare ambiguita' tra due omonimi).",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    outcome = run_backfill(
        dry_run=args.dry_run, delay=args.delay, max_candidates_per_source=args.max_candidates
    )
    summary = outcome["summary"]

    print("Backfill source/activity completato:")
    print(f"  Candidati esaminati : {summary['total_candidates']}")
    print(f"  Aggiornati          : {summary['updated']}")
    print(f"  Da rivedere         : {summary['needs_review']}")
    print(f"  Errori              : {summary['errors']}")
    if summary["dry_run"]:
        print("  (--dry-run: nessuna scrittura effettuata)")
    if summary["review_log_path"]:
        print(f"  Log da rivedere scritto in: {summary['review_log_path']}")


if __name__ == "__main__":
    main()
