"""Indirizzi firmati delle foto profilo Telegram negli avatar della Mini App (#296).

La foto la chiede a Telegram il server (`apps/api/avatars.py`): il link di un file Telegram
contiene il token del bot e non puo' arrivare al client. La Mini App riceve invece
`/app/api/avatar/<id>?s=<firma>`, e lo mette in un `<img>`, che non puo' mandare initData.

La firma (HMAC con una chiave ricavata dal token del bot) e' quello che impedisce di usare
l'endpoint per scaricare la foto di un account Telegram qualunque: l'indirizzo valido di una
persona lo produce solo il server, e solo quando la mostra (classifica, leghe, profili). Non
scade, cosi' il browser puo' tenere l'immagine in cache; non dice niente di piu' della foto
stessa, che e' gia' visibile a chi vede quella classifica.
"""
from __future__ import annotations

import hashlib
import hmac

import config

AVATAR_PATH = "/app/api/avatar/"
SIGNATURE_LENGTH = 20
MAX_TELEGRAM_ID = 2**52


def _key() -> bytes:
    # Una chiave separata per questo uso: la firma non rivela niente del token.
    return hashlib.sha256(b"gtp-avatar-url:" + (config.BOT_TOKEN or "").encode()).digest()


def _valid_id(user_id) -> bool:
    return type(user_id) is int and 0 < user_id <= MAX_TELEGRAM_ID


def signature(user_id: int) -> str:
    return hmac.new(_key(), str(user_id).encode(), hashlib.sha256).hexdigest()[:SIGNATURE_LENGTH]


def avatar_url(user_id) -> str | None:
    """L'indirizzo della foto di `user_id`, o None per un id non valido."""
    if not _valid_id(user_id):
        return None
    return f"{AVATAR_PATH}{user_id}?s={signature(user_id)}"


def verify(user_id, sig) -> bool:
    return _valid_id(user_id) and isinstance(sig, str) and hmac.compare_digest(sig, signature(user_id))
