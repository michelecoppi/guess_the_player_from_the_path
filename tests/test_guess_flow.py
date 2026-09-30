"""Le risposte in chat privata: la sfida di oggi si gioca solo nella mini app (#243).

Le regole della sfida del giorno (punti, bonus, indizi, striscia, storico) sono provate in
tests/test_game_rules.py, sulle funzioni che la mini app usa davvero. Qui si prova soltanto
che la chat **non** le tocca: un nome scritto senza una partita aperta non consuma niente e
porta alla mini app.
"""
import asyncio
from types import SimpleNamespace

import pytest

from handlers import guess_handler, hint_handler, menu_handler
from services import game
from services.i18n import t


class FakeMessage:
    def __init__(self, text=""):
        self.text = text
        self.chat = SimpleNamespace(type="private")
        self.replies = []
        self.markups = []

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)
        self.markups.append(kwargs.get("reply_markup"))


def make_update(text, user_id=42):
    message = FakeMessage(text)
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id, first_name="Anna", language_code="it"),
        message=message,
        effective_message=message,
    )
    return update, message


@pytest.fixture
def no_daily(monkeypatch):
    """Qualunque strada che arrivi alla sfida di oggi fa fallire il test."""
    def fail(name):
        return lambda *a, **k: pytest.fail(f"la chat ha chiamato {name}")

    monkeypatch.setattr(game, "play_daily", fail("game.play_daily"))
    monkeypatch.setattr(game, "take_hint", fail("game.take_hint"))
    monkeypatch.setattr(guess_handler.firebase_service, "take_daily_hint", fail("take_daily_hint"))
    state = {"user": {"language": "it"}}
    monkeypatch.setattr(guess_handler.firebase_service, "get_user_data", lambda uid: state["user"])
    monkeypatch.setattr(guess_handler, "app_keyboard", lambda lang: "APP")
    monkeypatch.setattr(hint_handler, "app_keyboard", lambda lang: "APP")
    monkeypatch.setattr(hint_handler, "language_for", lambda update: "it")
    monkeypatch.setattr(menu_handler, "app_keyboard", lambda lang: "APP")
    monkeypatch.setattr(menu_handler, "language_for", lambda update: "it")
    return state


@pytest.mark.parametrize("user", [{"language": "it"}, None], ids=["registered", "unregistered"])
def test_a_name_in_chat_does_not_play_today_and_points_to_the_mini_app(no_daily, user):
    no_daily["user"] = user
    update, message = make_update("Messi")

    asyncio.run(guess_handler.free_text_guess(update, None))

    assert message.replies == [t("it", "guess.daily_in_app")]
    assert message.markups == ["APP"]


def test_the_guess_command_in_private_does_not_play_today_either(no_daily):
    update, message = make_update("/guess messi")

    asyncio.run(guess_handler.guess(update, None))

    assert message.replies == [t("it", "guess.daily_in_app")]


def test_a_message_that_is_not_a_name_explains_where_to_play(no_daily):
    update, message = make_update("https://esempio.it/una-pagina-qualsiasi")

    asyncio.run(guess_handler.free_text_guess(update, None))

    assert message.replies == [t("it", "guess.free_text_hint")]
    assert message.markups == ["APP"]


def test_a_missing_name_after_the_command_is_explained(no_daily):
    update, message = make_update("/guess")

    asyncio.run(guess_handler.guess(update, None))

    assert "nome del calciatore" in message.replies[0]


def test_guess_in_a_group_answers_the_group_round(no_daily, monkeypatch):
    """In un gruppo /guess risponde al round del gruppo, mai alla sfida di oggi."""
    from domains.groups import repository as groups_repository

    monkeypatch.setattr(groups_repository, "get_group_round", lambda chat_id: None)
    update, message = make_update("/guess messi")
    update.message.chat = SimpleNamespace(type="group", id=-100123)

    asyncio.run(guess_handler.guess(update, None))

    assert "round" in message.replies[0].lower()


def _callback(data):
    message = FakeMessage()

    async def answer(*args, **kwargs):
        return None

    user = SimpleNamespace(id=42, first_name="Anna", language_code="it")
    query = SimpleNamespace(data=data, answer=answer, message=message, from_user=user)
    return SimpleNamespace(callback_query=query, effective_user=user, effective_message=message), message


def test_an_old_hint_button_takes_no_hint(no_daily):
    update, message = _callback(hint_handler.CALLBACK_DATA)

    asyncio.run(hint_handler.hint_callback(update, None))

    assert message.replies == [t("it", "guess.daily_in_app")]


def test_an_old_menu_play_button_opens_the_mini_app_invitation(no_daily):
    update, message = _callback("menu_play")

    asyncio.run(menu_handler.menu_callback(update, None))

    assert message.replies == [t("it", "guess.daily_in_app")]
    assert message.markups == ["APP"]
