"""Catalogue promises survive the renderer and the real purchase/equip projection."""
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageChops

from domains.shop import service as shop
from services.path_image import render_share_card

ROOT = Path(__file__).resolve().parents[1]


def test_card_samples_cover_exact_catalogue_styles_and_current_renderer():
    target = ROOT / "webapp/src/assets/card-previews"
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["cards"] == [{"id": i["id"], "style": i["style"]}
                                 for i in shop.all_items() if i["kind"] == "card"]
    renderer = (ROOT / "services/path_image.py").read_text(encoding="utf-8").encode("utf-8")
    assert manifest["renderer_sha256"] == hashlib.sha256(renderer).hexdigest(), "Run python -m scripts.shop_previews"
    for card in manifest["cards"]:
        with Image.open(target / f"{card['id']}.png") as image:
            assert image.size == (400, 500)
            assert image.getextrema() != ((0, 0), (0, 0), (0, 0))


def test_travel_bundle_delivers_four_distinct_slots_and_prorates_missing_pieces():
    bundle = shop.get_item("pacchetto_trasferta")
    pieces = [shop.get_item(i) for i in shop.grants_of(bundle)]
    assert {i["kind"] for i in pieces} == {"theme", "frame", "title", "card"}
    assert sum(i["price"] for i in pieces) == 42
    assert shop.price_for({}, bundle) == 32
    partial = {"cosmetics": {"owned": ["card_trasferta"]}}
    assert shop.price_for(partial, bundle) == 21  # ceil(32 * 27 / 42)
    complete = {"cosmetics": {"owned": bundle["grants"],
                              "equipped": {i["kind"]: i["id"] for i in pieces}}}
    assert shop.purchase_status(complete, bundle["id"]) == "already_owned"
    assert shop.price_for(complete, bundle) == 0
    for lang in ("it", "en", "es"):
        appearance = shop.appearance(complete, lang)
        assert appearance["card"]["finish"] == "ticket"
        assert appearance["theme"]["pattern"]
        assert appearance["title"]["label"] == shop.get_item("titolo_trasferta")["style"].get(
            "label_i18n", {}).get(lang, "Sempre in trasferta")


def test_ticket_finish_is_distinct_and_preserves_the_result_content():
    style = shop.get_item("card_trasferta")["style"]
    ticket = Image.open(render_share_card(412, 2, 3, style=style))
    plain = Image.open(render_share_card(412, 2, 3, style={**style, "finish": "plain"}))
    assert ImageChops.difference(ticket, plain).getbbox()
    # The attempt and score area is identical: decoration cannot obscure the result.
    assert ImageChops.difference(ticket.crop((160, 260, 630, 560)),
                                plain.crop((160, 260, 630, 560))).getbbox() is None


def test_final_minute_collection_prices_and_equips_all_five_slots():
    bundle = shop.get_item("pacchetto_ultimo_minuto")
    pieces = [shop.get_item(i) for i in shop.grants_of(bundle)]
    assert {i["kind"] for i in pieces} == {"theme", "frame", "title", "badge", "squares"}
    assert sum(i["price"] for i in pieces) == 41
    assert shop.price_for({}, bundle) == 32
    assert shop.price_for({"cosmetics": {"owned": ["tabellone_acceso"]}}, bundle) == 23
    complete = {"cosmetics": {"owned": bundle["grants"] + ["maglia_novanta", "festa_onda_stadio"],
                              "equipped": {**{i["kind"]: i["id"] for i in pieces},
                                           "number": "maglia_novanta", "celebration": "festa_onda_stadio"}}}
    assert shop.purchase_status(complete, bundle["id"]) == "already_owned"
    assert shop.price_for(complete, bundle) == 0
    for lang in ("it", "en", "es"):
        appearance = shop.appearance(complete, lang)
        assert appearance["theme"]["pattern"]
        assert appearance["frame"]["ring"]
        assert appearance["title"]["label"]
        assert appearance["badge"] == "🏁"
        assert appearance["squares"]["correct"] == "✦"
        assert appearance["number"] == "90"
        assert appearance["celebration"] == "stadium_wave"
