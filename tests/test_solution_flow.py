"""/solution: la risposta di una giornata gia' chiusa, e la percentuale di chi l'ha presa.

Il controllo che conta piu' di tutti e' `test_today_is_never_revealed`: la sfida di oggi e'
la stessa per tutti, e una soluzione a richiesta la renderebbe incollabile in un gruppo
dieci minuti dopo la mezzanotte. Se quel test smette di passare, il gioco e' rotto.
"""
import asyncio
from types import SimpleNamespace

import pytest

from handlers import solution_handler
from services.daily_stats import MIN_PLAYERS_FOR_RATE, rate_line, solve_percent

CHALLENGE = {
    "day": "2026-09-06",
    "difficulty": "hard",
    "correct_answers": ["messi", "lionel messi"],
    "career_path": [
        {"team": "Barcelona", "country": "Spagna", "league": "La Liga", "start_year": 2004, "end_year": 2021},
        {"team": "Inter Miami", "country": "USA", "league": "MLS", "start_year": 2023, "end_year": None},
    ],
}


class FakeMessage:
    def __init__(self):
        self.replies = []
        self.photos = []
        self.markups = []

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)
        self.markups.append(kwargs.get("reply_markup"))

    async def reply_photo(self, photo, caption=None, **kwargs):
        self.photos.append((photo, caption))
        self.markups.append(kwargs.get("reply_markup"))


def make_update(user_id=42):
    message = FakeMessage()
    user = SimpleNamespace(id=user_id, first_name="Anna", language_code="it")
    return SimpleNamespace(effective_user=user, effective_message=message, message=message), message


def context_with(*args):
    return SimpleNamespace(args=list(args))


@pytest.fixture
def backend(monkeypatch):
    state = {
        "today": "2026-09-08",
        "challenge": CHALLENGE,
        "name": "Lionel Messi",
        "stats": (100, 41),
        "registered": True,
    }
    monkeypatch.setattr(solution_handler, "today_iso", lambda: state["today"])
    monkeypatch.setattr(solution_handler, "yesterday_iso", lambda: "2026-09-07")
    monkeypatch.setattr(solution_handler, "language_for", lambda update: "it")
    monkeypatch.setattr(
        solution_handler.firebase_service, "get_user_data",
        lambda uid: {"language": "it"} if state["registered"] else None,
    )
    monkeypatch.setattr(
        solution_handler.firebase_service, "get_daily_path", lambda day: state["challenge"]
    )
    monkeypatch.setattr(
        solution_handler.firebase_service, "get_display_name_for_day", lambda day: state["name"]
    )
    monkeypatch.setattr(
        solution_handler.firebase_service, "get_daily_stats", lambda day: state["stats"]
    )
    return SimpleNamespace(state=state)


# ---------------------------------------------------------------------------
# Cosa si rivela e cosa no
# ---------------------------------------------------------------------------

def test_yesterday_is_revealed_with_the_card(backend):
    update, message = make_update()
    asyncio.run(solution_handler.solution(update, context_with()))

    _, caption = message.photos[0]
    assert "Lionel Messi" in caption


def test_today_is_never_revealed(backend):
    """La sfida di oggi e' ancora in gioco per tutti: la soluzione arriva a mezzanotte."""
    update, message = make_update()
    asyncio.run(solution_handler.solution(update, context_with("08/09/26")))

    assert message.photos == []
    assert "Messi" not in message.replies[0]
    assert "mezzanotte" in message.replies[0]


def test_a_future_day_is_not_revealed_either(backend):
    update, message = make_update()
    asyncio.run(solution_handler.solution(update, context_with("31/12/26")))

    assert message.photos == []
    assert "Messi" not in message.replies[0]


def test_an_explicit_past_day_is_revealed(backend):
    update, message = make_update()
    asyncio.run(solution_handler.solution(update, context_with("06/09/26")))

    _, caption = message.photos[0]
    assert "06/09/26" in caption
    assert "Lionel Messi" in caption


def test_an_unreadable_date_explains_the_format(backend):
    update, message = make_update()
    asyncio.run(solution_handler.solution(update, context_with("il", "giorno", "prima")))

    assert message.photos == []
    assert "/solution" in message.replies[0]


def test_a_missing_day_says_so(backend):
    backend.state["challenge"] = None
    update, message = make_update()
    asyncio.run(solution_handler.solution(update, context_with("01/01/26")))

    assert message.photos == []
    assert "01/01/26" in message.replies[0]


def test_an_unregistered_user_is_sent_to_start(backend):
    backend.state["registered"] = False
    update, message = make_update()
    asyncio.run(solution_handler.solution(update, context_with()))

    assert "/start" in message.replies[0]


def test_a_day_without_a_career_path_still_gives_the_answer(backend):
    """Le giornate vecchie hanno solo un'immagine su un hosting esterno: la risposta si dice
    comunque, in testo."""
    backend.state["challenge"] = {"difficulty": "easy", "correct_answers": ["messi"]}
    update, message = make_update()
    asyncio.run(solution_handler.solution(update, context_with()))

    assert message.photos == []
    assert "Lionel Messi" in message.replies[0]


# ---------------------------------------------------------------------------
# La percentuale
# ---------------------------------------------------------------------------

def test_the_solution_says_how_many_got_it(backend):
    update, message = make_update()
    asyncio.run(solution_handler.solution(update, context_with()))

    _, caption = message.photos[0]
    assert "41%" in caption


def test_too_few_players_means_no_percentage(backend):
    """Con tre partecipanti "33%" e' un solo utente: meglio non dire niente."""
    backend.state["stats"] = (3, 1)
    update, message = make_update()
    asyncio.run(solution_handler.solution(update, context_with()))

    _, caption = message.photos[0]
    assert "%" not in caption


def test_days_from_before_the_counters_say_nothing(backend):
    backend.state["stats"] = (0, 0)
    update, message = make_update()
    asyncio.run(solution_handler.solution(update, context_with()))

    _, caption = message.photos[0]
    assert "%" not in caption


@pytest.mark.parametrize("players,solved,expected", [
    (100, 41, 41),
    (7, 7, 100),
    (7, 0, 0),
    (3, 3, None),                        # troppo pochi
    (0, 0, None),
    (None, 0, None),
    (MIN_PLAYERS_FOR_RATE, 1, 20),
])
def test_solve_percent(players, solved, expected):
    assert solve_percent(players, solved) == expected


def test_more_solvers_than_players_is_capped():
    """Non deve poter uscire un 120%: i due contatori sono incrementi indipendenti, e un
    tentativo perso per strada renderebbe il numeratore piu' grande del denominatore."""
    assert solve_percent(10, 12) == 100


def test_the_rate_line_can_stay_silent():
    assert rate_line("it", 0, 0, unknown_key=None) == ""
    assert rate_line("it", 0, 0) != ""
