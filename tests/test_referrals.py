"""Referral qualification must follow durable daily evidence, never client counters."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from services import firebase_service as fs
from services import referrals, shop


@pytest.fixture
def database(monkeypatch):
    records = {}

    class Ref:
        def __init__(self, path):
            self.path = path

        def get(self, transaction=None):
            if transaction:
                assert not transaction.wrote, "Firestore disallows reads after writes"
            return SimpleNamespace(exists=self.path in records,
                                   to_dict=lambda: deepcopy(records.get(self.path)))

        def set(self, value):
            records[self.path] = deepcopy(value)

    class Transaction:
        wrote = False

        def set(self, reference, value):
            self.wrote = True
            reference.set(value)

        def update(self, reference, values):
            self.wrote = True
            target = records[reference.path]
            for key, value in values.items():
                if key == "cosmetics.earned":
                    owned = target.setdefault("cosmetics", {}).setdefault("earned", [])
                    owned.extend(v for v in value.values if v not in owned)
                else:
                    target[key] = deepcopy(value)

    monkeypatch.setattr(fs, "db", SimpleNamespace(transaction=Transaction))
    monkeypatch.setattr(fs.firestore, "transactional", lambda fn: fn)
    monkeypatch.setattr(fs, "user_ref", lambda uid: Ref(f"user/{uid}"))
    monkeypatch.setattr(fs, "history_ref", lambda uid, day: Ref(f"history/{uid}/{day}"))
    monkeypatch.setattr(referrals, "ref", lambda uid: Ref(f"ref/{uid}"))
    monkeypatch.setattr(referrals, "BOT_TOKEN", "test-secret")
    monkeypatch.setattr(referrals, "today_iso", lambda: "2026-09-01")
    records["user/1"] = {"first_name": "Owner", "referral_qualified": 2}
    return records


def register(records, uid=2, inviter=1):
    return fs.save_user(uid, "Friend", referral_code=referrals.code_for(inviter))


def finish(records, uid, day, solved=True, attempts=1):
    records[f"history/{uid}/{day}"] = {"day": day, "solved": solved, "attempts": attempts}
    return referrals.credit_day(uid, day)


def test_signed_links_cannot_be_changed(database):
    code = referrals.code_for(1)
    assert referrals.inviter_from_code(code) == 1
    assert referrals.inviter_from_code(code.replace("ref_1_", "ref_2_")) is None
    assert referrals.inviter_from_code("ref_1_garbage") is None


def test_registration_is_first_touch_only(database):
    assert register(database)["created"]
    database["user/3"] = {"first_name": "Other"}
    assert not register(database, inviter=3)["created"]
    assert database["ref/2"]["inviter_id"] == 1
    fs.save_user(4, "Existing")
    register(database, uid=4)
    assert "ref/4" not in database


def test_self_missing_and_deleted_referrals_are_rejected(database):
    register(database, uid=5, inviter=5)
    assert "ref/5" not in database
    register(database, uid=6, inviter=99)
    assert "ref/6" not in database
    database["ref/7"] = {"status": "deleted"}
    register(database, uid=7)
    assert database["ref/7"] == {"status": "deleted"}


def test_five_distinct_finishes_qualify_once_and_grant_permanent_reward(database):
    register(database)
    for n in range(1, 5):
        assert finish(database, 2, f"2026-09-{n:02}")
    assert database["user/1"]["referral_qualified"] == 2
    assert not referrals.credit_day(2, "2026-09-04")
    # A loss counts. The fifth day does not have to be consecutive.
    assert finish(database, 2, "2026-09-09", solved=False, attempts=3)
    assert database["user/1"]["referral_qualified"] == 3
    assert database["user/1"]["cosmetics"]["earned"] == ["referral_intesa"]
    assert database["ref/2"]["status"] == "qualified"
    assert len(database["ref/2"]["days"]) == 5
    assert not referrals.credit_day(2, "2026-09-09")
    assert not finish(database, 2, "2026-09-10")
    assert database["user/1"]["referral_qualified"] == 3


def test_open_abandoned_archive_and_pre_attribution_days_do_not_count(database):
    register(database)
    assert not referrals.credit_day(2, "2026-09-01")
    assert not finish(database, 2, "2026-09-01", solved=False, attempts=1)
    assert not finish(database, 2, "2026-08-31")
    database["archive/2/2026-09-03"] = {"solved": True, "attempts": 1}
    assert not referrals.credit_day(2, "2026-09-03")
    assert database["ref/2"]["days"] == []


def test_reconciliation_recovers_a_failed_credit_from_history(database, monkeypatch):
    register(database)
    history = [{"day": f"2026-09-{n:02}", "solved": True, "attempts": 1} for n in range(1, 6)]
    for row in history:
        database[f"history/2/{row['day']}"] = row
    monkeypatch.setattr(fs, "get_daily_history", lambda uid, limit: history)
    assert referrals.reconcile(deepcopy(database["ref/2"]))
    # Niente da recuperare, nessuna rilettura: e' quello che dice al club di non ricaricare.
    assert not referrals.reconcile(deepcopy(database["ref/2"]))
    assert database["user/1"]["referral_qualified"] == 3


@pytest.mark.parametrize("target", [3, 5, 10])
def test_rewards_are_exclusive_and_survive_counter_changes(target):
    for item_id in referrals.REWARDS[target]:
        assert item_id not in shop.owned_ids({"referral_qualified": target - 1})
        assert item_id in shop.owned_ids({"referral_qualified": target})
        assert item_id in shop.owned_ids({"cosmetics": {"earned": [item_id]}})
        assert shop.purchase_status({}, item_id) == "not_for_sale"


def test_daily_history_hook_preserves_evidence_before_credit(database, monkeypatch):
    from services.repos.archive import record_daily_history
    register(database)
    record_daily_history(2, "2026-09-01", True, 1)
    assert database["ref/2"]["days"] == ["2026-09-01"]
    # Chi non ha un invito in corso e' la quasi totalita': non deve pagare una transazione
    # a ogni daily conclusa, e la lettura secca basta a saperlo.
    opened = []
    monkeypatch.setattr(fs.db, "transaction", lambda: opened.append(1))
    record_daily_history(3, "2026-09-01", True, 1)
    assert not opened


def test_tactics_finishes_render_differently_from_existing_cards():
    from PIL import Image

    from services.path_image import FINISHES
    plain = Image.new("RGB", (600, 800), (16, 41, 37))
    images = [FINISHES[key](plain.copy(), (16, 41, 37), (200, 244, 139)).tobytes()
              for key in ["plain", "tactics", "eleven"]]
    assert len(set(images)) == 3
