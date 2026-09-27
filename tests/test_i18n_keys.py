"""Le tre lingue devono avere esattamente le stesse chiavi.

Senza questo test una chiave aggiunta solo in italiano non si nota: `t()` ripiega in
silenzio sull'italiano, e un utente inglese si ritrova una frase in italiano in mezzo a un
messaggio suo. Qui invece la CI se ne accorge subito.
"""
import string

import pytest

from services.i18n import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, TRANSLATIONS


def _placeholders(template):
    return {name for _, name, _, _ in string.Formatter().parse(template) if name}


@pytest.mark.parametrize("lang", [lang for lang in SUPPORTED_LANGUAGES if lang != DEFAULT_LANGUAGE])
def test_every_language_has_the_same_keys(lang):
    reference = set(TRANSLATIONS[DEFAULT_LANGUAGE])
    assert set(TRANSLATIONS[lang]) == reference


@pytest.mark.parametrize("lang", [lang for lang in SUPPORTED_LANGUAGES if lang != DEFAULT_LANGUAGE])
def test_every_translation_uses_the_same_placeholders(lang):
    """Un `{points}` dimenticato in una traduzione diventa un KeyError in faccia all'utente
    nel momento peggiore: quando ha appena indovinato."""
    mismatched = {
        key: (_placeholders(TRANSLATIONS[DEFAULT_LANGUAGE][key]), _placeholders(value))
        for key, value in TRANSLATIONS[lang].items()
        if key in TRANSLATIONS[DEFAULT_LANGUAGE]
        and _placeholders(value) != _placeholders(TRANSLATIONS[DEFAULT_LANGUAGE][key])
    }
    assert mismatched == {}
