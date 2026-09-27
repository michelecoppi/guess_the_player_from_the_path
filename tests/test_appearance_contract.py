"""V2 examples must match the backend resolver, including default/earned slots."""
import json
from pathlib import Path

import pytest

from domains.shop import service as shop

FIXTURES = json.loads((Path(__file__).resolve().parents[1] /
                       "webapp/src/prototypes/appearance-fixtures.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", FIXTURES)
def test_v2_snapshot_matches_resolved_backend_appearance(name):
    expected = FIXTURES[name]
    worn = expected["equipped"]
    owned = list(worn.values())
    if name == "collection":
        owned.extend(shop.get_item("pacchetto_neve")["grants"])
    user = {"cosmetics": {"owned": owned, "equipped": worn}}
    assert expected == shop.appearance(user, "it")
    assert set(expected["equipped"]) == set(shop.KINDS)


THEMES = json.loads((Path(__file__).resolve().parents[1] /
                     "webapp/src/prototypes/theme-fixtures.json").read_text(encoding="utf-8"))


def test_theme_review_covers_every_real_theme():
    assert set(THEMES) == {item["id"] for item in shop.all_items() if item["kind"] == "theme"}


@pytest.mark.parametrize("theme_id", THEMES)
def test_theme_review_snapshot_matches_backend(theme_id):
    worn = {**shop.default_equipped(), "theme": theme_id}
    user = {"cosmetics": {"owned": list(worn.values()), "equipped": worn}}
    item = shop.get_item(theme_id)
    assert THEMES[theme_id]["appearance"] == shop.appearance(user, "it")
    assert THEMES[theme_id]["name"] == shop.localize(item, "it")[0]
