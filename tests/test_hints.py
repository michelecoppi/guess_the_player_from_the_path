"""Indizi a pagamento: la scala, il costo, e il bottone che li offre.

Le due cose che qui non devono rompersi mai sono il **pavimento sui punti** (una sfida
"easy" vale 1 punto: due indizi non possono portarla a -1) e il fatto che gli indizi si
costruiscono **prima** di essere consumati, cosi' nessuno paga un punto per un messaggio
vuoto.
"""
import asyncio
from types import SimpleNamespace

import pytest

from handlers import hint_handler
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


# ---------------------------------------------------------------------------
# Il bottone e la callback
# ---------------------------------------------------------------------------

class FakeMessage:
    def __init__(self):
        self.replies = []
        self.markups = []

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)
        self.markups.append(kwargs.get("reply_markup"))


def make_query(user_id=42):
    message = FakeMessage()

    async def answer():
        return None

    user = SimpleNamespace(id=user_id, first_name="Anna", language_code="it")
    query = SimpleNamespace(data=hint_handler.CALLBACK_DATA, answer=answer, message=message, from_user=user)
    return SimpleNamespace(callback_query=query, effective_user=user), message


@pytest.fixture
def hints_backend(monkeypatch):
    """Firestore e la sfida del giorno sostituiti: resta solo la logica dell'handler."""
    state = {"taken": 0, "result": None, "challenge": CHALLENGE, "player": PLAYER}
    calls = []

    def take_daily_hint(user_id, day_iso, max_hints, max_attempts):
        calls.append({"user_id": user_id, "max_hints": max_hints, "max_attempts": max_attempts})
        if state["result"] is not None:
            return state["result"]
        state["taken"] += 1
        return {"ok": True, "index": state["taken"], "hints_used": state["taken"]}

    monkeypatch.setattr(hint_handler.game.firebase_service, "take_daily_hint", take_daily_hint)
    monkeypatch.setattr(hint_handler, "get_today_challenge", lambda: state["challenge"])
    monkeypatch.setattr(hint_handler.game, "get_player_by_id", lambda pid: state["player"])
    monkeypatch.setattr(hint_handler, "language_for", lambda update: "it")
    return SimpleNamespace(state=state, calls=calls)


def _buttons(markup):
    return [b.callback_data for row in markup.inline_keyboard for b in row] if markup else []


def test_the_first_hint_is_the_nationality_and_says_what_it_costs(hints_backend):
    update, message = make_query()
    asyncio.run(hint_handler.hint_callback(update, None))

    assert "Argentina" in message.replies[0]
    # hard vale 3 punti: dopo un indizio ne restano 2.
    assert "2" in message.replies[0] and "3" in message.replies[0]


def test_the_button_comes_back_until_the_hints_run_out(hints_backend):
    update, message = make_query()
    asyncio.run(hint_handler.hint_callback(update, None))
    assert _buttons(message.markups[0]) == [hint_handler.CALLBACK_DATA]

    asyncio.run(hint_handler.hint_callback(update, None))
    # Secondo (e ultimo) indizio: niente bottone, non c'e' piu' niente da offrire.
    assert _buttons(message.markups[1]) == []


def test_a_challenge_without_hints_costs_nothing(hints_backend):
    """Nessun indizio disponibile: si avvisa e **non** si consuma niente."""
    hints_backend.state["player"] = {}
    update, message = make_query()
    asyncio.run(hint_handler.hint_callback(update, None))

    assert hints_backend.calls == []
    assert "indizi" in message.replies[0].lower()


def test_the_maximum_offered_follows_the_player_card(hints_backend):
    """Una scheda con un solo indizio non deve permettere di pagarne due."""
    hints_backend.state["player"] = {"nationality": "Italia"}
    update, _ = make_query()
    asyncio.run(hint_handler.hint_callback(update, None))

    assert hints_backend.calls[0]["max_hints"] == 1


@pytest.mark.parametrize("reason,expected", [
    ("needs_attempt", "tentativo"),
    ("already_guessed", "indovinato"),
    ("no_attempts", "finiti"),
    ("no_more", "già usato"),
])
def test_every_refusal_has_its_own_message(hints_backend, reason, expected):
    hints_backend.state["result"] = {"ok": False, "reason": reason}
    update, message = make_query()
    asyncio.run(hint_handler.hint_callback(update, None))

    assert expected in message.replies[0].lower()


def test_without_a_challenge_nothing_is_consumed(hints_backend):
    hints_backend.state["challenge"] = None
    update, message = make_query()
    asyncio.run(hint_handler.hint_callback(update, None))

    assert hints_backend.calls == []
    assert message.replies
