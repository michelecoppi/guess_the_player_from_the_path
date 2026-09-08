"""Riserva una fetta del dataset all'allenamento (`"practice_only": true`).

I giocatori riservati **non escono mai** come sfida del giorno ne' dentro un evento: e' cio'
che rende allenamento e round di gruppo materiale infinito senza spoiler. Chi si allena su
quelle schede non vedra' mai lo stesso percorso arrivare come sfida vera, perche' per
costruzione non ci puo' arrivare.

La scelta e' scritta nel dataset e non calcolata a runtime, per una ragione precisa: se la
regola cambiasse (un hash, una percentuale diversa) un giocatore passerebbe da una parte
all'altra, e chi si e' allenato su di lui si ritroverebbe la risposta gia' pronta il giorno
in cui esce. Una volta riservato, un giocatore resta riservato; e la scelta sta in git, dove
si vede.

La fetta e' **bilanciata per difficolta'**: prendere gli ultimi N del file darebbe un
allenamento tutto di un colore, e svuoterebbe una fascia della rotazione quotidiana.

I calciatori da copertina (`popularity` 5: Maldini, Buffon, Ronaldo...) restano fuori dalla
riserva. Sono quelli che fanno venire voglia di rispondere a chi apre il bot per la prima
volta, e toglierli per sempre dalla sfida del giorno costerebbe piu' di quanto renda averli
in allenamento.

    python scripts/reserve_practice_players.py --dry-run     # cosa riserverebbe
    python scripts/reserve_practice_players.py               # scrive data/players.json
    python scripts/reserve_practice_players.py --ratio 0.3   # una fetta piu' grande
    python scripts/reserve_practice_players.py --reset       # riassegna da zero (vedi sotto)

`--reset` rifa' l'assegnazione da capo invece di aggiungere: si puo' usare **solo finche'
nessuno si e' allenato**, perche' un giocatore che esce dalla riserva torna nel giro delle
sfide, e chi si e' allenato su di lui avrebbe la risposta gia' pronta.
"""
import argparse
import json
import logging
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.difficulty import DIFFICULTY_ORDER, group_players_by_difficulty  # noqa: E402
from services.player_pool import _PLAYERS_PATH, is_practice_only, reload_dataset  # noqa: E402

# Un quarto del dataset: abbastanza da non ripetersi in allenamento, poco abbastanza da
# lasciare al gioco vero molti piu' giorni della finestra anti-ripetizione.
DEFAULT_RATIO = 0.25
# Seme fisso: rieseguire lo script non deve rimescolare le carte gia' distribuite.
SEED = "practice-pool"
# Sopra questa notorieta' un calciatore non si riserva mai: sono i nomi che fanno venire
# voglia di rispondere a chi apre il bot la prima volta.
MAX_RESERVED_POPULARITY = 4


def choose(players, ratio=DEFAULT_RATIO, seed=SEED, max_popularity=MAX_RESERVED_POPULARITY, reset=False):
    """Gli id da riservare, bilanciati per fascia di difficolta'.

    Funzione pura: e' la parte che decide chi sparisce dal gioco quotidiano, quindi va
    provata senza toccare il file. Chi e' gia' riservato resta riservato, a meno di
    `reset=True`."""
    already = set() if reset else {p["id"] for p in players if is_practice_only(p)}
    chosen = set(already)

    for difficulty, group in group_players_by_difficulty(players).items():
        target = round(len(group) * ratio)
        missing = target - sum(1 for player in group if player["id"] in already)
        candidates = sorted(
            (
                player for player in group
                if player["id"] not in already
                and player.get("popularity", 3) <= max_popularity
            ),
            key=lambda player: player["id"],
        )
        if missing <= 0 or not candidates:
            continue
        rng = random.Random(f"{seed}:{difficulty}")
        chosen.update(p["id"] for p in rng.sample(candidates, min(missing, len(candidates))))

    return chosen


def main():
    parser = argparse.ArgumentParser(description="Riserva una fetta del dataset all'allenamento")
    parser.add_argument("--ratio", type=float, default=DEFAULT_RATIO, help="quota da riservare per fascia")
    parser.add_argument(
        "--max-popularity", type=int, default=MAX_RESERVED_POPULARITY,
        help="notorieta' massima di un giocatore riservabile",
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="riassegna da zero invece di aggiungere (solo finche' nessuno si e' allenato)",
    )
    parser.add_argument("--dry-run", action="store_true", help="mostra cosa farebbe senza scrivere")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    with open(_PLAYERS_PATH, encoding="utf-8") as f:
        dataset = json.load(f)
    players = dataset["players"]

    reserved = choose(players, ratio=args.ratio, max_popularity=args.max_popularity, reset=args.reset)

    by_difficulty: dict[str, int] = {}
    for difficulty, group in group_players_by_difficulty(
        [p for p in players if p["id"] in reserved]
    ).items():
        by_difficulty[difficulty] = len(group)

    logging.info(f"[PRACTICE] {len(reserved)} giocatori riservati su {len(players)}")
    for difficulty in DIFFICULTY_ORDER:
        logging.info(f"[PRACTICE]   {difficulty}: {by_difficulty.get(difficulty, 0)}")

    if args.dry_run:
        for player in sorted(players, key=lambda p: p["id"]):
            if player["id"] in reserved:
                logging.info(f"[PRACTICE] riservato: {player['full_name']}")
        return

    for player in players:
        if player["id"] in reserved:
            player["practice_only"] = True
        else:
            player.pop("practice_only", None)

    with open(_PLAYERS_PATH, "w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False, indent=2)
        f.write("\n")

    reload_dataset()
    logging.info(f"[PRACTICE] data/players.json aggiornato ({len(reserved)} riservati)")


if __name__ == "__main__":
    main()
