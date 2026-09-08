"""Flusso di /guess dopo il passaggio a tentativi transazionali e reset "pigro"."""
import asyncio
from types import SimpleNamespace

import pytest

from handlers import guess_handler


class FakeMessage:
    def __init__(self, text):
        self.text = text
        self.chat = SimpleNamespace(type="private")
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)


def make_update(text, user_id=42):
    message = FakeMessage(text)
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id, first_name="Anna"),
        message=message,
        effective_message=message,
    )
    return update, message


CHALLENGE = {"correct_answers": ["messi", "lionel messi"], "difficulty": "medium", "career_path": [{}, {}]}


@pytest.fixture
def firebase(monkeypatch):
    """Sostituto in memoria delle sole funzioni Firestore usate da /guess."""
    calls = {"registered": [], "claims": 0, "attempts": []}

    state = {"attempt": {"ok": True, "attempts_used": 1, "attempts_left": 2}, "first_free": True}

    def begin_guess_attempt(user_id, day, max_attempts):
        calls["attempts"].append((user_id, day, max_attempts))
        return state["attempt"]

    def claim_daily_first_correct(day):
        calls["claims"] += 1
        if state["first_free"]:
            state["first_free"] = False
            return True
        return False

    def register_correct_guess(user_id, points, bonus, day, monthly=True):
        calls["registered"].append({"user_id": user_id, "points": points, "bonus": bonus, "day": day})

    monkeypatch.setattr(guess_handler.firebase_service, "begin_guess_attempt", begin_guess_attempt)
    monkeypatch.setattr(guess_handler.firebase_service, "claim_daily_first_correct", claim_daily_first_correct)
    monkeypatch.setattr(guess_handler.firebase_service, "register_correct_guess", register_correct_guess)
    monkeypatch.setattr(guess_handler.firebase_service, "get_user_data", lambda uid: None)
    monkeypatch.setattr(
        guess_handler.firebase_service, "add_points_to_leagues",
        lambda uid, codes, points, name=None: calls.setdefault("leagues", []).append((codes, points)),
    )
    monkeypatch.setattr(guess_handler, "get_today_challenge", lambda: CHALLENGE)
    return SimpleNamespace(calls=calls, state=state)


def test_correct_answer_awards_points_plus_first_bonus(firebase):
    update, message = make_update("/guess Messi")
    asyncio.run(guess_handler.guess(update, None))

    registered = firebase.calls["registered"][0]
    assert registered["bonus"] == 1
    assert registered["points"] == 3  # medium (2) + bonus (1)
    assert "Corretto" in message.replies[0]


def test_only_the_first_correct_user_gets_the_bonus(firebase):
    update, _ = make_update("/guess messi", user_id=1)
    asyncio.run(guess_handler.guess(update, None))
    update, message = make_update("/guess messi", user_id=2)
    asyncio.run(guess_handler.guess(update, None))

    assert [r["bonus"] for r in firebase.calls["registered"]] == [1, 0]
    assert [r["points"] for r in firebase.calls["registered"]] == [3, 2]
    assert "Bonus" not in message.replies[0]


def test_wrong_answer_reports_remaining_attempts(firebase):
    update, message = make_update("/guess ronaldo")
    asyncio.run(guess_handler.guess(update, None))

    assert firebase.calls["registered"] == []
    assert "2 tentativi rimasti" in message.replies[0]


def test_last_wrong_attempt_says_the_day_is_over(firebase):
    firebase.state["attempt"] = {"ok": True, "attempts_used": 3, "attempts_left": 0}
    update, message = make_update("/guess ronaldo")
    asyncio.run(guess_handler.guess(update, None))

    assert "esaurito i tentativi" in message.replies[0]


@pytest.mark.parametrize("reason,expected", [
    ("not_registered", "registrarti"),
    ("already_guessed", "già indovinato"),
    ("no_attempts", "esaurito i tentativi"),
])
def test_refused_attempts_are_explained(firebase, reason, expected):
    firebase.state["attempt"] = {"ok": False, "reason": reason}
    update, message = make_update("/guess messi")
    asyncio.run(guess_handler.guess(update, None))

    assert expected in message.replies[0]
    assert firebase.calls["registered"] == []


def test_empty_guess_does_not_consume_an_attempt(firebase):
    update, message = make_update("/guess   ")
    asyncio.run(guess_handler.guess(update, None))

    assert firebase.calls["attempts"] == []
    assert "Devi scrivere" in message.replies[0]


def test_missing_challenge_does_not_consume_an_attempt(firebase, monkeypatch):
    monkeypatch.setattr(guess_handler, "get_today_challenge", lambda: None)
    update, message = make_update("/guess messi")
    asyncio.run(guess_handler.guess(update, None))

    assert firebase.calls["attempts"] == []
    assert "sfida giornaliera" in message.replies[0]


def test_guess_outside_private_chat_is_refused(firebase):
    update, message = make_update("/guess messi")
    update.message.chat = SimpleNamespace(type="group")
    asyncio.run(guess_handler.guess(update, None))

    assert "chat privata" in message.replies[0]
    assert firebase.calls["attempts"] == []


def test_a_plain_message_counts_as_a_guess(firebase):
    """Scrivere il nome senza /guess deve valere come tentativo: era l'attrito principale."""
    update, message = make_update("Messi")
    asyncio.run(guess_handler.free_text_guess(update, None))

    assert firebase.calls["registered"][0]["points"] == 3
    assert "Corretto" in message.replies[0]


def test_a_message_that_is_not_an_answer_does_not_consume_an_attempt(firebase):
    update, message = make_update("https://esempio.it/una-pagina-qualsiasi")
    asyncio.run(guess_handler.free_text_guess(update, None))

    assert firebase.calls["attempts"] == []
    assert "Scrivimi il nome" in message.replies[0]


def test_a_typo_is_accepted_and_signalled(firebase):
    update, message = make_update("/guess messsi")
    asyncio.run(guess_handler.guess(update, None))

    assert firebase.calls["registered"][0]["points"] == 3
    assert "Corretto" in message.replies[0]
    assert "messsi" in message.replies[0]


def test_another_player_is_still_wrong(firebase):
    update, message = make_update("/guess maldini")
    asyncio.run(guess_handler.guess(update, None))

    assert firebase.calls["registered"] == []
    assert "2 tentativi rimasti" in message.replies[0]
