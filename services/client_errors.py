"""Errori JavaScript della Mini App, segnalati dal telefono (#180).

Il backend ha Sentry (#18), ma un crash nel browser di un utente restava invisibile. La Mini
App manda un campione degli errori non gestiti a `POST /app/api/client-error`; qui si decide
cosa ne sopravvive: un insieme chiuso di campi, ciascuno limitato e ripulito con
`observability.scrub_text`, senza id ne' testo arbitrariamente lungo. Il record va nei log a
livello WARNING: resta interrogabile in Cloud Logging ma non consuma la quota di Sentry.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from services import observability

KINDS = ("error", "unhandledrejection")
MAX_MESSAGE = 300
MAX_SOURCE = 160
MAX_STACK = 1200
MAX_POSITION = 10_000_000

# La schermata e' un id di tab (`play`, `shop`, `arena`...): solo minuscole, niente testo libero.
_SCREEN = re.compile(r"^[a-z][a-z_-]{0,23}$")
# Query string e frammenti possono portare dati (anche initData): dalle URL si tiene il path.
_URL_TAIL = re.compile(r"[?#][^\s)]*")


def _text(value: Any, limit: int) -> Optional[str]:
    if not isinstance(value, str):
        return None
    text = _URL_TAIL.sub("", value).strip()
    if not text:
        return None
    return observability.scrub_text(text[:limit])


def _position(value: Any) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if 0 <= value <= MAX_POSITION else None


def client_error_fields(payload: Any) -> Optional[dict[str, Any]]:
    """The accepted, bounded subset of a Mini App error report, or None if unusable."""
    if not isinstance(payload, dict) or payload.get("kind") not in KINDS:
        return None
    message = _text(payload.get("message"), MAX_MESSAGE)
    if message is None:
        return None
    # `message` e' un campo riservato del record di log (sarebbe scartato): qui error_message.
    fields: dict[str, Any] = {"kind": payload["kind"], "error_message": message}
    for name, limit in (("source", MAX_SOURCE), ("stack", MAX_STACK)):
        text = _text(payload.get(name), limit)
        if text is not None:
            fields[name] = text
    for name in ("line", "col"):
        position = _position(payload.get(name))
        if position is not None:
            fields[name] = position
    screen = payload.get("screen")
    if isinstance(screen, str) and _SCREEN.match(screen):
        fields["screen"] = screen
    return fields
