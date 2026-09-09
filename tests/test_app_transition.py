import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from handlers import daily_job, help_handler, keyboards, menu_handler, start_handler
from services.i18n import SUPPORTED_LANGUAGES, t

APP_URL = "https://example.com/app"


@pytest.mark.parametrize("lang", SUPPORTED_LANGUAGES)
def test_friend_invite_registers_then_opens_exact_duel(monkeypatch, lang):
    import config

    monkeypatch.setattr(config, "WEBAPP_URL", APP_URL)
    registered = []

    def save(uid, name, language):
        registered.append(uid)
        return {"language": lang, "created": True}

    monkeypatch.setattr(start_handler, "save_user", save)
    reply = AsyncMock()
    update = SimpleNamespace(effective_user=SimpleNamespace(id=42, first_name="A&B", language_code=lang),
                             effective_chat=SimpleNamespace(type="private"),
                             effective_message=SimpleNamespace(reply_text=reply))
    code = "a" * 24
    asyncio.run(start_handler.start(update, SimpleNamespace(args=["duel_" + code])))
    assert registered == [42]
    assert reply.await_count == 1
    button = reply.call_args.kwargs["reply_markup"].inline_keyboard[0][0]
    assert button.web_app.url == APP_URL + "?duel=" + code
    assert button.text == t(lang, "app.duel")


@pytest.mark.parametrize("lang", SUPPORTED_LANGUAGES)
def test_app_is_first_and_chat_actions_remain_available(monkeypatch, lang):
    monkeypatch.setattr(keyboards, "WEBAPP_URL", APP_URL)
    rows = keyboards.menu_keyboard(lang).inline_keyboard
    assert rows[0][0].web_app.url == APP_URL
    assert rows[0][0].text == t(lang, "menu.app")
    assert any(button.callback_data == "menu_play" for row in rows for button in row)
    assert [command.command for command in keyboards.bot_commands(lang)][:2] == ["start", "app"]


def test_unconfigured_app_has_no_invites_or_buttons(monkeypatch):
    monkeypatch.setattr(keyboards, "WEBAPP_URL", "")
    assert keyboards.app_invitation("it") == ""
    assert keyboards.app_keyboard("it") is None
    assert "app" not in [command.command for command in keyboards.bot_commands("it")]
    assert all(not b.web_app for row in keyboards.menu_keyboard("it").inline_keyboard for b in row)


@pytest.mark.parametrize("handler", [menu_handler.menu, help_handler.help])
@pytest.mark.parametrize("chat_type", ["private", "group"])
def test_invitation_is_only_shown_in_private_chat(monkeypatch, handler, chat_type):
    monkeypatch.setattr(keyboards, "WEBAPP_URL", APP_URL)
    monkeypatch.setattr(keyboards, "get_user_data", lambda uid: {"language": "es"})
    reply = AsyncMock()
    update = SimpleNamespace(effective_user=SimpleNamespace(id=42),
                             effective_chat=SimpleNamespace(type=chat_type),
                             effective_message=SimpleNamespace(reply_text=reply))
    asyncio.run(handler(update, None))
    text = reply.call_args.args[0]
    buttons = reply.call_args.kwargs["reply_markup"].inline_keyboard
    assert (t("es", "app.intro") in text) == (chat_type == "private")
    assert any(b.web_app for row in buttons for b in row) == (chat_type == "private")


def test_start_promotes_app_without_losing_league_invites(monkeypatch):
    monkeypatch.setattr(keyboards, "WEBAPP_URL", APP_URL)
    monkeypatch.setattr(start_handler, "save_user", lambda *a, **kw: {"language": "it", "created": True})
    join = AsyncMock()
    monkeypatch.setattr(start_handler, "league_join", join)
    reply = AsyncMock()
    update = SimpleNamespace(effective_user=SimpleNamespace(id=42, first_name="A&B", language_code="en"),
                             effective_chat=SimpleNamespace(type="private"),
                             effective_message=SimpleNamespace(reply_text=reply))
    context = SimpleNamespace(args=[start_handler.DEEP_LINK_PREFIX + "ABC23X"])
    asyncio.run(start_handler.start(update, context))
    assert t("it", "app.intro") in reply.call_args.args[0]
    assert "A&amp;B" in reply.call_args.args[0]
    join.assert_awaited_once_with(update, context, code="ABC23X")


def test_daily_notification_contains_app_invitation(monkeypatch):
    monkeypatch.setattr(keyboards, "WEBAPP_URL", APP_URL)
    monkeypatch.setattr(daily_job.firebase_service, "get_broadcast_users", lambda day: [
        {"chat_id": 42, "language": "it", "has_guessed_today": True},
    ])
    bot = SimpleNamespace(send_message=AsyncMock())
    monkeypatch.setattr(daily_job, "get_bot", lambda: bot)
    monkeypatch.setattr(daily_job.asyncio, "sleep", AsyncMock())
    assert asyncio.run(daily_job._broadcast("2026-09-08", "Messi", None, None)) == (1, 0)
    sent = bot.send_message.call_args.kwargs
    assert sent["chat_id"] == 42
    assert t("it", "app.daily_invite") in sent["text"]
    assert sent["reply_markup"].inline_keyboard[0][0].web_app.url == APP_URL
