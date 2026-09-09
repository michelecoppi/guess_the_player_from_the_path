"""Firestore shop repository. Shared dependencies live in the compatibility facade."""
import logging
import time

from firebase_admin import firestore

from services.dates import today_iso


def purchase_ref(charge_id):
    from services import firebase_service as fs
    return fs.db.collection(fs.PURCHASES_COLLECTION).document(str(charge_id))


def deliver_purchase(user_id, charge_id, item_id, granted_ids, stars, day_iso=None):
    """Consegna gli oggetti comprati e registra l'acquisto. Una volta sola.

    L'idempotenza non e' un lusso: se il webhook non risponde in tempo Telegram rispedisce
    l'update, e una consegna doppia lascerebbe due righe nel registro da cui si rimborsa.
    L'id documento e' `telegram_payment_charge_id`, quindi la seconda consegna trova la riga
    gia' scritta e non fa niente.

    `set(..., merge=True)` e non `update()`: fonde la mappa `cosmetics` campo per campo, cosi'
    quello che l'utente ha addosso resta dov'e' e non serve che il campo esista gia'.

    Ritorna True se ha consegnato adesso, False se era gia' stato consegnato."""
    from services import firebase_service as fs
    ref = fs.purchase_ref(charge_id)
    granted = list(granted_ids)

    @firestore.transactional
    def _deliver(transaction):
        if ref.get(transaction=transaction).exists:
            return False
        transaction.set(ref, {
            "charge_id": str(charge_id),
            "user_id": user_id,
            "item_id": item_id,
            "granted": granted,
            "stars": int(stars),
            "day": day_iso or today_iso(),
            "created_at": firestore.SERVER_TIMESTAMP,
            "refunded": False,
        })
        transaction.set(
            fs.user_ref(user_id),
            {"cosmetics": {"owned": firestore.ArrayUnion(granted)}, "shop_checkout": None},
            merge=True,
        )
        return True

    delivered = _deliver(fs.db.transaction())
    if delivered:
        logging.info(f"[SHOP] {user_id} ha comprato {item_id} per {stars} stelle ({charge_id})")
    else:
        logging.warning(f"[SHOP] Pagamento {charge_id} gia' consegnato, ignorato")
    return delivered


def pin_trophies(user_id, codes):
    """Quali trofei stanno sul profilo. La regola su cosa e' appendibile sta in
    services/trophies.py: qui si scrive e basta, come per i cosmetici.

    Sta dentro `cosmetics` e non accanto a `trophies` perche' e' una scelta di come ci si
    vede, non un dato sui trofei vinti: `trophies` lo scrive chi assegna un podio, questo lo
    scrive l'utente."""
    from services import firebase_service as fs
    fs.user_ref(user_id).set({"cosmetics": {"pinned": list(codes)}}, merge=True)


def equip_cosmetic(user_id, kind, item_id):
    """Cambia quello che l'utente ha addosso in uno slot. Non controlla se lo possiede: la
    regola sta in services/shop.py, qui si scrive e basta."""
    from services import firebase_service as fs
    fs.user_ref(user_id).set({"cosmetics": {"equipped": {kind: item_id}}}, merge=True)


def equip_look(user_id, slots):
    from services import firebase_service as fs
    fs.user_ref(user_id).set({"cosmetics": {"equipped": slots}}, merge=True)


def save_looks(user_id, looks):
    from services import firebase_service as fs
    fs.user_ref(user_id).set({"cosmetics": {"looks": looks}}, merge=True)


def reserve_checkout(user_id, query_id, expected_owned):
    """Serialize pre-checkouts across tabs/bot replicas. Abandoned checkouts expire."""
    from services import firebase_service as fs
    ref = fs.user_ref(user_id)

    @firestore.transactional
    def reserve(transaction):
        snapshot = ref.get(transaction=transaction)
        data = snapshot.to_dict() or {}
        if set((data.get("cosmetics") or {}).get("owned", [])) != set(expected_owned):
            return "price_changed"
        pending = data.get("shop_checkout") or {}
        now = time.time()
        if pending.get("expires", 0) > now:
            return "ok" if pending.get("query_id") == query_id else "checkout_busy"
        transaction.set(ref, {"shop_checkout": {"query_id": query_id, "expires": now + 120}}, merge=True)
        return "ok"

    return reserve(fs.db.transaction())


def get_purchase(charge_id):
    from services import firebase_service as fs
    snapshot = fs.purchase_ref(charge_id).get()
    return snapshot.to_dict() if snapshot.exists else None


def get_user_purchases(user_id, limit=None):
    """Gli acquisti di un utente, dal piu' recente. Il filtro e' su un campo solo e
    l'ordinamento si fa qui: un `order_by` insieme al `where` vorrebbe un indice composito
    per una lista che non arriva a dieci righe."""
    from services import firebase_service as fs
    query = fs.db.collection(fs.PURCHASES_COLLECTION).where("user_id", "==", user_id)
    purchases = [doc.to_dict() for doc in query.stream()]
    return sorted(purchases, key=lambda p: (p.get("day") or "", str(p.get("created_at") or "")), reverse=True)[:limit]


def revoke_purchase(charge_id):
    """Segna un acquisto come rimborsato e ritira quello che aveva consegnato.

    Ritira **solo** quello che nessun altro acquisto ancora valido gli ha dato: chi ha preso
    il tema Neon da solo e poi il Pacchetto Neon, e si fa rimborsare il pacchetto, il tema
    l'aveva gia' pagato e resta suo.

    Ritorna la lista degli id davvero ritirati, o None se l'acquisto non esiste."""
    from services import firebase_service as fs
    purchase = fs.get_purchase(charge_id)
    if not purchase:
        return None

    user_id = purchase.get("user_id")
    granted = set(purchase.get("granted") or [])
    kept = {
        item_id
        for other in fs.get_user_purchases(user_id)
        if other.get("charge_id") != str(charge_id) and not other.get("refunded")
        for item_id in (other.get("granted") or [])
    }
    revoked = sorted(granted - kept)

    fs.purchase_ref(charge_id).update({"refunded": True, "refunded_at": firestore.SERVER_TIMESTAMP})
    if revoked:
        fs.user_ref(user_id).set(
            {"cosmetics": {"owned": firestore.ArrayRemove(revoked)}}, merge=True
        )
    logging.info(f"[SHOP] Rimborso {charge_id} a {user_id}: ritirati {revoked}")
    return revoked

