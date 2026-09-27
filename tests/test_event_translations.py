"""Nome e descrizione dell'evento nella lingua di chi guarda.

Erano gli ultimi testi che restavano in italiano per tutti: stanno nel contenuto
(data/event_templates.json) e non fra le traduzioni, quindi non li copriva il test che
verifica l'allineamento delle tre lingue.
"""
import json
import os

import pytest

from handlers.events_handler import _event_name, get_event_home_message
from services.i18n import SUPPORTED_LANGUAGES, content_text

TEMPLATES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "event_templates.json"
)

EVENT = {
    "code": "giramondo_20260901",
    "name": "Giramondo",
    "description": "Calciatori che hanno girato il mondo.",
    "name_i18n": {"es": "Trotamundos", "en": "Globetrotters"},
    "description_i18n": {"es": "Futbolistas que dieron la vuelta al mundo.", "en": "Players who travelled the world."},
    "dates": ["2026-09-01"],
    "type": "path",
}


def _templates():
    with open(TEMPLATES_PATH, encoding="utf-8") as f:
        return json.load(f)["templates"]


# ---------------------------------------------------------------------------
# Il contenuto
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("lang", SUPPORTED_LANGUAGES)
@pytest.mark.parametrize("field", ["name", "description"])
def test_every_template_is_translated_in_every_language(lang, field):
    """Come per le tre lingue di TRANSLATIONS: un evento aggiunto solo in italiano non si
    nota finche' non lo apre uno spagnolo."""
    for template in _templates():
        assert content_text(template, field, lang), f"{template['id']}: manca {field} in {lang}"


def test_the_italian_stays_the_default_field():
    """`name` e `description` restano il testo italiano: sono il ripiego, e sono anche cio'
    che l'amministrazione (in italiano) continua a leggere."""
    for template in _templates():
        assert template["name"] == content_text(template, "name", "it")


# ---------------------------------------------------------------------------
# L'uso
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("lang,expected", [("it", "Giramondo"), ("es", "Trotamundos"), ("en", "Globetrotters")])
def test_the_event_name_follows_the_reader(lang, expected):
    assert _event_name(EVENT, lang) == expected


@pytest.mark.parametrize("lang,expected", [("es", "Trotamundos"), ("en", "Globetrotters")])
def test_the_home_message_is_translated_end_to_end(lang, expected):
    message = get_event_home_message(EVENT, lang)

    assert expected in message
    assert "Giramondo" not in message


def test_an_event_generated_before_the_translations_still_shows_something():
    """Gli eventi gia' su Firestore non hanno i campi `_i18n`: meglio il nome italiano che
    una riga vuota."""
    old_event = {k: v for k, v in EVENT.items() if not k.endswith("_i18n")}

    assert _event_name(old_event, "en") == "Giramondo"
    assert content_text(old_event, "description", "es") == EVENT["description"]


def test_an_event_without_a_name_at_all_falls_back_to_the_label():
    assert _event_name({}, "en") == content_text({}, "name", "en", default=_event_name({}, "en"))
    assert _event_name({}, "en")  # mai una stringa vuota
