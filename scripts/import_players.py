"""Importa nuovi calciatori dentro data/players.json.

E' il modo previsto per ampliare il dataset nel tempo: si prepara un file JSON con i nuovi
giocatori (stesso schema di data/players.json, vedi data/incoming/) e lo si importa qui.
Lo script fa tutto quello che a mano si dimentica sempre:

- normalizza i campi (id minuscolo, alias in minuscolo senza duplicati, spazi tolti)
- salta i giocatori gia' presenti (o li aggiorna con --update)
- rifiuta i giocatori con dati incoerenti, spiegando il motivo, senza sporcare il dataset
- intercetta gli alias ambigui, cioe' la stessa risposta valida per due calciatori diversi
- mantiene i nuovi arrivi con "verified": false finche' qualcuno non li ha controllati

Esempi:
    python scripts/import_players.py data/incoming/batch_2026_09_1.json
    python scripts/import_players.py data/incoming/*.json --dry-run
    python scripts/import_players.py nuovi.json --update --verified
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.player_pool import (  # noqa: E402
    _PLAYERS_PATH,
    get_answer_aliases,
    load_config,
    reload_dataset,
    validate_player,
)

# "loan" e' opzionale ma va tenuto: senza, un prestito sarebbe indistinguibile da un
# trasferimento, sia nei dati sia nell'immagine del percorso.
CAREER_KEYS = ("team", "country", "league", "start_year", "end_year", "loan", "apps", "goals")


def _normalize_player(player):
    normalized = dict(player)
    normalized["id"] = str(player.get("id", "")).strip().lower().replace(" ", "_")
    normalized["full_name"] = str(player.get("full_name", "")).strip()

    aliases = []
    for alias in player.get("aliases", []) or []:
        alias = str(alias).strip().lower()
        if alias and alias not in aliases:
            aliases.append(alias)
    normalized["aliases"] = aliases

    for field in ("nationality", "position"):
        if normalized.get(field):
            normalized[field] = str(normalized[field]).strip()

    normalized["verified"] = bool(player.get("verified", False))

    career = []
    for entry in player.get("career", []) or []:
        stop = {key: entry.get(key) for key in CAREER_KEYS if key in entry}
        for key in ("team", "country", "league"):
            if stop.get(key):
                stop[key] = str(stop[key]).strip()
        career.append(stop)
    normalized["career"] = career

    return normalized


def _load_incoming(paths):
    players = []
    for path in paths:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        batch = data.get("players", data) if isinstance(data, dict) else data
        if not isinstance(batch, list):
            raise ValueError(f"{path}: atteso un oggetto con la chiave 'players' o una lista di giocatori")
        for player in batch:
            players.append((path, player))
    return players


def import_players(paths, update=False, force_verified=False, dry_run=False):
    with open(_PLAYERS_PATH, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    existing = dataset.get("players", [])
    by_id = {p.get("id"): i for i, p in enumerate(existing)}

    alias_owner = {}
    for player in existing:
        for alias in get_answer_aliases(player):
            alias_owner[alias] = player.get("id")

    min_teams = load_config().get("min_teams_in_career", 2)

    added, updated, skipped, rejected = [], [], [], []

    for source, raw_player in _load_incoming(paths):
        player = _normalize_player(raw_player)
        player_id = player["id"]

        if not player_id:
            rejected.append((source, "?", ["campo 'id' mancante"]))
            continue

        if force_verified:
            player["verified"] = True

        problems = validate_player(player, min_teams=min_teams)

        for alias in get_answer_aliases(player):
            owner = alias_owner.get(alias)
            if owner and owner != player_id:
                problems.append(f"alias ambiguo '{alias}': gia' usato da '{owner}'")

        if problems:
            rejected.append((source, player_id, problems))
            continue

        if player_id in by_id:
            if not update:
                skipped.append(player_id)
                continue
            existing[by_id[player_id]] = player
            updated.append(player_id)
        else:
            existing.append(player)
            by_id[player_id] = len(existing) - 1
            added.append(player_id)

        for alias in get_answer_aliases(player):
            alias_owner[alias] = player_id

    if not dry_run and (added or updated):
        dataset["players"] = existing
        with open(_PLAYERS_PATH, "w", encoding="utf-8") as f:
            json.dump(dataset, f, ensure_ascii=False, indent=2)
            f.write("\n")
        reload_dataset()

    return {"added": added, "updated": updated, "skipped": skipped, "rejected": rejected}


def main():
    parser = argparse.ArgumentParser(description="Importa nuovi calciatori in data/players.json")
    parser.add_argument("files", nargs="+", help="file JSON con i nuovi giocatori")
    parser.add_argument("--update", action="store_true", help="aggiorna i giocatori con id gia' presente invece di saltarli")
    parser.add_argument("--verified", action="store_true", help="marca i giocatori importati come gia' verificati")
    parser.add_argument("--dry-run", action="store_true", help="mostra cosa succederebbe senza scrivere il file")
    args = parser.parse_args()

    result = import_players(
        args.files,
        update=args.update,
        force_verified=args.verified,
        dry_run=args.dry_run,
    )

    print(f"Aggiunti:    {len(result['added'])}")
    for player_id in result["added"]:
        print(f"  + {player_id}")
    if result["updated"]:
        print(f"Aggiornati:  {len(result['updated'])}")
        for player_id in result["updated"]:
            print(f"  ~ {player_id}")
    if result["skipped"]:
        print(f"Gia' presenti (saltati): {len(result['skipped'])}: {', '.join(result['skipped'])}")
    if result["rejected"]:
        print(f"Scartati:    {len(result['rejected'])}")
        for source, player_id, problems in result["rejected"]:
            print(f"  ! {player_id} ({os.path.basename(source)})")
            for problem in problems:
                print(f"      - {problem}")

    if args.dry_run:
        print("\n(dry run: nessuna modifica scritta)")

    return 1 if result["rejected"] else 0


if __name__ == "__main__":
    sys.exit(main())
