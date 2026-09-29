"""Il bottone "La figurina" del bot disegna solo quello che il server ha registrato (#222)."""
import asyncio
from types import SimpleNamespace

import pytest

from handlers import guess_handler
from services import daily_result
from services.daily_challenge import challenge_number

YESTERDAY = "2026-09-28"
TODAY = "2026-09-29"


class FakeQuery:
    def __init__(self, data):
        self.data = data
        self.answers = []
        self.photos = []
        self.message = SimpleNamespace(reply_photo=self._reply_photo)

    async def answer(self, text=None, show_alert=False):
        self.answers.append((text, show_alert))

    async def _reply_photo(self, photo, caption):
        self.photos.append(caption)


class Snapshot:
    def __init__(self, data):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return self._data


@pytest.fixture
def world(monkeypatch):
    """Storico in memoria per giorno, e la card intercettata al posto del disegno."""
    state = {"history": {}, "user": {"first_name": "Anna"}, "drawn": []}
    monkeypatch.setattr(daily_result.firebase_service, "history_ref",
                        lambda uid, day: SimpleNamespace(get=lambda: Snapshot(state["history"].get(day))))
    monkeypatch.setattr(daily_result.firebase_service, "get_daily_history",
                        lambda uid, limit: [state["history"][d] for d in sorted(state["history"], reverse=True)][:limit])
    monkeypatch.setattr(guess_handler.firebase_service, "get_user_data", lambda uid: state["user"])
    monkeypatch.setattr(guess_handler.trophies, "showcase", lambda user, lang: [])
    monkeypatch.setattr(guess_handler.referrals, "invite_link", lambda uid: "https://t.me/bot?start=ref")

    def fake_card(user, lang, number, attempts, max_attempts, **kwargs):
        state["drawn"].append({"number": number, "attempts": attempts, **kwargs})
        return b"png"

    monkeypatch.setattr(guess_handler, "card_image", fake_card)
    return state


def press(data):
    query = FakeQuery(data)
    update = SimpleNamespace(callback_query=query,
                             effective_user=SimpleNamespace(id=42, language_code="it"))
    asyncio.run(guess_handler.share_card_callback(update, None))
    return query


def record(day, attempts, solved=True, hints=0):
    return {"day": day, "attempts": attempts, "solved": solved, "hints": hints}


def test_the_card_uses_the_recorded_result_and_the_number_of_that_day(world):
    """Premuto dopo mezzanotte su un messaggio di ieri: numero di ieri, risultato di ieri."""
    world["history"][YESTERDAY] = record(YESTERDAY, 2, hints=1)
    query = press(f"sharecard:{YESTERDAY}")
    assert world["drawn"] == [{"number": challenge_number(YESTERDAY), "attempts": 2, "solved": True,
                               "streak": 0, "hints": 1, "trophy": None, "day": YESTERDAY}]
    assert f"#{challenge_number(YESTERDAY)}" in query.photos[0]
    assert query.answers == [(None, False)]


def test_a_day_without_a_closed_game_draws_nothing(world):
    query = press(f"sharecard:{TODAY}")
    assert world["drawn"] == [] and query.photos == []
    assert query.answers[0][1] is True


@pytest.mark.parametrize("data", ["sharecard:not-a-day", "sharecard:", "sharecard:1:1", "sharecard:a:b:c:d:e:f"])
def test_a_malformed_button_draws_nothing(world, data):
    world["history"][TODAY] = record(TODAY, 1)
    query = press(data)
    assert world["drawn"] == [] and query.answers[0][1] is True


@pytest.mark.parametrize("stored", [record(TODAY, 9), record(TODAY, 0), record(TODAY, 1, hints=99),
                                    {"day": TODAY, "attempts": "1", "solved": True, "hints": 0}])
def test_stored_numbers_out_of_range_are_refused(world, stored):
    world["history"][TODAY] = stored
    press(f"sharecard:{TODAY}")
    assert world["drawn"] == []


def test_a_legacy_button_matching_the_last_game_still_works(world):
    """I bottoni gia' in chat portano i numeri e non il giorno: valgono solo se coincidono
    con l'ultima partita chiusa. La serie scritta nel bottone non conta."""
    world["history"][TODAY] = record(TODAY, 2, hints=1)
    world["user"].update(last_correct_day=TODAY, current_streak=3)
    press("sharecard:2:1:1:999")
    assert world["drawn"][0]["number"] == challenge_number(TODAY)
    assert world["drawn"][0]["streak"] == 3


@pytest.mark.parametrize("data", ["sharecard:1:1:0:999", "sharecard:2:0:1:0", "sharecard:2:1:0:0"])
def test_a_forged_or_stale_legacy_button_draws_nothing(world, data):
    world["history"][TODAY] = record(TODAY, 2, hints=1)
    press(data)
    assert world["drawn"] == []


def test_the_streak_is_shown_only_for_the_day_it_belongs_to(world):
    """`current_streak` e' la serie di `last_correct_day`: su una giornata precedente o persa
    non c'e' una serie vera da mostrare."""
    world["user"].update(last_correct_day=TODAY, current_streak=5)
    world["history"][YESTERDAY] = record(YESTERDAY, 1)
    world["history"][TODAY] = record(TODAY, 1)
    press(f"sharecard:{YESTERDAY}")
    press(f"sharecard:{TODAY}")
    assert [card["streak"] for card in world["drawn"]] == [0, 5]


def test_a_lost_day_has_no_streak(world):
    world["user"].update(last_correct_day=TODAY, current_streak=5)
    world["history"][TODAY] = record(TODAY, 3, solved=False)
    press(f"sharecard:{TODAY}")
    assert world["drawn"][0]["streak"] == 0 and world["drawn"][0]["solved"] is False


def test_the_button_carries_only_the_day():
    markup = guess_handler._share_keyboard("it", 2, 5, hints=1, day=TODAY)
    datas = [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]
    assert datas == [f"sharecard:{TODAY}"]
    assert len(datas[0].encode()) <= 64
