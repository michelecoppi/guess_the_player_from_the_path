"""Modifiche al catalogo locale (`data/shop.json`).

E' il livello che sta sotto la sezione *Shop* della dashboard (`admin_ui.py`), sullo stesso
schema di `services/dataset_editor.py` per `data/players.json`: la dashboard mostra la
tabella e raccoglie le modifiche, qui ci sono le regole.

I campi modificabili sono pochi di proposito - prezzo, nome (italiano) e il flag
`locked` - perche' sono le uniche leve che un admin tocca per la gestione ordinaria del
negozio (ritarare un prezzo, rinominare un oggetto, aprire o chiudere la vendita separata
di un pezzo di pacchetto). Stile, traduzioni, `achievement`/`grants` e la creazione di
oggetti nuovi restano nel file: cambiarli a mano una volta ogni tanto e' piu' sicuro di un
editor visivo per una struttura che varia da un `kind` all'altro.

Come per il dataset dei calciatori: copia di sicurezza in `backup/` prima di scrivere,
riscrittura atomica, e la cache in memoria di `domains/shop/service.py` viene svuotata dopo,
altrimenti bot e dashboard continuerebbero a vedere i valori vecchi.
"""
import json
import os
import shutil
import tempfile
from datetime import datetime

from domains.shop import service as shop

# Repository root: domains/shop/editor.py -> parents[2].
BACKUP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "backup")

EDITABLE_FIELDS = ("price", "name", "locked")


class ShopEditError(Exception):
    """Errore previsto (valore non valido) da mostrare cosi' com'e' nella dashboard."""


def list_items():
    """Tutti gli oggetti del catalogo, con i campi che la dashboard mostra e puo' cambiare."""
    return [
        {
            "id": item.get("id"),
            "kind": item.get("kind"),
            "name": item.get("name", ""),
            "price": int(item.get("price", 0) or 0),
            "locked": bool(item.get("locked", False)),
            "rarity": shop.rarity_of(item),
            "earned_only": bool(item.get("achievement") or item.get("completes") or item.get("trophy")),
        }
        for item in shop.all_items()
    ]


def _validate(item_id, field, value):
    if field == "price":
        try:
            price = int(value)
        except (TypeError, ValueError):
            raise ShopEditError(f"'{item_id}': il prezzo deve essere un numero intero.")
        if not (0 <= price <= shop.MAX_STARS):
            raise ShopEditError(f"'{item_id}': il prezzo deve essere fra 0 e {shop.MAX_STARS} Stelle.")
        return price
    if field == "name":
        name = (value or "").strip()
        if not name:
            raise ShopEditError(f"'{item_id}': il nome non puo' essere vuoto.")
        return name
    if field == "locked":
        return bool(value)
    raise ShopEditError(f"Campo '{field}' non modificabile.")


def _backup(path):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    destination = os.path.join(BACKUP_DIR, f"shop-{stamp}.json")
    shutil.copy2(path, destination)
    return destination


def _write_json(path, payload):
    """Riscrittura atomica: o c'e' il file nuovo o c'e' quello vecchio, mai mezzo file."""
    directory = os.path.dirname(path)
    handle, temp_path = tempfile.mkstemp(dir=directory, prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(temp_path, path)
    except BaseException:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise


def apply_item_changes(changes):
    """Salva le modifiche al catalogo in data/shop.json.

    `changes`: {id_oggetto: {campo: valore}} con i campi di EDITABLE_FIELDS.
    """
    with open(shop.SHOP_PATH, encoding="utf-8") as f:
        catalogue = json.load(f)

    items_by_id = {item.get("id"): item for item in catalogue.get("items", [])}
    applied = {}
    for item_id, fields in changes.items():
        item = items_by_id.get(item_id)
        if item is None:
            raise ShopEditError(f"Nessun oggetto con id '{item_id}' in data/shop.json.")
        item_changes = {}
        for field, value in fields.items():
            if field not in EDITABLE_FIELDS:
                raise ShopEditError(f"Campo '{field}' non modificabile.")
            validated = _validate(item_id, field, value)
            if validated != item.get(field, False if field == "locked" else None):
                item[field] = validated
                item_changes[field] = validated
        if item_changes:
            applied[item_id] = item_changes

    if not applied:
        raise ShopEditError("Nessuna modifica da salvare.")

    backup_path = _backup(shop.SHOP_PATH)
    _write_json(shop.SHOP_PATH, catalogue)
    shop.reload_catalogue()
    return {"changes": applied, "backup": backup_path}
