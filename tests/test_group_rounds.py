"""Partita di gruppo: round su materiale che non spoilera, punti che restano nel gruppo.

Le tre regole che questo file protegge sono quelle che rendono la modalita' accettabile:
non si gioca la sfida di oggi (spoiler), i punti non entrano nella classifica generale
(farmabilita'), e un round lo vince una persona sola anche se in due rispondono nello
stesso istante.
"""
import asyncio
from types import SimpleNamespace

import pytest

from handlers import group_handler, guess_handler
from handlers.group_handler import MAX_GROUP_ATTEMPTS

KEY = "pool:maldini"
CHALLENGE = {
    "key": KEY,
    "player_id": "maldini",
    "correct_answers": ["maldini", "paolo maldini"],
    "career_path": [{"team": "Milan", "country": "Italia", "league": "Serie A", "start_year": 1985, "end_year": 2009}],
    "difficulty": "hard",
    "answer": "Paolo Maldini",
    "day": None,
}
CHAT_ID = -1001234


class FakeMessage:
    def __init__(self, text="", chat_type="group"):
        self.text = text
        self.chat = SimpleNamespace(type=chat_type, id=CHAT_ID)
        self.replies = []
        self.photos = []

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)

    async def reply_photo(self, photo, caption=None, **kwargs):
        self.photos.append(caption)


def make_update(text="", user_id=7, name="Anna", chat_type="group"):
    message = FakeMessage(text, chat_type)
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id, first_name=name, username=None, language_code="it"),
        message=message,
        effective_message=message,
        effective_chat=message.chat,
    ), message


@pytest.fixture
def firebase(monkeypatch):
    state = {
        "round": {
            "chat_id": CHAT_ID, "number": 3, "key": KEY,
            "correct_answers": CHALLENGE["correct_answers"],
            "player_id": "maldini", "difficulty": "hard",
            "solved_by": None, "solved_name": None, "recent_keys": [KEY],
        },
        "claimable": True,
        "attempt": {"ok": True, "attempts_used": 1, "attempts_left": 2},
    }
    calls = {"points": [], "claims": 0, "started": [], "attempts": [], "daily_points": []}

    def claim(chat_id, number, user_id, name):
        calls["claims"] += 1
        if state["claimable"]:
            state["claimable"] = False
            state["round"]["solved_by"] = user_id
            state["round"]["solved_name"] = name
            return True
        return False

    def start_round(chat_id, challenge, **kwargs):
        calls["started"].append((chat_id, challenge["key"]))
        return {"number": state["round"]["number"] + 1, "key": challenge["key"]}

    monkeypatch.setattr(group_handler.firebase_service, "get_group_round", lambda chat_id: state["round"])
    monkeypatch.setattr(group_handler.firebase_service, "start_group_round", start_round)
    monkeypatch.setattr(group_handler.firebase_service, "claim_group_round", claim)
    monkeypatch.setattr(
        group_handler.firebase_service, "begin_group_attempt",
        lambda chat, uid, number, name, mx: calls["attempts"].append((uid, number)) or state["attempt"],
    )
    monkeypatch.setattr(
        group_handler.firebase_service, "add_group_points",
        lambda chat, uid, name, points: calls["points"].append((chat, uid, points)),
    )
    monkeypatch.setattr(group_handler.practice_content, "pick", lambda exclude_keys=(): CHALLENGE)
    monkeypatch.setattr(
        guess_handler.firebase_service, "register_correct_guess",
        lambda *a, **k: calls["daily_points"].append(a) or {},
    )
    monkeypatch.setattr(guess_handler.firebase_service, "begin_guess_attempt", lambda *a: 1 / 0)
    return SimpleNamespace(state=state, calls=calls)


def test_a_round_serves_a_challenge_that_cannot_spoil_today(firebase):
    update, message = make_update("/sfida")
    asyncio.run(group_handler.group_challenge(update, None))

    assert firebase.calls["started"] == [(CHAT_ID, KEY)]
    assert message.photos and "Round #4" in message.photos[0]


def test_the_first_correct_answer_wins_the_round(firebase):
    update, message = make_update("/guess Maldini")
    asyncio.run(guess_handler.guess(update, None))

    # "hard" vale 3 punti, gli stessi della sfida del giorno.
    assert firebase.calls["points"] == [(CHAT_ID, 7, 3)]
    assert "Anna" in message.replies[0]


def test_the_group_never_touches_the_general_standings(firebase):
    """E' quello che rende la modalita' non farmabile: un gruppo con un account
    secondario non sposta niente di quello che conta."""
    update, _ = make_update("/guess Maldini")
    asyncio.run(guess_handler.guess(update, None))

    assert firebase.calls["daily_points"] == []


def test_only_one_person_can_win_the_same_round(firebase):
    """Due risposte giuste nello stesso istante, in un gruppo, sono la norma."""
    first, _ = make_update("/guess Maldini", user_id=7, name="Anna")
    asyncio.run(guess_handler.guess(first, None))

    firebase.state["round"]["solved_by"] = None  # come se la lettura fosse arrivata prima
    second, message = make_update("/guess Maldini", user_id=8, name="Bruno")
    asyncio.run(guess_handler.guess(second, None))

    assert len(firebase.calls["points"]) == 1
    assert firebase.calls["claims"] == 2
    assert "già vinto" in message.replies[0] or "?" in message.replies[0]


def test_answering_a_solved_round_is_explained_without_consuming_attempts(firebase):
    firebase.state["round"]["solved_by"] = 7
    firebase.state["round"]["solved_name"] = "Anna"
    update, message = make_update("/guess Maldini", user_id=8)
    asyncio.run(guess_handler.guess(update, None))

    assert firebase.calls["attempts"] == []
    assert "Anna" in message.replies[0]


def test_a_wrong_answer_counts_down_and_is_compared(firebase):
    update, message = make_update("/guess Del Piero")
    asyncio.run(guess_handler.guess(update, None))

    assert firebase.calls["points"] == []
    assert "2" in message.replies[0]
    assert "Del Piero" in message.replies[0]


def test_running_out_of_attempts_stops_one_person_not_the_round(firebase):
    firebase.state["attempt"] = {"ok": False, "reason": "no_attempts"}
    update, message = make_update("/guess Maldini")
    asyncio.run(guess_handler.guess(update, None))

    assert firebase.calls["points"] == []
    assert "tentativi" in message.replies[0]


def test_guess_without_a_name_explains_how_to_answer(firebase):
    update, message = make_update("/guess")
    asyncio.run(guess_handler.guess(update, None))

    assert firebase.calls["attempts"] == []
    assert "/guess" in message.replies[0]


def test_without_an_open_round_nothing_is_consumed(firebase):
    firebase.state["round"] = None
    update, message = make_update("/guess Maldini")
    asyncio.run(guess_handler.guess(update, None))

    assert firebase.calls["attempts"] == []
    assert "/round" in message.replies[0]


def test_the_round_command_in_private_points_at_training(firebase):
    update, message = make_update("/sfida", chat_type="private")
    asyncio.run(group_handler.group_challenge(update, None))

    assert firebase.calls["started"] == []
    assert "/training" in message.replies[0]


def test_the_standings_are_the_group_ones(firebase, monkeypatch):
    monkeypatch.setattr(
        group_handler.firebase_service, "get_group_leaderboard",
        lambda chat_id, limit: [{"name": "Anna", "points": 9, "rounds_won": 3}],
    )
    update, message = make_update("/classifica")
    asyncio.run(group_handler.group_standings(update, None))

    assert "Anna" in message.replies[0]
    assert "/top" in message.replies[0]  # dice esplicitamente qual e' quella generale


def test_a_name_with_html_in_it_cannot_break_the_message(firebase):
    """I messaggi del gruppo sono in HTML e il nome lo sceglie l'utente."""
    update, message = make_update("/guess Maldini", name="<b>Anna")
    asyncio.run(guess_handler.guess(update, None))

    assert "&lt;b&gt;Anna" in message.replies[0]


def test_attempts_are_counted_per_round(firebase):
    """Il numero del round arriva alla transazione dei tentativi: e' quello che li azzera
    quando ne comincia uno nuovo, senza scrivere sul documento di ogni giocatore."""
    update, _ = make_update("/guess Del Piero")
    asyncio.run(guess_handler.guess(update, None))

    assert firebase.calls["attempts"] == [(7, 3)]
    assert MAX_GROUP_ATTEMPTS == 3
