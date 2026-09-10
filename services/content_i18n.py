"""Traduzione dei **dati** del dataset: paesi e ruoli.

`services/i18n.py` traduce i messaggi del bot; qui si traduce quello che sta scritto in
data/players.json. Sono due cose diverse e il confine e' netto: li' le frasi che scrive il
bot, qui i valori che scrive chi cura il dataset.

Serve perche' il dataset e' redatto in italiano (`"country": "Spagna"`, `"position":
"Attaccante"`) ma il paese finisce **dentro l'immagine del percorso**, disegnata sotto il
nome della squadra come "campionato · paese" (services/path_image.py). L'immagine e' la
stessa per tutti, quindi fino a ieri un inglese leggeva "La Liga · Spagna" e uno spagnolo
"La Liga · Spagna" invece di "España". Il ruolo non si vede ancora da nessuna parte - il
confronto dopo un tentativo sbagliato dice solo "stesso/diverso" - ma si vedra' appena un
indizio lo dira' per esteso, ed e' lo stesso identico problema.

Perche' una tabella e non i codici ISO nel dataset: cambiare data/players.json vorrebbe
dire una migrazione su 360 schede e un formato meno leggibile per chi le scrive a mano. La
tabella costa una riga per paese ed e' controllata dai test, che falliscono appena il
dataset introduce un paese che non e' qui dentro (vedi tests/test_content_i18n.py e
`services/dataset_health.py`): il disallineamento non puo' passare inosservato.

I **campionati** invece non si traducono: "Premier League", "La Liga" e "Eredivisie" sono
nomi propri, nessuno li traduce, e infatti nel dataset stanno gia' in lingua originale.
"""
from services.i18n import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES

# Paesi come sono scritti nel dataset (italiano) -> le altre due lingue.
# Vale sia per `career[].country` sia per `nationality`: nel dataset sono lo stesso
# vocabolario, quindi la tabella e' una sola.
COUNTRY_NAMES = {
    "Algeria": {"es": "Argelia", "en": "Algeria"},
    "Angola": {"es": "Angola", "en": "Angola"},
    "Arabia Saudita": {"es": "Arabia Saudí", "en": "Saudi Arabia"},
    "Argentina": {"es": "Argentina", "en": "Argentina"},
    "Armenia": {"es": "Armenia", "en": "Armenia"},
    "Australia": {"es": "Australia", "en": "Australia"},
    "Austria": {"es": "Austria", "en": "Austria"},
    "Azerbaigian": {"es": "Azerbaiyán", "en": "Azerbaijan"},
    "Belgio": {"es": "Bélgica", "en": "Belgium"},
    "Bhutan": {"es": "Bután", "en": "Bhutan"},
    "Bielorussia": {"es": "Bielorrusia", "en": "Belarus"},
    "Bosnia": {"es": "Bosnia", "en": "Bosnia"},
    "Brasile": {"es": "Brasil", "en": "Brazil"},
    "Bulgaria": {"es": "Bulgaria", "en": "Bulgaria"},
    "Camerun": {"es": "Camerún", "en": "Cameroon"},
    "Canada": {"es": "Canadá", "en": "Canada"},
    "Cile": {"es": "Chile", "en": "Chile"},
    "Cina": {"es": "China", "en": "China"},
    "Cipro": {"es": "Chipre", "en": "Cyprus"},
    "Colombia": {"es": "Colombia", "en": "Colombia"},
    "Corea del Sud": {"es": "Corea del Sur", "en": "South Korea"},
    "Costa d'Avorio": {"es": "Costa de Marfil", "en": "Ivory Coast"},
    "Croazia": {"es": "Croacia", "en": "Croatia"},
    "Danimarca": {"es": "Dinamarca", "en": "Denmark"},
    "Ecuador": {"es": "Ecuador", "en": "Ecuador"},
    "Egitto": {"es": "Egipto", "en": "Egypt"},
    "El Salvador": {"es": "El Salvador", "en": "El Salvador"},
    "Emirati Arabi Uniti": {"es": "Emiratos Árabes Unidos", "en": "United Arab Emirates"},
    "Estonia": {"es": "Estonia", "en": "Estonia"},
    "Finlandia": {"es": "Finlandia", "en": "Finland"},
    "Francia": {"es": "Francia", "en": "France"},
    "Galles": {"es": "Gales", "en": "Wales"},
    "Gambia": {"es": "Gambia", "en": "Gambia"},
    "Georgia": {"es": "Georgia", "en": "Georgia"},
    "Germania": {"es": "Alemania", "en": "Germany"},
    "Ghana": {"es": "Ghana", "en": "Ghana"},
    "Giappone": {"es": "Japón", "en": "Japan"},
    "Gibuti": {"es": "Yibuti", "en": "Djibouti"},
    "Giordania": {"es": "Jordania", "en": "Jordan"},
    "Grecia": {"es": "Grecia", "en": "Greece"},
    "Guinea": {"es": "Guinea", "en": "Guinea"},
    "Honduras": {"es": "Honduras", "en": "Honduras"},
    "Hong Kong": {"es": "Hong Kong", "en": "Hong Kong"},
    "India": {"es": "India", "en": "India"},
    "Indonesia": {"es": "Indonesia", "en": "Indonesia"},
    "Inghilterra": {"es": "Inglaterra", "en": "England"},
    "Iran": {"es": "Irán", "en": "Iran"},
    "Iraq": {"es": "Irak", "en": "Iraq"},
    "Irlanda": {"es": "Irlanda", "en": "Ireland"},
    "Irlanda del Nord": {"es": "Irlanda del Norte", "en": "Northern Ireland"},
    "Islanda": {"es": "Islandia", "en": "Iceland"},
    "Israele": {"es": "Israel", "en": "Israel"},
    "Italia": {"es": "Italia", "en": "Italy"},
    "Jugoslavia": {"es": "Yugoslavia", "en": "Yugoslavia"},
    "Kazakistan": {"es": "Kazajistán", "en": "Kazakhstan"},
    "Lettonia": {"es": "Letonia", "en": "Latvia"},
    "Liberia": {"es": "Liberia", "en": "Liberia"},
    "Lituania": {"es": "Lituania", "en": "Lithuania"},
    "Lussemburgo": {"es": "Luxemburgo", "en": "Luxembourg"},
    "Macedonia del Nord": {"es": "Macedonia del Norte", "en": "North Macedonia"},
    "Malesia": {"es": "Malasia", "en": "Malaysia"},
    "Mali": {"es": "Malí", "en": "Mali"},
    "Malta": {"es": "Malta", "en": "Malta"},
    "Marocco": {"es": "Marruecos", "en": "Morocco"},
    "Mauritania": {"es": "Mauritania", "en": "Mauritania"},
    "Messico": {"es": "México", "en": "Mexico"},
    "Moldova": {"es": "Moldavia", "en": "Moldova"},
    "Montenegro": {"es": "Montenegro", "en": "Montenegro"},
    "Nigeria": {"es": "Nigeria", "en": "Nigeria"},
    "Norvegia": {"es": "Noruega", "en": "Norway"},
    "Olanda": {"es": "Países Bajos", "en": "Netherlands"},
    "Paraguay": {"es": "Paraguay", "en": "Paraguay"},
    "Perù": {"es": "Perú", "en": "Peru"},
    "Polonia": {"es": "Polonia", "en": "Poland"},
    "Portogallo": {"es": "Portugal", "en": "Portugal"},
    "Qatar": {"es": "Catar", "en": "Qatar"},
    "RD Congo": {"es": "RD Congo", "en": "DR Congo"},
    "Repubblica Ceca": {"es": "República Checa", "en": "Czech Republic"},
    "Romania": {"es": "Rumanía", "en": "Romania"},
    "Russia": {"es": "Rusia", "en": "Russia"},
    "San Marino": {"es": "San Marino", "en": "San Marino"},
    "Scozia": {"es": "Escocia", "en": "Scotland"},
    "Senegal": {"es": "Senegal", "en": "Senegal"},
    "Serbia": {"es": "Serbia", "en": "Serbia"},
    "Singapore": {"es": "Singapur", "en": "Singapore"},
    "Slovacchia": {"es": "Eslovaquia", "en": "Slovakia"},
    "Slovenia": {"es": "Eslovenia", "en": "Slovenia"},
    "Spagna": {"es": "España", "en": "Spain"},
    "Sudafrica": {"es": "Sudáfrica", "en": "South Africa"},
    "Svezia": {"es": "Suecia", "en": "Sweden"},
    "Svizzera": {"es": "Suiza", "en": "Switzerland"},
    "Thailandia": {"es": "Tailandia", "en": "Thailand"},
    "Togo": {"es": "Togo", "en": "Togo"},
    "Tunisia": {"es": "Túnez", "en": "Tunisia"},
    "Turchia": {"es": "Turquía", "en": "Turkey"},
    "USA": {"es": "EE. UU.", "en": "USA"},
    "Ucraina": {"es": "Ucrania", "en": "Ukraine"},
    "Ungheria": {"es": "Hungría", "en": "Hungary"},
    "Uruguay": {"es": "Uruguay", "en": "Uruguay"},
    "Uzbekistan": {"es": "Uzbekistán", "en": "Uzbekistan"},
    "Venezuela": {"es": "Venezuela", "en": "Venezuela"},
    "Vietnam": {"es": "Vietnam", "en": "Vietnam"},
}

# Ruoli come sono scritti nel dataset. Sono quattro: il dataset non distingue fra terzino e
# centrale, ed e' voluto - come indizio "Difensore" e' gia' abbastanza generoso.
POSITION_NAMES = {
    "Attaccante": {"es": "Delantero", "en": "Forward"},
    "Centrocampista": {"es": "Centrocampista", "en": "Midfielder"},
    "Difensore": {"es": "Defensa", "en": "Defender"},
    "Portiere": {"es": "Portero", "en": "Goalkeeper"},
}


def _translate(table, value, lang):
    """Il valore tradotto, o il valore com'e' se non lo sappiamo tradurre.

    Il ripiego e' voluto: un paese aggiunto al dataset e non ancora messo in tabella deve
    comparire in italiano (leggibile, anche se nella lingua sbagliata) e non sparire dalla
    card. Che manchi lo dicono i test e /admin_pool, non l'utente finale."""
    if not value:
        return value
    if lang == DEFAULT_LANGUAGE or lang not in SUPPORTED_LANGUAGES:
        return value
    return table.get(value, {}).get(lang, value)


def country_name(country, lang):
    return _translate(COUNTRY_NAMES, country, lang)


def position_name(position, lang):
    return _translate(POSITION_NAMES, position, lang)


def localize_career(career, lang):
    """Le tappe di carriera con il paese nella lingua di chi guarda.

    Copia superficiale delle sole tappe toccate: la lista in ingresso arriva dal dataset in
    cache (services/player_pool.py) o dal documento Firestore della sfida, e modificarla sul
    posto vorrebbe dire tradurre il dataset di tutti nella lingua del primo che gioca.

    Il campionato resta com'e': e' un nome proprio."""
    if lang == DEFAULT_LANGUAGE or lang not in SUPPORTED_LANGUAGES:
        return list(career or [])
    return [dict(stop, country=country_name(stop.get("country"), lang)) for stop in (career or [])]


def untranslated_values(players):
    """I valori del dataset che non hanno una traduzione, per il controllo di integrita'.

    Ritorna una lista di stringhe gia' pronte da mostrare, nella forma degli altri problemi
    di `validate_dataset`. Vuota quando e' tutto a posto."""
    missing_countries = set()
    missing_positions = set()

    for player in players or []:
        nationality = player.get("nationality")
        if nationality and nationality not in COUNTRY_NAMES:
            missing_countries.add(nationality)
        position = player.get("position")
        if position and position not in POSITION_NAMES:
            missing_positions.add(position)
        for stop in player.get("career", []):
            country = stop.get("country")
            if country and country not in COUNTRY_NAMES:
                missing_countries.add(country)

    problems = []
    for country in sorted(missing_countries):
        problems.append(
            f"paese senza traduzione: '{country}' (aggiungilo a COUNTRY_NAMES in services/content_i18n.py, "
            "altrimenti compare in italiano anche a inglesi e spagnoli)"
        )
    for position in sorted(missing_positions):
        problems.append(
            f"ruolo senza traduzione: '{position}' (aggiungilo a POSITION_NAMES in services/content_i18n.py)"
        )
    return problems
