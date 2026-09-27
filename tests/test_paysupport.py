import asyncio
from types import SimpleNamespace

from handlers import support_handler


class Message:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)


class Bot:
    def __init__(self):
        self.sent = []

    async def send_message(self, **kwargs):
        self.sent.append(kwargs)


def make_update(chat_id=42):
    message = Message()
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=42, first_name="Anna", language_code="it"),
        effective_chat=SimpleNamespace(id=chat_id),
        effective_message=message,
    ), message


def test_paysupport_forwards_the_request_to_every_admin(monkeypatch):
    monkeypatch.setattr(support_handler, "ADMIN_TELEGRAM_IDS", [7, 8])
    monkeypatch.setattr(support_handler.firebase_service, "get_user_data", lambda uid: {"language": "it"})
    bot = Bot()
    update, message = make_update()
    asyncio.run(support_handler.paysupport(
        update, SimpleNamespace(args=["Oggetto", "non", "ricevuto"], bot=bot)
    ))
    assert [item["chat_id"] for item in bot.sent] == [7, 8]
    assert all("Telegram ID: 42" in item["text"] for item in bot.sent)
    assert "inviata" in message.replies[0]


def test_paysupport_requires_a_description(monkeypatch):
    monkeypatch.setattr(support_handler.firebase_service, "get_user_data", lambda uid: {"language": "it"})
    update, message = make_update()
    asyncio.run(support_handler.paysupport(update, SimpleNamespace(args=[], bot=Bot())))
    assert "/paysupport" in message.replies[0]


def test_paysupport_is_private_only(monkeypatch):
    monkeypatch.setattr(support_handler.firebase_service, "get_user_data", lambda uid: {"language": "it"})
    update, message = make_update(chat_id=-100)
    asyncio.run(support_handler.paysupport(
        update, SimpleNamespace(args=["Aiuto"], bot=Bot())
    ))
    assert "chat privata" in message.replies[0]
