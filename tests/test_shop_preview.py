"""Bundle previews must describe exactly what the buyer receives."""
import pytest

from handlers import keyboards, shop_handler
from services import shop


@pytest.mark.parametrize("lang", ["it", "es", "en"])
def test_bundle_preview_includes_exclusive_items_and_localized_names(lang):
    catalogue = shop.catalogue_for({}, lang)
    for bundle in catalogue["bundles"]:
        assert [item["id"] for item in bundle["contents"]] == bundle["grants"]
        for item in bundle["contents"]:
            source = shop.get_item(item["id"])
            assert item["name"] == shop.localize(source, lang)[0]
            assert item["style"] == source["style"]


@pytest.mark.parametrize("lang", ["it", "es", "en"])
def test_legal_pages_are_directly_accessible_before_payment(monkeypatch, lang):
    monkeypatch.setattr(keyboards, "PUBLIC_BASE_URL", "https://example.com/")
    views = [keyboards.menu_keyboard(lang), shop_handler._main_view(lang, {})[1],
             shop_handler._item_view(lang, {}, shop.get_item("neon"))[1]]
    for view in views:
        urls = {button.url for row in view.inline_keyboard for button in row}
        assert f"https://example.com/privacy?lang={lang}" in urls
        assert f"https://example.com/terms?lang={lang}#refunds" in urls
