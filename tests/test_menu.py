"""Il menu a bottoni deve restare allineato agli handler che richiama.

Il rischio vero e' un bottone che non fa niente: la callback arriva, `ACTIONS` non ha la
chiave e l'utente preme senza che succeda nulla. Qui si controlla che ogni bottone abbia il
suo handler e che la callback lo chiami davvero.
"""
import asyncio
from types import SimpleNamespace

import pytest

from handlers import keyboards, menu_handler
from services.i18n import SUPPORTED_LANGUAGES, t


def _callback_data(keyboard):
    return [button.callback_data for row in keyboard.inline_keyboard for button in row if button.callback_data]


def test_every_menu_button_has_a_handler():
    data = _callback_data(keyboards.menu_keyboard("it"))
    assert data
    for callback in data:
        action = callback[len(keyboards.CALLBACK_PREFIX):]
        assert action in menu_handler.ACTIONS, action


@pytest.mark.parametrize("lang", SUPPORTED_LANGUAGES)
def test_the_menu_is_translated(lang):
    labels = [b.text for row in keyboards.menu_keyboard(lang).inline_keyboard for b in row]
    assert t(lang, "menu.stats") in labels


@pytest.mark.parametrize("lang", SUPPORTED_LANGUAGES)
def test_bot_commands_are_translated_and_unique(lang):
    commands = keyboards.bot_commands(lang)
    names = [c.command for c in commands]
    assert len(names) == len(set(names))
    assert all(c.description for c in commands)


def test_the_callback_calls_the_handler_of_the_pressed_button(monkeypatch):
    called = []

    async def fake_stats(update, context):
        called.append("stats")

    monkeypatch.setitem(menu_handler.ACTIONS, "stats", fake_stats)

    async def answer():
        called.append("answered")

    query = SimpleNamespace(data="menu_stats", answer=answer)
    update = SimpleNamespace(callback_query=query)

    asyncio.run(menu_handler.menu_callback(update, None))
    assert called == ["answered", "stats"]


def test_an_unknown_action_is_ignored():
    async def answer():
        return None

    update = SimpleNamespace(callback_query=SimpleNamespace(data="menu_inesistente", answer=answer))
    asyncio.run(menu_handler.menu_callback(update, None))
