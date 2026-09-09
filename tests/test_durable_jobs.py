import asyncio
import copy
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from google.api_core.exceptions import AlreadyExists
from google.cloud.firestore_v1.transforms import Increment
from telegram.error import Forbidden, RetryAfter

from handlers import daily_job
from services import broadcast_store, firebase_service, monthly_closure, task_queue, work_receipts


class MemoryDB:
    """Minimal Firestore fake, with ordered pages and persistent document state."""
    def __init__(self):
        self.data = {}

    def collection(self, name):
        return Query(self, name)

    def transaction(self):
        return SimpleNamespace(set=lambda ref, data: ref.set(data), update=lambda ref, data: ref.update(data),
                               delete=lambda ref: ref.delete())


class Ref:
    def __init__(self, db, path):
        self.db, self.path = db, path
        self.id = path.split("/")[-1]

    def get(self, **kwargs):
        return SimpleNamespace(exists=self.path in self.db.data, id=self.id, reference=self,
                               to_dict=lambda: copy.deepcopy(self.db.data.get(self.path)))

    def set(self, data):
        self.db.data[self.path] = copy.deepcopy(data)

    def create(self, data):
        if self.path in self.db.data:
            raise AlreadyExists("duplicate")
        self.set(data)

    def update(self, data):
        # `Increment` lo risolve il server, non il client: senza questo il finto database
        # salverebbe l'oggetto della trasformazione al posto del numero.
        current = self.db.data[self.path]
        for key, value in copy.deepcopy(data).items():
            current[key] = current.get(key, 0) + value.value if isinstance(value, Increment) else value

    def delete(self):
        self.db.data.pop(self.path, None)


class Query:
    def __init__(self, db, name):
        self.db, self.name = db, name
        self.size, self.cursor, self.filter = 10000, "", None

    def document(self, key):
        return Ref(self.db, f"{self.name}/{key}")

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, size):
        self.size = size
        return self

    def start_after(self, cursor):
        self.cursor = cursor["__name__"].id
        return self

    def where(self, field, operator, value):
        self.filter = (field, operator, value)
        return self

    def stream(self):
        refs = [Ref(self.db, key) for key in sorted(self.db.data) if key.startswith(self.name + "/")]
        refs = [ref for ref in refs if ref.id > self.cursor]
        if self.filter:
            field, operator, value = self.filter
            refs = [ref for ref in refs if (ref.get().to_dict().get(field, 0) > value if operator == ">"
                                          else ref.get().to_dict().get(field) == value)]
        return iter([ref.get() for ref in refs[:self.size]])


@pytest.fixture
def db(monkeypatch):
    database = MemoryDB()
    monkeypatch.setattr(firebase_service, "db", database)
    monkeypatch.setattr(firebase_service.firestore, "transactional", lambda fn: fn)
    return database


def test_receipts_serialize_users_and_never_replay_ambiguous_work(db, monkeypatch):
    clock = [1000]
    monkeypatch.setattr(work_receipts.time, "time", lambda: clock[0])
    assert work_receipts.claim("a", serial_key="42") == "claimed"
    assert work_receipts.claim("a", serial_key="42") == "busy"
    assert work_receipts.claim("b", serial_key="42") == "busy"
    assert work_receipts.claim("c", serial_key="43") == "claimed"
    work_receipts.finish("a")
    assert work_receipts.claim("a") == "done"
    assert work_receipts.claim("b", serial_key="42") == "claimed"
    clock[0] += 241
    assert work_receipts.claim("b", serial_key="42") == "uncertain"
    assert work_receipts.claim("b", serial_key="42") == "uncertain"


def test_monthly_reset_retry_preserves_new_month_points(db):
    user = db.collection("users").document("42")
    user.set({"monthly_points": 110, "monthly_earned": {"2026-08": 100, "2026-09": 10}})
    closure = {"closed_month": "2026-08", "new_month": "2026-09"}
    assert monthly_closure.reset_user(user, closure) == 1
    assert user.get().to_dict()["monthly_points"] == 10
    user.update({"monthly_points": 15, "monthly_earned": {"2026-09": 15}})
    assert monthly_closure.reset_user(user, closure) == 0
    assert user.get().to_dict()["monthly_points"] == 15


def test_monthly_podium_snapshot_survives_partial_reset(db, monkeypatch):
    monkeypatch.setattr(firebase_service, "get_or_create_season", lambda *a: ({"season_number": 4}, False))
    db.collection("users").document("1").set({"telegram_id": 1, "first_name": "Anna", "monthly_points": 25,
                                             "monthly_earned": {"2026-09": 5}})
    db.collection("users").document("2").set({"telegram_id": 2, "first_name": "Bruno", "monthly_points": 21})
    now = datetime(2026, 9, 1)
    initial = monthly_closure.prepare(now)
    assert [w["username"] for w in initial["winners"]] == ["Bruno", "Anna"]
    monthly_closure.reset_user(db.collection("users").document("2"), initial)
    assert monthly_closure.prepare(now) == initial


def test_broadcast_pages_bound_reads_and_skip_unsubscribed(db):
    """Chi ha le notifiche spente non deve nemmeno essere letto.

    Il filtro sta nella query, quindi una pagina e' fatta di 100 destinatari veri e non di
    100 documenti da scartare a meta': con la maggioranza degli iscritti a notifiche spente
    la differenza e' fra pagare tutta la collection e pagare solo chi riceve il messaggio."""
    for uid in range(201):
        db.collection("users").document(f"{uid:04}").set({"chat_id": uid, "notifications_enabled": uid % 2 == 0})
    first, cursor = broadcast_store.page("2026-09-08")
    second, last = broadcast_store.page("2026-09-08", cursor)
    assert len(first) == 100 and len(second) == 1
    assert cursor == "0198" and last is None
    assert all(user["chat_id"] % 2 == 0 for user in first + second)
    assert {u["user_id"] for u in first}.isdisjoint({u["user_id"] for u in second})


def test_broadcast_page_skips_users_without_a_chat(db):
    """Un utente importato senza `chat_id` non ha una chat dove scrivere: si salta qui,
    invece di collezionare un errore Telegram per ognuno."""
    db.collection("users").document("0001").set({"chat_id": -1, "notifications_enabled": True})
    db.collection("users").document("0002").set({"chat_id": 22, "notifications_enabled": True})
    users, _ = broadcast_store.page("2026-09-08")
    assert [user["user_id"] for user in users] == ["0002"]


def test_broadcast_retry_does_not_resend_successful_users(db, monkeypatch):
    users = [{"user_id": "1", "chat_id": 1}, {"user_id": "2", "chat_id": 2}]
    for user in users:
        db.collection("users").document(user["user_id"]).set(user)
    send = AsyncMock(side_effect=[None, RetryAfter(2), None])
    monkeypatch.setattr(daily_job, "get_bot", lambda: SimpleNamespace(send_message=send))
    monkeypatch.setattr(daily_job, "app_keyboard", lambda lang: None)
    monkeypatch.setattr(daily_job.asyncio, "sleep", AsyncMock())

    async def run():
        assert await daily_job._broadcast("2026-09-08", "Messi", None, None,
                                          users=users, notification_day="2026-09-09") == (1, 1)
        assert await daily_job._broadcast("2026-09-08", "Messi", None, None,
                                          users=users, notification_day="2026-09-09") == (1, 0)
    asyncio.run(run())
    assert [call.kwargs["chat_id"] for call in send.call_args_list] == [1, 2, 2]
    assert db.data["users/1"]["last_notification_day"] == "2026-09-09"


def test_blocked_recipient_is_disabled_and_not_retried(db, monkeypatch):
    user = {"user_id": "1", "chat_id": 1}
    db.collection("users").document("1").set(user)
    send = AsyncMock(side_effect=Forbidden("blocked"))
    monkeypatch.setattr(daily_job, "get_bot", lambda: SimpleNamespace(send_message=send))
    monkeypatch.setattr(daily_job, "app_keyboard", lambda lang: None)
    assert asyncio.run(daily_job._broadcast("2026-09-08", "Messi", None, None,
                                            users=[user], notification_day="2026-09-09")) == (0, 0)
    assert not db.data["users/1"]["notifications_enabled"]
    assert work_receipts.claim("notify-2026-09-09-1") == "done"


def test_daily_retry_reuses_snapshot_and_does_not_broadcast_inline(db, monkeypatch):
    payload = {"reference_day": "2026-09-08", "monthly_result": None}
    broadcast_store.save_job("2026-09-09", payload)
    monkeypatch.setattr(daily_job, "today_iso", lambda: "2026-09-09")
    def forbidden():
        pytest.fail("Retry must not generate again")
    monkeypatch.setattr(daily_job, "ensure_daily_buffer", forbidden)
    send = AsyncMock()
    monkeypatch.setattr(daily_job, "_broadcast", send)
    calls = []
    monkeypatch.setattr(task_queue, "enqueue", lambda *a, **kw: calls.append((a, kw)))
    asyncio.run(daily_job.update_daily_challenge())
    asyncio.run(daily_job.update_daily_challenge())
    assert calls[0] == calls[1]
    send.assert_not_called()


def test_monthly_close_is_bounded_and_enqueues_continuation(db, monkeypatch):
    closure = {"closed_month": "2026-08", "new_month": "2026-09", "winners": []}
    broadcast_store.save_job("2026-09-01", {"monthly_result": closure})
    for uid in range(201):
        db.collection("users").document(f"{uid:04}").set({"monthly_points": 10})
    calls = []
    monkeypatch.setattr(task_queue, "enqueue", lambda *a, **kw: calls.append((a, kw)))
    result = monthly_closure.close_batch("2026-09-01")
    assert result == {"processed": 100}
    assert calls[0][0][0] == "/internal/monthly-close"
    assert calls[0][0][1] == {"day": "2026-09-01", "cursor": "0099"}
    assert db.data["users/0100"]["monthly_points"] == 10


def test_admin_summary_arrives_once_when_the_last_page_is_done(db, monkeypatch):
    """Il riepilogo di mezzanotte non e' sparito con il broadcast a pagine: lo manda
    l'ultima pagina, che e' l'unico punto in cui il giro e' davvero finito.

    Il totale viene dal contatore sul documento del giorno, non dalla singola pagina:
    con piu' richieste in fila, quella che chiude non ha visto le precedenti."""
    broadcast_store.save_job("2026-09-09", {
        "reference_day": "2026-09-08", "yesterday_player": "Messi", "current_event": None,
        "monthly_result": None, "stats": [10, 4], "finished_event_name": "Numeri 10",
    })
    db.collection("users").document("0001").set({"chat_id": 1, "notifications_enabled": True})
    monkeypatch.setattr(daily_job, "_broadcast", AsyncMock(return_value=(7, 0)))
    notify = AsyncMock()
    monkeypatch.setattr(daily_job, "_notify_admins", notify)
    enqueued = []
    monkeypatch.setattr(task_queue, "enqueue", lambda *a, **kw: enqueued.append(a))

    asyncio.run(daily_job.broadcast_batch("2026-09-09"))

    assert enqueued == []
    assert db.data["daily_jobs/2026-09-09"]["sent_total"] == 7
    summary = notify.call_args.args[0]
    assert "7" in summary and "Numeri 10" in summary


def test_intermediate_pages_report_nothing_and_keep_the_running_total(db, monkeypatch):
    broadcast_store.save_job("2026-09-09", {"reference_day": "2026-09-08", "monthly_result": None})
    for uid in range(100):
        db.collection("users").document(f"{uid:04}").set({"chat_id": uid, "notifications_enabled": True})
    monkeypatch.setattr(daily_job, "_broadcast", AsyncMock(return_value=(100, 0)))
    notify = AsyncMock()
    monkeypatch.setattr(daily_job, "_notify_admins", notify)
    monkeypatch.setattr(task_queue, "enqueue", lambda *a, **kw: None)

    assert asyncio.run(daily_job.broadcast_batch("2026-09-09"))["next_cursor"] == "0099"
    notify.assert_not_called()
    assert db.data["daily_jobs/2026-09-09"]["sent_total"] == 100


def test_a_failed_page_still_counts_what_left_and_reports_nothing(db, monkeypatch):
    """Il conteggio precede l'errore: i messaggi partiti restano partiti, e al retry le
    ricevute saltano quegli utenti, quindi il totale non li conta due volte."""
    broadcast_store.save_job("2026-09-09", {"reference_day": "2026-09-08", "monthly_result": None})
    db.collection("users").document("0001").set({"chat_id": 1, "notifications_enabled": True})
    monkeypatch.setattr(daily_job, "_broadcast", AsyncMock(return_value=(3, 1)))
    notify = AsyncMock()
    monkeypatch.setattr(daily_job, "_notify_admins", notify)

    with pytest.raises(RuntimeError):
        asyncio.run(daily_job.broadcast_batch("2026-09-09"))
    assert db.data["daily_jobs/2026-09-09"]["sent_total"] == 3
    notify.assert_not_called()
