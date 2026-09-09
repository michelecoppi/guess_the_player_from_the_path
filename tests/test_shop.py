"""Il negozio: cosa si puo' comprare, cosa non si puo', e cosa non deve mai finire in vendita.

Il test che vale piu' di tutti e' `test_nothing_on_sale_touches_the_game`: il negozio esiste a
patto che quello che vende non cambi la partita. Un oggetto che desse un tentativo in piu'
non si noterebbe leggendo data/shop.json - si noterebbe in classifica, un mese dopo.

Il secondo che conta e' `test_a_repeated_payment_delivers_only_once`: Telegram rispedisce
l'update se il webhook non risponde in tempo, e una consegna doppia lascerebbe due righe nel
registro da cui si rimborsa.
"""
import asyncio
import json
from types import SimpleNamespace

import pytest

from handlers import shop_handler
from services import shop
from services.share import share_text

FREE = {"theme": "notturno", "frame": "cornice_nessuna", "title": "titolo_nessuno",
        "badge": "distintivo_nessuno", "squares": "quadratini_classici"}


def user_with(*owned, **worn):
    return {"cosmetics": {"owned": list(owned), "equipped": dict(worn)}}


# ---------------------------------------------------------------------------
# Il catalogo
# ---------------------------------------------------------------------------

def test_nothing_on_sale_touches_the_game():
    """La regola del negozio, scritta come test.

    Non si controlla una lista di parole vietate a caso: si controlla che uno `style` non
    contenga nessuna delle chiavi con cui il gioco misura una partita. Se un giorno qualcuno
    aggiunge "un tema che da' un tentativo in piu'", il modo piu' naturale di scriverlo e'
    esattamente una di queste chiavi."""
    forbidden = {"points", "attempts", "hints", "bonus", "streak", "multiplier", "extra_attempts"}
    for item in shop.all_items():
        keys = set(item.get("style") or {}) | set(item)
        assert not (keys & forbidden), f"{item['id']} vende un vantaggio, non un colore"


def test_every_item_is_well_formed():
    seen = set()
    for item in shop.all_items():
        assert item["id"] not in seen, f"id doppio: {item['id']}"
        seen.add(item["id"])
        assert item["kind"] in shop.KINDS or item["kind"] == "bundle"
        assert isinstance(item.get("price"), int) and item["price"] >= 0
        if item["price"]:
            assert shop.MIN_STARS <= item["price"] <= shop.MAX_STARS


def test_every_slot_has_exactly_one_free_default():
    """Senza un gratuito per tipo ci sarebbe uno slot vuoto da gestire come caso speciale in
    ogni punto che disegna un utente."""
    for kind in shop.KINDS:
        free = [item for item in shop.items_of_kind(kind) if shop.is_free(item)]
        assert len(free) == 1, f"{kind}: {len(free)} oggetti gratuiti"


def test_bundles_only_grant_items_that_exist():
    for bundle in shop.bundles():
        assert bundle["grants"], f"{bundle['id']} non consegna niente"
        for item_id in bundle["grants"]:
            assert shop.get_item(item_id), f"{bundle['id']} promette {item_id}, che non esiste"


def test_a_bundle_is_either_cheaper_or_exclusive():
    """Un pacchetto deve dare una ragione per comprarlo al posto dei pezzi singoli, e le
    ragioni ammesse sono due: costa meno della somma, oppure contiene qualcosa che da solo
    non si vende (il Pacchetto Sostenitore, che non e' uno sconto: e' un'offerta a cui
    corrispondono un titolo e un distintivo che non ha nessun altro).

    Un pacchetto che non e' ne' l'uno ne' l'altro e' solo un modo piu' scomodo di comprare le
    stesse cose."""
    for bundle in shop.bundles():
        pieces = sum(shop.get_item(one)["price"] for one in bundle["grants"])
        exclusive = [one for one in bundle["grants"] if shop.get_item(one).get("locked")]
        assert bundle["price"] < pieces or exclusive, (
            f"{bundle['id']} costa {bundle['price']} contro {pieces} e non ha niente di esclusivo"
        )


def test_locked_items_are_only_reachable_inside_a_bundle():
    locked = [item["id"] for item in shop.all_items() if item.get("locked")]
    inside = {one for bundle in shop.bundles() for one in bundle["grants"]}
    for item_id in locked:
        assert item_id in inside, f"{item_id} non si compra e nessun pacchetto lo contiene"
        assert shop.purchase_status({}, item_id) == "not_for_sale"


def test_every_item_is_translated_into_the_three_languages():
    """Stessa regola dei messaggi del bot (tests/test_i18n_keys.py): una descrizione solo in
    italiano diventa una riga italiana in mezzo a un negozio inglese."""
    for item in shop.all_items():
        for lang in ("es", "en"):
            name, description = shop.localize(item, lang)
            assert name and name != item["id"], f"{item['id']}: manca il nome in {lang}"
            assert description, f"{item['id']}: manca la descrizione in {lang}"


def test_the_catalogue_file_is_valid_json():
    with open(shop.SHOP_PATH, encoding="utf-8") as f:
        assert json.load(f)["items"]


# ---------------------------------------------------------------------------
# Cosa ha addosso un utente
# ---------------------------------------------------------------------------

def test_a_brand_new_user_wears_the_free_defaults():
    assert shop.equipped({}) == FREE
    assert shop.equipped(None) == FREE


def test_the_free_items_are_owned_without_being_written_anywhere():
    """I gratuiti non stanno sul documento utente: se ci stessero, aggiungerne uno vorrebbe
    dire ripassare su tutti gli utenti registrati."""
    assert shop.owned_ids({}) == shop.free_ids()
    assert "notturno" in shop.owned_ids({})


def test_something_worn_but_no_longer_owned_falls_back_to_the_default():
    """Succede dopo un rimborso: l'oggetto viene ritirato mentre l'utente ce l'ha addosso.
    Senza questo ripiego la pagina disegnerebbe un tema che non esiste piu'."""
    without = user_with(theme="neon")            # equipaggiato ma non posseduto
    assert shop.equipped(without)["theme"] == "notturno"

    with_it = user_with("neon", theme="neon")
    assert shop.equipped(with_it)["theme"] == "neon"


def test_an_item_from_the_wrong_slot_is_ignored():
    user = user_with("distintivo_diamante", theme="distintivo_diamante")
    assert shop.equipped(user)["theme"] == "notturno"


# ---------------------------------------------------------------------------
# Comprare
# ---------------------------------------------------------------------------

def test_what_can_and_cannot_be_bought():
    empty = {}
    assert shop.purchase_status(empty, "neon") == "ok"
    assert shop.purchase_status(user_with("neon"), "neon") == "already_owned"
    assert shop.purchase_status(empty, "notturno") == "not_for_sale"     # gratuito
    assert shop.purchase_status(empty, "non_esiste") == "unknown_item"


def test_a_bundle_stays_on_sale_until_the_last_piece_is_missing():
    """Chi ha gia' il tema Neon puo' comprare il Pacchetto Neon per gli altri tre pezzi. Se
    li ha tutti no: incassare per non consegnare niente sarebbe una fregatura."""
    pieces = shop.get_item("pacchetto_neon")["grants"]
    assert shop.purchase_status(user_with(pieces[0]), "pacchetto_neon") == "ok"
    assert shop.purchase_status(user_with(*pieces), "pacchetto_neon") == "already_owned"


def test_the_payload_survives_the_round_trip():
    payload = shop.payload_for(42, "neon")
    assert shop.parse_payload(payload) == ("neon", 42)


def test_a_payload_that_is_not_ours_is_refused_without_raising():
    assert shop.parse_payload("") == (None, None)
    assert shop.parse_payload("qualcosa:altro") == (None, None)
    assert shop.parse_payload("cosmetic:neon:non_un_numero") == (None, None)


def test_what_can_and_cannot_be_worn():
    assert shop.equip_status(user_with("neon"), "neon") == "ok"
    assert shop.equip_status({}, "neon") == "not_owned"
    assert shop.equip_status({}, "notturno") == "ok"                     # gratuito
    assert shop.equip_status({}, "pacchetto_neon") == "not_owned"
    assert shop.equip_status({}, "non_esiste") == "unknown_item"


# ---------------------------------------------------------------------------
# La vetrina
# ---------------------------------------------------------------------------

def test_the_shop_window_never_shows_a_locked_item_on_its_own():
    catalogue = shop.catalogue_for({}, "en")
    shown = {item["id"] for section in catalogue["sections"] for item in section["items"]}
    assert "sostenitore_titolo" not in shown
    assert "distintivo_stella" not in shown


def test_the_shop_window_says_what_is_already_owned_and_worn():
    user = user_with("neon", theme="neon")
    catalogue = shop.catalogue_for(user, "it")
    themes = next(s for s in catalogue["sections"] if s["kind"] == "theme")
    neon = next(item for item in themes["items"] if item["id"] == "neon")
    assert neon["owned"] and neon["equipped"]

    other = next(item for item in themes["items"] if item["id"] == "ghiaccio")
    assert not other["owned"] and not other["equipped"]


# ---------------------------------------------------------------------------
# I quadratini comprati finiscono nella card da condividere
# ---------------------------------------------------------------------------

def test_bought_squares_replace_the_symbols_but_not_the_score():
    user = user_with("quadratini_semaforo", squares="quadratini_semaforo")
    text = share_text("it", 142, 2, 3, solved=True, symbols=shop.squares_symbols(user))
    assert "🔴🟢⚫" in text
    assert "2/3" in text          # il punteggio resta leggibile da chiunque


def test_a_two_codepoint_symbol_does_not_shorten_the_card():
    """I cuori usano ❤️, che in Python e' lungo due caratteri: contando `len()` invece dei
    tentativi la card sarebbe uscita piu' corta di una classica, e in un gruppo le due righe
    non si sarebbero piu' potute confrontare."""
    user = user_with("quadratini_cuori", squares="quadratini_cuori")
    correct, wrong, unused = shop.squares_symbols(user)
    from services.share import result_squares

    row = result_squares(1, 3, solved=True, symbols=(correct, wrong, unused))
    assert row == correct + unused * 2


def test_without_a_bought_set_the_card_is_the_one_it_has_always_been():
    assert share_text("it", 1, 1, 3) == share_text("it", 1, 1, 3, symbols=shop.squares_symbols({}))


# ---------------------------------------------------------------------------
# Il pagamento, dai due lati che contano
# ---------------------------------------------------------------------------

class FakeMessage:
    def __init__(self, payment=None):
        self.successful_payment = payment
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)


def payment_update(payload, charge_id="ch_1", stars=25, user_id=42):
    payment = SimpleNamespace(
        invoice_payload=payload, telegram_payment_charge_id=charge_id, total_amount=stars,
    )
    message = FakeMessage(payment)
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id, first_name="Anna", language_code="it"),
        effective_message=message,
    ), message


@pytest.fixture
def firestore(monkeypatch):
    """Sostituto in memoria delle sole scritture che il negozio fa davvero."""
    state = {"user": {"cosmetics": {"owned": [], "equipped": {}}}, "delivered": {}, "saved": 0}

    def deliver_purchase(user_id, charge_id, item_id, granted, stars, day_iso=None):
        if charge_id in state["delivered"]:
            return False
        state["delivered"][charge_id] = {"item": item_id, "granted": list(granted), "stars": stars}
        state["user"]["cosmetics"]["owned"] += list(granted)
        return True

    def save_user(user_id, first_name, language):
        state["saved"] += 1

    monkeypatch.setattr(shop.firebase_service, "reserve_checkout", lambda *args: "ok")
    monkeypatch.setattr(shop.firebase_service, "deliver_purchase", deliver_purchase)
    monkeypatch.setattr(shop_handler.firebase_service, "save_user", save_user)
    monkeypatch.setattr(shop_handler.firebase_service, "get_user_data", lambda uid: state["user"])
    monkeypatch.setattr("handlers.keyboards.get_user_data", lambda uid: state["user"])
    return state


def test_a_payment_delivers_every_piece_of_a_bundle(firestore):
    update, message = payment_update(shop.payload_for(42, "pacchetto_neon"), stars=60)
    asyncio.run(shop_handler.successful_payment_callback(update, None))

    delivered = firestore["delivered"]["ch_1"]
    assert delivered["granted"] == shop.get_item("pacchetto_neon")["grants"]
    assert delivered["stars"] == 60
    assert len(message.replies) == 1


def test_a_repeated_payment_delivers_only_once(firestore):
    """Telegram rispedisce l'update se il webhook non ha risposto in tempo. La seconda volta
    non si consegna e non si ringrazia: un secondo "grazie" farebbe pensare a un secondo
    addebito."""
    payload = shop.payload_for(42, "neon")
    for _ in range(2):
        update, message = payment_update(payload)
        asyncio.run(shop_handler.successful_payment_callback(update, None))

    assert firestore["user"]["cosmetics"]["owned"] == ["neon"]
    assert message.replies == []


def test_a_payment_with_an_unknown_payload_is_logged_not_swallowed(firestore):
    update, message = payment_update("cosmetic:sparito:42")
    asyncio.run(shop_handler.successful_payment_callback(update, None))

    assert firestore["delivered"] == {}
    assert message.replies, "l'utente ha pagato: deve almeno sapere che qualcosa non va"


def buttons(keyboard):
    return [button.text for row in keyboard.inline_keyboard for button in row]


@pytest.mark.parametrize("lang", ["it", "es", "en"])
def test_every_screen_of_the_shop_can_be_drawn_in_every_language(lang):
    """Rende ogni schermata in tutte e tre le lingue.

    Non e' un test estetico: le viste pescano una decina di chiavi da services/i18n.py, e una
    chiave scritta male esce come eccezione in faccia a chi apre il negozio, non come una
    riga storta."""
    user = user_with("terra_rossa", theme="terra_rossa")

    text, keyboard = shop_handler._main_view(lang, user)
    # Gli scaffali piu' i pacchetti. Il bottone verso termini e privacy c'e' solo con
    # PUBLIC_BASE_URL configurata, quindi si conta il minimo e non il totale esatto: senza,
    # questo test passerebbe sulla macchina di chi sviluppa e fallirebbe su quella di chi ha
    # l'ambiente completo.
    assert text and len(buttons(keyboard)) >= len(shop.KINDS) + 1

    for kind in list(shop.KINDS) + ["bundle"]:
        text, keyboard = shop_handler._section_view(lang, user, kind)
        assert text and buttons(keyboard)

    for item in shop.all_items():
        text, keyboard = shop_handler._item_view(lang, user, item)
        assert text and buttons(keyboard)


def test_the_screen_offers_the_one_action_that_makes_sense():
    user = user_with("terra_rossa", theme="terra_rossa")

    _, worn = shop_handler._item_view("it", user, shop.get_item("terra_rossa"))
    assert not [b for b in buttons(worn) if "Indossa" in b]           # ce l'ha gia' addosso

    _, owned = shop_handler._item_view("it", user_with("terra_rossa"), shop.get_item("terra_rossa"))
    assert [b for b in buttons(owned) if "Indossa" in b]

    _, on_sale = shop_handler._item_view("it", user, shop.get_item("neon"))
    assert [b for b in buttons(on_sale) if "25" in b]


class FakeBot:
    def __init__(self):
        self.invoices = []

    async def send_invoice(self, **kwargs):
        self.invoices.append(kwargs)


class FakeQuery:
    def __init__(self, data, user_id=42):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id, language_code="it")
        self.message = SimpleNamespace(chat_id=7)
        self.answers = []
        self.edits = []

    async def answer(self, text=None, **kwargs):
        self.answers.append(text)

    async def edit_message_text(self, text, **kwargs):
        self.edits.append(text)


def callback_update(query):
    return SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=query.from_user.id, language_code="it"),
    )


def test_the_invoice_carries_the_price_from_the_catalogue(firestore):
    """Il prezzo non arriva mai da fuori: se lo decidesse chi preme il bottone, la collezione
    completa si comprerebbe per una Stella."""
    bot = FakeBot()
    query = FakeQuery("shop_buy_collezione_completa")
    asyncio.run(shop_handler.shop_callback(callback_update(query), SimpleNamespace(bot=bot)))

    invoice = bot.invoices[0]
    assert invoice["currency"] == "XTR"
    assert invoice["prices"][0].amount == shop.get_item("collezione_completa")["price"]
    assert shop.parse_payload(invoice["payload"]) == ("collezione_completa", 42)
    assert shop.payment_quote(invoice["payload"])["price"] == 220
    # Le Stelle non passano da un fornitore esterno: il token vuoto e' la configurazione giusta.
    assert invoice["provider_token"] == ""


def test_nothing_is_invoiced_for_something_already_owned(firestore):
    firestore["user"]["cosmetics"]["owned"] = ["neon"]
    bot = FakeBot()
    query = FakeQuery("shop_buy_neon")
    asyncio.run(shop_handler.shop_callback(callback_update(query), SimpleNamespace(bot=bot)))

    assert bot.invoices == []
    assert query.answers and query.answers[0]


def test_wearing_something_writes_it_and_redraws_the_card(firestore, monkeypatch):
    written = {}
    monkeypatch.setattr(
        shop.firebase_service, "equip_cosmetic",
        lambda user_id, kind, item_id: written.update({"kind": kind, "item": item_id}),
    )
    firestore["user"]["cosmetics"]["owned"] = ["neon"]

    query = FakeQuery("shop_equip_neon")
    asyncio.run(shop_handler.shop_callback(callback_update(query), None))

    assert written == {"kind": "theme", "item": "neon"}
    assert query.edits, "la scheda deve tornare indietro aggiornata"


def test_you_cannot_wear_what_you_have_not_bought(firestore, monkeypatch):
    monkeypatch.setattr(
        shop.firebase_service, "equip_cosmetic",
        lambda *args: pytest.fail("non doveva scrivere niente"),
    )
    query = FakeQuery("shop_equip_neon")
    asyncio.run(shop_handler.shop_callback(callback_update(query), None))

    assert query.answers and query.answers[0]
    assert query.edits == []


class FakePreCheckout:
    def __init__(self, payload, user_id=42):
        self.invoice_payload = payload
        self.id = "checkout_1"
        self.currency = "XTR"
        self.total_amount = 25
        self.from_user = SimpleNamespace(id=user_id, language_code="it")
        self.answers = []

    async def answer(self, ok=None, error_message=None, **kwargs):
        self.answers.append((ok, error_message))


def precheckout_update(query):
    return SimpleNamespace(
        pre_checkout_query=query,
        effective_user=SimpleNamespace(id=query.from_user.id, language_code="it"),
    )


def test_the_last_chance_to_say_no_is_taken_when_the_item_is_already_owned(firestore):
    firestore["user"]["cosmetics"]["owned"] = ["neon"]
    query = FakePreCheckout(shop.payload_for(42, "neon"))
    asyncio.run(shop_handler.precheckout_callback(precheckout_update(query), None))

    ok, error = query.answers[0]
    assert ok is False and error


def test_a_precheckout_for_someone_else_is_refused(firestore):
    """Il payload dice di chi era la fattura: se non e' di chi sta pagando, e' una fattura
    girata a un altro, e quello che ha comprato non lo riceverebbe lui."""
    query = FakePreCheckout(shop.payload_for(99, "neon"), user_id=42)
    asyncio.run(shop_handler.precheckout_callback(precheckout_update(query), None))

    assert query.answers[0][0] is False


def test_a_regular_purchase_passes_the_precheckout(firestore):
    query = FakePreCheckout(shop.payload_for(42, "neon"))
    asyncio.run(shop_handler.precheckout_callback(precheckout_update(query), None))

    assert query.answers[0] == (True, None)


# ---------------------------------------------------------------------------
# Rimborso
# ---------------------------------------------------------------------------

def refund_update(user_id=42):
    message = FakeMessage()
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id, first_name="Anna", language_code="it"),
        message=message,
        effective_message=message,
    ), message


@pytest.fixture
def refundable(monkeypatch):
    """Un acquisto rimborsabile, con Telegram e Firestore finti."""
    state = {
        "purchase": {"charge_id": "ch_1", "user_id": 7, "item_id": "neon",
                     "granted": ["neon"], "stars": 25, "refunded": False},
        "telegram_ok": True,
        "revoked": None,
    }

    async def refund(user_id, charge_id):
        return state["telegram_ok"], "" if state["telegram_ok"] else "CHARGE_ALREADY_REFUNDED"

    def revoke(charge_id):
        state["revoked"] = charge_id
        return ["neon"]

    monkeypatch.setattr(shop_handler, "ADMIN_TELEGRAM_IDS", [42])
    monkeypatch.setattr(shop_handler, "_refund_star_payment", refund)
    monkeypatch.setattr(shop_handler.firebase_service, "get_purchase",
                        lambda charge_id: state["purchase"] if charge_id == "ch_1" else None)
    monkeypatch.setattr(shop_handler.firebase_service, "revoke_purchase", revoke)
    return state


def test_a_refund_gives_back_the_stars_and_takes_back_the_cosmetics(refundable):
    update, message = refund_update()
    asyncio.run(shop_handler.admin_refund(update, SimpleNamespace(args=["ch_1"])))

    assert refundable["revoked"] == "ch_1"
    assert "25" in message.replies[0]


def test_nothing_is_taken_back_if_telegram_refuses_the_refund(refundable):
    """Le due cose vanno insieme: ritirare l'oggetto senza restituire le Stelle e' peggio che
    non rimborsare affatto."""
    refundable["telegram_ok"] = False
    update, message = refund_update()
    asyncio.run(shop_handler.admin_refund(update, SimpleNamespace(args=["ch_1"])))

    assert refundable["revoked"] is None
    assert message.replies


def test_only_an_administrator_can_refund(refundable):
    update, message = refund_update(user_id=99)
    asyncio.run(shop_handler.admin_refund(update, SimpleNamespace(args=["ch_1"])))

    assert refundable["revoked"] is None
