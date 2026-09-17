"""/help spiega il gioco e porta alla mini app, e basta; /info e /app non ci sono piu'.

Prima /help mandava il muro dei comandi piu' tutta la tastiera del menu, e /info ripeteva in
breve le stesse cose: due punti di ingresso per una sola domanda ("come si gioca?"). Ora c'e'
solo /help, con un bottone solo: quello della mini app.
"""
import asyncio
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from apps.bot import application as bot_application
from handlers import help_handler, keyboards
from services.i18n import SUPPORTED_LANGUAGES, t

APP_URL = "https://example.com/app"


def _run_help(monkeypatch, lang, chat_type):
    monkeypatch.setattr(keyboards, "get_user_data", lambda uid: {"language": lang})
    reply = AsyncMock()
    update = SimpleNamespace(effective_user=SimpleNamespace(id=42, language_code="en"),
                             effective_chat=SimpleNamespace(type=chat_type),
                             effective_message=SimpleNamespace(reply_text=reply))
    asyncio.run(help_handler.help(update, None))
    reply.assert_awaited_once()
    return reply.call_args


@pytest.mark.parametrize("lang", SUPPORTED_LANGUAGES)
def test_private_help_explains_the_game_with_only_the_mini_app_button(monkeypatch, lang):
    monkeypatch.setattr(keyboards, "WEBAPP_URL", APP_URL)
    call = _run_help(monkeypatch, lang, "private")

    assert call.args[0] == f"{t(lang, 'help.message')}\n\n{t(lang, 'help.open_app')}"
    assert call.kwargs["parse_mode"] == "HTML"
    buttons = [b for row in call.kwargs["reply_markup"].inline_keyboard for b in row]
    assert len(buttons) == 1
    assert buttons[0].web_app.url == APP_URL
    assert buttons[0].text == t(lang, "menu.app")


@pytest.mark.parametrize("lang", SUPPORTED_LANGUAGES)
def test_group_help_has_no_buttons(monkeypatch, lang):
    # I bottoni web_app non sono ammessi nei gruppi: si manda solo la spiegazione.
    monkeypatch.setattr(keyboards, "WEBAPP_URL", APP_URL)
    call = _run_help(monkeypatch, lang, "group")
    assert call.args[0] == t(lang, "help.message")
    assert call.kwargs["reply_markup"] is None


def test_help_without_a_configured_app_has_no_button_nor_invitation(monkeypatch):
    monkeypatch.setattr(keyboards, "WEBAPP_URL", "")
    call = _run_help(monkeypatch, "it", "private")
    assert call.args[0] == t("it", "help.message")
    assert call.kwargs["reply_markup"] is None


@pytest.mark.parametrize("lang", SUPPORTED_LANGUAGES)
def test_help_message_is_valid_telegram_html(lang):
    # parse_mode="HTML": un tag non chiuso o un "<" nudo fanno rifiutare il messaggio.
    text = t(lang, "help.message")
    assert re.findall(r"</?[a-z]+>", text).count("<b>") == re.findall(r"</?[a-z]+>", text).count("</b>")
    assert not re.search(r"<(?!/?b>)", text)
    assert "&" not in text


@pytest.mark.parametrize("webapp_url", [APP_URL, ""])
def test_info_and_app_commands_are_gone(monkeypatch, webapp_url):
    # /info faceva lo stesso di /help, /app lo stesso di /start (che mostra gia' il bottone
    # della mini app): restano solo /help e /start.
    monkeypatch.setattr(keyboards, "WEBAPP_URL", webapp_url)
    names = [c.command for c in keyboards.bot_commands("it")]
    assert "info" not in names and "app" not in names

    registered = []
    fake_app = SimpleNamespace(add_handler=lambda h, *a, **kw: registered.append(h),
                               add_error_handler=lambda *a, **kw: None)
    bot_application.register_handlers(fake_app)
    commands = {c for h in registered for c in getattr(h, "commands", ())}
    assert {"help", "start"} <= commands
    assert not {"info", "app"} & commands
