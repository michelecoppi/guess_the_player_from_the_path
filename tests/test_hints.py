"""Indizi a pagamento: la scala e il costo (li usa la mini app, /app/api/hint).

Le due cose che qui non devono rompersi mai sono il **pavimento sui punti** (una sfida
"easy" vale 1 punto: due indizi non possono portarla a -1) e il fatto che gli indizi si
costruiscono **prima** di essere consumati, cosi' nessuno paga un punto per un messaggio
vuoto.
"""

import pytest

from services.hints import HINT_LADDER, MAX_HINTS, build_hints, points_after_hints
from services.i18n import SUPPORTED_LANGUAGES

PLAYER = {
    "id": "messi",
    "full_name": "Lionel Messi",
    "nationality": "Argentina",
    "position": "Attaccante",
    "birth_year": 1987,
}

CHALLENGE = {"player_id": "messi", "difficulty": "hard", "correct_answers": ["messi"]}


# ---------------------------------------------------------------------------
# La scala
# ---------------------------------------------------------------------------

def test_the_ladder_is_as_long_as_the_maximum():
    """Una scala piu' lunga del massimo sarebbe codice morto: le voci in fondo non
    uscirebbero mai."""
    assert MAX_HINTS == len(HINT_LADDER)


@pytest.mark.parametrize("lang", SUPPORTED_LANGUAGES)
def test_a_complete_player_offers_every_hint(lang):
    hints = build_hints(PLAYER, lang)
    assert len(hints) == MAX_HINTS


def test_the_hint_is_translated():
    assert "Argentina" in build_hints(PLAYER, "en")[0]
    assert "Forward" in build_hints(PLAYER, "en")[1]
    assert "Delantero" in build_hints(PLAYER, "es")[1]


def test_a_player_without_a_position_offers_one_hint_only():
    """`position` non e' obbligatorio nel dataset: quell'indizio semplicemente non esiste."""
    assert len(build_hints({"nationality": "Italia"}, "it")) == 1


def test_a_player_without_data_offers_nothing():
    assert build_hints({}, "it") == []
    assert build_hints(None, "it") == []


def test_the_nationality_comes_before_the_position():
    """La nazionalita' restringe di piu' senza risolvere: i ruoli sono quattro."""
    first, second = build_hints(PLAYER, "it")
    assert "Argentina" in first
    assert "Attaccante" in second


# ---------------------------------------------------------------------------
# Il costo
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("base,hints,expected", [
    (4, 0, 4),
    (4, 1, 3),
    (4, 2, 2),
    (2, 2, 1),
    (1, 1, 1),   # pavimento: una sfida "easy" resta da 1 punto
    (1, 2, 1),
])
def test_points_after_hints(base, hints, expected):
    assert points_after_hints(base, hints) == expected
