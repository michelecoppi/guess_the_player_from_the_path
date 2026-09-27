# -*- coding: utf-8 -*-
"""Allinea un batch di refresh_careers.py al vocabolario del dataset, e scarta cio' che non
si puo' importare con onesta'.

Tre passaggi, in quest'ordine:

1. **Club con due nomi.** Wikipedia scrive "Leeds", "Schalke", "PAOK Salonicco"; il dataset
   ha gia' "Leeds United", "Schalke 04", "PAOK". Importare la grafia nuova non e' un
   dettaglio estetico: lo stesso club comparirebbe con due nomi in due sfide diverse.
2. **Campionati.** Ri-normalizzati con le tabelle di clubs.py, che nel frattempo hanno
   imparato "Souper Ligka Ellada" = Super League Greece e compagnia.
3. **Tappe non affidabili.** Una tappa risolta leggendo la pagina del club e finita in un
   top 5 e' quasi sempre un errore: un club di Serie A o Premier League sarebbe gia'
   nell'indice del dataset, che di club dei top 5 ne ha centinaia. Sono i casi in cui la
   ricerca ha preso la pagina sbagliata (Paro, club bhutanese, dato come Serie A) o ha
   attribuito alla squadra riserve il campionato della prima squadra ("Monaco 2" in
   Bundesliga). Meglio un buco nel percorso che una tappa che sposta la difficolta'.

    python scripts/wikipedia/normalize_batch.py <batch.json> <out.json>
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import clubs  # noqa: E402

from services.player_pool import load_config  # noqa: E402

# Stesso club, nome diverso. Le squadre riserve (Benfica B, Zenit-2, Bordeaux 2...) NON
# stanno qui: sono entita' diverse dalla prima squadra e vanno tenute distinte.
CLUB_RENAMES = {
    "Leeds": "Leeds United",
    "Schalke": "Schalke 04",
    "PAOK Salonicco": "PAOK",
    "Cerezo": "Cerezo Osaka",
    "Vissel": "Vissel Kobe",
    "Velez": "Velez Sarsfield",
    "Newell's": "Newell's Old Boys",
    "Kuban": "Kuban Krasnodar",
    "Rubin": "Rubin Kazan",
    "Petrolul": "Petrolul Ploiesti",
    "Malmo": "Malmo FF",
    "Darmstadt": "Darmstadt 98",
    "Plymouth": "Plymouth Argyle",
    "Wigan": "Wigan Athletic",
    "West Bromwich": "West Bromwich Albion",
    "Swansea City": "Swansea",
    "Leicester City": "Leicester",
    "Excelsior Rotterdam": "Excelsior",
    "Differdange 03": "Differdange",
    "Real Oviedo": "Oviedo",
    "Nacional Medellin": "Atletico Nacional",
    "Independiente Medellin": "Independiente Medellin",
    "Monaco 1860": "1860 Munich",
    "CF Montreal": "Montreal Impact",
    "Dalian Professional": "Dalian Yifang",
    "Shanghai Greenland": "Shanghai Shenhua",
    "Neftchi Baku": "Neftci Baku",
    "Al Jaish": "El Jaish",
    "Grampus": "Nagoya Grampus",
}


def main():
    batch = json.load(open(sys.argv[1], encoding="utf-8"))["players"]
    top = set(load_config()["top_leagues"])
    out, renamed, releagued, dropped = [], 0, 0, []

    for player in batch:
        career = []
        for stop, how in zip(player["career"], player.pop("_resolved")):
            team = CLUB_RENAMES.get(stop["team"], stop["team"])
            if team != stop["team"]:
                renamed += 1
            league = clubs.normalize_league_for(stop["league"], stop["country"])
            if league != stop["league"]:
                releagued += 1
            if how == "pagina del club" and league in top and stop["team"] not in CLUB_RENAMES:
                dropped.append((player["id"], stop["team"], stop["country"], league, stop["start_year"]))
                continue
            stop["team"], stop["league"] = team, league
            career.append(stop)
        player.pop("_title", None)
        if len(career) < 2:
            dropped.append((player["id"], "*", "*", "scheda intera: meno di 2 tappe", ""))
            continue
        player["career"] = career
        out.append(player)

    json.dump({"players": out}, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    open(sys.argv[2], "a", encoding="utf-8").write("\n")
    print(f"schede: {len(out)} | club rinominati: {renamed} | campionati allineati: {releagued}")
    print(f"\nTAPPE SCARTATE ({len(dropped)}):")
    for row in dropped:
        print("   %-20s %-24s %-12s %-18s %s" % row)


if __name__ == "__main__":
    main()
