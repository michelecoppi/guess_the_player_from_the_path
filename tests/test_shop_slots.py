"""Gli slot arrivati dopo i cinque fondamentali, e i tre modi di avere una cosa senza comprarla."""
import pytest

from services import shop


def user(*owned, trophies=None, **worn):
    return {"cosmetics": {"owned": list(owned), "equipped": dict(worn)},
            "trophies": list(trophies or [])}


# ---------------------------------------------------------------------------
# Slot
# ---------------------------------------------------------------------------

def test_the_core_slots_are_the_ones_a_collection_must_fill():
    assert shop.KINDS == shop.CORE_KINDS + shop.EXTRA_KINDS
    assert set(shop.CORE_KINDS) & set(shop.EXTRA_KINDS) == set()


@pytest.mark.parametrize("kind", shop.EXTRA_KINDS)
def test_every_new_slot_has_its_own_way_of_doing_nothing(kind):
    """Anche gli slot nuovi hanno il loro oggetto di partenza: e' quello che permette di
    tornare indietro, ed e' il motivo per cui nessun punto del codice deve gestire lo slot
    vuoto come caso speciale."""
    default = shop.default_item_id(kind)
    assert default and shop.get_item(default)["kind"] == kind
    assert shop.equipped({})[kind] == default


def test_what_a_new_user_wears_reaches_the_page_already_resolved():
    look = shop.appearance({}, "it")
    assert look["number"] == ""
    assert look["celebration"] == ""
    assert look["card"]["finish"] == "plain"


def test_a_worn_number_is_a_string_because_zero_seven_is_not_seven():
    data = user("maglia_sette", number="maglia_sette")
    assert shop.appearance(data, "it")["number"] == "7"


# ---------------------------------------------------------------------------
# Rarita'
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("item_id,expected", [
    ("notturno", "free"),
    ("distintivo_pallone", "common"),
    ("neon", "rare"),
    ("figurina_foil", "collector"),
    ("traguardo_cartografo", "earned"),
    ("festa_neve", "earned"),
    ("oro_del_podio", "earned"),
    ("figurina_cinegiornale", "collector"),
])
def test_the_rarity_of_an_item_follows_its_price_unless_it_says_otherwise(item_id, expected):
    assert shop.rarity_of(shop.get_item(item_id)) == expected


def test_every_rarity_in_the_catalogue_is_one_we_know_how_to_draw():
    for item in shop.all_items():
        assert shop.rarity_of(item) in shop.RARITIES


# ---------------------------------------------------------------------------
# Premi di completamento
# ---------------------------------------------------------------------------

def test_a_celebration_arrives_with_the_last_piece_of_its_collection():
    pack = shop.get_item("pacchetto_neve")
    reward = next(one for one in shop.all_items()
                  if one.get("completes") == pack["grants"])

    almost = user(*pack["grants"][:-1])
    assert reward["id"] not in shop.owned_ids(almost)
    assert shop.missing_for(almost, reward) == [pack["grants"][-1]]

    complete = user(*pack["grants"])
    assert reward["id"] in shop.owned_ids(complete)
    assert shop.missing_for(complete, reward) == []


def test_a_completion_reward_is_never_for_sale_and_is_not_free_either():
    for item in shop.all_items():
        if not item.get("completes"):
            continue
        assert shop.purchase_status({}, item["id"]) == "not_for_sale"
        assert item["id"] not in shop.free_ids()


def test_a_completion_reward_never_depends_on_another_one():
    """`owned_ids` calcola i premi una volta sola, sopra tutto il resto. Un premio che ne
    richiede un altro non scatterebbe mai, e non si vedrebbe: sarebbe solo un oggetto che
    nessuno riesce a ottenere."""
    rewards = {item["id"] for item in shop.all_items() if item.get("completes")}
    for item in shop.all_items():
        assert not (set(item.get("completes") or []) & rewards), item["id"]


def test_a_refund_that_breaks_a_collection_takes_the_reward_with_it():
    """Il premio **e'** la collezione completa, non un fatto avvenuto una volta: se un pezzo
    torna indietro, la collezione non e' piu' completa. E' il contrario di un traguardo, che
    una volta preso resta."""
    pack = shop.get_item("pacchetto_fango")
    reward = next(one for one in shop.all_items() if one.get("completes") == pack["grants"])
    assert reward["id"] in shop.owned_ids(user(*pack["grants"]))
    assert reward["id"] not in shop.owned_ids(user(*pack["grants"][1:]))


# ---------------------------------------------------------------------------
# Podio e benvenuto
# ---------------------------------------------------------------------------

def test_a_first_place_unlocks_what_no_amount_of_stars_can_buy():
    assert shop.purchase_status({}, "oro_del_podio") == "not_for_sale"
    assert "oro_del_podio" not in shop.owned_ids(user())
    assert "oro_del_podio" in shop.owned_ids(user(trophies=["1_giramondo_20260101"]))


def test_a_podium_requirement_is_satisfied_from_above_and_not_from_below():
    third = user(trophies=["3_giramondo_20260101"])
    first = user(trophies=["1_giramondo_20260101"])
    assert "cornice_alloro" in shop.owned_ids(third)
    assert "oro_del_podio" not in shop.owned_ids(third)
    assert "cornice_alloro" in shop.owned_ids(first)


def test_a_monthly_trophy_counts_as_a_podium_too():
    assert "oro_del_podio" in shop.owned_ids(user(trophies=["MON_July_3_2026_1"]))
    assert "oro_del_podio" not in shop.owned_ids(user(trophies=["MON_July_3_2026_2"]))


def test_the_welcome_item_leaves_the_shop_after_the_first_purchase():
    assert shop.purchase_status(user(), "distintivo_primo_passo") == "ok"
    assert shop.purchase_status(user("neon"), "distintivo_primo_passo") == "welcome_only"


def test_the_welcome_item_costs_the_smallest_price_telegram_allows():
    assert shop.get_item("distintivo_primo_passo")["price"] == shop.MIN_STARS


# ---------------------------------------------------------------------------
# Vetrina della settimana
# ---------------------------------------------------------------------------

def test_the_showcase_does_not_change_inside_a_week_and_does_change_across_weeks():
    monday = shop.weekly_showcase({}, "it", "2026-09-07")
    friday = shop.weekly_showcase({}, "it", "2026-09-11")
    next_week = shop.weekly_showcase({}, "it", "2026-09-16")
    assert monday["week"] == friday["week"] == "2026-W37"
    assert [one["id"] for one in monday["items"]] == [one["id"] for one in friday["items"]]
    assert next_week["week"] == "2026-W38"
    assert [one["id"] for one in next_week["items"]] != [one["id"] for one in monday["items"]]


def test_the_showcase_is_the_same_for_everyone():
    """Una vetrina personalizzata sarebbe solo un altro ordinamento del catalogo: il senso
    e' che due persone nello stesso gruppo vedano la stessa cosa nello stesso momento."""
    rich = shop.weekly_showcase(user(*[one["id"] for one in shop.all_items()]), "it", "2026-09-07")
    poor = shop.weekly_showcase({}, "it", "2026-09-07")
    assert [one["id"] for one in rich["items"]] == [one["id"] for one in poor["items"]]


def test_the_showcase_shows_things_that_can_actually_be_bought_from_different_slots():
    window = shop.weekly_showcase({}, "it", "2026-09-07")["items"]
    assert len(window) == 3
    assert len({one["kind"] for one in window}) == 3
    for one in window:
        assert shop.purchase_status({}, one["id"]) == "ok"
