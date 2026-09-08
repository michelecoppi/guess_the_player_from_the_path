"""Archivio: rigiocare una sfida passata non deve dare punti ne' toccare la giornata."""
import asyncio
from types import SimpleNamespace

import pytest

from handlers import archive_handler, guess_handler

DAY = "2026-09-01"
CHALLENGE = {"day": DAY, "correct_answers": ["messi", "lionel messi"], "difficulty": "medium", "career_path": [{"team": "Barcelona", "start_year": 2004, "end_year": 2021}]}


class FakeMessage:
    def __init__(self, text=""):
        self.text = text
        self.chat = SimpleNamespace(type="private")
        self.replies = []
        self.photos = []
        self.markups = []

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)
        self.markups.append(kwargs.get("reply_markup"))

    async def reply_photo(self, photo, caption=None, **kwargs):
        self.photos.append(caption)


def make_update(text="", user_id=42):
    message = FakeMessage(text)
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id, language_code="it"),
        message=message,
        effective_message=message,
        effective_chat=message.chat,
    ), message


@pytest.fixture
def firebase(monkeypatch):
    state = {
        "user": {"telegram_id": 42, "language": "it", "archive_day": DAY},
        "attempt": {"ok": True, "attempts_used": 1, "attempts_left": 2},
    }
    calls = {"solved": [], "archive_day": [], "daily_registered": [], "closed": []}

    monkeypatch.setattr(archive_handler.firebase_service, "get_user_data", lambda uid: state["user"])
    monkeypatch.setattr(archive_handler.firebase_service, "get_daily_path", lambda day: CHALLENGE if day == DAY else None)
    monkeypatch.setattr(archive_handler.firebase_service, "begin_archive_attempt", lambda uid, day, mx: state["attempt"])
    monkeypatch.setattr(
        archive_handler.firebase_service, "register_archive_solved",
        lambda uid, day, attempts: calls["solved"].append((uid, day, attempts)),
    )
    monkeypatch.setattr(
        archive_handler.firebase_service, "set_archive_day",
        lambda uid, day: calls["archive_day"].append(day),
    )
    monkeypatch.setattr(archive_handler.firebase_service, "get_display_name_for_day", lambda day: "Messi")
    monkeypatch.setattr(
        archive_handler.firebase_service, "clear_training_key",
        lambda uid: calls["closed"].append("training"),
    )
    monkeypatch.setattr(
        archive_handler.firebase_service, "clear_event_key",
        lambda uid: calls["closed"].append("event"),
    )
    monkeypatch.setattr(guess_handler.firebase_service, "get_user_data", lambda uid: state["user"])
    monkeypatch.setattr(
        guess_handler.firebase_service, "register_correct_guess",
        lambda *a, **k: calls["daily_registered"].append(a) or {},
    )
    return SimpleNamespace(state=state, calls=calls)


def test_an_answer_goes_to_the_open_archive_challenge_not_to_today(firebase):
    update, message = make_update("Messi")
    asyncio.run(guess_handler.free_text_guess(update, None))

    assert firebase.calls["solved"] == [(42, DAY, 1)]
    assert firebase.calls["daily_registered"] == []  # nessun punto, e la giornata resta intatta
    assert "recuperata" in message.replies[0]


def test_leaving_the_archive_restores_the_daily_challenge(firebase):
    update, message = make_update()
    asyncio.run(archive_handler.back_to_today(update, None))

    assert firebase.calls["archive_day"] == [None]
    assert "oggi" in message.replies[0]


def test_a_wrong_answer_counts_down_the_attempts(firebase):
    firebase.state["attempt"] = {"ok": True, "attempts_used": 1, "attempts_left": 2}
    update, message = make_update("Maldini")
    asyncio.run(guess_handler.free_text_guess(update, None))

    assert firebase.calls["solved"] == []
    assert "2" in message.replies[0]


def test_the_last_wrong_attempt_reveals_the_answer(firebase):
    """A differenza della sfida di oggi, qui la risposta si puo' dire: e' gia' passata."""
    firebase.state["attempt"] = {"ok": True, "attempts_used": 3, "attempts_left": 0}
    update, message = make_update("Maldini")
    asyncio.run(guess_handler.free_text_guess(update, None))

    assert "Messi" in message.replies[0]
    assert firebase.calls["archive_day"] == [None]


def test_an_already_solved_day_is_not_replayable(firebase):
    firebase.state["attempt"] = {"ok": False, "reason": "already_solved"}
    update, message = make_update("Messi")
    asyncio.run(guess_handler.free_text_guess(update, None))

    assert firebase.calls["solved"] == []
    assert "già" in message.replies[0]


def test_a_deleted_archive_day_closes_the_session(firebase):
    firebase.state["user"]["archive_day"] = "1999-01-01"
    update, message = make_update("Messi")
    asyncio.run(guess_handler.free_text_guess(update, None))

    assert firebase.calls["archive_day"] == [None]
    assert "disponibile" in message.replies[0]


def test_opening_a_day_sends_the_path_and_starts_the_session(firebase, monkeypatch):
    async def answer():
        return None

    monkeypatch.setattr(archive_handler.firebase_service, "get_archive_result", lambda uid, day: {"solved": False})

    update, message = make_update()
    update.callback_query = SimpleNamespace(
        data=f"{archive_handler.CALLBACK_PREFIX}{DAY}", answer=answer, message=message
    )

    asyncio.run(archive_handler.archive_callback(update, None))

    assert firebase.calls["archive_day"] == [DAY]
    assert message.photos and "01/09/26" in message.photos[0]


def test_a_recovered_day_can_be_shared_as_an_archive_result(firebase, monkeypatch):
    """La sfida recuperata si condivide, ma marcata come archivio: in un gruppo dove quella
    di oggi e' ancora aperta, la riga va letta al volo."""
    from services import share

    monkeypatch.setattr(share, "BOT_USERNAME", "guess_the_player_bot")
    update, message = make_update("Messi")
    asyncio.run(guess_handler.free_text_guess(update, None))

    assert message.markups[0] is not None
    assert "archivio" in message.markups[0].inline_keyboard[0][0].url


def test_a_wrong_archive_answer_is_compared_too(firebase, monkeypatch):
    monkeypatch.setattr(
        archive_handler.firebase_service, "get_daily_path",
        lambda day: dict(CHALLENGE, player_id="messi") if day == DAY else None,
    )
    update, message = make_update("Del Piero")
    asyncio.run(guess_handler.free_text_guess(update, None))

    assert "Del Piero" in message.replies[0]
    assert "messi" not in message.replies[0].lower()


# ---------------------------------------------------------------------------
# /today chiude qualunque partita che non sia quella di oggi
# ---------------------------------------------------------------------------

def test_today_closes_an_open_training(firebase):
    firebase.state["user"] = {"telegram_id": 42, "language": "it", "training_key": "pool:maldini"}
    update, message = make_update()
    asyncio.run(archive_handler.back_to_today(update, None))

    assert firebase.calls["closed"] == ["training"]
    assert "llenamento" in message.replies[0]


def test_today_closes_an_open_event(firebase):
    """L'evento e' la terza sessione: prima di questa tranche /today non la chiudeva, e un
    utente restava a rispondere all'evento senza capire perche'."""
    firebase.state["user"] = {"telegram_id": 42, "language": "it", "event_key": "giramondo:2026-09-08"}
    update, message = make_update()
    asyncio.run(archive_handler.back_to_today(update, None))

    assert firebase.calls["closed"] == ["event"]
    assert "vento" in message.replies[0]


def test_today_says_so_when_there_is_nothing_to_close(firebase):
    firebase.state["user"] = {"telegram_id": 42, "language": "it"}
    update, message = make_update()
    asyncio.run(archive_handler.back_to_today(update, None))

    assert firebase.calls["closed"] == []
    assert firebase.calls["archive_day"] == []
    assert "/archive" in message.replies[0]
