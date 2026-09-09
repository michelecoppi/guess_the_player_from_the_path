"""Firestore admin repository. Shared dependencies live in the compatibility facade."""
import logging

from firebase_admin import firestore
from google.api_core.exceptions import GoogleAPICallError

from services.dates import now_italy, today_iso


def _count_collection(query):
    """Conta i documenti usando l'aggregazione lato server (una lettura fatturata invece di N).
    Se il backend non la supporta, ripiega sul conteggio in streaming."""
    try:
        result = query.count().get()
        return int(result[0][0].value)
    except GoogleAPICallError:
        logging.info("[ADMIN] count() non disponibile, fallback su stream()")
        return sum(1 for _ in query.stream())


def get_admin_overview():
    """Numeri di riepilogo per /admin_stats, senza scaricare l'intera collection users."""
    from services import firebase_service as fs
    users_ref = fs.db.collection(fs.USERS_COLLECTION)
    return {
        "users_total": fs._count_collection(users_ref),
        "users_with_notifications": fs._count_collection(users_ref.where("notifications_enabled", "==", True)),
        "users_guessed_today": fs._count_collection(
            users_ref.where("last_played_day", "==", today_iso()).where("has_guessed_today", "==", True)
        ),
    }


def get_blocked_player_ids():
    """Giocatori sospesi a mano dall'admin (dato sbagliato segnalato): esclusi dalla
    selezione automatica senza dover ridistribuire il bot."""
    from services import firebase_service as fs
    doc = fs.db.collection(fs.ADMIN_SETTINGS_COLLECTION).document(fs.DATASET_OVERRIDES_DOC).get()
    if not doc.exists:
        return []
    return doc.to_dict().get("blocked_player_ids", [])


def block_player_id(player_id):
    from services import firebase_service as fs
    fs.db.collection(fs.ADMIN_SETTINGS_COLLECTION).document(fs.DATASET_OVERRIDES_DOC).set(
        {"blocked_player_ids": firestore.ArrayUnion([player_id])}, merge=True
    )
    logging.info(f"[ADMIN] Giocatore sospeso dalla selezione automatica: {player_id}")


def unblock_player_id(player_id):
    from services import firebase_service as fs
    fs.db.collection(fs.ADMIN_SETTINGS_COLLECTION).document(fs.DATASET_OVERRIDES_DOC).set(
        {"blocked_player_ids": firestore.ArrayRemove([player_id])}, merge=True
    )
    logging.info(f"[ADMIN] Giocatore riammesso nella selezione automatica: {player_id}")


def add_father_son_pair(pair):
    """Salva una coppia padre/figlio inviata dall'admin via Telegram (foto + risposte).
    Il campo 'file_id' e' l'identificativo della foto su Telegram: puo' essere rispedito
    come immagine senza doverla ospitare da nessuna parte."""
    from services import firebase_service as fs
    doc_ref = fs.db.collection(fs.FATHER_SON_COLLECTION).document()
    payload = dict(pair)
    payload["created_at"] = now_italy()
    payload["used_in_events"] = payload.get("used_in_events", [])
    doc_ref.set(payload)
    logging.info(f"[ADMIN] Coppia padre/figlio salvata: {doc_ref.id}")
    return doc_ref.id


def list_father_son_pairs(limit=50, only_unused=False):
    from services import firebase_service as fs
    query = fs.db.collection(fs.FATHER_SON_COLLECTION).limit(limit)
    pairs = []
    for doc in query.stream():
        data = doc.to_dict()
        data["id"] = doc.id
        if only_unused and data.get("used_in_events"):
            continue
        pairs.append(data)
    return pairs


def delete_father_son_pair(pair_id):
    from services import firebase_service as fs
    doc_ref = fs.db.collection(fs.FATHER_SON_COLLECTION).document(pair_id)
    if not doc_ref.get().exists:
        return False
    doc_ref.delete()
    logging.info(f"[ADMIN] Coppia padre/figlio eliminata: {pair_id}")
    return True


def mark_father_son_pairs_used(pair_ids, event_code):
    from services import firebase_service as fs
    for pair_id in pair_ids:
        fs.db.collection(fs.FATHER_SON_COLLECTION).document(pair_id).update(
            {"used_in_events": firestore.ArrayUnion([event_code])}
        )

