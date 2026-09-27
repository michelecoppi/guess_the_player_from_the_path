"""La firma di initData e' l'unica cosa che separa "sono l'utente 42" dall'esserlo davvero."""
import hashlib
import hmac
import json
from urllib.parse import urlencode

import pytest

from services.webapp_auth import parse_init_data, user_id_from_init_data

TOKEN = "123456:FAKE-TOKEN-PER-I-TEST"


def sign(fields, token=TOKEN):
    check_string = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    signature = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode({**fields, "hash": signature})


def init_data(user_id=42, auth_date=1_000_000):
    return sign({
        "auth_date": str(auth_date),
        "query_id": "AAA",
        "user": json.dumps({"id": user_id, "first_name": "Anna"}, separators=(",", ":")),
    })


def test_valid_data_is_accepted_and_the_user_is_parsed():
    fields = parse_init_data(init_data(), TOKEN, now=1_000_100)
    assert fields["user"]["id"] == 42
    assert user_id_from_init_data(init_data(), TOKEN, now=1_000_100) == 42


def test_a_tampered_field_invalidates_the_signature():
    original = init_data()
    tampered = original.replace("%3A42", "%3A99")
    assert tampered != original
    with pytest.raises(ValueError):
        parse_init_data(tampered, TOKEN, now=1_000_100)


def test_data_signed_with_another_token_is_refused():
    other = sign({"auth_date": "1000000", "user": json.dumps({"id": 42})}, token="999:ALTRO")
    with pytest.raises(ValueError):
        parse_init_data(other, TOKEN, now=1_000_100)


def test_old_data_is_refused_even_if_the_signature_is_valid():
    with pytest.raises(ValueError):
        parse_init_data(init_data(auth_date=1), TOKEN, now=1_000_000)


@pytest.mark.parametrize("payload", ["", "user=%7B%22id%22%3A42%7D"])
def test_missing_data_or_signature_is_refused(payload):
    with pytest.raises(ValueError):
        parse_init_data(payload, TOKEN, now=1_000_100)


def test_without_a_bot_token_nothing_is_ever_accepted():
    with pytest.raises(ValueError):
        parse_init_data(init_data(), "", now=1_000_100)
