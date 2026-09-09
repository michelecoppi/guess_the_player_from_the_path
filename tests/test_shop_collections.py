"""The coordinated collections are complete outfits with usable cosmetic styles."""
import pytest

from services import shop

COLLECTIONS = [item["id"] for item in shop.bundles() if item.get("featured")]


@pytest.mark.parametrize("bundle_id", COLLECTIONS)
def test_collection_fills_every_slot_and_costs_less_than_its_pieces(bundle_id):
    bundle = shop.get_item(bundle_id)
    pieces = [shop.get_item(item_id) for item_id in bundle["grants"]]
    kinds = [item["kind"] for item in pieces]
    # Una collezione riempie tutti gli slot fondamentali e puo' aggiungerne altri (una
    # figurina esclusiva, per esempio), ma mai due pezzi per lo stesso slot: si indossa un
    # oggetto per tipo, quindi il secondo non si potrebbe mettere.
    assert set(shop.CORE_KINDS) <= set(kinds)
    assert len(kinds) == len(set(kinds))
    assert set(kinds) <= set(shop.KINDS)
    assert bundle["price"] < sum(item["price"] for item in pieces)
    for item in pieces:
        # Ogni pezzo si compra anche da solo, tranne gli esclusivi: quelli sono la ragione
        # per cui il pacchetto esiste (tests/test_shop.py, "cheaper or exclusive").
        expected = "not_for_sale" if item.get("locked") else "ok"
        assert shop.purchase_status({}, item["id"]) == expected
        assert set(item["name_i18n"]) == {"es", "en"}
        assert set(item["description_i18n"]) == {"es", "en"}


@pytest.mark.parametrize("bundle_id", COLLECTIONS)
def test_full_outfit_reaches_the_profile_and_shared_result(bundle_id):
    ids = shop.grants_of(shop.get_item(bundle_id))
    equipped = {shop.get_item(item_id)["kind"]: item_id for item_id in ids}
    user = {"cosmetics": {"owned": ids, "equipped": equipped}}
    appearance = shop.appearance(user, "en")
    assert appearance["theme"]["pattern"]
    assert appearance["frame"]["ring"]
    assert appearance["badge"]
    title = shop.get_item(equipped["title"])["style"]
    assert appearance["title"]["label"] == title["label_i18n"]["en"]
    assert len(set(shop.squares_symbols(user))) == 3
    assert shop.purchase_status(user, bundle_id) == "already_owned"


def luminance(color):
    channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in channels]
    return sum(c * weight for c, weight in zip(linear, [.2126, .7152, .0722]))


@pytest.mark.parametrize("theme_id", [shop.get_item(one)["id"]
                                      for bundle in COLLECTIONS
                                      for one in shop.get_item(bundle)["grants"]
                                      if shop.get_item(one)["kind"] == "theme"])
def test_collection_theme_text_and_buttons_have_readable_contrast(theme_id):
    style = shop.get_item(theme_id)["style"]
    pairs = [(text, surface) for text in ("text", "muted") for surface in ("bg", "bg2", "card")]
    pairs.append(("accentText", "accent"))
    for foreground, background in pairs:
        light, dark = sorted([luminance(style[foreground]), luminance(style[background])], reverse=True)
        assert (light + .05) / (dark + .05) >= 4.5, (theme_id, foreground, background)
