"""Il documento utente si completa da solo.

I campi si sono aggiunti col tempo e chi si era registrato prima e' rimasto senza: `/start`
sul documento gia' esistente non scriveva niente. Qui si fissa il comportamento nuovo, cioe'
che un documento vecchio torna completo senza che nessun valore gia' scritto cambi.
"""
from types import SimpleNamespace

import pytest

from scripts.backfill_users import plan_backfill
from services.firebase_service import (
    USER_FIELD_DEFAULTS,
    missing_user_fields,
    new_user_document,
)

# Un utente registrato prima che esistessero lingua, striscia, indizi e sessioni: sono i
# campi che il backup di Firestore mostra sui documenti veri.
LEGACY_USER = {
    "first_name": "Anna",
    "telegram_id": 7,
    "chat_id": 7,
    "notifications_enabled": True,
    "monthly_points": 12,
    "points_totali": 40,
    "daily_attempts": 0,
    "has_guessed_today": False,
    "last_played_day": None,
    "trophies": ["1_evento"],
    "players_guessed": 9,
    "bonus_first_guessed": 2,
}


def test_new_user_document_has_every_known_field():
    document = new_user_document(7, "Anna", language="en")
    for field in USER_FIELD_DEFAULTS:
        assert field in document
    assert document["language"] == "en"
    assert document["telegram_id"] == 7


def test_legacy_user_is_completed_with_the_missing_fields():
    missing = missing_user_fields(LEGACY_USER, user_id=7, first_name="Anna", language="en")

    assert missing["current_streak"] == 0
    assert missing["best_streak"] == 0
    assert missing["last_correct_day"] is None
    assert missing["daily_hints"] == 0
    assert missing["archive_solved"] == 0
    assert missing["training_key"] is None
    assert missing["event_key"] is None
    assert missing["leagues"] == []
    assert missing["language"] == "en"


def test_nothing_that_is_already_there_gets_rewritten():
    missing = missing_user_fields(LEGACY_USER, user_id=7, first_name="Bruno", language="en")

    for field in ("points_totali", "monthly_points", "trophies", "players_guessed",
                  "bonus_first_guessed", "first_name", "notifications_enabled", "chat_id"):
        assert field not in missing


def test_a_language_chosen_by_hand_wins_over_the_one_of_the_client():
    user = dict(LEGACY_USER, language="es")
    assert "language" not in missing_user_fields(user, language="en")


def test_an_unsupported_language_counts_as_missing():
    user = dict(LEGACY_USER, language="pt")
    assert missing_user_fields(user, language="en")["language"] == "en"


def test_without_a_detected_language_the_field_is_left_alone():
    """Meglio nessuna lingua che una a caso: chi legge un campo assente ripiega sulla lingua
    del client Telegram, che e' un'informazione vera."""
    assert "language" not in missing_user_fields(LEGACY_USER)


def test_a_complete_user_needs_nothing():
    complete = new_user_document(7, "Anna", language="it")
    assert missing_user_fields(complete, user_id=7, first_name="Anna", language="it") == {}


def test_zero_values_are_not_mistaken_for_missing_fields():
    user = dict(LEGACY_USER, current_streak=0, best_streak=0, archive_solved=0, language="it")
    missing = missing_user_fields(user, language="it")
    for field in ("current_streak", "best_streak", "archive_solved", "language"):
        assert field not in missing


def test_the_defaults_are_not_shared_between_documents():
    first = new_user_document(1, "Anna")
    second = new_user_document(2, "Bruno")
    first["trophies"].append("1_evento")
    assert second["trophies"] == []
    assert USER_FIELD_DEFAULTS["trophies"] == []


# ---------------------------------------------------------------------------
# Lo script che completa tutti gli utenti in una volta
# ---------------------------------------------------------------------------

def test_the_backfill_only_plans_the_users_that_need_it():
    documents = [
        ("7", dict(LEGACY_USER)),
        ("8", new_user_document(8, "Bruno", language="it")),
    ]
    plan = plan_backfill(documents)

    assert [doc_id for doc_id, _ in plan] == ["7"]
    assert "current_streak" in plan[0][1]


def test_the_backfill_can_take_the_telegram_id_from_the_document_id():
    documents = [("7", {k: v for k, v in LEGACY_USER.items() if k != "telegram_id"})]
    assert plan_backfill(documents)[0][1]["telegram_id"] == 7


# ---------------------------------------------------------------------------
# /start: la transazione che ripara, e la lingua che ne esce
# ---------------------------------------------------------------------------

class FakeSnapshot:
    def __init__(self, data):
        self.exists = data is not None
        self._data = data

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class FakeRef:
    def __init__(self, data=None):
        self.data = data

    def get(self, transaction=None):
        return FakeSnapshot(self.data)


class FakeTransaction:
    def __init__(self):
        self.sets = []
        self.updates = []

    def set(self, ref, payload):
        self.sets.append(payload)
        ref.data = dict(payload)

    def update(self, ref, payload):
        self.updates.append(payload)
        ref.data.update(payload)


@pytest.fixture
def firestore_stub(monkeypatch):
    """Sostituisce la sola parte Firestore di save_user: il decoratore transazionale, il
    riferimento al documento e il client."""
    from services import firebase_service

    transaction = FakeTransaction()
    holder = {}

    def transactional(func):
        def run(_transaction):
            return func(transaction)
        return run

    monkeypatch.setattr(firebase_service.firestore, "transactional", transactional)
    monkeypatch.setattr(firebase_service.firestore, "SERVER_TIMESTAMP", "TS", raising=False)
    monkeypatch.setattr(firebase_service, "user_ref", lambda user_id: holder["ref"])
    monkeypatch.setattr(firebase_service, "db", SimpleNamespace(transaction=lambda: transaction))
    return holder, transaction


def test_start_of_a_legacy_user_repairs_the_document(firestore_stub):
    from services.firebase_service import save_user

    holder, transaction = firestore_stub
    holder["ref"] = FakeRef(dict(LEGACY_USER))

    result = save_user(7, "Anna", language="en")

    assert result["created"] is False
    # La lingua e' quella rilevata dal client, e da adesso e' scritta sul documento.
    assert result["language"] == "en"
    assert holder["ref"].data["language"] == "en"
    assert holder["ref"].data["current_streak"] == 0
    # I valori di prima sono intatti.
    assert holder["ref"].data["points_totali"] == 40
    assert holder["ref"].data["trophies"] == ["1_evento"]
    assert "current_streak" in result["repaired"]


def test_start_of_a_complete_user_writes_nothing(firestore_stub):
    from services.firebase_service import save_user

    holder, transaction = firestore_stub
    holder["ref"] = FakeRef(new_user_document(7, "Anna", language="es"))

    result = save_user(7, "Anna", language="en")

    assert result == {"created": False, "language": "es", "repaired": []}
    assert transaction.updates == []


def test_start_of_a_new_user_creates_the_complete_document(firestore_stub):
    from services.firebase_service import save_user

    holder, transaction = firestore_stub
    holder["ref"] = FakeRef(None)

    result = save_user(7, "Anna", language="en")

    assert result["created"] is True
    assert result["language"] == "en"
    for field in USER_FIELD_DEFAULTS:
        assert field in transaction.sets[0]
