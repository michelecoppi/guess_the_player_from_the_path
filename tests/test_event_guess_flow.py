"""Flusso di /events <risposta> con i partecipanti su sotto-collection."""
import asyncio
from types import SimpleNamespace

import pytest

from handlers import events_handler
from services.dates import today_iso


class FakeMessage:
    def __init__(self):
        self.chat = SimpleNamespace(type="private")
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)


def make_update(user_id=42, name="Anna"):
    message = FakeMessage()
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id, first_name=name),
        message=message,
        effective_message=message,
        effective_chat=message.chat,
    ), message


def path_event():
    return {
        "code": "giramondo_20261201",
        "type": "path",
        "name": "Giramondo",
        "dates": [today_iso()],
        "daily_data": {today_iso(): {"correct_answers": ["messi"], "points": 2, "first_correct_user": False}},
    }


def career_event():
    return {
        "code": "carriera_20261201",
        "type": "career",
        "name": "Carriera",
        "dates": [today_iso()],
        "daily_data": {
            today_iso(): {
                "correct_answers": ["Roma", "Milan", "Inter", "Juventus"],
                "min_correct": 2,
                "points": 2,
                "first_correct_user": False,
            }
        },
    }


@pytest.fixture
def firebase(monkeypatch):
    calls = {"registered": [], "attempts": []}
    state = {"attempt": {"ok": True, "attempts_used": 1, "attempts_left": 2}, "first_free": True}

    def begin_event_attempt(code, user_id, name, day, max_attempts):
        calls["attempts"].append((code, user_id, name, day))
        return state["attempt"]

    def claim_event_first_correct(code, day):
        if state["first_free"]:
            state["first_free"] = False
            return True
        return False

    def register_event_correct_guess(code, user_id, points, day):
        calls["registered"].append({"code": code, "user_id": user_id, "points": points, "day": day})

    monkeypatch.setattr(events_handler.firebase_service, "begin_event_attempt", begin_event_attempt)
    monkeypatch.setattr(events_handler.firebase_service, "claim_event_first_correct", claim_event_first_correct)
    monkeypatch.setattr(events_handler.firebase_service, "register_event_correct_guess", register_event_correct_guess)
    monkeypatch.setattr(events_handler.firebase_service, "get_user_data", lambda uid: None)
    return SimpleNamespace(calls=calls, state=state)


def test_path_event_correct_answer_gets_points_and_bonus(firebase):
    update, message = make_update()
    context = SimpleNamespace(args=["messi"], user_data={})
    asyncio.run(events_handler.process_event_guess(update, context, path_event()))

    assert firebase.calls["registered"][0]["points"] == 3  # 2 + bonus primo
    assert "Bonus 1°" in message.replies[0]


def test_event_bonus_is_given_once(firebase):
    for user_id in (1, 2):
        update, message = make_update(user_id=user_id)
        asyncio.run(events_handler.process_event_guess(update, SimpleNamespace(args=["messi"]), path_event()))

    assert [r["points"] for r in firebase.calls["registered"]] == [3, 2]


def test_career_event_needs_enough_correct_teams(firebase):
    update, message = make_update()
    asyncio.run(events_handler.process_event_guess(update, SimpleNamespace(args=["Roma,", "Palermo"]), career_event()))

    assert firebase.calls["registered"] == []
    assert "Risposte corrette trovate: 1/4" in message.replies[0]

    update, message = make_update()
    asyncio.run(events_handler.process_event_guess(update, SimpleNamespace(args=["Roma,", "Inter"]), career_event()))
    assert firebase.calls["registered"][0]["points"] == 3


def test_career_event_limits_answers_per_attempt(firebase):
    update, message = make_update()
    context = SimpleNamespace(args=["a,", "b,", "c,", "d,", "e,", "f"])
    asyncio.run(events_handler.process_event_guess(update, context, career_event()))

    assert firebase.calls["attempts"] == []  # non consuma il tentativo
    assert "al massimo 5 squadre" in message.replies[0]


def test_refused_attempt_is_explained(firebase):
    firebase.state["attempt"] = {"ok": False, "reason": "already_guessed"}
    update, message = make_update()
    asyncio.run(events_handler.process_event_guess(update, SimpleNamespace(args=["messi"]), path_event()))

    assert "già indovinato" in message.replies[0]
    assert firebase.calls["registered"] == []


def test_day_without_content_does_not_consume_an_attempt(firebase):
    event = path_event()
    event["daily_data"] = {}
    update, message = make_update()
    asyncio.run(events_handler.process_event_guess(update, SimpleNamespace(args=["messi"]), event))

    assert firebase.calls["attempts"] == []
    assert "Nessuna sfida disponibile" in message.replies[0]


def test_evaluate_event_guess_is_case_and_space_insensitive():
    day = {"correct_answers": ["Roma", "Inter"], "min_correct": 2}
    assert events_handler.evaluate_event_guess("career", " roma ,  inter ", day)[0] is True
    assert events_handler.evaluate_event_guess("path", "messi", {"correct_answers": ["messi"]})[0] is True
    assert events_handler.evaluate_event_guess("path", "pele", {"correct_answers": ["messi"]})[0] is False


def test_leaderboard_message_uses_the_participants_query():
    podium = [{"name": "Anna", "points": 9}, {"name": "Bruno", "points": 4}]
    message = events_handler.get_event_leaderboard_message(podium)
    assert "Anna" in message and "Bruno" in message

    assert "Nessun partecipante" in events_handler.get_event_leaderboard_message([])
