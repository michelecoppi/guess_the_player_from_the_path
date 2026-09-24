"""Da un nome di squadra letto da Wikipedia a (squadra, paese, campionato) del dataset.

L'infobox di un calciatore su it.wikipedia.org da' solo il nome della squadra: paese e
campionato vanno ricavati. La fonte migliore e' il dataset stesso (~800 club con paese e
campionato gia' decisi); per un club mai visto si legge l'infobox della pagina del club.

Usato dal refresh delle carriere (`domains.players.career_refresh`) e dagli script legacy
in `scripts/wikipedia/` (che riesportano da qui tabelle e regole, per non averne due copie).
Nessun accesso alla rete qui: la lettura della pagina del club arriva come callable.
"""

from __future__ import annotations

import collections
import re
import unicodedata
from typing import Any, Callable, Iterable, Optional

ClubLookup = Callable[[str, Optional[str]], tuple[Optional[str], Optional[str]]]


def norm(text: Optional[str]) -> str:
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


def country_for_code(code: Optional[str]) -> Optional[str]:
    return _CODE_TO_COUNTRY.get(code or "")


def club_info_from_params(nazione: str, campionato: str) -> tuple[Optional[str], Optional[str]]:
    """(paese, campionato) dai parametri gia' ripuliti di {{Squadra di calcio}}."""
    m = re.search(r"\{\{\s*([A-Z]{3})\s*\}\}", nazione or "")
    country = country_for_code(m.group(1)) if m else None
    return country, (campionato or None)


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

# Valori che l'infobox di un club mette in "campionato" quando il club non gioca piu':
# non sono campionati e non devono finire nel dataset come se lo fossero.
NON_LEGHE = {"inattivo", "sciolto", "sciolta", "non attivo", "-", ""}


class ClubCatalog:
    """Indice dei club e dei campionati gia' presenti nel dataset."""

    def __init__(self, players: Iterable[dict[str, Any]]) -> None:
        seen: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
        league_countries: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
        self.league_vocab: dict[str, str] = {}
        for player in players:
            for stop in player.get("career") or []:
                team, country, league = stop.get("team"), stop.get("country"), stop.get("league")
                if not (team and country and league):
                    continue
                seen[norm(team)][(team, country, league)] += 1
                league_countries[league][country] += 1
                self.league_vocab.setdefault(norm(league), league)
        self.index: dict[str, tuple[str, str, str]] = {
            key: counter.most_common(1)[0][0] for key, counter in seen.items()
        }
        self.league_home: dict[str, str] = {
            league: counter.most_common(1)[0][0] for league, counter in league_countries.items()
        }

    def add(self, team: str, country: str, league: str) -> None:
        """Registra un club appena risolto, cosi' il giocatore successivo non rifa' la ricerca."""
        self.index.setdefault(norm(team), (team, country, league))

    def exact(self, name: Optional[str]) -> Optional[tuple[str, str, str]]:
        """Solo corrispondenza esatta (con gli alias): niente match approssimati."""
        if not name:
            return None
        key = norm(name)
        alias = ALIASES.get(key)
        if alias and norm(alias) in self.index:
            return self.index[norm(alias)]
        return self.index.get(key)

    def prefix(self, name: str) -> Optional[tuple[str, str, str]]:
        """Fuzzy solo nel verso sicuro ("Leeds" -> "Leeds United") e solo se univoco."""
        key = norm(name)
        if not key:
            return None
        hits = [v for k, v in self.index.items() if k.startswith(key + " ")]
        if hits and len({h[0] for h in hits}) == 1:
            return hits[0]
        return None

    def normalize_league(self, league: Optional[str], country: Optional[str] = None) -> Optional[str]:
        """Il nome del campionato come lo scrive il dataset, quando lo conosce gia'."""
        if not league:
            return league
        key = norm(league)
        if key in LEAGUE_ALIASES:
            league = LEAGUE_ALIASES[key]
            key = norm(league)
        if country == "Svizzera" and key == "super league":
            return "Swiss Super League"
        return self.league_vocab.get(key, league)

    def normalize_league_for(self, league: Optional[str], country: Optional[str]) -> Optional[str]:
        """Il campionato come lo scrive il dataset PER QUEL PAESE."""
        if not league:
            return league
        fixed = LEAGUE_BY_COUNTRY.get((country or "", norm(league)))
        if fixed:
            return fixed
        league = self.normalize_league(league, country)
        if not league or league in CROSS_BORDER_LEAGUES:
            return league
        home = self.league_home.get(league)
        if home and country and home != country:
            # nome giusto, paese sbagliato: si disambigua col paese, come fa gia' il dataset
            # ("Primera Division Cile", "Primera Division Paraguay").
            return f"{league} {country}"
        return league


def resolve_club(
    team: str,
    link: Optional[str],
    catalog: ClubCatalog,
    club_lookup: Optional[ClubLookup] = None,
) -> Optional[tuple[str, str, str, str]]:
    """(squadra, paese, campionato, come_risolto), oppure None se non risolvibile.

    Ordine: tabella manuale, indice esatto (nome, poi link), pagina del club, e solo alla
    fine il prefisso univoco. Il fuzzy prima della pagina del club sbaglia in silenzio su un
    nome piu' specifico di quello in indice ("Nacional Medellin" non e' il "Nacional"
    uruguaiano).
    """
    manual = MANUAL_CLUBS.get(norm(team))
    if manual:
        return _finish(team, manual[0], manual[1], "manuale", catalog)
    for name, how in ((team, "esatto"), (link, "esatto (link)")):
        hit = catalog.exact(name)
        if hit:
            return _finish(hit[0], hit[1], hit[2], how, catalog)
    if club_lookup is not None:
        country, league = club_lookup(team, link)
        if country and league:
            resolved = _finish(team, country, league, "pagina del club", catalog)
            if resolved:
                return resolved
    hit = catalog.prefix(team)
    if hit:
        return _finish(hit[0], hit[1], hit[2], "approssimato", catalog)
    return None


def _finish(
    team: str, country: str, league: str, how: str, catalog: ClubCatalog
) -> Optional[tuple[str, str, str, str]]:
    normalized = catalog.normalize_league_for(league, country)
    if not normalized or norm(normalized) in NON_LEGHE:
        return None
    return team, country, normalized, how
