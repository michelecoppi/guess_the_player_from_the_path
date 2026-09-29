"""Sfida inline (#240) su un Firestore vero: tetto giornaliero e conto una volta per giocatore."""
from concurrent.futures import ThreadPoolExecutor

import pytest

from services import firebase_service
from services.repos import inline_cards

pytestmark = pytest.mark.usefixtures("emulator_db")

TODAY = "2026-09-30"


def test_sent_cards_are_remembered_and_capped():
    firebase_service.save_user(1, "Anna")

    results = [inline_cards.record_sent(1, f"pool:p{n}", TODAY, limit=2, memory=3) for n in range(4)]

    user = firebase_service.get_user_data(1)
    assert results == [True, True, False, False]
    assert user["inline_count"] == 2 and user["inline_day"] == TODAY
    assert user["inline_sent"] == ["pool:p1", "pool:p2", "pool:p3"]  # solo le ultime `memory`


def test_the_cap_starts_again_the_next_day():
    firebase_service.save_user(1, "Anna")
    inline_cards.record_sent(1, "pool:a", "2026-09-29", limit=1, memory=10)

    assert inline_cards.record_sent(1, "pool:b", TODAY, limit=1, memory=10) is True


def test_unknown_senders_record_nothing():
    assert inline_cards.record_sent(999, "pool:a", TODAY, limit=5, memory=10) is False
    assert firebase_service.get_user_data(999) is None


def test_each_player_counts_once_per_card_even_when_retried_together():
    firebase_service.save_user(1, "Anna")
    firebase_service.save_user(2, "Bruno")
    card = inline_cards.create_card("abcdefghijkl", "it", "IMID")

    def attempt(_):
        try:
            return inline_cards.record_result(1, card, solved=True)
        except Exception:  # l'emulatore puo' far rinunciare i perdenti (vedi test_firestore_transactions)
            return None

    ref = firebase_service.db.collection(inline_cards.INLINE_CARDS).document(card)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(attempt, range(4)))
    # Sull'emulatore i perdenti possono rinunciare tutti: l'invariante e' che non vinca piu'
    # di uno, e che un nuovo tentativo porti il conto a uno esatto, mai a due.
    assert ref.get().to_dict()["solved"] <= 1
    inline_cards.record_result(1, card, solved=True)
    second = inline_cards.record_result(2, card, solved=False)

    stored = ref.get().to_dict()
    assert stored["solved"] == 1 and stored["failed"] == 1
    assert second["failed"] == 1
    # Nessun id utente sulla card: chi chiede /forgetme non lascia tracce qui.
    assert set(stored) == {"code", "lang", "inline_message_id", "solved", "failed", "created_at", "expires_at"}


def test_a_missing_card_counts_nothing():
    firebase_service.save_user(1, "Anna")
    assert inline_cards.record_result(1, "0123456789", solved=True) is None
