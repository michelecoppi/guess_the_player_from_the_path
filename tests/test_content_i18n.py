"""Traduzione dei dati del dataset (paesi, ruoli) e sua tenuta nel tempo.

Il test che conta davvero e' `test_every_dataset_value_has_a_translation`: e' quello che si
accorge di un paese nuovo arrivato con un batch di import. Senza, il difetto non si vede -
il ripiego mostra l'italiano e non si rompe niente - ma un inglese si ritrova "Spagna"
disegnato nella card.
"""
import json

import pytest
from PIL import Image

from services.content_i18n import (
    COUNTRY_NAMES,
    POSITION_NAMES,
    country_name,
    localize_career,
    position_name,
    untranslated_values,
)
from services.i18n import SUPPORTED_LANGUAGES
from services.path_image import render_career_path_image
from services.player_pool import _load_raw_players, validate_dataset

OTHER_LANGUAGES = [lang for lang in SUPPORTED_LANGUAGES if lang != "it"]


def test_every_dataset_value_has_a_translation():
    """Il dataset non deve contenere paesi o ruoli che non sappiamo tradurre."""
    assert untranslated_values(_load_raw_players()) == []


def test_dataset_validation_reports_untranslated_values():
    players = [{
        "id": "tizio", "full_name": "Tizio Caio", "aliases": ["tizio"],
        "nationality": "Atlantide", "position": "Libero",
        "career": [
            {"team": "A", "country": "Spagna", "league": "La Liga", "start_year": 2010, "end_year": 2012},
            {"team": "B", "country": "Terra di Mezzo", "league": "X", "start_year": 2012, "end_year": 2014},
        ],
    }]
    problems = " | ".join(validate_dataset(players))
    assert "Atlantide" in problems
    assert "Terra di Mezzo" in problems
    assert "Libero" in problems
    assert "Spagna" not in problems


@pytest.mark.parametrize("lang", OTHER_LANGUAGES)
def test_every_country_and_position_is_translated_in_every_language(lang):
    """Una voce a meta' (solo 'en', niente 'es') ripiegherebbe in silenzio sull'italiano."""
    assert [name for name, table in COUNTRY_NAMES.items() if not table.get(lang)] == []
    assert [name for name, table in POSITION_NAMES.items() if not table.get(lang)] == []


def test_translation_of_known_values():
    assert country_name("Spagna", "es") == "España"
    assert country_name("Spagna", "en") == "Spain"
    assert country_name("Spagna", "it") == "Spagna"
    assert position_name("Attaccante", "en") == "Forward"


def test_unknown_values_fall_back_to_the_dataset_spelling():
    """Meglio il paese in italiano che una card con un buco al posto del paese."""
    assert country_name("Atlantide", "en") == "Atlantide"
    assert position_name("Libero", "es") == "Libero"
    assert country_name(None, "en") is None
    assert country_name("", "en") == ""


def test_unsupported_language_falls_back_to_the_dataset_spelling():
    assert country_name("Spagna", "pt") == "Spagna"


CAREER = [
    {"team": "Barcelona", "country": "Spagna", "league": "La Liga", "start_year": 2004, "end_year": 2021},
    {"team": "Inter Miami", "country": "USA", "league": "MLS", "start_year": 2023, "end_year": None},
]


def test_localize_career_translates_the_country_and_leaves_the_league_alone():
    localized = localize_career(CAREER, "es")
    assert [stop["country"] for stop in localized] == ["España", "EE. UU."]
    # Il campionato e' un nome proprio: non si traduce.
    assert [stop["league"] for stop in localized] == ["La Liga", "MLS"]


def test_localize_career_does_not_touch_the_input():
    """La lista arriva dalla cache del dataset: tradurla sul posto tradurrebbe il dataset di
    tutti nella lingua del primo che gioca."""
    before = json.dumps(CAREER, sort_keys=True)
    localize_career(CAREER, "en")
    assert json.dumps(CAREER, sort_keys=True) == before


def test_localize_career_accepts_an_empty_or_missing_career():
    assert localize_career(None, "en") == []
    assert localize_career([], "es") == []


def test_localize_career_keeps_every_other_field():
    localized = localize_career(
        [{"team": "A", "country": "Spagna", "league": "La Liga", "start_year": 2000,
          "end_year": 2001, "apps": 30, "goals": 5, "loan": True}],
        "en",
    )
    assert localized[0] == {
        "team": "A", "country": "Spain", "league": "La Liga", "start_year": 2000,
        "end_year": 2001, "apps": 30, "goals": 5, "loan": True,
    }


@pytest.mark.parametrize("lang", SUPPORTED_LANGUAGES)
def test_the_card_renders_in_every_language(lang):
    """La traduzione non deve rompere il disegno: i glifi accentati devono esserci nel font
    e la card deve restare una PNG valida."""
    image = Image.open(render_career_path_image(CAREER, lang=lang))
    assert image.format == "PNG"
    assert image.width > 0 and image.height > 0
