# -*- coding: utf-8 -*-
"""Estrae la carriera di un calciatore dall'infobox di it.wikipedia.org.

L'infobox {{Sportivo}} contiene {{Carriera sportivo}}, che e' esattamente il formato del
dataset: anni, squadra, "presenze (gol)". I prestiti sono marcati con una freccia.
"""
import hashlib
import io
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://it.wikipedia.org/w/api.php"
UA = "guess-the-player-dataset/1.0 (local dataset build; contact: repo owner)"
_cache = {}


CACHE_DIR = os.environ.get("GTP_WIKI_CACHE") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".wikicache")
os.makedirs(CACHE_DIR, exist_ok=True)


def _cache_path(title):
    key = hashlib.sha1(title.encode("utf-8")).hexdigest()
    return os.path.join(CACHE_DIR, key + ".txt")


def wikitext(title):
    """Il wikitext della pagina, con cache su disco.

    La cache non e' un'ottimizzazione: e' quello che permette di rilanciare lo script
    mentre si aggiusta il parser senza ributtarsi addosso a Wikipedia (e prendersi un 429).
    """
    if title in _cache:
        return _cache[title]
    path = _cache_path(title)
    if os.path.exists(path):
        text = io.open(path, encoding="utf-8").read()
        _cache[title] = text
        return text

    url = (API + "?action=parse&page=" + urllib.parse.quote(title)
           + "&prop=wikitext&format=json&formatversion=2&redirects=1")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    data = None
    for attempt in range(5):
        try:
            data = json.load(urllib.request.urlopen(req, timeout=30))
            break
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                wait = int(exc.headers.get("Retry-After") or 0) or (5 * (attempt + 1))
                time.sleep(wait)
                continue
            if exc.code == 404:
                raise LookupError(f"pagina non trovata: {title}")
            if attempt == 4:
                raise
            time.sleep(3)
        except Exception:
            if attempt == 4:
                raise
            time.sleep(3)
    if data is None or "parse" not in data:
        raise LookupError(f"pagina non trovata: {title}")
    text = data["parse"]["wikitext"]
    io.open(path, "w", encoding="utf-8").write(text)
    _cache[title] = text
    time.sleep(0.6)  # gentile con i server di Wikipedia
    return text


def _strip_markup(value):
    """Toglie ref, template e link wiki lasciando il testo leggibile."""
    value = re.sub(r"<ref[^>]*/>", "", value)
    value = re.sub(r"\[\[\s*(?:File|Immagine|Image):[^\]]*\]\]", "", value, flags=re.I)
    value = re.sub(r"\d+px\s*\|", "", value)
    value = re.sub(r"<ref.*?</ref>", "", value, flags=re.S)
    value = re.sub(r"<!--.*?-->", "", value, flags=re.S)
    # {{Calcio Modena|N}} -> Modena ; {{Bandiera|ITA}} -> (nulla)
    value = re.sub(r"\{\{\s*[Bb]andiera\s*\|[^}]*\}\}", "", value)
    value = re.sub(r"\{\{\s*(?:Calcio|Naz)\s+([^|}]+)(?:\|[^}]*)?\}\}", r"\1", value)
    value = re.sub(r"\{\{[^}]*\}\}", "", value)
    value = re.sub(r"\[\[[^|\]]*\|([^\]]*)\]\]", r"\1", value)
    value = re.sub(r"\[\[([^\]]*)\]\]", r"\1", value)
    value = re.sub(r"</?[a-zA-Z][^>]*>", "", value)
    value = value.replace("'''", "").replace("''", "")
    return value.strip()


def _split_template_args(body):
    """Divide sui '|' di primo livello (ignora quelli dentro {{...}} e [[...]])."""
    parts, depth_c, depth_b, current = [], 0, 0, ""
    i = 0
    while i < len(body):
        two = body[i:i + 2]
        if two in ("{{", "}}", "[[", "]]"):
            if two == "{{":
                depth_c += 1
            elif two == "}}":
                depth_c -= 1
            elif two == "[[":
                depth_b += 1
            else:
                depth_b -= 1
            current += two
            i += 2
            continue
        ch = body[i]
        if ch == "|" and depth_c == 0 and depth_b == 0:
            parts.append(current)
            current = ""
        else:
            current += ch
        i += 1
    parts.append(current)
    return parts


def _find_template(text, name):
    """Il corpo del primo template {{name ...}}, bilanciando le graffe."""
    match = re.search(r"\{\{\s*" + name + r"\b", text)
    if not match:
        return None
    start = match.start()
    depth, i = 0, start
    while i < len(text):
        if text[i:i + 2] == "{{":
            depth += 1
            i += 2
            continue
        if text[i:i + 2] == "}}":
            depth -= 1
            i += 2
            if depth == 0:
                return text[start + 2:i - 2]
            continue
        i += 1
    return None


def _named_params(body):
    out = {}
    for part in _split_template_args(body):
        if "=" in part:
            key, _, value = part.partition("=")
            out[key.strip().lower()] = value.strip()
    return out


_YEARS = re.compile(r"^\s*(?:[a-z]{3}\.?\s*)?(\d{4})\s*(?:[-–—]\s*(?:[a-z]{3}\.?\s*)?(\d{4})?)?\s*$", re.I)


def _parse_years(token):
    m = _YEARS.match(_strip_markup(token))
    if not m:
        return None
    start = int(m.group(1))
    if m.group(2):
        return start, int(m.group(2))
    # "2012" da solo = una stagione; "2010-" = ancora in corso
    return (start, None) if "-" in token or "–" in token else (start, start)


_STATS = re.compile(r"(\d+)\s*(?:\((-?\d+)\))?")


def _parse_stats(token):
    token = _strip_markup(token)
    m = _STATS.search(token)
    if not m:
        return None, None
    goals = int(m.group(2)) if m.group(2) is not None else None
    return int(m.group(1)), goals


def parse_career(wt):
    """Le tappe di club: [{team, start_year, end_year, apps, goals, loan}]."""
    infobox = _find_template(wt, "Sportivo") or _find_template(wt, "Calciatore")
    if not infobox:
        return []
    params = _named_params(infobox)
    squadre = params.get("squadre")
    if not squadre:
        return []
    body = _find_template(squadre, "Carriera sportivo")
    if not body:
        return []

    # Le note e i commenti vanno via PRIMA di dividere: una cella statistica con dentro
    # un <ref name=... >{{cita web|url=...}}</ref> contiene degli '=', quindi il filtro
    # qui sotto la scambierebbe per un parametro con nome e la butterebbe. Il
    # raggruppamento a tre perde l'allineamento e la carriera si ferma li': e' il motivo
    # per cui Hamsik si fermava allo Slovan Bratislava e Robinho al Santos.
    body = re.sub(r"<ref[^>]*/>", "", body)
    body = re.sub(r"<ref[^>]*>.*?</ref>", "", body, flags=re.S)
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)

    # Il primo pezzo e' il nome del template, poi ci sono i parametri con nome
    # (sport=, pos=, aggiornato=...): vanno tolti entrambi, altrimenti il
    # raggruppamento a tre (anni, squadra, statistiche) perde l'allineamento.
    args = _split_template_args(body)[1:]
    positional = [a for a in args if not re.match(r"\s*[A-Za-z][\w -]*=", a)]
    stops = []
    for i in range(0, len(positional) - 2, 3):
        years = _parse_years(positional[i])
        if not years:
            continue
        raw_team = positional[i + 1]
        loan = "→" in raw_team or "&rarr;" in raw_team
        team = _strip_markup(raw_team.replace("→", "").replace("&rarr;", ""))
        team = re.sub(r"^\W+", "", team).strip()
        if not team:
            continue
        apps, goals = _parse_stats(positional[i + 2])
        # Il bersaglio del link wiki e' il nome vero della pagina del club
        # ([[Helsingborgs IF|Helsingborg]]): serve a risolvere paese e campionato,
        # dove l'etichetta abbreviata da sola non basta.
        link = None
        m = re.search(r"\[\[\s*([^|\]]+?)\s*(?:\|[^\]]*)?\]\]", raw_team)
        if m and not re.match(r"(?i)(file|immagine|image):", m.group(1)):
            link = m.group(1).strip()
        stop = {"team": team, "link": link, "start_year": years[0], "end_year": years[1],
                "apps": apps, "goals": goals}
        if loan:
            stop["loan"] = True
        stops.append(stop)
    return stops


_ROLES = [
    ("portiere", "Portiere"),
    ("difensore", "Difensore"), ("terzino", "Difensore"), ("libero", "Difensore"),
    ("centrocampista", "Centrocampista"), ("mediano", "Centrocampista"),
    ("regista", "Centrocampista"), ("ala", "Centrocampista"), ("trequartista", "Centrocampista"),
    ("attaccante", "Attaccante"), ("punta", "Attaccante"), ("centravanti", "Attaccante"),
]


def parse_profile(wt):
    infobox = _find_template(wt, "Sportivo") or _find_template(wt, "Calciatore") or ""
    params = _named_params(infobox)
    role_raw = _strip_markup(params.get("ruolo", "")).lower()
    position = None
    for needle, label in _ROLES:
        if needle in role_raw:
            position = label
            break

    code = None
    m = re.search(r"\{\{\s*([A-Z]{3})\s*\}\}", params.get("codicenazione", ""))
    if m:
        code = m.group(1)

    bio = _find_template(wt, "Bio") or ""
    bio_params = _named_params(bio)
    birth = bio_params.get("annonascita", "")
    m = re.search(r"(\d{4})", birth)
    birth_year = int(m.group(1)) if m else None
    name = " ".join(x for x in (bio_params.get("nome", ""), bio_params.get("cognome", "")) if x).strip()

    return {"position": position, "country_code": code, "birth_year": birth_year,
            "full_name": _strip_markup(name) or None,
            "nationality_raw": _strip_markup(bio_params.get("nazionalità", ""))}


def fetch(title):
    wt = wikitext(title)
    profile = parse_profile(wt)
    profile["career"] = parse_career(wt)
    profile["title"] = title
    return profile


_SEARCH_CACHE_PATH = os.path.join(CACHE_DIR, "_search.json")
try:
    _search_cache = json.load(io.open(_SEARCH_CACHE_PATH, encoding="utf-8"))
except Exception:
    _search_cache = {}


def search(query, limit=5):
    """I titoli piu' probabili per una stringa, via l'API di ricerca.

    Le tabelle di carriera scrivono i club in forma breve e non linkata ("Helsingborg",
    "Norimberga"): senza una ricerca non si arriva alla pagina del club, e senza quella
    non si hanno paese e campionato."""
    if query in _search_cache:
        return _search_cache[query]
    url = (API + "?action=query&list=search&srsearch=" + urllib.parse.quote(query)
           + f"&srlimit={limit}&format=json&formatversion=2")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    titles = []
    for attempt in range(4):
        try:
            data = json.load(urllib.request.urlopen(req, timeout=30))
            titles = [hit["title"] for hit in data.get("query", {}).get("search", [])]
            break
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                time.sleep(int(exc.headers.get("Retry-After") or 0) or 5 * (attempt + 1))
                continue
            break
        except Exception:
            time.sleep(2)
    _search_cache[query] = titles
    json.dump(_search_cache, io.open(_SEARCH_CACHE_PATH, "w", encoding="utf-8"))
    time.sleep(0.6)
    return titles
