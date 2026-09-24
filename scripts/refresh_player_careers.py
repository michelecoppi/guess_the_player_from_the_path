"""Refresh da Wikipedia/Wikidata della carriera dei giocatori di produzione.

Front-end a riga di comando di `domains.players.career_refresh`: stesse regole della
pagina Admin "Refresh carriera" (lock, backup, scrittura atomica, merge che non cancella
mai tappe), ma senza il limite di una richiesta HTTP/Streamlit aperta per tutto il run.

Il lavoro viene salvato un blocco alla volta: se il run si interrompe, rilanciandolo con
`--resume` si riparte dai giocatori non ancora controllati.

Uso:
    # fine mercato: tutti i giocatori attivi (o con stato sconosciuto)
    python scripts/refresh_player_careers.py --all [--dry-run]

    # riprende un run interrotto saltando chi e' stato controllato nelle ultime 12 ore
    python scripts/refresh_player_careers.py --all --resume 12

    # uno o piu' giocatori, per id o per nome
    python scripts/refresh_player_careers.py --player dusan_vlahovic --player "Rafael Leao"

    # un elenco di id (uno per riga), es. i falliti di un run precedente
    python scripts/refresh_player_careers.py --ids-file data/logs/career_refresh_failed.txt
"""

from __future__ import annotations

import argparse
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from domains.players.career_refresh import (  # noqa: E402
    CareerRefreshResult,
    refresh_players,
    select_players_for_refresh,
)
from domains.players.production_dataset import load_production_players_strict  # noqa: E402

_BASE_DIR = Path(__file__).resolve().parents[1]
_PLAYERS_PATH = _BASE_DIR / "data" / "players.json"
_BACKUP_DIR = _BASE_DIR / "backup"
_FAILED_PATH = _BASE_DIR / "data" / "logs" / "career_refresh_failed.txt"


def _fold(text: Any) -> str:
    decomposed = unicodedata.normalize("NFKD", str(text or ""))
    return " ".join("".join(c for c in decomposed if not unicodedata.combining(c)).lower().split())


def find_players(players: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    """Id esatto, poi nome/alias esatto, poi nome che contiene la ricerca (senza accenti)."""
    exact_id = [p for p in players if p.get("id") == query]
    if exact_id:
        return exact_id
    q = _fold(query)
    exact_name = [
        p
        for p in players
        if q == _fold(p.get("full_name")) or q in {_fold(a) for a in p.get("aliases") or []}
    ]
    if exact_name:
        return exact_name
    return [p for p in players if q in _fold(p.get("full_name")) or q in _fold(p.get("id"))]


def _format_diff(diff: dict[str, Any]) -> list[str]:
    lines = []
    for team in diff.get("new_teams", []):
        lines.append(f"+ nuova squadra: {team}")
    for change in diff.get("team_changes", []):
        lines.append(
            f"~ {change['team']}: fine {change['previous_end_year']} -> {change['new_end_year']}"
        )
    for change in diff.get("stat_changes", []):
        lines.append(f"~ {change['team']} {change['field']}: {change['previous']} -> {change['new']}")
    if "active_changed" in diff:
        change = diff["active_changed"]
        lines.append(f"~ attivo: {change['previous']} -> {change['new']}")
    return lines


def _resolve_targets(
    args: argparse.Namespace, players: list[dict[str, Any]]
) -> tuple[Optional[list[str]], list[dict[str, Any]]]:
    """(id_da_aggiornare, senza_fonte); None se la selezione non e' valida."""
    if args.all:
        checked_before = None
        if args.resume is not None:
            since = datetime.now(timezone.utc) - timedelta(hours=args.resume)
            checked_before = since.strftime("%Y-%m-%dT%H:%M:%SZ")
        with_source, without_source = select_players_for_refresh(
            players, include_inactive=args.include_inactive, checked_before=checked_before
        )
        return [p["id"] for p in with_source], without_source

    ids: list[str] = []
    ok = True
    for query in args.player or []:
        matches = find_players(players, query)
        if len(matches) == 1:
            ids.append(matches[0]["id"])
        elif not matches:
            print(f"! nessun giocatore trovato per '{query}'", file=sys.stderr)
            ok = False
        else:
            print(f"! '{query}' e' ambiguo, usa l'id:", file=sys.stderr)
            for p in matches[:15]:
                print(f"    {p['id']}  ({p.get('full_name')})", file=sys.stderr)
            ok = False
    if args.ids_file:
        known = {p.get("id") for p in players}
        for line in Path(args.ids_file).read_text(encoding="utf-8").splitlines():
            pid = line.strip()
            if not pid or pid.startswith("#"):
                continue
            if pid not in known:
                print(f"! id non presente nel dataset: {pid}", file=sys.stderr)
                ok = False
                continue
            ids.append(pid)
    if not ok:
        return None, []
    by_id = {p.get("id"): p for p in players}
    without_source = [by_id[pid] for pid in ids if not by_id[pid].get("source_id")]
    return list(dict.fromkeys(ids)), without_source


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    target = parser.add_argument_group("selezione")
    target.add_argument("--all", action="store_true", help="tutti i giocatori attivi con una fonte collegata")
    target.add_argument("--player", action="append", metavar="ID_O_NOME", help="giocatore per id o nome (ripetibile)")
    target.add_argument("--ids-file", metavar="PATH", help="file con un id per riga")
    parser.add_argument("--include-inactive", action="store_true", help="con --all: anche i giocatori ritirati")
    parser.add_argument(
        "--resume",
        type=float,
        metavar="ORE",
        help="con --all: salta chi e' stato controllato nelle ultime ORE ore",
    )
    parser.add_argument("--dry-run", action="store_true", help="scarica e mostra le modifiche senza scrivere")
    parser.add_argument("--chunk-size", type=int, default=20, help="giocatori per blocco salvato (default 20)")
    parser.add_argument("--delay", type=float, default=1.5, help="pausa in secondi tra le richieste (default 1.5)")
    parser.add_argument("--players-path", type=Path, default=_PLAYERS_PATH, help=argparse.SUPPRESS)
    parser.add_argument("--backup-dir", type=Path, default=_BACKUP_DIR, help=argparse.SUPPRESS)
    parser.add_argument("--failed-out", type=Path, default=_FAILED_PATH, help=argparse.SUPPRESS)
    return parser


def main(argv: Optional[list[str]] = None, **refresh_overrides: Any) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not (args.all or args.player or args.ids_file):
        parser.error("indica --all, --player o --ids-file")
    if args.all and (args.player or args.ids_file):
        parser.error("--all non si combina con --player/--ids-file")

    players, err = load_production_players_strict(args.players_path)
    if players is None:
        print(f"! {err}", file=sys.stderr)
        return 2

    ids, without_source = _resolve_targets(args, players)
    if ids is None:
        return 2
    names = {p.get("id"): p.get("full_name") for p in players}
    ids = [pid for pid in ids if pid not in {p.get("id") for p in without_source}]

    mode = "DRY-RUN, nessuna scrittura" if args.dry_run else "scrittura attiva"
    print(f"Refresh carriera di {len(ids)} giocatori ({mode}).")

    def progress(done: int, total: int, result: CareerRefreshResult) -> None:
        label = f"{result.player_id} ({names.get(result.player_id, '?')})"
        if not result.success:
            status = f"ERRORE: {result.message}"
        elif result.changed:
            status = "MODIFICATO"
        else:
            status = "invariato"
        print(f"  [{done:>4}/{total}] {label}: {status}", flush=True)
        if result.success and result.changed:
            for line in _format_diff(result.diff):
                print(f"           {line}")

    results = refresh_players(
        ids,
        players_path=args.players_path,
        backup_dir=args.backup_dir,
        chunk_size=args.chunk_size,
        delay_seconds=args.delay,
        dry_run=args.dry_run,
        progress_callback=progress,
        **refresh_overrides,
    )

    failed = [r for r in results if not r.success]
    changed = [r for r in results if r.success and r.changed]
    print(
        f"\nFatto: {len(results)} controllati, {len(changed)} modificati, "
        f"{len(results) - len(changed) - len(failed)} invariati, {len(failed)} errori."
    )
    snapshot = next((r.diff.get("backup_snapshot") for r in results if r.diff.get("backup_snapshot")), None)
    if snapshot:
        print(f"Backup del dataset prima delle modifiche: {Path(args.backup_dir) / snapshot}")
    if without_source:
        print(f"\n{len(without_source)} giocatori senza fonte collegata (collegala dall'Admin o col backfill):")
        for p in without_source:
            print(f"  - {p.get('id')} ({p.get('full_name')})")
    if failed:
        args.failed_out.parent.mkdir(parents=True, exist_ok=True)
        args.failed_out.write_text("\n".join(r.player_id for r in failed) + "\n", encoding="utf-8")
        print(f"\nId falliti salvati in {args.failed_out}; per ritentarli:")
        print(f"  python scripts/refresh_player_careers.py --ids-file {args.failed_out}")
    if args.dry_run and changed:
        print("\nDry-run: nessuna modifica scritta. Rilancia senza --dry-run per applicarle.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
