# -*- coding: utf-8 -*-
"""Indice club -> (nome nel dataset, paese, campionato), costruito dal dataset esistente.

Il dataset ha gia' ~800 club con paese e campionato decisi a mano: e' la fonte migliore per
riempire i due campi che l'infobox di Wikipedia non da'. Per i club nuovi si va a leggere
l'infobox della pagina del club ({{Squadra di calcio}}), che ha 'nazione' e 'campionato'.

Tabelle e regole stanno in `domains/players/club_resolution.py`, condivise col refresh
delle carriere di produzione: qui restano solo il caricamento lazy del dataset e la
lettura della pagina del club via `wiki`.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import wiki  # noqa: E402

from domains.players.club_resolution import (  # noqa: E402,F401 - API storica del modulo
    ALIASES,
    CROSS_BORDER_LEAGUES,
    LEAGUE_ALIASES,
    LEAGUE_BY_COUNTRY,
    MANUAL_CLUBS,
    NON_LEGHE,
    ClubCatalog,
    club_info_from_params,
    country_for_code,
    norm,
)

BASE = os.environ.get("GTP_REPO") or os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PLAYERS = None
_CATALOG = None


def _load_players():
    global PLAYERS
    if PLAYERS is None:
        with open(os.path.join(BASE, "data", "players.json"), encoding="utf-8") as f:
            PLAYERS = json.load(f)["players"]
    return PLAYERS


def _catalog():
    global _CATALOG
    if _CATALOG is None:
        _CATALOG = ClubCatalog(_load_players())
    return _CATALOG


def build_index():
    """norm(nome) -> (nome dataset, paese, campionato), scegliendo la variante piu' usata."""
    return dict(_catalog().index)


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
            country, league = club_info_from_params(
                params.get("nazione", ""), wiki._strip_markup(params.get("campionato", "")))
            if country and league:
                result = (country, league)
                break
    _CLUB_CACHE[team] = result
    return result


def normalize_league(league, country=None):
    """Il nome del campionato come lo scrive il dataset, quando lo conosce gia'."""
    return _catalog().normalize_league(league, country)


def normalize_league_for(league, country):
    """Il campionato come lo scrive il dataset PER QUEL PAESE."""
    return _catalog().normalize_league_for(league, country)


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
