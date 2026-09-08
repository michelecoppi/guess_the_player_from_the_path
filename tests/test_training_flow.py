"""Allenamento: sfide a raffica, senza punti e senza toccare la giornata."""
import asyncio
from types import SimpleNamespace

import pytest

from handlers import guess_handler, training_handler
from handlers.training_handler import MAX_TRAINING_ATTEMPTS

KEY = "pool:maldini"
CHALLENGE = {
    "key": KEY,
    "player_id": "maldini",
    "correct_answers": ["maldini", "paolo maldini"],
    "career_path": [{"team": "Milan", "country": "Italia", "league": "Serie A", "start_year": 1985, "end_year": 2009}],
    "difficulty": "medium",
    "answer": "Paolo Maldini",
    "day": None,
}


class FakeMessage:
    def __init__(self, text=""):
        self.text = text
        self.chat = SimpleNamespace(type="private", id=42)
        self.replies = []
        self.photos = []

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)

    async def reply_photo(self, photo, caption=None, **kwargs):
        self.photos.append(caption)


def make_update(text="", user_id=42):
    message = FakeMessage(text)
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id, first_name="Anna", language_code="it"),
        message=message,
        effective_message=message,
        effective_chat=message.chat,
    ), message


async def _noop(*args, **kwargs):
    return None


@pytest.fixture
def firebase(monkeypatch):
    state = {
        "user": {"telegram_id": 42, "language": "it", "training_key": KEY, "training_attempts": 0},
        "loaded": CHALLENGE,
    }
    calls = {"opened": [], "attempts": 0, "solved": 0, "cleared": 0, "daily_points": []}

    monkeypatch.setattr(training_handler.firebase_service, "get_user_data", lambda uid: state["user"])
    monkeypatch.setattr(guess_handler.firebase_service, "get_user_data", lambda uid: state["user"])
    monkeypatch.setattr(
        training_handler.firebase_service, "set_training_key",
        lambda uid, key: calls["opened"].append(key),
    )
    monkeypatch.setattr(
        training_handler.firebase_service, "register_training_attempt",
        lambda uid: calls.__setitem__("attempts", calls["attempts"] + 1),
    )
    monkeypatch.setattr(
        training_handler.firebase_service, "register_training_solved",
        lambda uid: calls.__setitem__("solved", calls["solved"] + 1),
    )
    monkeypatch.setattr(
        training_handler.firebase_service, "clear_training_key",
        lambda uid: calls.__setitem__("cleared", calls["cleared"] + 1),
    )
    monkeypatch.setattr(
        guess_handler.firebase_service, "register_correct_guess",
        lambda *a, **k: calls["daily_points"].append(a) or {},
    )
    monkeypatch.setattr(training_handler.practice_content, "pick", lambda exclude_keys=(): CHALLENGE)
    monkeypatch.setattr(training_handler.practice_content, "load", lambda key: state["loaded"])
    return SimpleNamespace(state=state, calls=calls)


def test_starting_a_session_serves_a_challenge(firebase):
    firebase.state["user"]["training_key"] = None
    update, message = make_update("/allenamento")
    asyncio.run(training_handler.training(update, None))

    assert firebase.calls["opened"] == [KEY]
    assert message.photos and "allenamento" in message.photos[0].lower()


def test_training_is_refused_to_someone_who_never_started(firebase):
    firebase.state["user"] = None
    update, message = make_update("/allenamento")
    asyncio.run(training_handler.training(update, None))

    assert firebase.calls["opened"] == []
    assert "registrarti" in message.replies[0]


def test_an_answer_goes_to_the_training_session_not_to_today(firebase):
    """Come per l'archivio: con una sessione aperta il messaggio libero vale per quella."""
    update, message = make_update("Maldini")
    asyncio.run(guess_handler.free_text_guess(update, None))

    assert firebase.calls["solved"] == 1
    assert firebase.calls["daily_points"] == []  # nessun punto, mai
    assert "Preso" in message.replies[0]


def test_a_wrong_answer_is_compared_and_counts_down(firebase):
    update, message = make_update("Del Piero")
    asyncio.run(guess_handler.free_text_guess(update, None))

    assert firebase.calls["attempts"] == 1
    assert f"{MAX_TRAINING_ATTEMPTS - 1}" in message.replies[0]
    assert "Del Piero" in message.replies[0]  # il confronto c'e' anche qui


def test_the_last_attempt_reveals_the_answer(firebase):
    """La sfida non e' in gioco per nessuno: tenersi la risposta non proteggerebbe niente."""
    firebase.state["user"]["training_attempts"] = MAX_TRAINING_ATTEMPTS - 1
    update, message = make_update("Del Piero")
    asyncio.run(guess_handler.free_text_guess(update, None))

    assert "Paolo Maldini" in message.replies[0]
    assert firebase.calls["cleared"] == 1


def test_the_reveal_button_closes_the_session(firebase):
    update, message = make_update()
    update.callback_query = SimpleNamespace(
        data=training_handler.REVEAL, message=message,
        from_user=update.effective_user, answer=_noop,
    )
    asyncio.run(training_handler.training_callback(update, None))

    assert "Paolo Maldini" in message.replies[0]
    assert firebase.calls["cleared"] == 1


def test_the_next_button_serves_another_one(firebase):
    update, message = make_update()
    update.callback_query = SimpleNamespace(
        data=training_handler.NEXT, message=message,
        from_user=update.effective_user, answer=_noop,
    )
    asyncio.run(training_handler.training_callback(update, None))

    assert firebase.calls["opened"] == [KEY]


def test_a_session_whose_challenge_disappeared_closes_itself(firebase):
    """Succede con una sfida passata cancellata dalla pulizia, o con una scheda tolta dal
    dataset: la sessione si chiude invece di rispondere sul vuoto."""
    firebase.state["loaded"] = None
    update, message = make_update("Maldini")
    asyncio.run(guess_handler.free_text_guess(update, None))

    assert firebase.calls["cleared"] == 1
    assert "disponibile" in message.replies[0]


def test_nothing_to_serve_is_said_and_not_crashed(firebase, monkeypatch):
    monkeypatch.setattr(training_handler.practice_content, "pick", lambda exclude_keys=(): None)
    firebase.state["user"]["training_key"] = None
    update, message = make_update("/allenamento")
    asyncio.run(training_handler.training(update, None))

    assert firebase.calls["opened"] == []
    assert message.photos == []
