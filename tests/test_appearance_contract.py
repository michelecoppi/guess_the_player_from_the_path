"""V2 examples must match the backend resolver, including default/earned slots."""
import json
from pathlib import Path

import pytest

from services import shop

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
