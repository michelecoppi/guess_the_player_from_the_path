# -*- coding: utf-8 -*-
"""Riscarica da Wikipedia la carriera di schede gia' presenti in data/players.json.

Fratello di build_wiki.py: quello crea schede nuove, questo rifa' la carriera di quelle che
ci sono gia'. Serve perche' le prime 130 schede del batch di settembre 2026 erano scritte a
memoria e le presenze non venivano da nessuna fonte (40,5% multipli di 5 contro il 19% del
resto del dataset: numeri arrotondati, non letti).

Tocca **solo** `career`: id, alias, notorieta' e `practice_only` sono decisioni editoriali
gia' prese, e cambiare full_name o alias vorrebbe dire cambiare le risposte accettate.

    python scripts/wikipedia/refresh_careers.py <ids.txt> <batch.json>
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import clubs  # noqa: E402
import wiki  # noqa: E402

from domains.players.club_resolution import resolve_club  # noqa: E402
from services.player_pool import _PLAYERS_PATH  # noqa: E402


def is_player_page(title):
    """Vera solo se la pagina e' quella di un calciatore con una carriera leggibile.

    Non basta che il titolo esista: "Anderson", "Maniche", "Giuseppe Rossi" e "Marco Negri"
    sono pagine di disambigua, si scaricano senza errore e producono zero tappe. Senza
    questo controllo la scheda veniva saltata invece di cercare la pagina giusta."""
    try:
        wt = wiki.wikitext(title)
    except Exception:
        return False
    if re.search(r"\{\{\s*disambigua", wt, re.I):
        return False
    return len(wiki.parse_career(wt)) >= 2


def resolve_title(player):
    """Il titolo su it.wikipedia.org per una scheda del dataset.

    Il nome completo azzecca la pagina nella grande maggioranza dei casi; quando no si passa
    dalla ricerca, filtrando i titoli che non sembrano una persona."""
    name = player["full_name"]
    for candidate in (name, f"{name} (calciatore)"):
        if is_player_page(candidate):
            return candidate
    for hit in wiki.search(f"{name} calciatore", limit=5):
        if re.search(r"(nazionale|campionato|coppa|stagione)", hit, re.I):
            continue
        if is_player_page(hit):
            return hit
    return None


def resolve_stop(stop, index):
    """(squadra, paese, campionato, come_risolto) per una tappa: vedi `resolve_club`."""
    return resolve_club(stop["team"], stop.get("link"), clubs._catalog(),
                        lambda team, link: clubs.resolve_new_club(link or team))


def build_career(data, index):
    """Le tappe risolte in (paese, campionato)."""
    career, dropped, how = [], [], []
    for stop_index, stop in enumerate(data["career"]):
        if stop["apps"] is None:
            continue  # tappa senza dati: meglio ometterla che inventarla
        resolved = resolve_stop(stop, index)
        if not resolved:
            dropped.append((stop_index, stop["team"], "club non risolto o campionato non valido"))
            continue
        team, country, league, why = resolved
        entry = {"team": team, "country": country, "league": league,
                 "start_year": stop["start_year"], "end_year": stop["end_year"],
                 "apps": stop["apps"]}
        # Per i portieri Wikipedia mette i gol SUBITI col segno meno: si omettono.
        if stop["goals"] is not None and stop["goals"] >= 0 and data["position"] != "Portiere":
            entry["goals"] = stop["goals"]
        if stop.get("loan"):
            entry["loan"] = True
        career.append(entry)
        how.append(why)
    late = [f"{t} ({w})" for i, t, w in dropped if 0 < i < len(data["career"]) - 1]
    return career, late, how


def main():
    # Serve la versione attuale delle pagine, non quella rimasta in cache da un run precedente.
    wiki.set_cache_cutoff(time.time())
    ids = [line.strip() for line in open(sys.argv[1], encoding="utf-8") if line.strip()]
    out_path = sys.argv[2]
    dataset = json.load(open(_PLAYERS_PATH, encoding="utf-8"))
    by_id = {p["id"]: p for p in dataset["players"]}
    index = clubs.build_index()

    out, failures, holes, mismatches = [], [], [], []
    for n, pid in enumerate(ids, 1):
        player = by_id.get(pid)
        if not player:
            failures.append((pid, "id non presente nel dataset"))
            continue
        title = resolve_title(player)
        if not title:
            failures.append((pid, f"nessuna pagina trovata per '{player['full_name']}'"))
            continue
        try:
            data = wiki.fetch(title)
        except Exception as exc:
            failures.append((pid, f"{type(exc).__name__}: {exc}"))
            continue
        career, late, how = build_career(data, index)
        if len(career) < 2:
            failures.append((pid, f"carriera troppo corta dopo la risoluzione ({len(career)})"))
            continue
        if late:
            holes.append((pid, title, late))
        # Ruolo e anno di nascita non li sovrascrivo: li segnalo, perche' se non
        # corrispondono e' probabile che la pagina sia di un'altra persona.
        if data.get("position") and data["position"] != player.get("position"):
            mismatches.append((pid, title, "ruolo", player.get("position"), data["position"]))
        if data.get("birth_year") and player.get("birth_year") and data["birth_year"] != player["birth_year"]:
            mismatches.append((pid, title, "nascita", player.get("birth_year"), data["birth_year"]))

        fresh = {k: v for k, v in player.items() if k != "career"}
        fresh["career"] = career
        fresh["_title"] = title
        fresh["_resolved"] = how
        out.append(fresh)
        print(f"  [{n:3}/{len(ids)}] {pid} <- {title} ({len(player['career'])} -> {len(career)} tappe)")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"players": out}, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"\n{len(out)} schede scritte in {out_path}")
    for label, rows in (("NON aggiornate", failures), ("PERCORSI BUCATI a meta'", holes),
                        ("CAMPI DIVERSI dalla pagina", mismatches)):
        if rows:
            print(f"\n{label} ({len(rows)}):")
            for row in rows:
                print("  ! " + " | ".join(str(x) for x in row))


if __name__ == "__main__":
    main()
