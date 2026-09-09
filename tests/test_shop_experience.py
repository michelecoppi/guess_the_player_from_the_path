"""Ownership, signed completion prices, outfits and earned cosmetics."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from handlers import shop_handler
from services import firebase_service, shop


def user(*ids, **fields):
    return {"cosmetics": {"owned": list(ids), "equipped": {}}, **fields}


def test_completion_price_decreases_and_owned_items_cannot_be_bought():
    pack = shop.get_item("pacchetto_neon")
    assert shop.price_for(user(), pack) == 60
    assert shop.price_for(user("neon"), pack) == 45
    complete = user(*pack["grants"])
    assert shop.price_for(complete, pack) == 0
    assert shop.purchase_status(complete, pack["id"]) == "already_owned"
    assert shop.purchase_status(user("neon"), "neon") == "already_owned"


def test_signed_invoice_records_only_missing_pieces_and_rejects_tampering():
    pack = shop.get_item("pacchetto_neon")
    payload = shop.payment_payload(42, user("neon"), pack)
    quote = shop.payment_quote(payload)
    assert len(payload.encode()) <= 128
    assert quote["price"] == 45
    assert "neon" not in quote["granted"]
    assert set(quote["granted"]) == set(pack["grants"]) - {"neon"}
    assert shop.payment_quote(payload.replace(":45:", ":1:")) is None
    assert shop.parse_payload(payload.replace(":42:", ":99:")) == (None, None)


@pytest.mark.parametrize("change", ["price", "currency", "owned", "owner", "busy"])
def test_precheckout_rejects_stale_or_invalid_invoices(monkeypatch, change):
    data = user("neon")
    item = shop.get_item("pacchetto_neon")
    payload = shop.payment_payload(42, data, item)
    query = SimpleNamespace(id="q1", invoice_payload=payload, from_user=SimpleNamespace(id=42),
                            currency="XTR", total_amount=45, answer=AsyncMock())
    if change == "price":
        query.total_amount = 1
    elif change == "currency":
        query.currency = "EUR"
    elif change == "owned":
        data["cosmetics"]["owned"].append("fuoco")
    elif change == "owner":
        query.from_user.id = 43
    monkeypatch.setattr(shop_handler, "language_for", lambda update: "it")
    monkeypatch.setattr(firebase_service, "get_user_data", lambda uid: data)
    monkeypatch.setattr(firebase_service, "reserve_checkout", lambda *args: "checkout_busy" if change == "busy" else "ok")
    asyncio.run(shop_handler.precheckout_callback(SimpleNamespace(pre_checkout_query=query), None))
    assert query.answer.call_args.kwargs["ok"] is False


def test_completion_delivery_preserves_the_snapshot_for_refunds(monkeypatch):
    data = user("neon")
    payload = shop.payment_payload(42, data, shop.get_item("pacchetto_neon"))
    written = {}
    monkeypatch.setattr(firebase_service, "deliver_purchase", lambda uid, charge, item, granted, stars:
                        written.update(granted=granted, stars=stars) or True)
    monkeypatch.setattr(firebase_service, "save_user", lambda *args: None)
    monkeypatch.setattr(shop_handler, "language_for", lambda update: "it")
    payment = SimpleNamespace(invoice_payload=payload, telegram_payment_charge_id="ch", total_amount=45)
    message = SimpleNamespace(successful_payment=payment, reply_text=AsyncMock())
    update = SimpleNamespace(effective_user=SimpleNamespace(id=42, first_name="Anna"), effective_message=message)
    asyncio.run(shop_handler.successful_payment_callback(update, None))
    assert "neon" not in written["granted"]
    assert written["stars"] == 45


@pytest.mark.parametrize("pack_id", ["pacchetto_europa", "pacchetto_neon", "pacchetto_esordio", "pacchetto_sostenitore"])
def test_wearing_a_pack_validates_all_ownership_before_one_write(monkeypatch, pack_id):
    pack = shop.get_item(pack_id)
    writes = []
    monkeypatch.setattr(firebase_service, "equip_look", lambda uid, slots: writes.append(slots))
    assert shop.equip(42, user(), pack_id) == "not_owned"
    assert not writes
    assert shop.equip(42, user(*pack["grants"]), pack_id) == "ok"
    assert len(writes) == 1
    assert set(writes[0].values()) == set(pack["grants"])
    assert not shop.can_wear_bundle(shop.get_item("collezione_completa"))


def test_saved_looks_are_bounded_replaceable_and_rechecked_after_refunds(monkeypatch):
    data = user("neon")
    data["cosmetics"]["equipped"] = {"theme": "neon"}
    monkeypatch.setattr(firebase_service, "save_looks", lambda uid, looks: data["cosmetics"].update(looks=looks))
    for index in range(5):
        assert shop.save_look(42, data, f"Look {index}") == "ok"
    assert shop.save_look(42, data, "Sixth") == "look_limit"
    assert shop.save_look(42, data, "Look 0") == "ok"
    assert shop.save_look(42, data, " " * 5) == "invalid_name"
    data["cosmetics"]["owned"] = []
    monkeypatch.setattr(firebase_service, "equip_look", lambda *args: pytest.fail("Refunded item was equipped"))
    assert shop.use_look(42, data, "Look 0") == "not_owned"


@pytest.mark.parametrize("item_id,field,target", [
    ("traguardo_esploratore", "players_guessed", 10),
    ("traguardo_costanza", "best_streak", 7),
    ("traguardo_archivista", "archive_solved", 25),
])
def test_earned_items_are_not_free_defaults_and_unlock_at_the_milestone(item_id, field, target):
    assert item_id not in shop.free_ids()
    assert item_id not in shop.owned_ids(user(**{field: target - 1}))
    assert item_id in shop.owned_ids(user(**{field: target}))
    assert shop.purchase_status(user(**{field: target}), item_id) == "not_for_sale"
    assert shop.equip_status(user(**{field: target}), item_id) == "ok"


def test_checkout_reservation_serializes_competing_payments(monkeypatch):
    data = user("neon")
    ref = SimpleNamespace(get=lambda **kwargs: SimpleNamespace(to_dict=lambda: data))
    transaction = SimpleNamespace(set=lambda ref, fields, **kwargs: data.update(fields))
    monkeypatch.setattr(firebase_service, "user_ref", lambda uid: ref)
    monkeypatch.setattr(firebase_service, "db", SimpleNamespace(transaction=lambda: transaction))
    monkeypatch.setattr(firebase_service.firestore, "transactional", lambda func: func)
    monkeypatch.setattr(firebase_service.time, "time", lambda: 1000)
    assert firebase_service.reserve_checkout(42, "q1", ["neon"]) == "ok"
    assert firebase_service.reserve_checkout(42, "q1", ["neon"]) == "ok"
    assert firebase_service.reserve_checkout(42, "q2", ["neon"]) == "checkout_busy"
    monkeypatch.setattr(firebase_service.time, "time", lambda: 1121)
    assert firebase_service.reserve_checkout(42, "q2", ["neon"]) == "ok"
    data["cosmetics"]["owned"].append("fuoco")
    assert firebase_service.reserve_checkout(42, "q3", ["neon"]) == "price_changed"
