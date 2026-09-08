"""Verifica dei dati che la mini app Telegram manda al server.

La pagina gira dentro Telegram e riceve una stringa firmata (`initData`) con dentro chi e'
l'utente. Senza controllare quella firma chiunque potrebbe chiamare le nostre API dicendo
"sono l'utente 12345" e leggersi (o falsare) i dati di un altro: e' l'unico punto in cui il
bot accetta una richiesta che non arriva da Telegram.

La procedura e' quella documentata da Telegram:

1. chiave segreta = HMAC-SHA256(chiave="WebAppData", messaggio=token del bot);
2. si rimette in fila `chiave=valore` di tutti i campi tranne `hash`, ordinati per nome,
   separati da a capo;
3. l'HMAC-SHA256 di quella stringa con la chiave segreta deve combaciare con `hash`.

Si controlla anche `auth_date`: una firma valida ma vecchia di giorni e' un replay.
"""
import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

MAX_AGE_SECONDS = 24 * 60 * 60


def _secret_key(bot_token):
    return hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()


def parse_init_data(init_data, bot_token, max_age_seconds=MAX_AGE_SECONDS, now=None):
    """Ritorna i campi di `initData` se la firma e' valida, altrimenti alza ValueError."""
    if not bot_token:
        raise ValueError("token del bot non configurato")
    if not init_data:
        raise ValueError("initData mancante")

    fields = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = fields.pop("hash", "")
    if not received_hash:
        raise ValueError("firma mancante")

    check_string = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    expected = hmac.new(_secret_key(bot_token), check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected, received_hash):
        raise ValueError("firma non valida")

    auth_date = int(fields.get("auth_date", 0) or 0)
    current = int(now if now is not None else time.time())
    if max_age_seconds and (current - auth_date) > max_age_seconds:
        raise ValueError("dati scaduti")

    if "user" in fields:
        try:
            fields["user"] = json.loads(fields["user"])
        except (TypeError, ValueError):
            raise ValueError("campo user illeggibile") from None

    return fields


def user_id_from_init_data(init_data, bot_token, **kwargs):
    fields = parse_init_data(init_data, bot_token, **kwargs)
    user = fields.get("user") or {}
    user_id = user.get("id")
    if not user_id:
        raise ValueError("utente assente")
    return int(user_id)
