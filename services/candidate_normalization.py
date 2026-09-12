"""Candidate Player Normalization Service.

Deterministic, reusable normalization layer for Candidate Players (#26).
- Cleans whitespace, Unicode, and punctuation inconsistencies;
- Resolves known club and league aliases based on repository standards;
- Preserves unresolved QIDs and ambiguous names without fuzzy guessing;
- Standardizes nationality, position, and aliases;
- Enforces canonical career ordering via `order_career`;
- Guarantees idempotency (multiple runs produce identical results);
- Integrates with CandidatePlayer lifecycle: transitions FETCHED -> NORMALIZED.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from typing import Any, Optional

from services.candidate_finding import CandidateFinding, FindingCode, FindingSeverity
from services.candidate_player import CandidatePlayer, CandidateState
from services.candidate_provenance import make_career_stop_id
from services.career_order import order_career

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PLAYERS_PATH = os.path.join(_BASE_DIR, "data", "players.json")

# Regex to detect raw Wikidata QID tokens (e.g. Q1853, Q201625)
_QID_REGEX = re.compile(r"^Q\d+$")

# Regex to strip wiki links: [[Target|Label]] -> Label, [[Target]] -> Target
_WIKI_LINK_REGEX = re.compile(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]")

# Regex to strip wiki templates: {{Template|...}} -> empty
_WIKI_TEMPLATE_REGEX = re.compile(r"\{\{[^}]*\}\}")

# Consolidated known club aliases (mapping normalized string -> canonical dataset team name)
# Reuses and unifies definitions from scripts/wikipedia/clubs.py and scripts/wikipedia/normalize_batch.py
CONSOLIDATED_CLUB_ALIASES: dict[str, str] = {
    "psv": "PSV Eindhoven",
    "cadice": "Cádiz",
    "barcellona": "Barcelona",
    "psg": "Paris Saint-Germain",
    "manchester utd": "Manchester United",
    "manchester united fc": "Manchester United",
    "man utd": "Manchester United",
    "man united": "Manchester United",
    "spurs": "Tottenham",
    "tottenham hotspur": "Tottenham",
    "monaco fc": "Monaco",
    "as monaco": "Monaco",
    "al nasr dubai": "Al-Nasr",
    "bayern": "Bayern Monaco",
    "bayern munchen": "Bayern Monaco",
    "bayern monaco": "Bayern Monaco",
    "inter milano": "Inter",
    "internazionale": "Inter",
    "fc internazionale": "Inter",
    "milan": "AC Milan",
    "ac milan": "AC Milan",
    "verona": "Hellas Verona",
    "atletico madrid": "Atletico Madrid",
    "club atletico de madrid": "Atletico Madrid",
    "atletico": "Atletico Madrid",
    "siviglia": "Siviglia",
    "sevilla fc": "Siviglia",
    "amburgo": "Amburgo",
    "hsv": "Amburgo",
    "colonia": "Colonia",
    "lilla": "Lilla",
    "lille": "Lilla",
    "lione": "Lione",
    "olympique lyonnais": "Lione",
    "nizza": "Nizza",
    "marsiglia": "Marsiglia",
    "olympique de marseille": "Marsiglia",
    "stoccarda": "Stoccarda",
    "vfb stuttgart": "Stoccarda",
    "saragozza": "Zaragoza",
    "real saragozza": "Zaragoza",
    "la coruna": "Deportivo La Coruna",
    "deportivo la coruna": "Deportivo La Coruna",
    "deportivo": "Deportivo La Coruna",
    "celta": "Celta Vigo",
    "celta de vigo": "Celta Vigo",
    "betis": "Real Betis",
    "real betis balompie": "Real Betis",
    "maiorca": "Maiorca",
    "rcd mallorca": "Maiorca",
    "salisburgo": "Salisburgo",
    "red bull salzburg": "Salisburgo",
    "basilea": "Basilea",
    "fc basel": "Basilea",
    "anversa": "Anversa",
    "royal antwerp": "Anversa",
    "brugge": "Club Brugge",
    "club brugge kv": "Club Brugge",
    "malines": "Mechelen",
    "stella rossa": "Red Star Belgrade",
    "dinamo mosca": "Dinamo Mosca",
    "cska mosca": "CSKA Mosca",
    "zenit san pietroburgo": "Zenit",
    "zenit": "Zenit",
    "shakhtar": "Shakhtar Donetsk",
    "shakhtar donetsk": "Shakhtar Donetsk",
    "dinamo kiev": "Dynamo Kyiv",
    "dynamo kiev": "Dynamo Kyiv",
    "steaua bucarest": "Steaua Bucarest",
    "fcsb": "Steaua Bucarest",
    "dinamo bucarest": "Dinamo Bucarest",
    "olympiakos": "Olympiacos",
    "panathinaikos": "Panathinaikos",
    "aek atene": "AEK Atene",
    "besiktas": "Besiktas",
    "galatasaray": "Galatasaray",
    "fenerbahce": "Fenerbahce",
    "sporting lisbona": "Sporting CP",
    "vitoria guimaraes": "Vitoria Guimaraes",
    "boca": "Boca Juniors",
    "river": "River Plate",
    "velez sarsfield": "Velez Sarsfield",
    "velez": "Velez Sarsfield",
    "gremio": "Gremio",
    "atletico mineiro": "Atletico Mineiro",
    "atletico paranaense": "Atletico Paranaense",
    "san paolo": "Sao Paulo",
    "corinthians": "Corinthians",
    "los angeles galaxy": "LA Galaxy",
    "la galaxy": "LA Galaxy",
    "new york red bulls": "New York Red Bulls",
    "d c united": "DC United",
    "dc united": "DC United",
    "washington d c united": "DC United",
    # Renames from normalize_batch
    "leeds": "Leeds United",
    "leeds united": "Leeds United",
    "schalke": "Schalke 04",
    "schalke 04": "Schalke 04",
    "paok salonicco": "PAOK",
    "cerezo": "Cerezo Osaka",
    "vissel": "Vissel Kobe",
    "newell s": "Newell's Old Boys",
    "newell s old boys": "Newell's Old Boys",
    "kuban": "Kuban Krasnodar",
    "rubin": "Rubin Kazan",
    "petrolul": "Petrolul Ploiesti",
    "malmo": "Malmo FF",
    "darmstadt": "Darmstadt 98",
    "plymouth": "Plymouth Argyle",
    "wigan": "Wigan Athletic",
    "west bromwich": "West Bromwich Albion",
    "swansea city": "Swansea",
    "leicester city": "Leicester",
    "excelsior rotterdam": "Excelsior",
    "differdange 03": "Differdange",
    "real oviedo": "Oviedo",
    "nacional medellin": "Atletico Nacional",
    "monaco 1860": "1860 Munich",
    "cf montreal": "Montreal Impact",
    "dalian professional": "Dalian Yifang",
    "shanghai greenland": "Shanghai Shenhua",
    "neftchi baku": "Neftci Baku",
    "al jaish": "El Jaish",
    "grampus": "Nagoya Grampus",
}

# Known ambiguous aliases that should not be automatically resolved without warning
AMBIGUOUS_CLUB_ALIASES: dict[str, list[str]] = {
    "sporting": ["Sporting CP", "Sporting Gijón"],
    "inter": ["Inter", "Inter Miami", "SC Internacional"],
    "real": ["Real Madrid", "Real Sociedad", "Real Betis", "Real Zaragoza"],
    "racing": ["Racing Club", "Racing Santander", "Racing de Ferrol"],
    "nacional": ["Nacional", "Atletico Nacional", "CD Nacional"],
    "dynamo": ["Dynamo Kyiv", "Dinamo Mosca", "Dinamo Zagreb"],
    "dinamo": ["Dynamo Kyiv", "Dinamo Mosca", "Dinamo Zagreb", "Dinamo Bucarest"],
    "united": ["Manchester United", "Newcastle United", "Leeds United", "West Ham United"],
    "city": ["Manchester City", "Leicester City", "Swansea City"],
}

# Known League Aliases
KNOWN_LEAGUE_ALIASES: dict[str, str] = {
    "fussball bundesliga": "Bundesliga",
    "fusball bundesliga": "Bundesliga",
    "zweite bundesliga": "2. Bundesliga",
    "2 fussball bundesliga": "2. Bundesliga",
    "2 fusball bundesliga": "2. Bundesliga",
    "primera division": "La Liga",
    "primera division de espana": "La Liga",
    "super league": "Swiss Super League",
    "super lig": "Super Lig",
    "premier league inglese": "Premier League",
    "liga portugal": "Primeira Liga",
    "primeira liga portoghese": "Primeira Liga",
    "campionato di calcio uruguaiano": "Uruguayan Primera Division",
    "primera division argentina": "Liga Profesional",
    "campeonato brasileiro serie a": "Brasileirao",
}

# League names disambiguated by country
LEAGUE_BY_COUNTRY: dict[tuple[str, str], str] = {
    ("Brasile", "serie a"): "Brasileirao",
    ("Brasile", "serie b"): "Campeonato Brasileiro Serie B",
    ("Brasile", "campeonato brasileiro serie a"): "Brasileirao",
    ("Cile", "la liga"): "Primera Division Cile",
    ("Cile", "primera division"): "Primera Division Cile",
    ("Cile", "segunda division"): "Primera B Cile",
    ("Malta", "premier league"): "Maltese Premier League",
    ("Austria", "bundesliga"): "Austrian Bundesliga",
    ("Argentina", "primera division"): "Liga Profesional",
    ("Argentina", "la liga"): "Liga Profesional",
    ("Messico", "primera division"): "Liga MX",
    ("Messico", "primera division de mexico"): "Liga MX",
    ("Uruguay", "primera division"): "Uruguayan Primera Division",
    ("Uruguay", "primera division profesional de uruguay"): "Uruguayan Primera Division",
    ("Uruguay", "segunda division profesional de uruguay"): "Uruguayan Segunda Division",
    ("Paraguay", "primera division"): "Primera Division Paraguay",
    ("Paraguay", "division intermedia"): "Division Intermedia Paraguay",
    ("Perù", "primera division"): "Primera Division Perù",
    ("Israele", "ligat ha al"): "Israeli Premier League",
    ("Svizzera", "super league"): "Swiss Super League",
    ("Armenia", "arajin xowmb"): "Armenian Premier League",
    ("Cina", "league two"): "China League Two",
    ("Cina", "league one"): "China League One",
    ("Bulgaria", "parva liga"): "Bulgarian First League",
    ("Bulgaria", "a pfg"): "Bulgarian First League",
    ("Grecia", "souper ligka ellada"): "Super League Greece",
    ("Russia", "prem er liga"): "Russian Premier League",
    ("Russia", "pervaja liga"): "Pervaja Liga",
    ("Ucraina", "prem jer liha"): "Ukrainian Premier League",
    ("Repubblica Ceca", "1 liga"): "Czech First League",
    ("Slovacchia", "superliga"): "Slovak First League",
    ("Slovenia", "1 snl"): "PrvaLiga",
    ("Croazia", "2 nl"): "Croatian Second League",
    ("Portogallo", "segunda liga"): "Liga Portugal 2",
    ("Uruguay", "primera division uruguaya"): "Uruguayan Primera Division",
    ("Azerbaigian", "premyer liqas"): "Azerbaijan Premier League",
    ("Brasile", "campionato paulista serie d"): "Campeonato Paulista Serie D",
    ("Iran", "lega azadegan"): "Azadegan League",
    ("Lussemburgo", "division nationale"): "Luxembourg National Division",
    ("Svizzera", "challenge league"): "Swiss Challenge League",
    ("Svizzera", "promotion league"): "Swiss Promotion League",
    ("Inghilterra", "efl championship"): "Championship",
    ("Inghilterra", "northern premier league division one west"): "Northern Premier League",
    ("Canada", "major league soccer"): "MLS",
    ("USA", "major league soccer"): "MLS",
    ("Colombia", "categoria primera b"): "Categoria Primera B",
    ("Brasile", "serie c brasile"): "Campeonato Brasileiro Serie C",
    ("Spagna", "segunda federacion"): "Segunda Federacion",
    ("Italia", "eccellenza lazio"): "Eccellenza",
    ("Italia", "eccellenza veneto"): "Eccellenza",
    ("Italia", "promozione toscana"): "Promozione",
    ("Jugoslavia", "serbian superliga"): "Serbian SuperLiga",
    ("Jugoslavia", "serbian superliga jugoslavia"): "Serbian SuperLiga",
}

# Country code mappings (IOC and ISO 3166-1 alpha-3)
CODE_TO_COUNTRY: dict[str, str] = {
    "ITA": "Italia", "ESP": "Spagna", "ENG": "Inghilterra", "FRA": "Francia",
    "GER": "Germania", "DEU": "Germania", "NED": "Olanda", "NLD": "Olanda",
    "POR": "Portogallo", "PRT": "Portogallo", "BRA": "Brasile", "ARG": "Argentina",
    "URU": "Uruguay", "URY": "Uruguay", "CHI": "Cile", "CHL": "Cile",
    "COL": "Colombia", "PAR": "Paraguay", "PRY": "Paraguay", "PER": "Perù",
    "ECU": "Ecuador", "VEN": "Venezuela", "BOL": "Bolivia", "MEX": "Messico",
    "USA": "USA", "CAN": "Canada", "CRC": "Costa Rica", "HON": "Honduras",
    "JAM": "Giamaica", "BEL": "Belgio", "SUI": "Svizzera", "CHE": "Svizzera",
    "AUT": "Austria", "SWE": "Svezia", "NOR": "Norvegia", "DEN": "Danimarca",
    "DNK": "Danimarca", "FIN": "Finlandia", "ISL": "Islanda", "IRL": "Irlanda",
    "NIR": "Irlanda del Nord", "SCO": "Scozia", "WAL": "Galles", "POL": "Polonia",
    "CZE": "Repubblica Ceca", "SVK": "Slovacchia", "HUN": "Ungheria",
    "ROU": "Romania", "ROM": "Romania", "BUL": "Bulgaria", "BGR": "Bulgaria",
    "GRE": "Grecia", "GRC": "Grecia", "TUR": "Turchia", "RUS": "Russia",
    "UKR": "Ucraina", "BLR": "Bielorussia", "GEO": "Georgia", "SRB": "Serbia",
    "CRO": "Croazia", "HRV": "Croazia", "SVN": "Slovenia", "BIH": "Bosnia",
    "MNE": "Montenegro", "MKD": "Macedonia del Nord", "ALB": "Albania",
    "YUG": "Jugoslavia", "SCG": "Serbia", "LVA": "Lettonia", "LTU": "Lituania",
    "EST": "Estonia", "MDA": "Moldova", "AZE": "Azerbaigian", "KAZ": "Kazakistan",
    "UZB": "Uzbekistan", "ARM": "Armenia", "CYP": "Cipro", "MLT": "Malta",
    "LUX": "Lussemburgo", "ISR": "Israele", "IRN": "Iran", "IRQ": "Iraq",
    "KSA": "Arabia Saudita", "UAE": "Emirati Arabi Uniti", "QAT": "Qatar",
    "JPN": "Giappone", "KOR": "Corea del Sud", "CHN": "Cina", "IND": "India",
    "AUS": "Australia", "NZL": "Nuova Zelanda", "THA": "Thailandia",
    "IDN": "Indonesia", "MAS": "Malesia", "SGP": "Singapore", "VIE": "Vietnam",
    "HKG": "Hong Kong", "MAR": "Marocco", "ALG": "Algeria", "DZA": "Algeria",
    "TUN": "Tunisia", "EGY": "Egitto", "LBY": "Libia", "SEN": "Senegal",
    "CIV": "Costa d'Avorio", "GHA": "Ghana", "NGA": "Nigeria", "NGR": "Nigeria",
    "CMR": "Camerun", "MLI": "Mali", "GUI": "Guinea", "TOG": "Togo",
    "BEN": "Benin", "BFA": "Burkina Faso", "GAB": "Gabon", "COD": "RD Congo",
    "CGO": "Congo", "ANG": "Angola", "RSA": "Sudafrica", "ZAF": "Sudafrica",
    "ZAM": "Zambia", "KEN": "Kenya", "LBR": "Liberia", "GAM": "Gambia",
    "MTN": "Mauritania", "CPV": "Capo Verde", "GNB": "Guinea-Bissau",
    "SLE": "Sierra Leone", "MOZ": "Mozambico", "GBR": "Inghilterra",
}

# Country adjectives (Italian and English common forms)
ADJECTIVE_TO_COUNTRY: dict[str, str] = {
    "italiano": "Italia", "italian": "Italia", "italy": "Italia",
    "spagnolo": "Spagna", "spanish": "Spagna", "spain": "Spagna",
    "inglese": "Inghilterra", "english": "Inghilterra", "england": "Inghilterra",
    "francese": "Francia", "french": "Francia", "france": "Francia",
    "tedesco": "Germania", "german": "Germania", "germany": "Germania",
    "olandese": "Olanda", "dutch": "Olanda", "netherlands": "Olanda",
    "portoghese": "Portogallo", "portuguese": "Portogallo", "portugal": "Portogallo",
    "brasiliano": "Brasile", "brazilian": "Brasile", "brazil": "Brasile",
    "argentino": "Argentina", "argentine": "Argentina",
    "uruguaiano": "Uruguay", "uruguayan": "Uruguay",
    "cileno": "Cile", "chilean": "Cile", "chile": "Cile",
    "colombiano": "Colombia", "colombian": "Colombia",
    "bulgaro": "Bulgaria", "bulgarian": "Bulgaria",
    "croato": "Croazia", "croatian": "Croazia", "croatia": "Croazia",
    "serbo": "Serbia", "serbian": "Serbia",
    "rumeno": "Romania", "romeno": "Romania", "romanian": "Romania",
    "greco": "Grecia", "greek": "Grecia", "greece": "Grecia",
    "turco": "Turchia", "turkish": "Turchia", "turkey": "Turchia",
    "russo": "Russia", "russian": "Russia",
    "ucraino": "Ucraina", "ukrainian": "Ucraina", "ukraine": "Ucraina",
    "polacco": "Polonia", "polish": "Polonia", "poland": "Polonia",
    "ceco": "Repubblica Ceca", "czech": "Repubblica Ceca",
    "slovacco": "Slovacchia", "slovak": "Slovacchia", "slovakia": "Slovacchia",
    "ungherese": "Ungheria", "hungarian": "Ungheria", "hungary": "Ungheria",
    "svedese": "Svezia", "swedish": "Svezia", "sweden": "Svezia",
    "norvegese": "Norvegia", "norwegian": "Norvegia", "norway": "Norvegia",
    "danese": "Danimarca", "danish": "Danimarca", "denmark": "Danimarca",
    "finlandese": "Finlandia", "finnish": "Finlandia", "finland": "Finlandia",
    "svizzero": "Svizzera", "swiss": "Svizzera", "switzerland": "Svizzera",
    "austriaco": "Austria", "austrian": "Austria",
    "belga": "Belgio", "belgian": "Belgio", "belgium": "Belgio",
    "irlandese": "Irlanda", "irish": "Irlanda", "ireland": "Irlanda",
    "scozzese": "Scozia", "scottish": "Scozia", "scotland": "Scozia",
    "gallese": "Galles", "welsh": "Galles", "wales": "Galles",
    "nigeriano": "Nigeria", "nigerian": "Nigeria",
    "ghanese": "Ghana", "ghanaian": "Ghana",
    "camerunese": "Camerun", "cameroonian": "Camerun", "cameroon": "Camerun",
    "senegalese": "Senegal",
    "ivoriano": "Costa d'Avorio", "ivorian": "Costa d'Avorio",
    "marocchino": "Marocco", "moroccan": "Marocco", "morocco": "Marocco",
    "algerino": "Algeria", "algerian": "Algeria",
    "egiziano": "Egitto", "egyptian": "Egitto", "egypt": "Egitto",
    "giapponese": "Giappone", "japanese": "Giappone", "japan": "Giappone",
    "sudcoreano": "Corea del Sud", "south korean": "Corea del Sud", "korean": "Corea del Sud",
    "cinese": "Cina", "chinese": "Cina", "china": "Cina",
    "australiano": "Australia", "australian": "Australia",
    "statunitense": "USA", "american": "USA", "united states": "USA",
    "messicano": "Messico", "mexican": "Messico", "mexico": "Messico",
    "paraguaiano": "Paraguay", "paraguayan": "Paraguay",
    "peruviano": "Perù", "peruvian": "Perù", "peru": "Perù",
    "ecuadoriano": "Ecuador", "ecuadorian": "Ecuador",
    "sloveno": "Slovenia", "slovenian": "Slovenia",
    "bosniaco": "Bosnia", "bosnian": "Bosnia",
    "montenegrino": "Montenegro",
    "macedone": "Macedonia del Nord", "macedonian": "Macedonia del Nord",
    "albanese": "Albania", "albanian": "Albania",
    "georgiano": "Georgia", "georgian": "Georgia",
    "israeliano": "Israele", "israeli": "Israele", "israel": "Israele",
    "iraniano": "Iran", "iranian": "Iran",
    "jugoslavo": "Jugoslavia", "yugoslav": "Jugoslavia",
}

# Position standardizations into dataset roles
POSITION_STANDARDIZATION: dict[str, str] = {
    "portiere": "Portiere", "goalkeeper": "Portiere", "gk": "Portiere",
    "difensore": "Difensore", "defender": "Difensore", "df": "Difensore",
    "terzino": "Difensore", "centrale": "Difensore", "cb": "Difensore",
    "lb": "Difensore", "rb": "Difensore", "full-back": "Difensore",
    "centrocampista": "Centrocampista", "midfielder": "Centrocampista",
    "mf": "Centrocampista", "cm": "Centrocampista", "dm": "Centrocampista",
    "am": "Centrocampista", "ala": "Centrocampista", "winger": "Attaccante",
    "attaccante": "Attaccante", "forward": "Attaccante", "fw": "Attaccante",
    "striker": "Attaccante", "st": "Attaccante", "punta": "Attaccante",
}

_CANONICAL_INDEX: Optional[dict[str, tuple[str, str, Optional[str]]]] = None


def _clean_key(text: Optional[str]) -> str:
    """Normalize text into lower-case alphanumeric key for dictionary lookup."""
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", str(text))
    without_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    lower = without_accents.lower()
    # Strip common club affixes that differ between data sources
    stripped_affixes = re.sub(
        r"\b(fc|cf|ac|as|ss|ssc|sc|us|usc|afc|cd|club|calcio|football|futbol)\b",
        " ",
        lower,
    )
    cleaned = re.sub(r"[^a-z0-9]+", " ", stripped_affixes)
    return " ".join(cleaned.split())


def get_canonical_club_index() -> dict[str, tuple[str, str, Optional[str]]]:
    """Builds an index of norm(team) -> (canonical_team_name, country, None)
    from data/players.json. Strictly read-only.

    Deterministic club identity may be used to backfill country when unambiguous.
    Historical league is intentionally NOT indexed or backfilled purely from club identity,
    as clubs change divisions across seasons.
    """
    global _CANONICAL_INDEX
    if _CANONICAL_INDEX is not None:
        return _CANONICAL_INDEX

    index: dict[str, dict[tuple[str, str], int]] = {}
    country_counts: dict[str, set[str]] = {}
    try:
        if os.path.exists(_PLAYERS_PATH):
            with open(_PLAYERS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            for player in data.get("players", []):
                for stop in player.get("career", []):
                    team = stop.get("team")
                    country = stop.get("country")
                    if team and country:
                        key = _clean_key(team)
                        if key and key not in AMBIGUOUS_CLUB_ALIASES:
                            counts = index.setdefault(key, {})
                            entry = (team, country)
                            counts[entry] = counts.get(entry, 0) + 1
                            country_counts.setdefault(key, set()).add(country)
    except Exception:
        pass

    result: dict[str, tuple[str, str, Optional[str]]] = {}
    for key, counts in index.items():
        # Only index when club identity is unambiguous (single country in dataset)
        if len(country_counts.get(key, set())) == 1:
            best_team, best_country = max(counts.items(), key=lambda item: item[1])[0]
            result[key] = (best_team, best_country, None)

    _CANONICAL_INDEX = result
    return _CANONICAL_INDEX


def resolve_historical_league_with_temporal_evidence(
    team: str,
    country: Optional[str] = None,
    start_year: Optional[int] = None,
    end_year: Optional[int] = None,
) -> Optional[str]:
    """Extension point for future season-aware league resolution.

    Historical league cannot be inferred purely from club identity without temporal
    evidence because clubs change divisions across seasons.
    Returns None until a temporal/season-aware resolver is implemented.
    """
    return None


def parse_loan_flag(raw: Any) -> Optional[bool]:
    """Deterministically parses a loan flag value.

    Recognizes:
    - Booleans: True, False
    - Integers/Floats: 1 -> True, 0 -> False
    - Strings: "true", "1" -> True; "false", "0" -> False (case-insensitive, trimmed)

    Unknown or unhandled values return None and MUST NOT silently become True.
    """
    if raw is None:
        return False
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        if raw == 1:
            return True
        if raw == 0:
            return False
        return None
    if isinstance(raw, str):
        cleaned = raw.strip().lower()
        if cleaned in ("true", "1"):
            return True
        if cleaned in ("false", "0"):
            return False
        return None
    return None


def strip_wiki_markup(text: str) -> str:
    """Removes templates {{...}} and unpacks [[Target|Label]] into Label."""
    if not text:
        return ""
    s = _WIKI_TEMPLATE_REGEX.sub("", text)
    s = _WIKI_LINK_REGEX.sub(r"\1", s)
    return s.strip()


def clean_text(text: Optional[str]) -> str:
    """Normalizes whitespace, smart quotes, dashes, and applies Unicode NFC."""
    if not text:
        return ""
    s = strip_wiki_markup(str(text))
    # Replace curly quotes and typographic dashes
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = s.replace("–", "-").replace("—", "-")
    # Unicode NFC normalization
    s = unicodedata.normalize("NFC", s)
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def normalize_country(raw: Optional[str]) -> Optional[str]:
    """Deterministically normalizes a country string or code into canonical Italian name."""
    if not raw:
        return None
    cleaned = clean_text(raw)
    if not cleaned:
        return None

    # Check IOC / ISO code
    upper_code = cleaned.upper()
    if upper_code in CODE_TO_COUNTRY:
        return CODE_TO_COUNTRY[upper_code]

    # Check direct lower match or adjective match
    key = cleaned.lower()
    if key in ADJECTIVE_TO_COUNTRY:
        return ADJECTIVE_TO_COUNTRY[key]

    # Words in raw string
    words = re.findall(r"[a-zàèéìòùA-Z]+", key)
    for word in words:
        if word in ADJECTIVE_TO_COUNTRY:
            return ADJECTIVE_TO_COUNTRY[word]

    # If already capitalized like a country, return clean
    return cleaned


def normalize_position(raw: Optional[str]) -> Optional[str]:
    """Maps a raw position string to standard Italian role."""
    if not raw:
        return None
    cleaned = clean_text(raw)
    if not cleaned:
        return None
    key = cleaned.lower().strip()
    return POSITION_STANDARDIZATION.get(key, cleaned)


def normalize_league_name(league: Optional[str], country: Optional[str] = None) -> Optional[str]:
    """Normalizes league names using repository conventions."""
    if not league:
        return None
    cleaned = clean_text(league)
    if not cleaned:
        return None

    key = _clean_key(cleaned)
    # Check country-specific rule
    if country:
        by_country = LEAGUE_BY_COUNTRY.get((country, key))
        if by_country:
            return by_country

    if key in KNOWN_LEAGUE_ALIASES:
        return KNOWN_LEAGUE_ALIASES[key]

    if country == "Svizzera" and key == "super league":
        return "Swiss Super League"

    return cleaned


def normalize_club_name(
    raw_team: Optional[str],
    raw_country: Optional[str] = None,
) -> tuple[str, list[CandidateFinding]]:
    """Deterministically normalizes a club name without fuzzy guessing.

    Returns:
        (normalized_team_name, findings_list)
    """
    findings: list[CandidateFinding] = []
    if not raw_team or not str(raw_team).strip():
        findings.append(
            CandidateFinding(
                code=FindingCode.CLUB_NAME_MISSING,
                severity=FindingSeverity.ERROR,
                message="Nome del club mancante o vuoto",
                field_path="team",
                input_value=raw_team,
            )
        )
        return "", findings

    cleaned = clean_text(raw_team)

    # Check for raw Wikidata QID
    if _QID_REGEX.match(cleaned):
        findings.append(
            CandidateFinding(
                code=FindingCode.CLUB_UNRESOLVED_QID,
                severity=FindingSeverity.ERROR,
                message=f"Il club '{cleaned}' è un identificativo Wikidata QID non risolto",
                field_path="team",
                input_value=cleaned,
                context={"qid": cleaned},
            )
        )
        return cleaned, findings

    key = _clean_key(cleaned)

    # Check ambiguous alias
    if key in AMBIGUOUS_CLUB_ALIASES:
        candidates = AMBIGUOUS_CLUB_ALIASES[key]
        findings.append(
            CandidateFinding(
                code=FindingCode.CLUB_AMBIGUOUS_ALIAS,
                severity=FindingSeverity.WARNING,
                message=(
                    f"Il nome del club '{cleaned}' corrisponde a un alias ambiguo tra: "
                    f"{', '.join(candidates)}"
                ),
                field_path="team",
                input_value=cleaned,
                context={"candidates": candidates},
            )
        )
        return cleaned, findings

    # 1. Exact or normalized lookup in known aliases
    if key in CONSOLIDATED_CLUB_ALIASES:
        canonical = CONSOLIDATED_CLUB_ALIASES[key]
        if canonical != cleaned:
            findings.append(
                CandidateFinding(
                    code=FindingCode.CLUB_NORMALIZED,
                    severity=FindingSeverity.WARNING,
                    message=f"Club '{cleaned}' normalizzato nel canonico '{canonical}'",
                    field_path="team",
                    input_value=cleaned,
                    context={"original": cleaned, "normalized": canonical},
                    requires_review=False,
                )
            )
            return canonical, findings
        return cleaned, findings

    # 2. Lookup in canonical dataset index
    canonical_index = get_canonical_club_index()
    if key in canonical_index:
        canonical_team, _, _ = canonical_index[key]
        if canonical_team != cleaned:
            findings.append(
                CandidateFinding(
                    code=FindingCode.CLUB_NORMALIZED,
                    severity=FindingSeverity.WARNING,
                    message=f"Club '{cleaned}' allineato al nome dataset '{canonical_team}'",
                    field_path="team",
                    input_value=cleaned,
                    context={"original": cleaned, "normalized": canonical_team},
                    requires_review=False,
                )
            )
            return canonical_team, findings

    # 3. Unfamiliar club: KEEP ORIGINAL CLEANED (do NOT fuzzy guess!)
    return cleaned, findings


def normalize_aliases(aliases: list[str], full_name: Optional[str] = None) -> list[str]:
    """Normalizes player aliases: lowercase, trimmed, deduplicated in stable order."""
    res: list[str] = []
    seen: set[str] = set()

    for a in aliases or []:
        cleaned = clean_text(a).lower()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            res.append(cleaned)

    if full_name:
        fn_clean = clean_text(full_name).lower()
        if fn_clean and fn_clean not in seen:
            seen.add(fn_clean)
            res.append(fn_clean)

    return res


def normalize_career_stop(
    stop: dict[str, Any],
    stop_index: int,
) -> tuple[dict[str, Any], list[CandidateFinding]]:
    """Normalizes a single career stop and returns (normalized_stop, findings)."""
    findings: list[CandidateFinding] = []
    norm_stop = dict(stop)

    # 1. Team normalization
    raw_team = stop.get("team")
    norm_team, team_findings = normalize_club_name(raw_team, stop.get("country"))
    for f in team_findings:
        f.field_path = f"career[{stop_index}].{f.field_path}"
        findings.append(f)
    norm_stop["team"] = norm_team

    # 2. Country normalization
    raw_country = stop.get("country")
    norm_country = normalize_country(raw_country)

    # 3. League normalization
    raw_league = stop.get("league")
    norm_league = normalize_league_name(raw_league, norm_country)

    # 4. Canonical index backfill for missing country on known unambiguous clubs.
    # Deterministic club identity may be used to backfill country when unambiguous.
    # NEVER backfill league purely from club identity without temporal evidence.
    if norm_team:
        key = _clean_key(norm_team)
        if key not in AMBIGUOUS_CLUB_ALIASES:
            canonical_index = get_canonical_club_index()
            if key in canonical_index:
                cat_team, cat_country, _ = canonical_index[key]
                if not norm_country and cat_country:
                    norm_country = cat_country
                    findings.append(
                        CandidateFinding(
                            code=FindingCode.CLUB_NORMALIZED,
                            severity=FindingSeverity.WARNING,
                            message=f"Paese del club '{norm_team}' dedotto dal dataset: '{cat_country}'",
                            field_path=f"career[{stop_index}].country",
                            input_value=raw_country,
                            context={"deduced_country": cat_country},
                            requires_review=False,
                        )
                    )

    # 5. League inference: NEVER backfill from club identity alone without temporal evidence.
    # Preserve missing league, or consult season-aware extension point.
    if not norm_league and norm_team:
        norm_league = resolve_historical_league_with_temporal_evidence(
            team=norm_team,
            country=norm_country,
            start_year=norm_stop.get("start_year"),
            end_year=norm_stop.get("end_year"),
        )

    norm_stop["country"] = norm_country
    norm_stop["league"] = norm_league

    # 6. Numeric fields conversion
    for year_field in ("start_year", "end_year"):
        val = norm_stop.get(year_field)
        if val is not None and not isinstance(val, int):
            try:
                norm_stop[year_field] = int(str(val).strip())
            except (ValueError, TypeError):
                # Keep raw for validator to detect
                pass

    for stat_field in ("apps", "goals"):
        val = norm_stop.get(stat_field)
        if val is not None and not isinstance(val, int):
            try:
                norm_stop[stat_field] = int(str(val).strip())
            except (ValueError, TypeError):
                pass

    # 7. Safe loan flag standardization
    raw_loan = norm_stop.get("loan")
    if "loan" in norm_stop and raw_loan is not None:
        parsed_loan = parse_loan_flag(raw_loan)
        if parsed_loan is not None:
            norm_stop["loan"] = parsed_loan
        else:
            # Unknown value: must not silently become True
            norm_stop["loan"] = False
            findings.append(
                CandidateFinding(
                    code=FindingCode.CAREER_APPS_GOALS_INVALID,
                    severity=FindingSeverity.WARNING,
                    message=f"Valore del flag prestito non riconosciuto per '{norm_team}': '{raw_loan}' (impostato a False)",
                    field_path=f"career[{stop_index}].loan",
                    input_value=raw_loan,
                    requires_review=False,
                )
            )
    else:
        norm_stop["loan"] = False

    return norm_stop, findings


def normalize_candidate(
    candidate: CandidatePlayer,
    actor: str = "service:normalization",
) -> CandidatePlayer:
    """Applies deterministic normalization to a CandidatePlayer.

    - Cleans full_name, aliases, nationality, position;
    - Normalizes career stops and canonicalizes ordering via `order_career`;
    - Appends structured findings to `candidate.metadata['normalization_findings']`;
    - Appends warning strings to `candidate.validation_warnings` without duplicating;
    - Transitions FETCHED -> NORMALIZED (or remains NORMALIZED if already NORMALIZED).
    - Idempotent: multiple calls produce identical results.

    Args:
        candidate: CandidatePlayer to normalize.
        actor: System/service identifier for audit trail.

    Returns:
        The normalized CandidatePlayer (mutated in-place).
    """
    all_findings: list[CandidateFinding] = []

    # 1. Full name
    raw_name = candidate.full_name
    if raw_name:
        cleaned_name = clean_text(raw_name)
        if _QID_REGEX.match(cleaned_name):
            all_findings.append(
                CandidateFinding(
                    code=FindingCode.PLAYER_NAME_MALFORMED,
                    severity=FindingSeverity.ERROR,
                    message=f"Il nome del giocatore '{cleaned_name}' è un QID Wikidata non risolto",
                    field_path="full_name",
                    input_value=cleaned_name,
                )
            )
        candidate.full_name = cleaned_name
        if cleaned_name != raw_name and hasattr(candidate, "provenance") and candidate.provenance:
            candidate.provenance.record_normalization("full_name", raw_name, cleaned_name)
        if hasattr(candidate, "provenance") and candidate.provenance:
            name_fp = candidate.provenance.get_provenance_for_path("full_name")
            if name_fp:
                for obs in name_fp.observations:
                    if obs.raw_value:
                        c_name = clean_text(str(obs.raw_value))
                        if not _QID_REGEX.match(c_name):
                            obs.normalized_value = c_name
    else:
        all_findings.append(
            CandidateFinding(
                code=FindingCode.PLAYER_NAME_EMPTY,
                severity=FindingSeverity.ERROR,
                message="Il nome completo del giocatore è vuoto",
                field_path="full_name",
                input_value=raw_name,
            )
        )

    # 2. Nationality
    raw_nationality = candidate.nationality
    candidate.nationality = normalize_country(raw_nationality)
    if candidate.nationality != raw_nationality and hasattr(candidate, "provenance") and candidate.provenance:
        candidate.provenance.record_normalization("nationality", raw_nationality, candidate.nationality)
    if hasattr(candidate, "provenance") and candidate.provenance:
        nat_fp = candidate.provenance.get_provenance_for_path("nationality")
        if nat_fp:
            for obs in nat_fp.observations:
                if obs.raw_value:
                    norm_c = normalize_country(obs.raw_value)
                    if norm_c:
                        obs.normalized_value = norm_c

    # 3. Position
    raw_position = candidate.position
    candidate.position = normalize_position(raw_position)
    if candidate.position != raw_position and hasattr(candidate, "provenance") and candidate.provenance:
        candidate.provenance.record_normalization("position", raw_position, candidate.position)
    if hasattr(candidate, "provenance") and candidate.provenance:
        pos_fp = candidate.provenance.get_provenance_for_path("position")
        if pos_fp:
            for obs in pos_fp.observations:
                if obs.raw_value:
                    norm_p = normalize_position(obs.raw_value)
                    if norm_p:
                        obs.normalized_value = norm_p

    # 4. Aliases
    old_aliases = list(candidate.aliases)
    candidate.aliases = normalize_aliases(candidate.aliases, candidate.full_name)
    if hasattr(candidate, "provenance") and candidate.provenance:
        candidate.provenance.reindex_alias_paths(old_aliases, candidate.aliases)

    # 5. Career stops normalization
    normalized_stops: list[dict[str, Any]] = []
    for idx, stop in enumerate(candidate.career or []):
        norm_stop, stop_findings = normalize_career_stop(stop, idx)
        # Garantisce identità stabile stop_id per ogni tappa
        norm_stop.setdefault(
            "_stop_id",
            make_career_stop_id(getattr(candidate, "source", "cand"), idx, norm_stop.get("team")),
        )
        normalized_stops.append(norm_stop)
        all_findings.extend(stop_findings)

        # Traccia trasformazioni di normalizzazione nella provenienza
        if hasattr(candidate, "provenance") and candidate.provenance:
            sid = norm_stop.get("_stop_id")
            for f in stop_findings:
                if f.code in (FindingCode.CLUB_NORMALIZED, FindingCode.LEAGUE_NORMALIZED):
                    prop = f.field_path.split(".")[-1]
                    candidate.provenance.record_normalization(
                        f.field_path,
                        stop.get(prop),
                        norm_stop.get(prop),
                        finding_code=f.code,
                        rule=f.message,
                        stop_id=sid,
                    )
            # Risolve deterministically le osservazioni multi-source per il club
            team_fp = candidate.provenance.get_provenance_for_path(f"career[{idx}].team")
            if team_fp:
                for obs in team_fp.observations:
                    obs_raw = obs.raw_value
                    if obs_raw:
                        obs_norm, obs_findings = normalize_club_name(obs_raw, norm_stop.get("country"))
                        is_ambig = any(f.code == FindingCode.CLUB_AMBIGUOUS_ALIAS for f in obs_findings)
                        has_err = any(f.severity == FindingSeverity.ERROR for f in obs_findings)
                        if obs_norm and not is_ambig and not has_err:
                            obs.normalized_value = obs_norm
                            if obs_norm != obs_raw and not any(t.raw_value == obs_raw and t.normalized_value == obs_norm for t in team_fp.transformations):
                                from services.candidate_provenance import NormalizationRecord, now_utc_iso
                                team_fp.add_transformation(NormalizationRecord(
                                    raw_value=obs_raw,
                                    normalized_value=obs_norm,
                                    finding_code=FindingCode.CLUB_NORMALIZED.value if hasattr(FindingCode.CLUB_NORMALIZED, "value") else str(FindingCode.CLUB_NORMALIZED),
                                    timestamp=now_utc_iso(),
                                ))

    # 6. Career ordering via order_career
    ordered_stops = order_career(normalized_stops)
    if ordered_stops != normalized_stops:
        all_findings.append(
            CandidateFinding(
                code=FindingCode.CAREER_ORDER,
                severity=FindingSeverity.WARNING,
                message="L'ordine delle tappe di carriera è stato allineato alla convenzione canonica",
                field_path="career",
                context={"original_len": len(normalized_stops), "ordered_len": len(ordered_stops)},
                requires_review=False,
            )
        )
    candidate.career = ordered_stops

    # Riallinea i riferimenti dei percorsi career[i].prop nella provenienza senza perdere _stop_id
    if hasattr(candidate, "provenance") and candidate.provenance:
        candidate.provenance.reindex_career_paths(ordered_stops)
        candidate.metadata["has_source_conflicts"] = candidate.provenance.has_conflicts()


    # 7. Persist structured normalization findings in metadata
    norm_findings_dicts = [f.to_dict() for f in all_findings]
    if all_findings or "normalization_findings" not in candidate.metadata:
        candidate.metadata["normalization_findings"] = norm_findings_dicts

    # Merge warning messages into candidate.validation_warnings (deduplicated)
    existing_warnings = set(candidate.validation_warnings)
    for f in all_findings:
        if f.severity == FindingSeverity.WARNING and f.message not in existing_warnings:
            candidate.validation_warnings.append(f.message)
            existing_warnings.add(f.message)

    # 8. Transition state FETCHED -> NORMALIZED
    if candidate.status == CandidateState.FETCHED and candidate.can_transition_to(CandidateState.NORMALIZED):
        candidate.transition_to(
            CandidateState.NORMALIZED,
            reason="Normalizzazione deterministica completata",
            actor=actor,
            metadata={"findings_count": len(all_findings)},
        )

    return candidate
