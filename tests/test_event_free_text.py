"""Gli eventi rispondono al testo libero come tutte le altre modalita'.

Erano l'ultimo posto in cui bisognava ancora scrivere un comando (`/events Messi`). Ora
aprire la scheda "Giocatore" apre una sessione (`event_key`) e i messaggi liberi valgono
per l'evento.

Le due cose fragili, e quindi quelle su cui insistono i test:

- la chiave porta con se' il **giorno**, perche' a mezzanotte la sfida dell'evento cambia:
  una sessione di ieri non deve rispondere per l'immagine di oggi;
- le tre sessioni (archivio, allenamento, evento) si escludono, quindi il routing in
  handlers/guess_handler.py non e' una precedenza da ricordare.
"""
import asyncio
from types import SimpleNamespace

import pytest

from handlers import events_handler, guess_handler
from services.dates import today_iso
from services.matching import looks_like_an_answer


class FakeMessage:
    def __init__(self, text=""):
        self.text = text
        self.chat = SimpleNamespace(type="private")
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)


def make_update(text="messi", user_id=42):
    message = FakeMessage(text)
    user = SimpleNamespace(id=user_id, first_name="Anna", language_code="it")
    return SimpleNamespace(
        effective_user=user, message=message, effective_message=message, effective_chat=message.chat,
    ), message


def path_event(code="giramondo_20261201", day=None):
    day = day or today_iso()
    return {
        "code": code,
        "type": "path",
        "name": "Giramondo",
        "dates": [day],
        "daily_data": {day: {
            "correct_answers": ["messi", "lionel messi"],
            "player_id": "messi",
            "points": 2,
            "first_correct_user": False,
        }},
    }


@pytest.fixture
def firebase(monkeypatch):
    calls = {"registered": [], "attempts": [], "cleared": [], "opened": []}
    state = {
        "attempt": {"ok": True, "attempts_used": 1, "attempts_left": 2},
        "event": path_event(),
    }

    monkeypatch.setattr(
        events_handler.firebase_service, "begin_event_attempt",
        lambda code, uid, name, day, mx: (calls["attempts"].append((code, uid, day)) or state["attempt"]),
    )
    monkeypatch.setattr(events_handler.firebase_service, "claim_event_first_correct", lambda code, day: False)
    monkeypatch.setattr(
        events_handler.firebase_service, "register_event_correct_guess",
        lambda code, uid, points, day: calls["registered"].append({"code": code, "points": points}),
    )
    monkeypatch.setattr(
        events_handler.firebase_service, "clear_event_key", lambda uid: calls["cleared"].append(uid)
    )
    monkeypatch.setattr(
        events_handler.firebase_service, "set_event_key",
        lambda uid, key: calls["opened"].append((uid, key)),
    )
    monkeypatch.setattr(events_handler.firebase_service, "get_current_event", lambda *a: state["event"])
    monkeypatch.setattr(events_handler.firebase_service, "get_user_data", lambda uid: None)
    return SimpleNamespace(calls=calls, state=state)


# ---------------------------------------------------------------------------
# La sessione
# ---------------------------------------------------------------------------

def test_the_session_key_carries_the_day():
    key = events_handler.session_key("giramondo_20261201", "2026-09-08")
    assert key == "giramondo_20261201:2026-09-08"


def test_a_free_text_answer_counts_for_the_open_event(firebase):
    update, message = make_update("messi")
    user_data = {"event_key": events_handler.session_key("giramondo_20261201")}

    asyncio.run(events_handler.process_event_answer(update, None, "messi", user_data))

    assert firebase.calls["registered"][0]["points"] == 2
    assert "Corretto" in message.replies[0]


def test_guessing_right_closes_the_session(firebase):
    """Cosi' i messaggi successivi tornano a valere per la sfida del giorno, senza /today."""
    update, _ = make_update("messi")
    user_data = {"event_key": events_handler.session_key("giramondo_20261201")}

    asyncio.run(events_handler.process_event_answer(update, None, "messi", user_data))
    assert firebase.calls["cleared"] == [42]


def test_a_session_from_yesterday_is_closed_without_consuming_an_attempt(firebase):
    """A mezzanotte l'immagine dell'evento cambia: la sessione di ieri non vale piu'."""
    update, message = make_update("messi")
    user_data = {"event_key": events_handler.session_key("giramondo_20261201", "2020-01-01")}

    asyncio.run(events_handler.process_event_answer(update, None, "messi", user_data))

    assert firebase.calls["attempts"] == []
    assert firebase.calls["cleared"] == [42]
    assert "non è più in corso" in message.replies[0]


def test_a_session_on_a_finished_event_is_closed(firebase):
    firebase.state["event"] = path_event(code="un_altro_evento_20261210")
    update, message = make_update("messi")
    user_data = {"event_key": events_handler.session_key("giramondo_20261201")}

    asyncio.run(events_handler.process_event_answer(update, None, "messi", user_data))

    assert firebase.calls["attempts"] == []
    assert "non è più in corso" in message.replies[0]


def test_the_command_does_not_touch_the_session(firebase):
    """Chi risponde con `/events <nome>` una sessione non l'ha mai aperta: chiuderla sarebbe
    una scrittura per niente."""
    update, _ = make_update()
    asyncio.run(events_handler.process_event_guess(update, SimpleNamespace(args=["messi"]), path_event()))

    assert firebase.calls["registered"]
    assert firebase.calls["cleared"] == []


# ---------------------------------------------------------------------------
# Il routing dal flusso normale delle risposte
# ---------------------------------------------------------------------------

def test_the_answer_flow_routes_to_the_open_event(monkeypatch):
    routed = []

    async def fake_event_answer(update, context, answer, user_data):
        routed.append(answer)

    monkeypatch.setattr(guess_handler, "process_event_answer", fake_event_answer)
    monkeypatch.setattr(
        guess_handler.firebase_service, "get_user_data",
        lambda uid: {"event_key": "giramondo:2026-09-08", "language": "it"},
    )
    called = []
    monkeypatch.setattr(guess_handler, "get_today_challenge", lambda: called.append(1))

    update, _ = make_update("messi")
    asyncio.run(guess_handler.process_answer(update, None, "messi"))

    assert routed == ["messi"]
    # La sfida del giorno non viene nemmeno letta: la risposta era per l'evento.
    assert called == []


# ---------------------------------------------------------------------------
# Il filtro sul testo libero deve lasciar passare gli elenchi degli eventi "career"
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "Roma, Manchester United, Toronto FC",
    "roma,inter",
    "Roma, Inter, Milan, Juventus, Napoli",
])
def test_a_comma_list_looks_like_an_answer(text):
    assert looks_like_an_answer(text)


@pytest.mark.parametrize("text", [
    "ciao, come stai",
    "grazie, ciao",
    "Roma, Inter, Milan, Juventus, Napoli, Lazio",          # oltre il massimo di voci
    "guarda qui, https://esempio.it",
])
def test_a_message_with_commas_is_not_automatically_an_answer(text):
    assert not looks_like_an_answer(text)


def test_a_plain_name_still_works():
    assert looks_like_an_answer("Lionel Messi")
    assert not looks_like_an_answer("grazie")
