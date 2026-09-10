# -*- coding: utf-8 -*-
"""Indice club -> (nome nel dataset, paese, campionato), costruito dal dataset esistente.

Il dataset ha gia' ~800 club con paese e campionato decisi a mano: e' la fonte migliore per
riempire i due campi che l'infobox di Wikipedia non da'. Per i club nuovi si va a leggere
l'infobox della pagina del club ({{Squadra di calcio}}), che ha 'nazione' e 'campionato'.
"""
import collections
import json
import os
import re
import unicodedata

import wiki

BASE = os.environ.get("GTP_REPO") or os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PLAYERS = None


def norm(text):
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = re.sub(r"\b(fc|cf|ac|as|ss|ssc|sc|us|usc|afc|cd|club|calcio|football|futbol)\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


# Nomi che Wikipedia scrive in un modo e il dataset in un altro. Solo i casi in cui la
# normalizzazione non basta (esonimi, sigle, omonimie).
ALIASES = {
    "psv": "PSV Eindhoven",
    # Wikipedia in italiano italianizza qualche nome di citta': il dataset no.
    "cadice": "Cádiz",
    "barcellona": "Barcelona",
    "psg": "Paris Saint-Germain",
    "manchester utd": "Manchester United",
    "spurs": "Tottenham",
    "monaco fc": "Monaco",
    "al nasr dubai": "Al-Nasr",
    "bayern": "Bayern Monaco",
    "inter milano": "Inter",
    "internazionale": "Inter",
    "milan": "AC Milan",
    "verona": "Hellas Verona",
    "atletico madrid": "Atletico Madrid",
    "atletico": "Atletico Madrid",
    "siviglia": "Siviglia",
    "amburgo": "Amburgo",
    "colonia": "Colonia",
    "lilla": "Lilla",
    "lione": "Lione",
    "nizza": "Nizza",
    "marsiglia": "Marsiglia",
    "stoccarda": "Stoccarda",
    "saragozza": "Zaragoza",
    "real saragozza": "Zaragoza",
    "la coruna": "Deportivo La Coruna",
    "deportivo": "Deportivo La Coruna",
    "celta": "Celta Vigo",
    "betis": "Real Betis",
    "maiorca": "Maiorca",
    "salisburgo": "Salisburgo",
    "basilea": "Basilea",
    "anversa": "Anversa",
    "brugge": "Club Brugge",
    "malines": "Mechelen",
    "stella rossa": "Red Star Belgrade",
    "dinamo mosca": "Dinamo Mosca",
    "cska mosca": "CSKA Mosca",
    "zenit san pietroburgo": "Zenit",
    "shakhtar": "Shakhtar Donetsk",
    "dinamo kiev": "Dynamo Kyiv",
    "steaua bucarest": "Steaua Bucarest",
    "dinamo bucarest": "Dinamo Bucarest",
    "olympiakos": "Olympiacos",
    "panathinaikos": "Panathinaikos",
    "aek atene": "AEK Atene",
    "besiktas": "Besiktas",
    "galatasaray": "Galatasaray",
    "fenerbahce": "Fenerbahce",
    "sporting lisbona": "Sporting CP",
    "sporting": "Sporting CP",
    "vitoria guimaraes": "Vitoria Guimaraes",
    "boca": "Boca Juniors",
    "river": "River Plate",
    "velez sarsfield": "Velez Sarsfield",
    "gremio": "Gremio",
    "atletico mineiro": "Atletico Mineiro",
    "atletico paranaense": "Atletico Paranaense",
    "san paolo": "Sao Paulo",
    "corinthians": "Corinthians",
    "los angeles galaxy": "LA Galaxy",
    "new york red bulls": "New York Red Bulls",
    "d c united": "DC United",
    "washington d c united": "DC United",
}


def _load_players():
    global PLAYERS
    if PLAYERS is None:
        with open(os.path.join(BASE, "data", "players.json"), encoding="utf-8") as f:
            PLAYERS = json.load(f)["players"]
    return PLAYERS


def build_index():
    """norm(nome) -> (nome dataset, paese, campionato), scegliendo la variante piu' usata."""
    seen = collections.defaultdict(collections.Counter)
    for player in _load_players():
        for stop in player["career"]:
            key = norm(stop["team"])
            seen[key][(stop["team"], stop["country"], stop["league"])] += 1
    return {key: counter.most_common(1)[0][0] for key, counter in seen.items()}


_CODE_TO_COUNTRY = {
    "ITA": "Italia", "ESP": "Spagna", "ENG": "Inghilterra", "FRA": "Francia",
    "GER": "Germania", "DEU": "Germania", "NED": "Olanda", "POR": "Portogallo",
    "BRA": "Brasile", "ARG": "Argentina", "URU": "Uruguay", "CHI": "Cile",
    "COL": "Colombia", "PAR": "Paraguay", "PER": "Perù", "ECU": "Ecuador",
    "VEN": "Venezuela", "BOL": "Bolivia", "MEX": "Messico", "USA": "USA",
    "CAN": "Canada", "CRC": "Costa Rica", "HON": "Honduras", "JAM": "Giamaica",
    "BEL": "Belgio", "SUI": "Svizzera", "AUT": "Austria", "SWE": "Svezia",
    "NOR": "Norvegia", "DEN": "Danimarca", "FIN": "Finlandia", "ISL": "Islanda",
    "IRL": "Irlanda", "NIR": "Irlanda del Nord", "SCO": "Scozia", "WAL": "Galles",
    "POL": "Polonia", "CZE": "Repubblica Ceca", "SVK": "Slovacchia", "HUN": "Ungheria",
    "ROU": "Romania", "BUL": "Bulgaria", "GRE": "Grecia", "TUR": "Turchia",
    "RUS": "Russia", "UKR": "Ucraina", "BLR": "Bielorussia", "GEO": "Georgia",
    "SRB": "Serbia", "CRO": "Croazia", "SVN": "Slovenia", "BIH": "Bosnia",
    "MNE": "Montenegro", "MKD": "Macedonia del Nord", "ALB": "Albania",
    "YUG": "Jugoslavia", "SCG": "Serbia", "LVA": "Lettonia", "LTU": "Lituania",
    "EST": "Estonia", "MDA": "Moldova", "AZE": "Azerbaigian", "KAZ": "Kazakistan",
    "UZB": "Uzbekistan", "ARM": "Armenia", "CYP": "Cipro", "MLT": "Malta",
    "LUX": "Lussemburgo", "ISR": "Israele", "IRN": "Iran", "IRQ": "Iraq",
    "KSA": "Arabia Saudita", "UAE": "Emirati Arabi Uniti", "QAT": "Qatar",
    "JPN": "Giappone", "KOR": "Corea del Sud", "CHN": "Cina", "IND": "India",
    "AUS": "Australia", "NZL": "Nuova Zelanda", "THA": "Thailandia",
    "IDN": "Indonesia", "MAS": "Malesia", "SGP": "Singapore", "VIE": "Vietnam",
    "HKG": "Hong Kong", "MAR": "Marocco", "ALG": "Algeria", "TUN": "Tunisia",
    "EGY": "Egitto", "LBY": "Libia", "SEN": "Senegal", "CIV": "Costa d'Avorio",
    "GHA": "Ghana", "NGA": "Nigeria", "CMR": "Camerun", "MLI": "Mali",
    "GUI": "Guinea", "TOG": "Togo", "BEN": "Benin", "BFA": "Burkina Faso",
    "GAB": "Gabon", "COD": "RD Congo", "CGO": "Congo", "ANG": "Angola",
    "RSA": "Sudafrica", "ZAM": "Zambia", "KEN": "Kenya", "LBR": "Liberia",
    "GAM": "Gambia", "MTN": "Mauritania", "CPV": "Capo Verde", "GNB": "Guinea-Bissau",
    "SLE": "Sierra Leone", "CTA": "Repubblica Centrafricana", "MOZ": "Mozambico",
}


# Wikipedia usa a volte il codice CIO e a volte l'ISO 3166 alpha-3 per lo stesso paese.
_CODE_TO_COUNTRY.update({
    "NLD": "Olanda", "HRV": "Croazia", "SRB": "Serbia", "SWE": "Svezia",
    "DNK": "Danimarca", "FIN": "Finlandia", "NOR": "Norvegia", "ISL": "Islanda",
    "CHE": "Svizzera", "AUT": "Austria", "PRT": "Portogallo", "GRC": "Grecia",
    "TUR": "Turchia", "ROM": "Romania", "BGR": "Bulgaria", "POL": "Polonia",
    "HUN": "Ungheria", "SVN": "Slovenia", "MKD": "Macedonia del Nord",
    "GBR": "Inghilterra", "JPN": "Giappone", "KOR": "Corea del Sud",
    "CHN": "Cina", "PRK": "Corea del Nord", "ZAF": "Sudafrica",
    "MAR": "Marocco", "DZA": "Algeria", "TUN": "Tunisia", "NGR": "Nigeria",
    "CIV": "Costa d'Avorio", "CMR": "Camerun", "SEN": "Senegal",
    "URY": "Uruguay", "PRY": "Paraguay", "BOL": "Bolivia", "CHL": "Cile",
    "MEX": "Messico", "ESP": "Spagna", "DEU": "Germania",
})


def country_for_code(code):
    return _CODE_TO_COUNTRY.get(code)


_CLUB_CACHE = {}


def resolve_new_club(team):
    """Paese e campionato letti dall'infobox della pagina del club su Wikipedia.

    Il campionato e' quello ATTUALE del club, non quello della stagione in questione: e'
    un'approssimazione voluta, perche' serve solo a collocare la tappa in una delle tre
    fasce (top / noto / oscuro) usate dal calcolo della difficolta'.
    """
    if team in _CLUB_CACHE:
        return _CLUB_CACHE[team]
    manual = MANUAL_CLUBS.get(norm(team))
    if manual:
        _CLUB_CACHE[team] = manual
        return manual
    result = (None, None)
    candidates = [team] + [t for t in wiki.search(team + " calcio squadra", limit=4)
                           if t.lower() != team.lower()]
    for candidate in candidates:
        try:
            wt = wiki.wikitext(candidate)
        except Exception:
            continue
        body = wiki._find_template(wt, "Squadra di calcio")
        if body:
            params = wiki._named_params(body)
            code = None
            m = re.search(r"\{\{\s*([A-Z]{3})\s*\}\}", params.get("nazione", ""))
            if m:
                code = m.group(1)
            country = country_for_code(code) if code else None
            league = wiki._strip_markup(params.get("campionato", "")) or None
            if country and league:
                result = (country, league)
                break
    _CLUB_CACHE[team] = result
    return result


# Wikipedia e il dataset chiamano gli stessi campionati in modo diverso. Allinearli non e'
# estetica: il calcolo della difficolta' guarda se il campionato sta in top_leagues o
# known_leagues (data/config.json), e "Zweite Bundesliga" invece di "2. Bundesliga" farebbe
# scivolare la tappa nella fascia "oscura".
LEAGUE_ALIASES = {
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


def _league_vocabulary():
    vocab = {}
    for player in _load_players():
        for stop in player["career"]:
            vocab.setdefault(norm(stop["league"]), stop["league"])
    return vocab


_LEAGUE_VOCAB = None


def normalize_league(league, country=None):
    """Il nome del campionato come lo scrive il dataset, quando lo conosce gia'."""
    global _LEAGUE_VOCAB
    if not league:
        return league
    if _LEAGUE_VOCAB is None:
        _LEAGUE_VOCAB = _league_vocabulary()
    key = norm(league)
    if key in LEAGUE_ALIASES:
        league = LEAGUE_ALIASES[key]
        key = norm(league)
    if country == "Svizzera" and key == "super league":
        return "Swiss Super League"
    return _LEAGUE_VOCAB.get(key, league)


# Ripiego quando l'infobox non ha CodiceNazione: il template {{Bio}} ha l'aggettivo.
_ADJECTIVE_TO_COUNTRY = {
    "italiano": "Italia", "spagnolo": "Spagna", "inglese": "Inghilterra",
    "francese": "Francia", "tedesco": "Germania", "olandese": "Olanda",
    "portoghese": "Portogallo", "brasiliano": "Brasile", "argentino": "Argentina",
    "uruguaiano": "Uruguay", "cileno": "Cile", "colombiano": "Colombia",
    "bulgaro": "Bulgaria", "croato": "Croazia", "serbo": "Serbia",
    "rumeno": "Romania", "romeno": "Romania", "greco": "Grecia", "turco": "Turchia",
    "russo": "Russia", "ucraino": "Ucraina", "polacco": "Polonia",
    "ceco": "Repubblica Ceca", "slovacco": "Slovacchia", "ungherese": "Ungheria",
    "svedese": "Svezia", "norvegese": "Norvegia", "danese": "Danimarca",
    "finlandese": "Finlandia", "svizzero": "Svizzera", "austriaco": "Austria",
    "belga": "Belgio", "irlandese": "Irlanda", "scozzese": "Scozia",
    "gallese": "Galles", "nigeriano": "Nigeria", "ghanese": "Ghana",
    "camerunese": "Camerun", "senegalese": "Senegal", "ivoriano": "Costa d'Avorio",
    "marocchino": "Marocco", "algerino": "Algeria", "egiziano": "Egitto",
    "giapponese": "Giappone", "sudcoreano": "Corea del Sud", "cinese": "Cina",
    "australiano": "Australia", "statunitense": "USA", "messicano": "Messico",
    "paraguaiano": "Paraguay", "peruviano": "Perù", "ecuadoriano": "Ecuador",
    "sloveno": "Slovenia", "bosniaco": "Bosnia", "montenegrino": "Montenegro",
    "macedone": "Macedonia del Nord", "albanese": "Albania", "georgiano": "Georgia",
    "israeliano": "Israele", "iraniano": "Iran", "jugoslavo": "Jugoslavia",
}


def country_for_adjective(text):
    if not text:
        return None
    for word in re.findall(r"[a-zàèéìòù]+", text.lower()):
        if word in _ADJECTIVE_TO_COUNTRY:
            return _ADJECTIVE_TO_COUNTRY[word]
    return None


# Club che ne' l'indice del dataset ne' la ricerca su Wikipedia risolvono: quasi tutti
# dilettanti, giovanili o seconde divisioni esotiche. Riempirli a mano serve a non lasciare
# BUCHI A META' PERCORSO, che nel gioco sono peggio di una tappa in meno: il giocatore vede
# un salto di anni che non torna.
MANUAL_CLUBS = {
    "juventud": ("Uruguay", "Uruguayan Primera Division"),
    "anversa": ("Belgio", "Belgian Pro League"),
    "motherwell": ("Scozia", "Scottish Premiership"),
    "sogndal": ("Norvegia", "Eliteserien"),
    "aalesund": ("Norvegia", "Eliteserien"),
    "rollon": ("Norvegia", "Norwegian Third Division"),
    "marsonia": ("Croazia", "HNL"),
    "nask nasice": ("Croazia", "Croatian Second League"),
    "papuk orahovica": ("Croazia", "Croatian Second League"),
    "al wehdat": ("Giordania", "Jordanian Pro League"),
    "sagamihara": ("Giappone", "J3 League"),
    "nankatsu": ("Giappone", "Tokyo Amateur League"),
    "tecos": ("Messico", "Liga MX"),
    "santa tecla": ("El Salvador", "Primera Division El Salvador"),
    "magallanes": ("Cile", "Primera Division Cile"),
    "sud america": ("Uruguay", "Uruguayan Primera Division"),
    "plaza colonia": ("Uruguay", "Uruguayan Primera Division"),
    "porongos": ("Uruguay", "Uruguayan Segunda Division"),
    "beijing renhe": ("Cina", "Chinese Super League"),
    "taizhou yuanda": ("Cina", "China League Two"),
    "dalian sidelong": ("Cina", "China League One"),
    "banat zrenjanin": ("Serbia", "Serbian SuperLiga"),
    "proleter zrenjanin": ("Serbia", "Serbian SuperLiga"),
    "hvidovre": ("Danimarca", "Danish 1st Division"),
    "hadsund": ("Danimarca", "Denmark Series"),
    "sopron": ("Ungheria", "NB I"),
    "creteil": ("Francia", "Ligue 2"),
    "epinal": ("Francia", "Championnat National"),
    "plauen": ("Germania", "NOFV-Oberliga"),
    "ksv temse": ("Belgio", "Belgian Division 1"),
    "kooteepee": ("Finlandia", "Veikkausliiga"),
    "la fiorita": ("San Marino", "Campionato Sammarinese"),
    "charlotte independence": ("USA", "USL Championship"),
    "calabar rovers": ("Nigeria", "Nigeria Premier League"),
    "arta solar7": ("Gibuti", "Djibouti Premier League"),
    "hogaborg": ("Svezia", "Swedish Division 2"),
    "raa": ("Svezia", "Swedish Division 2"),
    "nasvikens ik": ("Svezia", "Swedish Division 3"),
    "hudiksvalls abk": ("Svezia", "Swedish Division 3"),
    "benaco bardolino": ("Italia", "Serie D"),
    "settignanese": ("Italia", "Eccellenza"),
    "pescatori ostia": ("Italia", "Eccellenza"),
    "lipari": ("Italia", "Eccellenza"),
    "igea virtus": ("Italia", "Serie D"),
    "incisa": ("Italia", "Eccellenza"),
    "montevarchi": ("Italia", "Serie C"),
    "rondinella": ("Italia", "Serie D"),
    "montemurlo": ("Italia", "Serie D"),
    "zagorje": ("Slovenia", "2. SNL"),
    "domzale": ("Slovenia", "PrvaLiga"),
    "fortaleza": ("Brasile", "Brasileirao"),
    "vion zlate moravce": ("Slovacchia", "Slovak First League"),
    "valur": ("Islanda", "Úrvalsdeild"),
    "shijiazhuang ever bright": ("Cina", "Chinese Super League"),
    "eskisehirspor": ("Turchia", "Super Lig"),
}


# Lo stesso nome di campionato vale per paesi diversi: "Serie A" e' l'Italia ma anche il
# Brasile, "Primera Division" la Spagna ma anche Cile e Paraguay. Attribuirlo al paese
# sbagliato non e' un dettaglio estetico: "Serie A" sta in top_leagues (data/config.json),
# quindi una tappa al Bangu conterebbe come un top 5 europeo e falserebbe la difficolta'.
LEAGUE_BY_COUNTRY = {
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

    # Nomi che le pagine dei club scrivono nella lingua del posto (o nella traslitterazione
    # di Wikipedia) e che il dataset ha gia' sotto un altro nome. Senza queste righe la
    # stessa competizione entra due volte con due grafie, e la seconda - non essendo in
    # top_leagues ne' known_leagues - pesa come campionato sconosciuto.
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
    # I campionati italiani regionali: il dataset li tiene senza la regione, altrimenti
    # avrebbe venti nomi per lo stesso livello.
    ("Italia", "eccellenza lazio"): "Eccellenza",
    ("Italia", "eccellenza veneto"): "Eccellenza",
    ("Italia", "promozione toscana"): "Promozione",
    # Il campionato serbo sotto il nome vecchio del paese: e' lo stesso, non va disambiguato
    # col paese (il dataset ha gia' tre tappe "Serbian SuperLiga" in Jugoslavia).
    ("Jugoslavia", "serbian superliga"): "Serbian SuperLiga",
    ("Jugoslavia", "serbian superliga jugoslavia"): "Serbian SuperLiga",
}

# Il paese a cui il dataset associa ciascun campionato: serve a capire quando un nome e'
# stato attribuito al paese sbagliato.
CROSS_BORDER_LEAGUES = {"MLS", "USL Championship", "NASL", "A-League"}

_LEAGUE_HOME = None


def _league_home():
    global _LEAGUE_HOME
    if _LEAGUE_HOME is None:
        tally = collections.defaultdict(collections.Counter)
        for player in _load_players():
            for stop in player["career"]:
                tally[stop["league"]][stop["country"]] += 1
        _LEAGUE_HOME = {k: v.most_common(1)[0][0] for k, v in tally.items()}
    return _LEAGUE_HOME


def normalize_league_for(league, country):
    """Il campionato come lo scrive il dataset PER QUEL PAESE."""
    if not league:
        return league
    key = norm(league)
    fixed = LEAGUE_BY_COUNTRY.get((country, key))
    if fixed:
        return fixed
    league = normalize_league(league, country)
    # Campionati che coprono davvero piu' paesi: qui il "paese sbagliato" non esiste.
    if league in CROSS_BORDER_LEAGUES:
        return league
    home = _league_home().get(league)
    if home and country and home != country:
        # nome giusto, paese sbagliato: si disambigua col paese, come fa gia' il dataset
        # ("Primera Division Cile", "Primera Division Paraguay").
        return f"{league} {country}"
    return league
