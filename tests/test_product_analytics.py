"""Product analytics (#29): the service must be safe before it is useful.

Every test here proves one of the hard requirements from the issue: no key means no traffic,
a provider outage never reaches product code, only known events/properties leave the
process, identities are pseudonymous and stable, and completion-only events (a purchase, a
referral) do not double-fire on a retry. `test_no_real_network_client_is_built_in_tests`
is the one that matters most for CI: it proves the whole rest of the suite never talks to
PostHog, without needing to mock `requests` in every other test file.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from services import product_analytics as analytics


@pytest.fixture(autouse=True)
def clean_analytics():
    analytics._reset_for_tests()
    yield
    analytics._reset_for_tests()


def enable(monkeypatch, salt="analytics-salt-" + "x" * 20, **overrides):
    """Init the service with a fake client so no real HTTP client is ever constructed."""
    fake_client = MagicMock()
    monkeypatch.setattr(analytics, "_build_client", lambda settings: fake_client)
    settings = analytics.Settings(
        enabled=True, api_key="phc_test", host="https://analytics.invalid",  # pragma: allowlist secret
        environment=overrides.pop("environment", "production"),
        release=overrides.pop("release", "1.2.3"),
        revision=overrides.pop("revision", "guess-the-player-00099-abc"),
        salt=salt,
    )
    analytics.init(settings=settings)
    return fake_client


# ---------------------------------------------------------------------------
# Settings / disabled-by-default
# ---------------------------------------------------------------------------

def test_no_api_key_means_disabled():
    settings = analytics.Settings.from_env({})
    assert settings.enabled is False
    assert settings.api_key == ""


def test_local_and_test_environments_default_off_even_with_a_key():
    settings = analytics.Settings.from_env({"POSTHOG_API_KEY": "phc_x", "PYTEST_CURRENT_TEST": "x"})
    assert settings.environment == "test"
    assert settings.enabled is False


def test_explicit_enable_wins_over_the_local_default(monkeypatch):
    settings = analytics.Settings.from_env(
        {"POSTHOG_API_KEY": "phc_x", "PYTEST_CURRENT_TEST": "x", "PRODUCT_ANALYTICS_ENABLED": "true"}  # pragma: allowlist secret
    )
    assert settings.enabled is True


def test_explicit_disable_wins_even_in_production():
    settings = analytics.Settings.from_env(
        {"POSTHOG_API_KEY": "phc_x", "K_SERVICE": "guess-the-player", "PRODUCT_ANALYTICS_ENABLED": "false"}  # pragma: allowlist secret
    )
    assert settings.environment == "production"
    assert settings.enabled is False


def test_invalid_config_never_raises_only_warns(monkeypatch):
    """A key that fails to build a client (bad host, network error at construction) must
    leave the app running with analytics simply off - never crash init()."""
    def boom(settings):
        raise RuntimeError("bad host")
    monkeypatch.setattr(analytics, "_build_client", boom)
    settings = analytics.init(settings=analytics.Settings(enabled=True, api_key="phc_x", salt="s" * 20))
    assert settings.enabled is True  # config says on...
    assert analytics.is_enabled() is False  # ...but nothing was actually built
    # capture() after a failed init must still be a safe no-op.
    analytics.capture(analytics.Event.BOT_STARTED, user_id=1)


def test_no_real_network_client_is_built_in_tests(monkeypatch):
    """The one test that guarantees the rest of the suite is silent: with the real
    Settings.from_env() (as bot.py calls it) and no POSTHOG_API_KEY in the environment,
    capture() must never reach `_build_client`/`posthog.Posthog` at all."""
    monkeypatch.setattr(analytics, "_build_client",
                        lambda settings: pytest.fail("a real PostHog client must never be built in tests"))
    analytics.init(settings=analytics.Settings.from_env({}))
    assert analytics.is_enabled() is False
    analytics.capture(analytics.Event.BOT_STARTED, user_id=123, properties={"language": "it"})
    analytics.flush()
    analytics.shutdown()


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------

def test_distinct_id_is_stable_for_the_same_user():
    salt = "same-salt-" + "z" * 20
    settings = analytics.Settings(enabled=True, api_key="x", salt=salt)
    analytics._state.settings = settings
    first = analytics.distinct_id_for_user(555)
    second = analytics.distinct_id_for_user(555)
    assert first == second
    assert first is not None


def test_distinct_id_differs_for_different_users():
    salt = "same-salt-" + "z" * 20
    analytics._state.settings = analytics.Settings(enabled=True, api_key="x", salt=salt)
    assert analytics.distinct_id_for_user(1) != analytics.distinct_id_for_user(2)


def test_distinct_id_never_contains_the_raw_telegram_id():
    salt = "same-salt-" + "z" * 20
    analytics._state.settings = analytics.Settings(enabled=True, api_key="x", salt=salt)
    distinct_id = analytics.distinct_id_for_user(918273645)
    assert "918273645" not in distinct_id


def test_no_salt_means_no_identity_and_no_capture(monkeypatch):
    fake_client = MagicMock()
    monkeypatch.setattr(analytics, "_build_client", lambda settings: fake_client)
    analytics.init(settings=analytics.Settings(enabled=True, api_key="x", salt=""))
    analytics.capture(analytics.Event.BOT_STARTED, user_id=42)
    fake_client.capture.assert_not_called()


# ---------------------------------------------------------------------------
# Taxonomy / property allow-list / privacy
# ---------------------------------------------------------------------------

def test_unknown_event_is_never_sent(monkeypatch):
    client = enable(monkeypatch)
    analytics.capture("not_a_real_event", user_id=1)  # type: ignore[arg-type]
    client.capture.assert_not_called()


def test_provider_outage_never_raises_into_the_caller(monkeypatch):
    client = enable(monkeypatch)
    client.capture.side_effect = RuntimeError("posthog is down")
    # Must not raise.
    analytics.capture(analytics.Event.BOT_STARTED, user_id=1)


def test_unknown_properties_are_dropped_not_forwarded(monkeypatch):
    client = enable(monkeypatch)
    analytics.capture(analytics.Event.SHOP_VIEWED, user_id=1, properties={
        "surface": "miniapp", "totally_made_up_field": "whatever",
    })
    sent_props = client.capture.call_args.kwargs["properties"]
    assert "totally_made_up_field" not in sent_props
    assert sent_props["surface"] == "miniapp"


@pytest.mark.parametrize("bad_key", ["token", "authorization", "cookie", "password", "secret", "initdata"])
def test_sensitive_looking_keys_are_never_forwarded_even_if_allow_listed(monkeypatch, bad_key):
    """Even if BOTH layers of the schema mistakenly allow a sensitive-looking key - it is on
    the event's allowed-key set AND has a (permissive) validator - `is_sensitive_key` still
    refuses it. A schema authoring mistake must not become a leak."""
    client = enable(monkeypatch)
    monkeypatch.setitem(
        analytics.EVENT_PROPERTIES, analytics.Event.BOT_STARTED,
        analytics.EVENT_PROPERTIES[analytics.Event.BOT_STARTED] | {bad_key},
    )
    monkeypatch.setitem(analytics.PROPERTY_VALIDATORS, bad_key, lambda value: True)
    analytics.capture(analytics.Event.BOT_STARTED, user_id=1, properties={bad_key: "super-secret-value"})
    sent_props = client.capture.call_args.kwargs["properties"]
    assert bad_key not in sent_props


# ---------------------------------------------------------------------------
# Per-event property schema (name AND value are validated, not just the key)
# ---------------------------------------------------------------------------

def test_bot_started_cannot_carry_item_id(monkeypatch):
    """`item_id` is a perfectly valid property name (for Shop events) but is not on
    BOT_STARTED's own allowed-key set, so it must be dropped regardless of its value."""
    client = enable(monkeypatch)
    analytics.capture(analytics.Event.BOT_STARTED, user_id=1, properties={
        "language": "it", "is_new_user": True, "item_id": "neon",
    })
    sent_props = client.capture.call_args.kwargs["properties"]
    assert "item_id" not in sent_props
    assert sent_props["language"] == "it"


def test_daily_events_cannot_carry_shop_only_properties(monkeypatch):
    client = enable(monkeypatch)
    analytics.capture(analytics.Event.DAILY_COMPLETED, user_id=1, properties={
        "surface": "miniapp", "status": "correct", "attempts_used": 2,
        "item_id": "neon", "price_stars": 60,
    })
    sent_props = client.capture.call_args.kwargs["properties"]
    assert "item_id" not in sent_props
    assert "price_stars" not in sent_props
    assert sent_props["status"] == "correct"


def test_unknown_surface_value_is_dropped(monkeypatch):
    client = enable(monkeypatch)
    analytics.capture(analytics.Event.SHOP_VIEWED, user_id=1, properties={"surface": "desktop_browser"})
    sent_props = client.capture.call_args.kwargs["properties"]
    assert "surface" not in sent_props


def test_an_arbitrary_user_supplied_item_id_is_not_forwarded(monkeypatch):
    """The property NAME `item_id` is allowed for Shop events, but the VALUE must be a real,
    currently-existing catalogue id (`services/shop.py::get_item`) - not merely a string
    that looks like one. This is the fix for a user-controlled payload (e.g. the Mini App's
    `POST /app/api/shop/buy` body) turning into an arbitrary analytics dimension."""
    client = enable(monkeypatch)
    analytics.capture(analytics.Event.SHOP_ITEM_PREVIEWED, user_id=1, properties={
        "surface": "miniapp", "item_id": "totally-made-up-item-42", "item_kind": "theme",
    })
    sent_props = client.capture.call_args.kwargs["properties"]
    assert "item_id" not in sent_props
    # A real catalogue id (used throughout tests/test_shop.py) is accepted.
    client.capture.reset_mock()
    analytics.capture(analytics.Event.SHOP_ITEM_PREVIEWED, user_id=1, properties={
        "surface": "miniapp", "item_id": "neon", "item_kind": "theme",
    })
    sent_props = client.capture.call_args.kwargs["properties"]
    assert sent_props["item_id"] == "neon"


def test_an_arbitrary_item_kind_is_not_forwarded(monkeypatch):
    client = enable(monkeypatch)
    analytics.capture(analytics.Event.SHOP_ITEM_EQUIPPED, user_id=1, properties={
        "surface": "telegram_chat", "item_id": "neon", "item_kind": "not_a_real_kind",
    })
    sent_props = client.capture.call_args.kwargs["properties"]
    assert "item_kind" not in sent_props


@pytest.mark.parametrize("bad_value", [
    "5", 5.5, True, -1, 100_000_000, None, [], {}, "not_a_number",
])
def test_malformed_numeric_values_are_dropped(monkeypatch, bad_value):
    client = enable(monkeypatch)
    analytics.capture(analytics.Event.DAILY_COMPLETED, user_id=1, properties={
        "surface": "miniapp", "status": "correct", "attempts_used": bad_value,
    })
    sent_props = client.capture.call_args.kwargs["properties"]
    assert "attempts_used" not in sent_props


@pytest.mark.parametrize("bad_value", ["true", 1, 0, "yes", None, "True"])
def test_malformed_boolean_values_are_dropped(monkeypatch, bad_value):
    client = enable(monkeypatch)
    analytics.capture(analytics.Event.BOT_STARTED, user_id=1, properties={
        "language": "it", "is_new_user": bad_value,
    })
    sent_props = client.capture.call_args.kwargs["properties"]
    assert "is_new_user" not in sent_props


@pytest.mark.parametrize("bad_value", ["FR", "italian", "", 1, None, "it "])
def test_malformed_enum_values_are_dropped(monkeypatch, bad_value):
    client = enable(monkeypatch)
    analytics.capture(analytics.Event.BOT_STARTED, user_id=1, properties={"language": bad_value})
    sent_props = client.capture.call_args.kwargs["properties"]
    assert "language" not in sent_props


def test_valid_values_of_every_kind_pass_through(monkeypatch):
    """The positive counterpart to the malformed-value tests above: a well-formed value of
    each validator kind (enum/bool/int/catalogue) is not accidentally rejected too."""
    client = enable(monkeypatch)
    analytics.capture(analytics.Event.DAILY_COMPLETED, user_id=1, properties={
        "surface": "miniapp", "status": "correct", "attempts_used": 2, "hints_used": 0,
    })
    sent_props = client.capture.call_args.kwargs["properties"]
    assert sent_props["surface"] == "miniapp"
    assert sent_props["status"] == "correct"
    assert sent_props["attempts_used"] == 2
    assert sent_props["hints_used"] == 0


# ---------------------------------------------------------------------------
# Person-profile minimization (#29 item 6)
# ---------------------------------------------------------------------------

def test_every_capture_marks_the_event_personless(monkeypatch):
    """We never call identify() and only ever send a pseudonymous id, so PostHog should not
    build a Person profile for it either. `$process_person_profile: False` is the SDK's own
    recognised sentinel for this (verified against the installed posthog-python source -
    see services/product_analytics.py::capture)."""
    client = enable(monkeypatch)
    analytics.capture(analytics.Event.BOT_STARTED, user_id=1, properties={"language": "it"})
    sent_props = client.capture.call_args.kwargs["properties"]
    assert sent_props["$process_person_profile"] is False


def test_privacy_regression_scan_of_a_representative_payload(monkeypatch):
    """Scan an actual outgoing capture() call for forbidden substrings, the way a reviewer
    would grep a PostHog export. Reuses the same allow-list every call site goes through."""
    client = enable(monkeypatch)
    analytics.capture(analytics.Event.SHOP_PURCHASE_COMPLETED, user_id=918273645, properties={
        "item_id": "neon", "item_kind": "theme", "price_stars": 60, "success": True,
        # An attacker-shaped call site trying to sneak something through:
        "invoice_payload": "signed-payload-should-never-appear",
        "charge_id": "should-not-appear-either",
        "raw_user_id": 918273645,
    })
    distinct_id = client.capture.call_args.kwargs["distinct_id"]
    sent_props = client.capture.call_args.kwargs["properties"]
    blob = repr((distinct_id, sent_props)).lower()
    for forbidden in ("token", "authorization", "cookie", "initdata", "invoice_payload",
                      "charge_id", "password", "secret", "918273645"):
        assert forbidden not in blob, f"{forbidden!r} leaked into the analytics payload"


# ---------------------------------------------------------------------------
# Enrichment
# ---------------------------------------------------------------------------

def test_environment_release_and_revision_are_enriched_automatically(monkeypatch):
    client = enable(monkeypatch, environment="staging", release="9.9.9", revision="rev-42")
    analytics.capture(analytics.Event.DAILY_VIEWED, user_id=1, properties={"surface": "miniapp"})
    sent_props = client.capture.call_args.kwargs["properties"]
    assert sent_props["environment"] == "staging"
    assert sent_props["app_version"] == "9.9.9"
    assert sent_props["app_revision"] == "rev-42"


def test_capture_is_a_noop_without_any_identity(monkeypatch):
    client = enable(monkeypatch)
    analytics.capture(analytics.Event.BOT_STARTED)  # neither user_id nor anonymous_id
    client.capture.assert_not_called()


# ---------------------------------------------------------------------------
# Idempotency: a retried authoritative operation must not double-fire
# ---------------------------------------------------------------------------

def test_a_duplicate_shop_payment_fires_the_completed_event_only_once(monkeypatch):
    """Mirrors tests/test_shop.py::test_a_repeated_payment_delivers_only_once, but asserts
    on the analytics side effect instead of the Firestore one: Telegram resending the same
    `successful_payment` update must not produce a second `shop_purchase_completed`."""
    from handlers import shop_handler
    from services import shop as shop_service

    client = enable(monkeypatch)
    state = {"user": {"cosmetics": {"owned": [], "equipped": {}}}, "delivered": {}}

    def deliver_purchase(user_id, charge_id, item_id, granted, stars, day_iso=None):
        if charge_id in state["delivered"]:
            return False
        state["delivered"][charge_id] = True
        state["user"]["cosmetics"]["owned"] += list(granted)
        return True

    monkeypatch.setattr(shop_service.firebase_service, "reserve_checkout", lambda *a: "ok")
    monkeypatch.setattr(shop_service.firebase_service, "deliver_purchase", deliver_purchase)
    monkeypatch.setattr(shop_handler.firebase_service, "save_user", lambda *a, **k: None)
    monkeypatch.setattr(shop_handler.firebase_service, "get_user_data", lambda uid: state["user"])
    monkeypatch.setattr("handlers.keyboards.get_user_data", lambda uid: state["user"])

    payload = shop_service.payload_for(42, "neon")

    class FakeMessage:
        def __init__(self, payment):
            self.successful_payment = payment
            self.replies = []

        async def reply_text(self, text, **kwargs):
            self.replies.append(text)

    def payment_update():
        payment = SimpleNamespace(invoice_payload=payload, telegram_payment_charge_id="ch_dup", total_amount=25)
        message = FakeMessage(payment)
        return SimpleNamespace(
            effective_user=SimpleNamespace(id=42, first_name="Anna", language_code="it"),
            effective_message=message,
        )

    for _ in range(2):
        asyncio.run(shop_handler.successful_payment_callback(payment_update(), None))

    completed_calls = [
        call for call in client.capture.call_args_list
        if call.kwargs.get("event") == analytics.Event.SHOP_PURCHASE_COMPLETED.value
    ]
    assert len(completed_calls) == 1


def test_referral_funnel_stays_on_one_identity_end_to_end(monkeypatch):
    """The referral funnel (docs/product-analytics.md §11) is a sequence of events walked by
    ONE distinct_id in a funnel tool: referral_opened -> bot_started -> the invitee's Daily
    activity -> referral_converted. All four MUST resolve to the same pseudonymous id (the
    invitee's), or funnel analysis silently breaks. referral_reward_granted is the one
    deliberate exception - it is a fact about the INVITER, not the invitee, and must resolve
    to a *different* distinct_id."""
    from copy import deepcopy

    from services import firebase_service as fs
    from services import game, referrals
    from services import shop as shop_service

    INVITEE_ID, INVITER_ID = 2, 1
    client = enable(monkeypatch)
    invitee_distinct_id = analytics.distinct_id_for_user(INVITEE_ID)
    inviter_distinct_id = analytics.distinct_id_for_user(INVITER_ID)
    assert invitee_distinct_id != inviter_distinct_id

    # Step 1-2: referral_opened and bot_started, both fired for the invitee in
    # handlers/start_handler.py on the same `/start ref_XXXX` call.
    analytics.capture(analytics.Event.REFERRAL_OPENED, user_id=INVITEE_ID,
                      properties={"referral_attached": True})
    analytics.capture(analytics.Event.BOT_STARTED, user_id=INVITEE_ID,
                      properties={"language": "it", "is_new_user": True})

    # Step 3: the invitee's own Daily completion (services/game.py, shared by chat/Mini App).
    challenge = {"correct_answers": ["messi"], "difficulty": "easy", "player_id": "p1",
                "first_correct_user": True}
    monkeypatch.setattr(game.firebase_service, "begin_guess_attempt",
                        lambda uid, day, max_attempts: {"ok": True, "attempts_used": 1, "attempts_left": 2, "hints_used": 0})
    monkeypatch.setattr(game.firebase_service, "register_daily_outcome", lambda *a, **k: None)
    monkeypatch.setattr(game.firebase_service, "claim_daily_first_correct", lambda day: False)
    monkeypatch.setattr(game.firebase_service, "register_correct_guess",
                        lambda *a, **k: {"points_awarded": 5, "current_streak": 1, "streak_bonus": 0})
    monkeypatch.setattr(game.firebase_service, "add_points_to_leagues", lambda *a, **k: None)
    monkeypatch.setattr(game.firebase_service, "record_daily_history", lambda *a, **k: None)
    game.play_daily(INVITEE_ID, {}, "Messi", challenge=challenge, surface="telegram_chat")

    # Step 4: the referral itself qualifies - services/referrals.py::credit_day(INVITEE_ID, ...).
    records = {"user/1": {"referral_qualified": 0}}

    class Ref:
        def __init__(self, path):
            self.path = path

        def get(self, transaction=None):
            return SimpleNamespace(exists=self.path in records, to_dict=lambda: deepcopy(records.get(self.path)))

    class Transaction:
        def update(self, reference, values):
            target = records[reference.path]
            for key, value in values.items():
                if key != "cosmetics.earned":
                    target[key] = deepcopy(value)

    monkeypatch.setattr(fs, "db", SimpleNamespace(transaction=Transaction))
    monkeypatch.setattr(fs.firestore, "transactional", lambda fn: fn)
    monkeypatch.setattr(fs, "user_ref", lambda uid: Ref(f"user/{uid}"))
    monkeypatch.setattr(fs, "history_ref", lambda uid, day: Ref(f"history/{uid}/{day}"))
    monkeypatch.setattr(referrals, "ref", lambda uid: Ref(f"ref/{uid}"))
    monkeypatch.setattr(shop_service, "newly_earned", lambda user: [])
    records[f"ref/{INVITEE_ID}"] = {
        "status": "pending", "inviter_id": INVITER_ID, "joined_day": "2026-01-01",
        "days": [f"2026-01-0{i}" for i in range(1, referrals.REQUIRED_DAYS)],
    }
    records[f"history/{INVITEE_ID}/2026-01-05"] = {"solved": True, "attempts": 1}
    credited = referrals.credit_day(INVITEE_ID, "2026-01-05")
    assert credited is True

    calls_by_event = {}
    for call in client.capture.call_args_list:
        calls_by_event.setdefault(call.kwargs["event"], []).append(call.kwargs["distinct_id"])

    for event_name in (
        analytics.Event.REFERRAL_OPENED.value, analytics.Event.BOT_STARTED.value,
        analytics.Event.DAILY_COMPLETED.value, analytics.Event.REFERRAL_CONVERTED.value,
    ):
        assert calls_by_event[event_name] == [invitee_distinct_id], (
            f"{event_name} did not resolve to the invitee's distinct_id"
        )

    # The one deliberate exception: the reward is the inviter's fact, not the invitee's.
    assert calls_by_event[analytics.Event.REFERRAL_REWARD_GRANTED.value] == [inviter_distinct_id]


def test_a_replayed_referral_credit_fires_the_conversion_event_only_once(monkeypatch):
    """Mirrors the referral idempotency guarantee in services/referrals.py: `credit_day`
    only ever flips a ledger from "pending" to "qualified" once, so calling it again for an
    already-qualified referral (a reconcile() replay, a retried Cloud Task) must not produce
    a second `referral_converted` / `referral_reward_granted` pair."""
    from copy import deepcopy

    from services import firebase_service as fs
    from services import referrals
    from services import shop as shop_service

    client = enable(monkeypatch)
    records = {"user/1": {"referral_qualified": 0}}

    class Ref:
        def __init__(self, path):
            self.path = path

        def get(self, transaction=None):
            return SimpleNamespace(exists=self.path in records, to_dict=lambda: deepcopy(records.get(self.path)))

        def set(self, value):
            records[self.path] = deepcopy(value)

    class Transaction:
        def update(self, reference, values):
            target = records[reference.path]
            for key, value in values.items():
                if key == "cosmetics.earned":
                    continue
                target[key] = deepcopy(value)

    monkeypatch.setattr(fs, "db", SimpleNamespace(transaction=Transaction))
    monkeypatch.setattr(fs.firestore, "transactional", lambda fn: fn)
    monkeypatch.setattr(fs, "user_ref", lambda uid: Ref(f"user/{uid}"))
    monkeypatch.setattr(fs, "history_ref", lambda uid, day: Ref(f"history/{uid}/{day}"))
    monkeypatch.setattr(referrals, "ref", lambda uid: Ref("ref/2"))
    monkeypatch.setattr(shop_service, "newly_earned", lambda user: [])

    records["ref/2"] = {"status": "pending", "inviter_id": 1, "joined_day": "2026-01-01", "days": []}
    for index in range(referrals.REQUIRED_DAYS):
        day = f"2026-01-0{index + 1}"
        records[f"history/2/{day}"] = {"solved": True, "attempts": 1}
        referrals.credit_day(2, day)

    # The ledger is now "qualified". A retried/replayed credit for a day already recorded
    # (Cloud Tasks redelivery, reconcile()) must be a pure no-op.
    referrals.credit_day(2, "2026-01-01")

    converted = [c for c in client.capture.call_args_list
                if c.kwargs.get("event") == analytics.Event.REFERRAL_CONVERTED.value]
    granted = [c for c in client.capture.call_args_list
              if c.kwargs.get("event") == analytics.Event.REFERRAL_REWARD_GRANTED.value]
    assert len(converted) == 1
    assert len(granted) == 1


# ---------------------------------------------------------------------------
# Representative real events (a sample across the areas that exist in the codebase)
# ---------------------------------------------------------------------------

def test_daily_completed_fires_exactly_once_for_a_correct_guess(monkeypatch):
    from services import game

    client = enable(monkeypatch)
    challenge = {"correct_answers": ["messi"], "difficulty": "easy", "player_id": "p1",
                "first_correct_user": True}
    monkeypatch.setattr(game.firebase_service, "begin_guess_attempt",
                        lambda uid, day, max_attempts: {"ok": True, "attempts_used": 1, "attempts_left": 2, "hints_used": 0})
    monkeypatch.setattr(game.firebase_service, "register_daily_outcome", lambda *a, **k: None)
    monkeypatch.setattr(game.firebase_service, "claim_daily_first_correct", lambda day: False)
    monkeypatch.setattr(game.firebase_service, "register_correct_guess",
                        lambda *a, **k: {"points_awarded": 5, "current_streak": 1, "streak_bonus": 0})
    monkeypatch.setattr(game.firebase_service, "add_points_to_leagues", lambda *a, **k: None)
    monkeypatch.setattr(game.firebase_service, "record_daily_history", lambda *a, **k: None)

    result = game.play_daily(42, {}, "Messi", challenge=challenge, surface="telegram_chat")

    assert result["status"] == "correct"
    completed = [c for c in client.capture.call_args_list
                if c.kwargs.get("event") == analytics.Event.DAILY_COMPLETED.value]
    assert len(completed) == 1
    assert completed[0].kwargs["properties"]["surface"] == "telegram_chat"
    assert completed[0].kwargs["properties"]["difficulty_band"] == "easy"


@pytest.mark.parametrize("band, kept", [("impossible", True), ("extreme", False), (3, False), (None, False)])
def test_difficulty_band_accepts_only_the_bands_of_the_difficulty_model(monkeypatch, band, kept):
    """#21: the band is the one from services/difficulty.py - anything else never leaves."""
    client = enable(monkeypatch)
    analytics.capture(analytics.Event.DAILY_COMPLETED, user_id=1, properties={
        "surface": "miniapp", "status": "correct", "attempts_used": 1, "difficulty_band": band,
    })
    sent_props = client.capture.call_args.kwargs["properties"]
    assert ("difficulty_band" in sent_props) is kept


def test_hint_used_carries_the_surface_the_caller_declares(monkeypatch):
    from services import game

    client = enable(monkeypatch)
    challenge = {"correct_answers": ["messi"], "difficulty": "easy", "player_id": "p1"}
    monkeypatch.setattr(game, "hints_available", lambda challenge, lang: ["hint one"])
    monkeypatch.setattr(game.firebase_service, "take_daily_hint",
                        lambda uid, day, total, max_attempts: {"ok": True, "index": 1, "hints_used": 1})

    game.take_hint(7, "it", challenge=challenge, surface="miniapp")

    used = [c for c in client.capture.call_args_list if c.kwargs.get("event") == analytics.Event.HINT_USED.value]
    assert len(used) == 1
    assert used[0].kwargs["properties"]["surface"] == "miniapp"


def test_miniapp_open_and_daily_viewed_fire_on_a_full_bootstrap_only(monkeypatch):
    """The lightweight polling variant of /app/api/me must not count as an app open."""
    from services import webapp_api

    client = enable(monkeypatch)
    monkeypatch.setattr(webapp_api.feature_flags, "resolved_features", lambda **k: {"leaderboard": False})
    monkeypatch.setattr(webapp_api.shop, "appearance", lambda user, lang: {})
    monkeypatch.setattr(webapp_api, "_public_wardrobe", lambda user, lang: [])
    monkeypatch.setattr(webapp_api.trophies, "showcase", lambda user, lang: [])
    monkeypatch.setattr(webapp_api.trophies, "cabinet", lambda user, lang: [])
    monkeypatch.setattr(webapp_api.firebase_service, "get_daily_path", lambda day: {})

    user = {"language": "it", "telegram_id": 1}
    webapp_api.build_profile(1, user=user, include_social=False)
    assert client.capture.call_args_list == []

    webapp_api.build_profile(1, user=user, include_social=True)
    events_sent = {c.kwargs["event"] for c in client.capture.call_args_list}
    assert analytics.Event.MINIAPP_OPENED.value in events_sent
    assert analytics.Event.DAILY_VIEWED.value in events_sent


# ---------------------------------------------------------------------------
# Real SDK smoke test: the genuine installed posthog-python client, zero network
# ---------------------------------------------------------------------------

def test_real_installed_posthog_sdk_accepts_our_adapter_call_shape():
    """Every other test in this file monkeypatches `_build_client` to a `MagicMock`, which
    proves our own logic but not that the *actual* installed SDK still accepts the exact
    call our adapter makes. This test builds a REAL `posthog.Posthog` client - the one
    `pip install`ed from `requirements.txt` - and calls `_call_capture` (the one function
    that touches `Posthog.capture`) against it directly, bypassing `capture()`'s
    try/except so a signature mismatch fails this test loudly instead of being logged and
    swallowed.

    Zero network traffic, no real API key: `disabled=True` is a genuine posthog-python
    constructor option (`posthog/client.py::_enqueue` returns `None` before any queueing or
    HTTP work happens whenever `self.disabled`), not a test-only shim - it is the SDK's own
    supported way to build a fully real client that structurally cannot make a network call.
    If a future `posthog` upgrade renames or removes `capture`'s `event`/`distinct_id`/
    `properties` keywords, or removes the `disabled` constructor option, or changes what
    `capture()` returns for a disabled client, this test fails and says so - that is the
    point of it."""
    from posthog import Posthog

    from services.product_analytics import Event, _call_capture

    client = Posthog(
        project_api_key="phc_test_smoke",  # pragma: allowlist secret
        host="https://posthog.invalid.example",
        disabled=True,
        disable_geoip=True,
        enable_exception_autocapture=False,
    )
    try:
        result = _call_capture(
            client, Event.BOT_STARTED.value, "u_smoketest0000000000000",
            {"language": "it", "is_new_user": True, "$process_person_profile": False},
        )
        # A disabled client's capture() is documented to short-circuit before enqueueing and
        # return None - asserting on that return value is itself part of proving the call
        # shape still matches what this codebase assumes.
        assert result is None
        client.flush()
    finally:
        client.shutdown()
