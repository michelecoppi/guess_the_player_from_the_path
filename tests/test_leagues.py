"""Leghe private: creazione, ingresso, classifica e link d'invito."""
import asyncio
from types import SimpleNamespace

import pytest

from handlers import league_handler, start_handler
from services import leagues as league_rules


class FakeMessage:
    def __init__(self):
        self.chat = SimpleNamespace(type="private")
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)


def make_update(user_id=42, name="Anna"):
    message = FakeMessage()
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id, first_name=name, language_code="it"),
        message=message,
        effective_message=message,
        effective_chat=message.chat,
    ), message


def context(*args):
    return SimpleNamespace(args=list(args))


@pytest.fixture
def firebase(monkeypatch):
    state = {
        "user": {"telegram_id": 42, "language": "it", "leagues": []},
        "leagues": {"ABC23X": {"code": "ABC23X", "name": "Amici del bar", "members_count": 2}},
        "join_result": "ok",
        "created": True,
    }
    calls = {"created": [], "joined": [], "left": []}

    monkeypatch.setattr(league_handler.firebase_service, "get_user_data", lambda uid: state["user"])
    monkeypatch.setattr(league_handler.firebase_service, "get_league", lambda code: state["leagues"].get(code))
    monkeypatch.setattr(
        league_handler.firebase_service, "create_league",
        lambda code, name, uid, uname: calls["created"].append((code, name)) or state["created"],
    )
    monkeypatch.setattr(
        league_handler.firebase_service, "join_league",
        lambda code, uid, name, mx: calls["joined"].append(code) or state["join_result"],
    )
    monkeypatch.setattr(
        league_handler.firebase_service, "leave_league",
        lambda code, uid: calls["left"].append(code) or True,
    )
    monkeypatch.setattr(league_handler.firebase_service, "get_league_leaderboard", lambda code, limit=20: [])
    return SimpleNamespace(state=state, calls=calls)


def test_the_code_avoids_characters_that_get_confused_when_dictated():
    for _ in range(50):
        code = league_rules.generate_code()
        assert len(code) == league_rules.CODE_LENGTH
        assert not set(code) & set("O0I1")


def test_the_invite_link_needs_the_bot_username(monkeypatch):
    monkeypatch.setattr(league_handler, "BOT_USERNAME", "")
    assert league_handler.invite_link("ABC23X") == ""

    monkeypatch.setattr(league_handler, "BOT_USERNAME", "guessplayerbot")
    assert league_handler.invite_link("ABC23X").endswith("?start=lega_ABC23X")


def test_creating_a_league_stores_it_and_shows_the_code(firebase):
    update, message = make_update()
    asyncio.run(league_handler.league_create(update, context("Amici", "del", "bar")))

    assert firebase.calls["created"][0][1] == "Amici del bar"
    assert "Amici del bar" in message.replies[0]


def test_a_league_name_too_long_is_refused(firebase):
    update, message = make_update()
    asyncio.run(league_handler.league_create(update, context("x" * 40)))

    assert firebase.calls["created"] == []
    assert str(league_handler.MAX_NAME_LENGTH) in message.replies[0]


def test_you_cannot_be_in_more_leagues_than_the_limit(firebase):
    firebase.state["user"]["leagues"] = ["A" * 6] * league_handler.MAX_LEAGUES_PER_USER
    update, message = make_update()
    asyncio.run(league_handler.league_join(update, context("ABC23X")))

    assert firebase.calls["joined"] == []
    assert str(league_handler.MAX_LEAGUES_PER_USER) in message.replies[0]


@pytest.mark.parametrize("result,expected", [
    ("not_found", "ABC23X"),
    ("already_member", "già"),
    ("full", str(league_handler.MAX_MEMBERS)),
])
def test_join_failures_are_explained(firebase, result, expected):
    firebase.state["join_result"] = result
    update, message = make_update()
    asyncio.run(league_handler.league_join(update, context("abc23x")))

    assert expected in message.replies[0]


def test_the_code_is_accepted_in_lowercase(firebase):
    update, _ = make_update()
    asyncio.run(league_handler.league_join(update, context("abc23x")))
    assert firebase.calls["joined"] == ["ABC23X"]


def test_the_leaderboard_marks_who_is_reading_it():
    league = {"code": "ABC23X", "name": "Amici del bar"}
    members = [
        {"telegram_id": 7, "name": "Bea", "points": 30},
        {"telegram_id": 42, "name": "Anna", "points": 12},
    ]
    text = league_handler.format_leaderboard(league, members, "it", viewer_id=42)

    assert "🥇 Bea" in text
    assert "Anna" in text
    assert text.index("Bea") < text.index("Anna")


def test_an_empty_league_says_so_instead_of_showing_nothing():
    text = league_handler.format_leaderboard({"code": "ABC23X", "name": "Vuota"}, [], "it")
    assert "Ancora nessun punto" in text


def test_the_invite_link_joins_the_league_from_start(monkeypatch):
    """Chi apre il link deve trovarsi dentro la lega senza copiare nessun codice."""
    joined = []

    monkeypatch.setattr(start_handler, "save_user", lambda uid, name, language=None: {"created": True, "language": "it"})

    async def fake_join(update, context, code=None):
        joined.append(code)

    monkeypatch.setattr(start_handler, "league_join", fake_join)

    update, _ = make_update()
    asyncio.run(start_handler.start(update, context("lega_ABC23X")))

    assert joined == ["ABC23X"]
