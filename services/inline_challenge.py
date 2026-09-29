"""Sfida inline (#240): un percorso misterioso lanciato in qualsiasi chat con `@<bot>`.

Chi scrive `@<bot>` in una chat vede qualche card con un percorso di carriera; ne sceglie
una, la card finisce nella chat con il bottone **Indovina**, e chi lo preme apre il bot su
quel calciatore (una sessione di allenamento, services/practice_content.py).

**Cosa si puo' mostrare.** Solo il materiale che non spoilera niente, lo stesso
dell'allenamento: il pool riservato (`practice_only`, non esce mai come sfida del giorno) e
le giornate gia' passate. La giornata di oggi e quelle future non hanno un codice, quindi
nessun link le puo' aprire.

**Perche' un codice opaco.** L'immagine della card sta a un URL pubblico (Telegram la scarica
da li') e il bottone porta un parametro `start` che chiunque nella chat puo' leggere. Con la
chiave in chiaro (`pool:maldini`) la risposta sarebbe scritta nel link. Il codice e' un HMAC
della chiave: si ricalcola, ma non si inverte; dal codice alla chiave si torna provando le
chiavi possibili, che sono poche centinaia e stanno tutte in memoria.

**Perche' un tetto e un registro.** Ogni card mostra un calciatore a una chat intera, che
dopo non lo trovera' piu' nuovo in allenamento. Il registro per mittente evita di rimandare
lo stesso percorso (Telegram non dice in quale chat va la card, quindi il controllo per chat
non si puo' fare) e il tetto giornaliero evita che una persona sola consumi il pool.
"""
import base64
import hashlib
import hmac
import random
import re
from datetime import timedelta
from functools import lru_cache

import config
from services import practice_content
from services.dates import parse_iso, to_iso, today_iso
from services.i18n import difficulty_label, t
from services.past_challenges import past_days_span
from services.player_pool import get_practice_players, load_config

CODE_LENGTH = 12
CODE = re.compile(rf"^[a-z2-7]{{{CODE_LENGTH}}}$")
CARD = re.compile(r"^[a-f0-9]{10}$")
# `/start inl_<codice>` oppure `/start inl_<codice>_<card>`: la seconda forma arriva dal
# bottone di una card gia' inviata e serve a tenerne il conto.
START_PREFIX = "inl_"
START_PARAMETER = re.compile(rf"^{START_PREFIX}([a-z2-7]{{{CODE_LENGTH}}})(?:_([a-f0-9]{{10}}))?$")

CARDS_PER_QUERY = 3
DEFAULT_DAILY_LIMIT = 20
# Quante chiavi inviate si ricordano per mittente: abbastanza per mesi di card, poco
# abbastanza da stare comodi sul documento utente.
SENT_MEMORY = 300


def _secret():
    # Derivato dal token del bot: e' gia' un segreto, e cambiarlo invalida anche i codici,
    # che e' quello che si vuole se il token e' stato esposto.
    return hashlib.sha256(b"inline-card:" + (config.BOT_TOKEN or "").encode()).digest()


def code_for(key):
    digest = hmac.new(_secret(), key.encode(), hashlib.sha256).digest()
    return base64.b32encode(digest).decode().lower()[:CODE_LENGTH]


def _candidate_keys(today=None):
    for player in get_practice_players():
        yield practice_content.POOL_PREFIX + player["id"]
    span = past_days_span(today)
    if span:
        first, last = (parse_iso(day) for day in span)
        for offset in range((last - first).days + 1):
            yield practice_content.DAY_PREFIX + to_iso(first + timedelta(days=offset))


def key_for(code, today=None):
    """La chiave di un codice, o None. Solo pool riservato e giornate passate: la giornata
    di oggi non e' fra le candidate, quindi nessun codice la apre."""
    if not code or not CODE.fullmatch(code):
        return None
    for key in _candidate_keys(today):
        if hmac.compare_digest(code_for(key), code):
            return key
    return None


def parse_start(argument):
    """(codice, card) da un parametro `/start`, oppure None."""
    match = START_PARAMETER.fullmatch(argument or "")
    return (match.group(1), match.group(2)) if match else None


def start_parameter(code, card=None):
    return f"{START_PREFIX}{code}_{card}" if card else f"{START_PREFIX}{code}"


def daily_limit():
    return int(load_config().get("inline_daily_limit", DEFAULT_DAILY_LIMIT))


def sent_today(user_data, today=None):
    user_data = user_data or {}
    if user_data.get("inline_day") != (today or today_iso()):
        return 0
    return int(user_data.get("inline_count") or 0)


def remaining_today(user_data, today=None):
    return max(0, daily_limit() - sent_today(user_data, today))


def pick_cards(sent_keys=(), count=CARDS_PER_QUERY, rng=None):
    """Fino a `count` sfide diverse, lontane da quelle gia' inviate da questo mittente."""
    rng = rng or random
    excluded = set(sent_keys or ())
    cards: list[dict] = []
    for _ in range(count * 2):
        if len(cards) == count:
            break
        challenge = practice_content.pick(exclude_keys=excluded, rng=rng)
        if not challenge or not challenge.get("career_path") or challenge["key"] in excluded:
            continue
        excluded.add(challenge["key"])
        cards.append(challenge)
    return cards


def challenge_for(code, today=None):
    key = key_for(code, today)
    return practice_content.load(key) if key else None


def caption(lang, challenge, solved=0, failed=0):
    """Il testo sotto la card; con il conto di chi ci ha gia' provato quando c'e'."""
    text = t(lang, "inline.caption", stops=len(challenge.get("career_path") or []),
             difficulty=difficulty_label(lang, challenge.get("difficulty")))
    if solved or failed:
        text += "\n" + t(lang, "inline.tally", solved=solved, failed=failed)
    return text


@lru_cache(maxsize=128)
def card_jpeg(code, lang):
    """L'immagine della card in JPEG, il solo formato che Telegram accetta per le foto
    inline. In cache: la stessa card viene scaricata una volta per ogni client che la vede."""
    from io import BytesIO

    from PIL import Image

    from services.path_image import render_career_path_image

    challenge = challenge_for(code)
    if not challenge or not challenge.get("career_path"):
        return None
    career = challenge["career_path"]
    png = render_career_path_image(
        career, title=t(lang, "image.path_title"),
        subtitle=t(lang, "image.path_subtitle", stops=len(career)),
        badge=difficulty_label(lang, challenge.get("difficulty")).upper(), lang=lang,
    )
    image = Image.open(png).convert("RGB")
    out = BytesIO()
    image.save(out, format="JPEG", quality=88)
    return out.getvalue()
