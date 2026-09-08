"""La lingua scelta con /language deve valere in **tutti** i comandi.

C'erano quattro handler (`/show`, `/help`, `/legend` e la callback della legenda) che
guardavano solo il `language_code` del client Telegram e ignoravano la lingua salvata sul
documento utente: chi imposta /language es continuava a ricevere quelle schermate in
inglese. Non si rompeva niente, quindi non se ne accorgeva nessun test.

Qui si controlla la regola per com'e' scritta: prima la lingua salvata, e solo se non c'e'
quella del client.
"""
import asyncio
from types import SimpleNamespace

import pytest

from handlers import help_handler, keyboards, legend_handler, show_daily_path_handler
from services.i18n import t

CHALLENGE = {
    "difficulty": "medium",
    "career_path": [
        {"team": "Barcelona", "country": "Spagna", "league": "La Liga", "start_year": 2004, "end_year": 2021},
        {"team": "Inter Miami", "country": "USA", "league": "MLS", "start_year": 2023, "end_year": None},
    ],
    "correct_answers": ["messi"],
}


class FakeMessage:
    def __init__(self):
        self.replies = []
        self.photos = []

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)

    async def reply_photo(self, photo, caption=None, **kwargs):
        self.photos.append((photo, caption))


def make_update(language_code="en"):
    message = FakeMessage()
    user = SimpleNamespace(id=7, first_name="Anna", language_code=language_code)
    return SimpleNamespace(effective_user=user, effective_message=message, message=message), message


@pytest.fixture
def saved_language(monkeypatch):
    """Sostituisce la lettura dell'utente: `None` = utente che non ha mai scelto la lingua."""
    box = {"language": "es"}
    monkeypatch.setattr(
        keyboards, "get_user_data",
        lambda user_id: {"language": box["language"]} if box["language"] else {},
    )
    return box


@pytest.fixture
def no_firestore(monkeypatch):
    monkeypatch.setattr(show_daily_path_handler, "get_today_challenge", lambda: CHALLENGE)
    monkeypatch.setattr(show_daily_path_handler, "bonus_available", lambda: False)
    monkeypatch.setattr(show_daily_path_handler, "challenge_number", lambda *a: 12)


def test_help_uses_the_saved_language_over_the_client_one(saved_language):
    update, message = make_update(language_code="en")
    asyncio.run(help_handler.help(update, None))
    assert message.replies == [t("es", "help.message")]


def test_help_falls_back_to_the_client_language(saved_language):
    saved_language["language"] = None
    update, message = make_update(language_code="en")
    asyncio.run(help_handler.help(update, None))
    assert message.replies == [t("en", "help.message")]


def test_legend_uses_the_saved_language(saved_language):
    update, message = make_update(language_code="en")
    asyncio.run(legend_handler.legend(update, None))
    assert message.replies == [t("es", "legend.text")]


def test_the_legend_button_uses_the_saved_language(saved_language):
    message = FakeMessage()

    async def answer():
        return None

    user = SimpleNamespace(id=7, first_name="Anna", language_code="en")
    query = SimpleNamespace(data="legend", answer=answer, message=message, from_user=user)
    update = SimpleNamespace(callback_query=query, effective_user=user)

    asyncio.run(legend_handler.legend_callback(update, None))
    assert message.replies == [t("es", "legend.text")]


def test_show_uses_the_saved_language(saved_language, no_firestore):
    update, message = make_update(language_code="en")
    asyncio.run(show_daily_path_handler.show(update, None))

    _, caption = message.photos[0]
    assert caption == t(
        "es", "show.caption", difficulty="Media", points=2, bonus_info="", attempts=3,
    )
