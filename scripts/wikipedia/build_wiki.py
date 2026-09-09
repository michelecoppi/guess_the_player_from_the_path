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
    # --- campioni che mancavano (4) ---
    ("Zvonimir Boban", 4), ("Dejan Savićević", 4), ("Predrag Mijatović", 4),
    ("Siniša Mihajlović", 4), ("Brian Laudrup", 4), ("Michael Laudrup", 4),
    ("Peter Schmeichel", 4), ("Henrik Larsson", 4), ("Ole Gunnar Solskjær", 4),
    ("Jari Litmanen", 4), ("Fernando Redondo", 4), ("Diego Simeone", 4),
    ("Roberto Ayala", 4), ("Gianluca Vialli", 4), ("Roberto Mancini", 4),
    ("Giuseppe Signori", 4), ("Fabrizio Ravanelli", 4), ("Filippo Inzaghi", 4),
    # --- titolari solidi (3) ---
    ("Sami Hyypiä", 3), ("Matías Almeyda", 3), ("Abel Balbo", 3),
    ("Marco Simone", 3), ("Enrico Chiesa", 3), ("Dino Baggio", 3),
    ("Angelo Di Livio", 3), ("Attilio Lombardo", 3), ("Marco Delvecchio", 3),
    ("Jon Dahl Tomasson", 3), ("Tore André Flo", 3), ("John Carew", 3),
    ("John Arne Riise", 3), ("Ivica Olić", 3), ("Darko Kovačević", 3),
    ("Robert Jarni", 3), ("Krasimir Balakov", 3), ("Marc-Vivien Foé", 3),
    ("Papa Bouba Diop", 3), ("Diego Godín", 3), ("Jermain Defoe", 3),
    ("Joe Cole", 3), ("Michael Carrick", 3), ("Marco Di Vaio", 3),
    ("Sebastian Giovinco", 3), ("Giampaolo Pazzini", 3), ("Graziano Pellè", 3),
    ("Alberto Aquilani", 3), ("Riccardo Montolivo", 3),
    # --- comprimari (2) ---
    ("Slaven Bilić", 2), ("Florin Răducioiu", 2), ("Ilie Dumitrescu", 2),
    ("Emil Kostadinov", 2), ("Geremi Njitap", 2), ("Alexandre Song", 2),
    ("Khalilou Fadiga", 2), ("Henri Camara", 2), ("Aliou Cissé", 2),
    ("Finidi George", 2), ("Sunday Oliseh", 2), ("Victor Ikpeba", 2),
    ("Tijani Babangida", 2), ("Emmanuel Amunike", 2), ("Daniel Amokachi", 2),
    ("Celestine Babayaro", 2), ("Samuel Kuffour", 2), ("Junichi Inamoto", 2),
    ("Shinji Ono", 2), ("Naohiro Takahara", 2), ("Tomas Brolin", 2),
    ("Kennet Andersson", 2), ("Martin Dahlin", 2), ("Ebbe Sand", 2),
    ("Thomas Helveg", 2), ("Teemu Pukki", 2), ("Sebastián Abreu", 2),
    ("Kily González", 2), ("Néstor Sensini", 2),
    ("José Chamot", 2), ("Cristian Rodríguez", 2), ("Álvaro Pereira", 2),
    ("Martín Cáceres", 2), ("Darren Bent", 2), ("Owen Hargreaves", 2),
    ("Kieron Dyer", 2), ("Scott Parker", 2), ("Louis Saha", 2),
    ("Mikaël Silvestre", 2), ("Alan Smith (calciatore 1980)", 2),
    ("Jonathan Woodgate", 2), ("Nikola Žigić", 2), ("Mladen Petrić", 2),
    ("Vedran Ćorluka", 2), ("Sergio Canales", 2), ("Denis Čeryšev", 2),
    ("Bernardo Corradi", 2), ("Cristiano Doni", 2), ("Igor Protti", 2),
    ("Nicola Amoruso", 2), ("Alessandro Matri", 2), ("Simone Zaza", 2),
    ("Stefano Fiore", 2), ("Damiano Tommasi", 2),
    # --- da aneddoto (1) ---
    ("Salif Diao", 1), ("Lee Young-pyo", 1), ("Seol Ki-hyeon", 1),
    ("Sun Jihai", 1), ("Dong Fangzhuo", 1), ("Jan Åge Fjørtoft", 1),
    ("Quinton Fortune", 1), ("Francis Jeffers", 1), ("Jay Bothroyd", 1),
    ("Federico Macheda", 1), ("Zoran Tošić", 1), ("Gabriel Obertan", 1),
    ("Andy van der Meyde", 1), ("Milan Jovanović", 1),
    ("Danijel Pranjić", 1), ("Vincent Janssen", 1), ("Christian Riganò", 1),
    ("Marco Marchionni", 1),
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
