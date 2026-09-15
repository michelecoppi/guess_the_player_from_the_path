import json

import pytest

from services import shop, shop_editor
from services.shop_editor import ShopEditError


def _item(item_id="tema_base", kind="theme", price=15, name="Tema", **extra):
    item = {"id": item_id, "kind": kind, "price": price, "name": name}
    item.update(extra)
    return item


@pytest.fixture
def catalogue(tmp_path, monkeypatch):
    """Catalogo finto: le funzioni qui sotto **scrivono su disco**, e devono farlo su una
    copia usa e getta, non su data/shop.json."""
    shop_path = tmp_path / "shop.json"
    backup_dir = tmp_path / "backup"

    monkeypatch.setattr(shop, "SHOP_PATH", str(shop_path))
    monkeypatch.setattr(shop_editor, "BACKUP_DIR", str(backup_dir))

    def write(items):
        shop_path.write_text(json.dumps({"items": items}, ensure_ascii=False), encoding="utf-8")
        shop.reload_catalogue()

    def read():
        return json.loads(shop_path.read_text(encoding="utf-8"))

    write([_item()])
    yield type("Catalogue", (), {"write": staticmethod(write), "read": staticmethod(read),
                                  "path": shop_path, "backup_dir": backup_dir})
    # Invalidazione pigra e non un reload_catalogue(): quest'ultimo rilegge subito da
    # SHOP_PATH, che a questo punto del teardown e' ancora il percorso temporaneo (il
    # monkeypatch si annulla solo dopo), e lascerebbe la cache in memoria popolata con il
    # catalogo finto anche dopo che il path e' tornato a quello vero.
    shop._catalogue = None


def test_list_items_reports_the_editable_fields(catalogue):
    catalogue.write([_item(), _item("frame_base", kind="frame", price=0, locked=True)])

    rows = {row["id"]: row for row in shop_editor.list_items()}

    assert rows["tema_base"]["price"] == 15
    assert rows["frame_base"]["locked"] is True
    assert rows["frame_base"]["price"] == 0


def test_apply_item_changes_updates_price_and_reloads_the_catalogue(catalogue):
    result = shop_editor.apply_item_changes({"tema_base": {"price": 30}})

    assert result["changes"] == {"tema_base": {"price": 30}}
    assert catalogue.read()["items"][0]["price"] == 30
    assert shop.get_item("tema_base")["price"] == 30  # cache svuotata, rilegge dal disco


def test_apply_item_changes_writes_a_backup(catalogue):
    result = shop_editor.apply_item_changes({"tema_base": {"name": "Tema nuovo"}})

    assert catalogue.backup_dir.exists()
    assert (catalogue.backup_dir / result["backup"].split("/")[-1].split("\\")[-1]).exists()


def test_apply_item_changes_rejects_an_unknown_id(catalogue):
    with pytest.raises(ShopEditError):
        shop_editor.apply_item_changes({"non_esiste": {"price": 10}})


def test_apply_item_changes_rejects_a_negative_price(catalogue):
    with pytest.raises(ShopEditError):
        shop_editor.apply_item_changes({"tema_base": {"price": -1}})


def test_apply_item_changes_rejects_a_price_above_the_star_limit(catalogue):
    with pytest.raises(ShopEditError):
        shop_editor.apply_item_changes({"tema_base": {"price": shop.MAX_STARS + 1}})


def test_apply_item_changes_rejects_an_empty_name(catalogue):
    with pytest.raises(ShopEditError):
        shop_editor.apply_item_changes({"tema_base": {"name": "   "}})


def test_apply_item_changes_rejects_no_op_changes(catalogue):
    with pytest.raises(ShopEditError):
        shop_editor.apply_item_changes({"tema_base": {"price": 15}})  # gia' 15


def test_apply_item_changes_toggles_locked(catalogue):
    result = shop_editor.apply_item_changes({"tema_base": {"locked": True}})

    assert result["changes"] == {"tema_base": {"locked": True}}
    assert catalogue.read()["items"][0]["locked"] is True
