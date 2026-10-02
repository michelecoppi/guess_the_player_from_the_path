"""`GET /app/api/avatar/<id>?s=<firma>`: la foto profilo Telegram negli avatar della Mini App (#296).

- L'indirizzo lo firma il server (`services.avatars`) quando mostra quella persona: senza firma
  valida si risponde 404, cosi' l'endpoint non serve a scaricare la foto di chiunque.
- La foto la chiede il bot (`get_user_profile_photos`, poi `get_file`): Telegram la restituisce
  solo se le impostazioni di privacy della persona lo permettono. Chi non ce l'ha riceve 404 e
  la Mini App lascia le iniziali.
- Cache in memoria per processo, anche dei "non ha foto": una classifica riaperta non rifa' le
  chiamate a Telegram. Un errore di Telegram si ricorda per poco, una risposta per ore. Il
  browser tiene l'immagine un giorno.
- Nessuna lettura Firestore e niente salvato: si perde con l'istanza e si ricostruisce.
"""
from __future__ import annotations

import logging
import time
from collections import OrderedDict
from typing import Any, Optional

from fastapi import APIRouter, Request
from fastapi.responses import Response
from telegram.error import TelegramError

from apps.api.bridge import telegram
from services import avatars

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_CACHED = 512            # ~10 kB l'una: qualche MB al massimo per istanza
FOUND_TTL = 6 * 3600        # una foto cambiata compare entro qualche ora
MISSING_TTL = 6 * 3600      # chi non ha foto (o la nasconde al bot)
ERROR_TTL = 5 * 60          # Telegram non ha risposto: si riprova presto
MIN_SIDE = 150              # il formato piu' piccolo che resta nitido in un avatar da 34-68 px
BROWSER_CACHE = "public, max-age=86400"
MISSING_CACHE = "public, max-age=3600"

_cache: "OrderedDict[int, tuple[float, Optional[bytes]]]" = OrderedDict()


def reset_cache() -> None:
    """Tests only."""
    _cache.clear()


def _cached(user_id: int, now: float):
    entry = _cache.get(user_id)
    if entry is None or entry[0] <= now:
        return False, None
    _cache.move_to_end(user_id)
    return True, entry[1]


def _remember(user_id: int, photo: Optional[bytes], ttl: float, now: float) -> None:
    _cache[user_id] = (now + ttl, photo)
    _cache.move_to_end(user_id)
    while len(_cache) > MAX_CACHED:
        _cache.popitem(last=False)


async def fetch_photo(bot: Any, user_id: int) -> tuple[Optional[bytes], float]:
    """(foto JPEG o None, per quanto ricordarla). Il formato piu' piccolo ancora nitido."""
    try:
        photos = await bot.get_user_profile_photos(user_id, limit=1)
        if not photos.total_count or not photos.photos:
            return None, MISSING_TTL
        sizes = sorted(photos.photos[0], key=lambda size: size.width)
        chosen = next((size for size in sizes if size.width >= MIN_SIDE), sizes[-1])
        file = await bot.get_file(chosen.file_id)
        return bytes(await file.download_as_bytearray()), FOUND_TTL
    except TelegramError as e:
        # Un utente che ha bloccato il bot o un id sconosciuto e' un "non ha foto" come gli altri;
        # il resto (rete, limiti) si riprova dopo poco. Il messaggio non contiene il token.
        logger.info("avatar non disponibile: %s", type(e).__name__)
        return None, ERROR_TTL


@router.get("/app/api/avatar/{user_id}")
async def avatar(user_id: int, request: Request, s: str = ""):
    if not avatars.verify(user_id, s):
        return Response(status_code=404)
    now = time.monotonic()
    hit, photo = _cached(user_id, now)
    if not hit:
        photo, ttl = await fetch_photo(telegram(request).application.bot, user_id)
        _remember(user_id, photo, ttl, now)
    if photo is None:
        return Response(status_code=404, headers={"Cache-Control": MISSING_CACHE})
    return Response(photo, media_type="image/jpeg", headers={"Cache-Control": BROWSER_CACHE})
