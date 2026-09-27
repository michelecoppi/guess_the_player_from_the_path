"""Feature flags (#51) at the runtime boundaries: Mini App API, Telegram handlers, payments.

Every test installs a flag configuration through the same service the runtime uses, then
checks two things: with the flag off the boundary refuses predictably (403
`FEATURE_DISABLED`, or a localized notice in chat) **without** touching the underlying
service; with the flag on (or absent) behaviour is exactly the one before #51.
"""
import asyncio
import logging
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

import bot
from apps.api import miniapp
from domains.shop import service as shop
from handlers import hint_handler, menu_handler, shop_handler, top_users_handler
from services import feature_flags as ff
from services import firebase_service, game, webapp_api
from services.feature_flags import Flag

USER = {"first_name": "Anna", "language": "en", "cosmetics": {"owned": [], "equipped": {}}}


def install(flags, revision=1):
    ff.set_service(ff.FeatureFlagService(
        lambda: {"schema_version": 1, "revision": revision, "flags": flags}, ttl=300))


def fail(name):
    def _unexpected(*args, **kwargs):
        pytest.fail(f"{name} must not run while its feature is disabled")
    return _unexpected


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(miniapp, "_webapp_user", lambda payload, cost=1: (42, dict(USER)))
    return TestClient(bot.app, raise_server_exceptions=False)


def assert_disabled(response, feature):
    assert response.status_code == 403
    assert response.json() == {"detail": "feature_disabled", "code": "FEATURE_DISABLED", "feature": feature}


# ---------------------------------------------------------------------------
# Mini App API
# ---------------------------------------------------------------------------

def test_shop_routes_refuse_with_a_stable_contract_when_disabled(api, monkeypatch):
    install({"shop": {"enabled": False}})
    monkeypatch.setattr(shop, "catalogue_for", fail("catalogue_for"))
    monkeypatch.setattr(shop, "equip", fail("equip"))
    monkeypatch.setattr(shop, "save_look", fail("save_look"))
    for route in ("/app/api/shop", "/app/api/shop/equip", "/app/api/shop/look"):
        assert_disabled(api.post(route, json={"initData": "x", "item": "neon", "action": "save", "name": "a"}), "shop")


def test_shop_catalogue_is_unchanged_when_the_flag_is_absent(api, monkeypatch):
    monkeypatch.setattr(shop, "catalogue_for", lambda user, lang: {"sections": ["ok"]})
    response = api.post("/app/api/shop", json={"initData": "x"})
    assert response.status_code == 200 and response.json() == {"sections": ["ok"]}


def test_no_invoice_link_is_created_while_the_shop_is_disabled(api, monkeypatch, caplog):
    install({"shop": {"enabled": False}})

    async def create_invoice_link(**kwargs):
        pytest.fail("no invoice may be created")

    monkeypatch.setattr(bot.telegram_app, "_bot", SimpleNamespace(create_invoice_link=create_invoice_link),
                        raising=False)
    monkeypatch.setattr(shop, "purchase_status", fail("purchase_status"))
    with caplog.at_level(logging.INFO):
        response = api.post("/app/api/shop/buy", json={"initData": "x", "item": "neon"})
    assert_disabled(response, "shop")
    assert "payment.invoice.refused" in caplog.text
    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]


def test_purchase_history_stays_reachable_for_refund_support_when_the_shop_is_disabled(api, monkeypatch):
    install({"shop": {"enabled": False}})
    monkeypatch.setattr(firebase_service, "get_user_purchases", lambda uid: [
        {"item_id": "neon", "day": "2026-09-01", "stars": 25, "charge_id": "ch_1"}])
    response = api.post("/app/api/shop/history", json={"initData": "x"})
    assert response.status_code == 200
    assert response.json()["purchases"][0]["charge_id"] == "ch_1"


def test_hints_are_refused_without_consuming_anything(api, monkeypatch):
    install({"hints": {"enabled": False}})
    monkeypatch.setattr(game, "take_hint", fail("take_hint"))
    assert_disabled(api.post("/app/api/hint", json={"initData": "x"}), "hints")


def test_daily_ui_blocks_todays_guess_but_not_the_archive(api, monkeypatch):
    install({"daily_ui": {"enabled": False}})
    played = []
    monkeypatch.setattr(miniapp, "play", lambda uid, user, answer, day=None, lang=None: played.append(day) or {"status": "wrong"})

    assert_disabled(api.post("/app/api/guess", json={"initData": "x", "answer": "Messi"}), "daily_ui")
    today = webapp_api.today_iso()
    assert_disabled(api.post("/app/api/guess", json={"initData": "x", "answer": "Messi", "day": today}), "daily_ui")
    archive = api.post("/app/api/guess", json={"initData": "x", "answer": "Messi", "day": "2020-01-01"})
    assert archive.status_code == 200 and played == ["2020-01-01"]


def test_arena_flag_covers_training_and_duels_but_not_events(api, monkeypatch):
    install({"arena": {"enabled": False}})
    from services import app_events, arena
    monkeypatch.setattr(arena, "training", fail("training"))
    monkeypatch.setattr(arena, "duel", fail("duel"))
    monkeypatch.setattr(arena, "list_duels", fail("list_duels"))
    monkeypatch.setattr(app_events, "list_events", lambda uid, lang: {"events": []})

    for body in ({"mode": "training", "action": "next"}, {"mode": "duel", "action": "list"},
                 {"mode": "duel", "action": "get", "code": "ABC"}):
        assert_disabled(api.post("/app/api/arena", json={"initData": "x", **body}), "arena")
    events = api.post("/app/api/arena", json={"initData": "x", "mode": "events"})
    assert events.status_code == 200 and events.json() == {"events": [], "feedback": None}
    # An unknown mode keeps its old answer.
    assert api.post("/app/api/arena", json={"initData": "x", "mode": "bogus"}).status_code == 409


def test_events_v2_flag_covers_only_the_mini_app_event_mode(api, monkeypatch):
    install({"events_v2": {"enabled": False}})
    from services import app_events, arena
    monkeypatch.setattr(app_events, "list_events", fail("list_events"))
    monkeypatch.setattr(app_events, "guess", fail("guess"))
    monkeypatch.setattr(arena, "training", lambda *args: {"session": None})
    assert_disabled(api.post("/app/api/arena", json={"initData": "x", "mode": "events", "action": "guess"}),
                    "events_v2")
    assert api.post("/app/api/arena", json={"initData": "x", "mode": "training"}).json() == {"session": None}


def test_a_rollout_is_evaluated_for_the_authenticated_user_only(api, monkeypatch):
    install({"hints": {"rollout_percentage": 0, "allow_users": ["42"]}})
    monkeypatch.setattr(game, "take_hint", lambda uid, lang, **kwargs: {"status": "ok", "user": uid})
    assert api.post("/app/api/hint", json={"initData": "x", "user_id": 7}).json() == {"status": "ok", "user": 42}

    monkeypatch.setattr(miniapp, "_webapp_user", lambda payload, cost=1: (7, dict(USER)))
    assert_disabled(api.post("/app/api/hint", json={"initData": "x"}), "hints")


def test_an_unauthenticated_request_learns_nothing_about_flags(monkeypatch):
    install({"shop": {"enabled": False}})
    response = TestClient(bot.app).post("/app/api/shop", json={"initData": "forged"})
    assert response.status_code == 401


def test_a_disabled_feature_is_an_expected_refusal_not_an_error(api, monkeypatch, caplog):
    install({"hints": {"enabled": False}})
    with caplog.at_level(logging.INFO):
        response = api.post("/app/api/hint", json={"initData": "x"})
    assert response.status_code == 403
    completed = [r for r in caplog.records if r.getMessage() == "api.request.completed"]
    assert completed and all(r.levelno == logging.INFO for r in completed)
    assert "Traceback" not in caplog.text
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


# ---------------------------------------------------------------------------
# /me: resolved booleans and leaderboard
# ---------------------------------------------------------------------------

@pytest.fixture
def profile_backend(monkeypatch):
    user = {"first_name": "Anna", "points_totali": 10, "leagues": []}
    monkeypatch.setattr(webapp_api.firebase_service, "get_user_data", lambda uid: user)
    monkeypatch.setattr(webapp_api.firebase_service, "get_daily_path", lambda day: None)
    monkeypatch.setattr(webapp_api.firebase_service, "get_top_users",
                        lambda limit=10: [{"telegram_id": 7, "username": "Bea", "points": 30}])
    return user


def test_the_profile_carries_only_resolved_booleans(profile_backend):
    install({"shop": {"rollout_percentage": 0, "allow_users": ["42"], "deny_groups": ["-100"]},
             "arena": {"enabled": False}})
    profile = webapp_api.build_profile(42)
    assert profile["features"] == {"arena": False, "shop": True, "daily_ui": True, "hints": True,
                                   "player_pipeline": True, "events_v2": True, "leaderboard": True}
    serialized = repr(profile)
    for leaked in ("allow_users", "deny_groups", "rollout", "-100", "revision", "updated_by"):
        assert leaked not in serialized


def test_a_disabled_leaderboard_is_an_empty_list_and_is_never_read(profile_backend, monkeypatch):
    install({"leaderboard": {"enabled": False}})
    monkeypatch.setattr(webapp_api.firebase_service, "get_top_users", fail("get_top_users"))
    profile = webapp_api.build_profile(42)
    assert profile["leaderboard"] == [] and profile["features"]["leaderboard"] is False


def test_the_me_route_returns_the_features_block(api, monkeypatch, profile_backend):
    install({"daily_ui": {"enabled": False}})
    response = api.post("/app/api/me", json={"initData": "x", "lightweight": True})
    assert response.status_code == 200
    assert response.json()["features"]["daily_ui"] is False


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

class FakeMessage:
    def __init__(self):
        self.replies = []
        self.chat_id = 7

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)


class FakeQuery:
    def __init__(self, data, answered=False):
        self.data = data
        self.message = FakeMessage()
        self.from_user = SimpleNamespace(id=42, language_code="en")
        self.answers = []
        self.answered = answered

    async def answer(self, text=None, show_alert=False, **kwargs):
        if self.answered:
            raise RuntimeError("Query is too old or already answered")
        self.answered = True
        self.answers.append((text, show_alert))


def command_update(chat_type="private", chat_id=42, user_id=42):
    message = FakeMessage()
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id, language_code="en"),
        effective_chat=SimpleNamespace(id=chat_id, type=chat_type),
        effective_message=message, callback_query=None,
    ), message


@pytest.fixture
def telegram(monkeypatch):
    monkeypatch.setattr("handlers.keyboards.get_user_data", lambda uid: {"language": "en"})


def test_the_shop_command_and_its_menu_button_show_a_notice_when_disabled(telegram, monkeypatch):
    install({"shop": {"enabled": False}})
    monkeypatch.setattr(shop_handler, "_main_view", fail("_main_view"))
    update, message = command_update()
    asyncio.run(shop_handler.shop_command(update, None))
    assert message.replies == ["⏸️ This feature is temporarily unavailable. Please try again later."]

    # The menu answers the callback first; the gate must still reach the user.
    query = FakeQuery("menu_shop")
    menu_update = SimpleNamespace(callback_query=query, effective_user=query.from_user,
                                  effective_chat=SimpleNamespace(id=42, type="private"),
                                  effective_message=query.message)
    asyncio.run(menu_handler.menu_callback(menu_update, None))
    assert query.message.replies and "temporarily unavailable" in query.message.replies[0]


def test_a_shop_button_gets_an_alert_and_no_invoice(telegram, monkeypatch):
    install({"shop": {"enabled": False}})
    query = FakeQuery("shop_buy_neon")
    bot_stub = SimpleNamespace(send_invoice=fail("send_invoice"))
    update = SimpleNamespace(callback_query=query, effective_user=query.from_user,
                             effective_chat=SimpleNamespace(id=42, type="private"),
                             effective_message=query.message)
    asyncio.run(shop_handler.shop_callback(update, SimpleNamespace(bot=bot_stub)))
    assert query.answers == [("⏸️ This feature is temporarily unavailable. Please try again later.", True)]


def test_the_hint_button_takes_no_hint_when_disabled(telegram, monkeypatch):
    install({"hints": {"enabled": False}})
    monkeypatch.setattr(hint_handler.game, "take_hint", fail("take_hint"))
    monkeypatch.setattr(hint_handler, "get_today_challenge", fail("get_today_challenge"))
    query = FakeQuery(hint_handler.CALLBACK_DATA)
    update = SimpleNamespace(callback_query=query, effective_user=query.from_user,
                             effective_chat=SimpleNamespace(id=42, type="private"),
                             effective_message=query.message)
    asyncio.run(hint_handler.hint_callback(update, None))
    assert query.answers and query.answers[0][1] is True


def test_the_leaderboard_can_be_disabled_for_one_group_only(telegram, monkeypatch):
    install({"leaderboard": {"deny_groups": ["-100123"]}})
    monkeypatch.setattr(top_users_handler, "_leaderboard_for", lambda view, uid, fallback_lang="it": "TOP")
    group_update, group_message = command_update(chat_type="supergroup", chat_id=-100123)
    asyncio.run(top_users_handler.top(group_update, None))
    assert "temporarily unavailable" in group_message.replies[0]

    private_update, private_message = command_update()
    asyncio.run(top_users_handler.top(private_update, None))
    assert private_message.replies == ["TOP"]


def test_gated_handlers_keep_their_identity_for_registration():
    assert top_users_handler.top.__name__ == "top"
    assert top_users_handler.top.feature_flag is Flag.LEADERBOARD
    assert shop_handler.shop_callback.feature_flag is Flag.SHOP
    assert hint_handler.hint_callback.feature_flag is Flag.HINTS


# ---------------------------------------------------------------------------
# Telegram Stars: disabling the shop never breaks an existing transaction
# ---------------------------------------------------------------------------

@pytest.fixture
def stars(monkeypatch):
    state = {"user": {"cosmetics": {"owned": [], "equipped": {}}}, "delivered": {}, "reserved": 0}

    def deliver_purchase(user_id, charge_id, item_id, granted, stars, day_iso=None):
        if charge_id in state["delivered"]:
            return False
        state["delivered"][charge_id] = list(granted)
        return True

    def reserve(*args):
        state["reserved"] += 1
        return "ok"

    monkeypatch.setattr(shop.firebase_service, "reserve_checkout", reserve)
    monkeypatch.setattr(shop.firebase_service, "deliver_purchase", deliver_purchase)
    monkeypatch.setattr(shop_handler.firebase_service, "save_user", lambda *args: None)
    monkeypatch.setattr(shop_handler.firebase_service, "get_user_data", lambda uid: state["user"])
    monkeypatch.setattr("handlers.keyboards.get_user_data", lambda uid: state["user"])
    return state


class FakePreCheckout:
    def __init__(self, payload):
        self.invoice_payload = payload
        self.id = "checkout_1"
        self.currency = "XTR"
        self.total_amount = 12
        self.from_user = SimpleNamespace(id=42, language_code="en")
        self.answers = []

    async def answer(self, ok=None, error_message=None, **kwargs):
        self.answers.append((ok, error_message))


def test_precheckout_is_refused_before_any_charge_or_reservation_when_disabled(stars, caplog):
    install({"shop": {"enabled": False}})
    query = FakePreCheckout(shop.payload_for(42, "neon"))
    with caplog.at_level(logging.INFO):
        asyncio.run(shop_handler.precheckout_callback(
            SimpleNamespace(pre_checkout_query=query, effective_user=query.from_user), None))
    ok, error = query.answers[0]
    assert ok is False and "temporarily unavailable" in error
    assert stars["reserved"] == 0
    assert "reason=feature_disabled" in caplog.text or any(
        getattr(r, "_gtp_context", {}).get("reason") == "feature_disabled" for r in caplog.records)


def test_precheckout_is_unchanged_when_the_shop_is_enabled(stars):
    query = FakePreCheckout(shop.payload_for(42, "neon"))
    asyncio.run(shop_handler.precheckout_callback(
        SimpleNamespace(pre_checkout_query=query, effective_user=query.from_user), None))
    assert query.answers == [(True, None)] and stars["reserved"] == 1


def test_an_already_charged_payment_is_delivered_exactly_once_even_with_the_shop_disabled(stars):
    install({"shop": {"enabled": False}})
    payment = SimpleNamespace(invoice_payload=shop.payload_for(42, "neon"),
                              telegram_payment_charge_id="ch_9", total_amount=12)
    for _ in range(2):
        message = FakeMessage()
        message.successful_payment = payment
        update = SimpleNamespace(effective_user=SimpleNamespace(id=42, first_name="Anna", language_code="en"),
                                 effective_message=message)
        asyncio.run(shop_handler.successful_payment_callback(update, None))
    assert stars["delivered"] == {"ch_9": ["neon"]}


def test_admin_refund_and_paysupport_are_never_gated():
    from handlers import support_handler
    assert not hasattr(shop_handler.admin_refund, "feature_flag")
    assert not hasattr(shop_handler.successful_payment_callback, "feature_flag")
    assert not hasattr(support_handler.paysupport, "feature_flag")


# ---------------------------------------------------------------------------
# Flag infrastructure failures never become request failures
# ---------------------------------------------------------------------------

def _broken(*args, **kwargs):
    raise RuntimeError("flag internals broke")


def test_a_broken_flag_service_does_not_fail_requests_on_a_cold_process(api, monkeypatch, profile_backend):
    service = ff.FeatureFlagService(lambda: None, ttl=300)
    ff.set_service(service)
    monkeypatch.setattr(service, "snapshot", _broken)
    monkeypatch.setattr(ff, "evaluate", _broken)
    monkeypatch.setattr(shop, "catalogue_for", lambda user, lang: {"sections": []})
    assert api.post("/app/api/shop", json={"initData": "x"}).status_code == 200
    me = api.post("/app/api/me", json={"initData": "x"})
    assert me.status_code == 200 and all(me.json()["features"].values())


def test_a_broken_flag_service_keeps_an_observed_shop_kill_switch(api, monkeypatch, profile_backend, stars):
    install({"shop": {"enabled": False}})
    service = ff.get_service()
    assert service.is_enabled(Flag.SHOP, user_id=42) is False
    monkeypatch.setattr(service, "snapshot", _broken)
    monkeypatch.setattr(ff, "evaluate", _broken)
    monkeypatch.setattr(shop, "catalogue_for", fail("catalogue_for"))

    assert_disabled(api.post("/app/api/shop", json={"initData": "x"}), "shop")
    assert_disabled(api.post("/app/api/shop/buy", json={"initData": "x", "item": "neon"}), "shop")
    me = api.post("/app/api/me", json={"initData": "x"})
    assert me.status_code == 200 and me.json()["features"]["shop"] is False

    query = FakePreCheckout(shop.payload_for(42, "neon"))
    asyncio.run(shop_handler.precheckout_callback(
        SimpleNamespace(pre_checkout_query=query, effective_user=query.from_user), None))
    assert query.answers[0][0] is False and stars["reserved"] == 0
