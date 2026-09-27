import asyncio
from types import SimpleNamespace

from handlers import privacy_handler


class Message:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)


def make_update(chat_id=42):
    message = Message()
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=42, language_code="it"),
        effective_chat=SimpleNamespace(id=chat_id),
        effective_message=message,
    ), message


def test_forgetme_requires_an_exact_confirmation(monkeypatch):
    deleted = []
    monkeypatch.setattr(privacy_handler.firebase_service, "get_user_data", lambda uid: {"language": "it"})
    monkeypatch.setattr(privacy_handler.firebase_service, "delete_user_data", deleted.append)
    update, message = make_update()
    asyncio.run(privacy_handler.forgetme(update, SimpleNamespace(args=[])))
    assert deleted == []
    assert "/forgetme DELETE" in message.replies[0]


def test_forgetme_deletes_only_after_confirmation(monkeypatch):
    deleted = []
    monkeypatch.setattr(privacy_handler.firebase_service, "get_user_data", lambda uid: {"language": "it"})
    monkeypatch.setattr(privacy_handler.firebase_service, "delete_user_data", deleted.append)
    update, message = make_update()
    asyncio.run(privacy_handler.forgetme(update, SimpleNamespace(args=["DELETE"])))
    assert deleted == [42]
    assert "cancellati" in message.replies[0]


def test_forgetme_is_private_only(monkeypatch):
    monkeypatch.setattr(privacy_handler.firebase_service, "get_user_data", lambda uid: {"language": "it"})
    update, message = make_update(chat_id=-100)
    asyncio.run(privacy_handler.forgetme(update, SimpleNamespace(args=["DELETE"])))
    assert "chat privata" in message.replies[0]
