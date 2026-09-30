"""Sfida inline (#240): codici opachi, materiale senza spoiler, tetto, card e contatore."""
import asyncio
import random
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import config
from apps.api import static
from handlers import inline_handler, start_handler, training_handler
from services import inline_challenge, practice_content
from services.player_pool import get_all_players, get_practice_players

TODAY = "2026-09-30"
# Un codice e una card finti, ben formati: servono solo a provare il formato dei link.
FAKE_CODE = "abcdefghijkl"
FAKE_CARD = "0123456789"


@pytest.fixture(autouse=True)
def secrets(monkeypatch):
    monkeypatch.setattr(config, "BOT_TOKEN", "test-token")
    monkeypatch.setattr(config, "BOT_USERNAME", "gtp_bot")
    monkeypatch.setattr(config, "PUBLIC_BASE_URL", "https://example.test")
    monkeypatch.setattr(inline_challenge, "past_days_span",
                        lambda today=None: ("2026-09-01", "2026-09-29"))
    inline_challenge.card_jpeg.cache_clear()


def _reserved():
    return get_practice_players()[0]


def _daily_pool_player():
    return get_all_players()[0]


# --- codici --------------------------------------------------------------------------------

def test_code_is_opaque_stable_and_round_trips_for_training_material():
    key = practice_content.POOL_PREFIX + _reserved()["id"]
    code = inline_challenge.code_for(key)

    assert inline_challenge.CODE.fullmatch(code)
    assert code == inline_challenge.code_for(key)
    assert _reserved()["id"] not in code
    assert inline_challenge.key_for(code) == key
    day_key = practice_content.DAY_PREFIX + "2026-09-10"
    assert inline_challenge.key_for(inline_challenge.code_for(day_key)) == day_key


@pytest.mark.parametrize("key", [
    practice_content.DAY_PREFIX + TODAY,           # la sfida di oggi
    practice_content.DAY_PREFIX + "2026-10-01",    # una sfida futura
])
def test_today_and_future_dailies_have_no_code(key):
    assert inline_challenge.key_for(inline_challenge.code_for(key)) is None


def test_a_daily_pool_player_has_no_code():
    """Un giocatore che puo' ancora uscire come sfida del giorno non si mostra mai."""
    player = _daily_pool_player()
    assert not player.get("practice_only")
    code = inline_challenge.code_for(practice_content.POOL_PREFIX + player["id"])
    assert inline_challenge.key_for(code) is None


def test_the_code_depends_on_the_bot_secret(monkeypatch):
    key = practice_content.POOL_PREFIX + _reserved()["id"]
    before = inline_challenge.code_for(key)
    monkeypatch.setattr(config, "BOT_TOKEN", "another-token")
    assert inline_challenge.code_for(key) != before


@pytest.mark.parametrize("code", ["", "short", "ABCDEFGHIJKL", "abcdefghijk1", None])
def test_malformed_codes_are_rejected(code):
    assert inline_challenge.key_for(code) is None


@pytest.mark.parametrize("argument, expected", [
    ("inl_" + FAKE_CODE, (FAKE_CODE, None)),
    ("inl_" + FAKE_CODE + "_" + FAKE_CARD, (FAKE_CODE, FAKE_CARD)),
    ("inl_" + FAKE_CODE + "_xyz", None),
    ("inl_ABCDEFGHIJKL", None),
    ("inline", None),
    ("ref_abc", None),
])
def test_start_parameter_parsing(argument, expected):
    assert inline_challenge.parse_start(argument) == expected


def test_start_parameter_fits_telegram_limit():
    parameter = inline_challenge.start_parameter(FAKE_CODE, FAKE_CARD)
    assert len(parameter) <= 64
    assert inline_challenge.parse_start(parameter) == (FAKE_CODE, FAKE_CARD)


# --- tetto e scelta ------------------------------------------------------------------------

def test_the_daily_cap_resets_with_the_day(monkeypatch):
    monkeypatch.setattr(inline_challenge, "daily_limit", lambda: 3)
    assert inline_challenge.remaining_today({}, TODAY) == 3
    assert inline_challenge.remaining_today({"inline_day": TODAY, "inline_count": 2}, TODAY) == 1
    assert inline_challenge.remaining_today({"inline_day": TODAY, "inline_count": 5}, TODAY) == 0
    assert inline_challenge.remaining_today({"inline_day": "2026-09-29", "inline_count": 5}, TODAY) == 3


def test_cards_avoid_what_the_sender_already_sent(monkeypatch):
    monkeypatch.setattr(practice_content, "load_config", lambda: {"practice_past_challenge_ratio": 0})
    reserved = get_practice_players()
    sent = [practice_content.POOL_PREFIX + p["id"] for p in reserved[:-3]]

    cards = inline_challenge.pick_cards(sent, rng=random.Random(1))

    keys = [card["key"] for card in cards]
    assert len(keys) == 3 == len(set(keys))
    assert not set(keys) & set(sent)


def test_caption_shows_the_tally_but_never_the_answer():
    challenge = practice_content.from_player(_reserved())
    plain = inline_challenge.caption("it", challenge)
    counted = inline_challenge.caption("it", challenge, solved=3, failed=1)

    assert "3" in counted and "1" in counted and counted.startswith(plain)
    assert challenge["answer"].lower() not in counted.lower()


# --- immagine pubblica ---------------------------------------------------------------------

def _client():
    app = FastAPI()
    app.include_router(static.router)
    return TestClient(app)


def test_card_image_is_a_jpeg_for_a_valid_code():
    code = inline_challenge.code_for(practice_content.POOL_PREFIX + _reserved()["id"])
    response = _client().get(f"/inline/card/{code}.jpg?lang=en")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content[:3] == b"\xff\xd8\xff"


@pytest.mark.parametrize("code", ["abcdefghijkl", "not-a-code", "ABCDEFGHIJKL"])
def test_unknown_or_malformed_codes_have_no_image(code):
    assert _client().get(f"/inline/card/{code}.jpg").status_code == 404


def test_the_daily_pool_has_no_image():
    code = inline_challenge.code_for(practice_content.POOL_PREFIX + _daily_pool_player()["id"])
    assert _client().get(f"/inline/card/{code}.jpg").status_code == 404


# --- handler -------------------------------------------------------------------------------

class FakeInlineQuery:
    def __init__(self, user_id=42):
        self.from_user = SimpleNamespace(id=user_id, language_code="it")
        self.answers = []

    async def answer(self, results, **kwargs):
        self.answers.append((results, kwargs))


def _inline_update(query):
    return SimpleNamespace(inline_query=query)


def test_inline_list_offers_photo_cards_that_do_not_name_the_player(monkeypatch):
    challenge = practice_content.from_player(_reserved())
    monkeypatch.setattr(inline_handler.firebase_service, "get_user_data", lambda uid: {"language": "it"})
    monkeypatch.setattr(inline_challenge, "pick_cards", lambda sent: [challenge])
    query = FakeInlineQuery()

    asyncio.run(inline_handler.inline_query(_inline_update(query), None))

    (results, kwargs), = query.answers
    assert kwargs["is_personal"] is True
    card, = results
    code = inline_challenge.code_for(challenge["key"])
    assert card.id == code
    assert card.photo_url == f"https://example.test/inline/card/{code}.jpg?lang=it"
    link = card.reply_markup.inline_keyboard[0][0].url
    assert link == f"https://t.me/gtp_bot?start=inl_{code}"
    for text in (card.photo_url, link, card.caption):
        assert challenge["player_id"] not in text


def test_unregistered_senders_are_sent_to_the_bot_first(monkeypatch):
    monkeypatch.setattr(inline_handler.firebase_service, "get_user_data", lambda uid: None)
    query = FakeInlineQuery()

    asyncio.run(inline_handler.inline_query(_inline_update(query), None))

    (results, kwargs), = query.answers
    assert results == [] and kwargs["button"].start_parameter == "inline"


def test_senders_over_the_daily_cap_get_no_cards(monkeypatch):
    monkeypatch.setattr(inline_handler.firebase_service, "get_user_data",
                        lambda uid: {"inline_day": "x", "inline_count": 99})
    monkeypatch.setattr(inline_handler, "today_iso", lambda: "x")
    monkeypatch.setattr(inline_challenge, "pick_cards", lambda sent: pytest.fail("no cards over the cap"))
    query = FakeInlineQuery()

    asyncio.run(inline_handler.inline_query(_inline_update(query), None))

    (results, kwargs), = query.answers
    assert results == [] and kwargs["button"] is not None


class FakeBot:
    def __init__(self):
        self.markups = []
        self.captions = []

    async def edit_message_reply_markup(self, inline_message_id, reply_markup):
        self.markups.append((inline_message_id, reply_markup))

    async def edit_message_caption(self, inline_message_id, caption, parse_mode, reply_markup):
        self.captions.append((inline_message_id, caption, reply_markup))


def test_a_chosen_card_is_recorded_and_gets_its_own_counter(monkeypatch):
    key = practice_content.POOL_PREFIX + _reserved()["id"]
    code = inline_challenge.code_for(key)
    sent = []
    monkeypatch.setattr(inline_handler.inline_cards, "record_sent",
                        lambda uid, k, today, limit, memory: sent.append((uid, k)) or True)
    monkeypatch.setattr(inline_handler.inline_cards, "create_card", lambda c, lang, mid: "0123456789")
    monkeypatch.setattr(inline_handler.firebase_service, "get_user_data", lambda uid: {"language": "it"})
    bot = FakeBot()
    chosen = SimpleNamespace(result_id=code, inline_message_id="IMID",
                             from_user=SimpleNamespace(id=42, language_code="it"))

    asyncio.run(inline_handler.chosen_inline_result(SimpleNamespace(chosen_inline_result=chosen),
                                                    SimpleNamespace(bot=bot)))

    assert sent == [(42, key)]
    (message_id, markup), = bot.markups
    assert message_id == "IMID"
    assert markup.inline_keyboard[0][0].url.endswith(f"start=inl_{code}_{FAKE_CARD}")


def test_a_forged_result_id_records_nothing(monkeypatch):
    monkeypatch.setattr(inline_handler.inline_cards, "record_sent", lambda *a: pytest.fail("recorded"))
    chosen = SimpleNamespace(result_id="abcdefghijkl", inline_message_id="IMID",
                             from_user=SimpleNamespace(id=42, language_code="it"))

    asyncio.run(inline_handler.chosen_inline_result(SimpleNamespace(chosen_inline_result=chosen),
                                                    SimpleNamespace(bot=FakeBot())))


def test_a_finished_game_rewrites_the_card_tally(monkeypatch):
    code = inline_challenge.code_for(practice_content.POOL_PREFIX + _reserved()["id"])
    monkeypatch.setattr(inline_handler.inline_cards, "record_result", lambda uid, card, solved: {
        "code": code, "lang": "it", "inline_message_id": "IMID", "solved": 2, "failed": 1})
    bot = FakeBot()

    asyncio.run(inline_handler.report_card_result(bot, 42, "0123456789", solved=True))

    (message_id, caption, _), = bot.captions
    assert message_id == "IMID" and "2" in caption and "1" in caption


def test_a_game_already_counted_leaves_the_card_alone(monkeypatch):
    monkeypatch.setattr(inline_handler.inline_cards, "record_result", lambda uid, card, solved: None)
    bot = FakeBot()

    asyncio.run(inline_handler.report_card_result(bot, 42, "0123456789", solved=True))

    assert bot.captions == []


# --- dal bottone alla partita --------------------------------------------------------------

class FakeMessage:
    def __init__(self):
        self.chat = SimpleNamespace(type="private", id=42)
        self.replies = []
        self.photos = []

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)

    async def reply_photo(self, photo, caption=None, **kwargs):
        self.photos.append(caption)


def test_the_guess_button_opens_training_on_that_card(monkeypatch):
    player = _reserved()
    code = inline_challenge.code_for(practice_content.POOL_PREFIX + player["id"])
    opened, events = [], []
    monkeypatch.setattr(start_handler, "save_user",
                        lambda *a, **k: {"language": "it", "created": True})
    monkeypatch.setattr(start_handler.analytics, "capture",
                        lambda event, user_id, properties=None: events.append((event, properties)))
    monkeypatch.setattr(training_handler.firebase_service, "set_training_key",
                        lambda uid, key, card=None: opened.append((key, card)))
    message = FakeMessage()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=42, first_name="Anna", language_code="it"),
        effective_chat=message.chat, effective_message=message,
    )

    asyncio.run(start_handler.start(update, SimpleNamespace(args=[f"inl_{code}_{FAKE_CARD}"])))

    assert opened == [(practice_content.POOL_PREFIX + player["id"], "0123456789")]
    assert message.photos
    started = [props for event, props in events if event == start_handler.analytics.Event.BOT_STARTED]
    assert started[0]["acquisition_channel"] == "inline"


def test_solving_a_card_game_reports_it(monkeypatch):
    challenge = practice_content.from_player(_reserved())
    user = {"language": "it", "training_key": challenge["key"], "training_attempts": 0,
            "training_card": "0123456789"}
    reported = []
    monkeypatch.setattr(training_handler.practice_content, "load", lambda key: challenge)
    monkeypatch.setattr(training_handler.firebase_service, "register_training_solved", lambda uid: None)

    async def report(bot, uid, card, solved):
        reported.append((uid, card, solved))

    monkeypatch.setattr(training_handler, "report_card_result", report)
    message = FakeMessage()
    update = SimpleNamespace(effective_user=SimpleNamespace(id=42, language_code="it"),
                             effective_message=message)

    asyncio.run(training_handler.process_training_answer(
        update, SimpleNamespace(bot=FakeBot()), challenge["answer"], user))

    assert reported == [(42, "0123456789", True)]
