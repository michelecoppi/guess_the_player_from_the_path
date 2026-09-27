# -*- coding: utf-8 -*-
"""Costruisce un batch per scripts/import_players.py prendendo le carriere da Wikipedia.

La notorieta' (popularity) resta una decisione editoriale: sta nella tabella qui sotto,
assegnata con la scala di docs/difficolta.md. Tutto il resto (squadre, anni, presenze, gol,
ruolo, nazionalita', anno di nascita) arriva dall'infobox di it.wikipedia.org.
"""
import json
import re
import sys
import unicodedata

import clubs
import wiki

# (titolo su Wikipedia, popularity). La popularity segue la scala di docs/difficolta.md:
# 5 = leggenda universale, 4 = campione, 3 = titolare solido, 2 = comprimario, 1 = aneddoto.
ROSTER = [
    # --- ripescati con i club aggiunti a MANUAL_CLUBS (percorsi che erano bucati) ---
    ("Samir Handanović", 3), ("David Luiz", 3), ("Milan Škriniar", 3),
    ("Gylfi Sigurðsson", 3), ("Eiður Guðjohnsen", 3), ("Burak Yılmaz", 2),
]

MIN_APPS = 0


def slug(text):
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"\(.*?\)", "", text).lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text


def build_aliases(full_name, legal_name=None, taken=None):
    """Nome comune + cognome + nome anagrafico, come le schede scritte a mano.

    Il cognome nudo si aggiunge solo se non e' gia' di qualcun altro: "laudrup" vale per
    due fratelli e "baggio" per due Baggio, e un alias ambiguo e' il difetto peggiore del
    dataset, perche' rende una risposta giusta sbagliata per meta' dei giocatori.
    """
    taken = taken or set()
    plain = unicodedata.normalize("NFKD", full_name)
    plain = "".join(c for c in plain if not unicodedata.combining(c))
    parts = [p for p in plain.split() if p]
    aliases = [plain.lower()]
    if len(parts) >= 2 and parts[-1].lower() not in taken:
        aliases.append(parts[-1].lower())
        if len(parts) >= 3:
            aliases.append(" ".join(parts[-2:]).lower())
    if full_name.lower() not in aliases:
        aliases.insert(0, full_name.lower())
    if legal_name and legal_name.lower() != full_name.lower():
        aliases.append(legal_name.lower())
    out = []
    for a in aliases:
        if a and a not in out:
            out.append(a)
    return out


def resolve_club(team, index):
    key = clubs.norm(team)
    alias = clubs.ALIASES.get(key)
    if alias:
        akey = clubs.norm(alias)
        if akey in index:
            return index[akey]
    if key in index:
        return index[key]
    # quasi-uguali: "Leeds" -> "Leeds United", ma solo se il candidato e' unico
    hits = [v for k, v in index.items()
            if k.startswith(key + " ") or key.startswith(k + " ")]
    if len({h[0] for h in hits}) == 1:
        return hits[0]
    return None


def main():
    out_path = sys.argv[1]
    index = clubs.build_index()
    taken_aliases = set()
    for existing in clubs._load_players():
        for alias in existing.get("aliases", []):
            taken_aliases.add(alias.strip().lower())
        taken_aliases.add(existing["full_name"].strip().lower())
    players, report_missing, failures, holes = [], {}, [], []

    for position, (title, popularity) in enumerate(ROSTER, 1):
        try:
            data = wiki.fetch(title)
        except Exception as exc:
            failures.append((title, f"{type(exc).__name__}: {exc}"))
            continue

        common = re.sub(r"\s*\(.*?\)\s*$", "", title).strip()
        full_name = common
        country = clubs.country_for_code(data["country_code"]) or clubs.country_for_adjective(data["nationality_raw"])
        if not country:
            failures.append((title, f"nazionalita' non mappata: {data['country_code']}"))
            continue
        if not data["position"]:
            failures.append((title, "ruolo non riconosciuto"))
            continue

        career, dropped = [], []
        for stop_index, stop in enumerate(data["career"]):
            if stop["apps"] is None:
                continue  # tappa senza dati: meglio ometterla che inventarla
            # L'ordine conta: prima la tabella manuale (che corregge le omonimie note),
            # poi l'indice del dataset, poi la ricerca su Wikipedia.
            manual = clubs.MANUAL_CLUBS.get(clubs.norm(stop["team"]))
            resolved = None
            if manual:
                resolved = (stop["team"], manual[0], manual[1])
            if not resolved:
                resolved = resolve_club(stop["team"], index)
            if not resolved and stop.get("link"):
                resolved = resolve_club(stop["link"], index)
            if resolved:
                team, stop_country, league = resolved
            else:
                stop_country, league = clubs.resolve_new_club(stop.get("link") or stop["team"])
                team = stop["team"]
                if not stop_country or not league:
                    report_missing.setdefault(stop["team"], []).append(full_name)
                    dropped.append((stop_index, stop["team"]))
                    continue
            # La normalizzazione va applicata SEMPRE, non solo ai club nuovi: l'indice e'
            # costruito dal dataset, quindi se un batch precedente ci ha messo dentro una
            # lega sbagliata, senza questo passaggio se la ritrova identica.
            league = clubs.normalize_league_for(league, stop_country)
            entry = {"team": team, "country": stop_country, "league": league,
                     "start_year": stop["start_year"], "end_year": stop["end_year"],
                     "apps": stop["apps"]}
            # Per i portieri Wikipedia mette i gol SUBITI, con il segno meno: non sono
            # i gol fatti, quindi si omettono (il dataset per i portieri fa cosi').
            if stop["goals"] is not None and stop["goals"] >= 0 and data["position"] != "Portiere":
                entry["goals"] = stop["goals"]
            if stop.get("loan"):
                entry["loan"] = True
            career.append(entry)

        # Le tappe perse a inizio carriera sono quasi sempre squadre giovanili o di
        # provincia, e il dataset parte comunque dal primo club vero. Quelle perse in
        # mezzo o in fondo invece bucano il percorso: quelle vanno guardate a mano.
        late = [t for i, t in dropped if i > 0 and i < len(data["career"]) - 1]
        if late:
            holes.append((title, late))
        if len(career) < 2:
            failures.append((title, f"carriera troppo corta dopo la risoluzione ({len(career)})"))
            continue

        players.append({
            "id": slug(title),
            "full_name": full_name,
            "aliases": build_aliases(full_name, data["full_name"], taken_aliases),
            "nationality": country,
            "position": data["position"],
            "birth_year": data["birth_year"],
            "popularity": popularity,
            "verified": True,
            "career": career,
        })
        for alias in players[-1]["aliases"]:
            taken_aliases.add(alias)
        print(f"  [{position:3}/{len(ROSTER)}] {full_name} ({len(career)} tappe)")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"players": players}, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"\n{len(players)} giocatori scritti in {out_path}")
    if failures:
        print(f"\nNON importati ({len(failures)}):")
        for title, why in failures:
            print(f"  ! {title}: {why}")
    if holes:
        print(f"\nPERCORSI BUCATI a meta' carriera ({len(holes)}), da guardare a mano:")
        for title, teams in holes:
            print(f"  * {title}: {', '.join(teams)}")
    if report_missing:
        print(f"\nTappe saltate, club non risolto ({len(report_missing)}):")
        for team, who in sorted(report_missing.items()):
            print(f"  ? {team}  ({', '.join(sorted(set(who))[:3])})")


if __name__ == "__main__":
    main()
