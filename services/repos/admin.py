"""Firestore admin repository. Shared dependencies live in the compatibility facade."""
import logging
from datetime import datetime, timezone

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
    """Numeri di riepilogo per /admin_stats e per la dashboard #33, senza scaricare
    l'intera collection users."""
    from services import firebase_service as fs
    users_ref = fs.db.collection(fs.USERS_COLLECTION)
    today = today_iso()

    # Chi ha giocato oggi e' un insieme limitato (non l'intera userbase): a differenza dei
    # conteggi sopra, qui serve leggere i valori (tentativi/hint), non solo contarli, quindi
    # si scorre in streaming invece di usare l'aggregazione lato server.
    active_count = 0
    attempts_total = 0
    hints_total = 0
    for doc in users_ref.where("last_played_day", "==", today).stream():
        data = doc.to_dict()
        active_count += 1
        attempts_total += data.get("daily_attempts", 0) or 0
        hints_total += data.get("daily_hints", 0) or 0

    return {
        "users_total": fs._count_collection(users_ref),
        "users_with_notifications": fs._count_collection(users_ref.where("notifications_enabled", "==", True)),
        "users_guessed_today": fs._count_collection(
            users_ref.where("last_played_day", "==", today).where("has_guessed_today", "==", True)
        ),
        "active_users_today": active_count,
        "avg_attempts_today": (attempts_total / active_count) if active_count else 0.0,
        "avg_hints_today": (hints_total / active_count) if active_count else 0.0,
        # work_receipts.claim() lascia lo stato "uncertain" quando la lease scade senza
        # che finish() sia mai arrivato: e' il segnale di un job/broadcast che si e'
        # interrotto, senza dover leggere i log strutturati (dettaglio completo in #38).
        "failed_jobs_recent": _count_collection(
            fs.db.collection("work_receipts").where("status", "==", "uncertain")
        ),
    }


def list_failed_jobs(limit=50):
    """Job bloccati: `work_receipts.claim()` (services/work_receipts.py) ha lasciato la
    lease scaduta senza che `finish()` sia mai arrivato - il segnale di un job o una pagina
    di broadcast che si e' interrotta a meta'."""
    from services import firebase_service as fs
    query = fs.db.collection("work_receipts").where("status", "==", "uncertain").limit(limit)
    jobs = []
    for doc in query.stream():
        data = doc.to_dict()
        expires = data.get("expires")
        jobs.append({
            "key": doc.id,
            "serial_key": data.get("serial_key"),
            "expired_at": datetime.fromtimestamp(expires, tz=timezone.utc) if expires else None,
        })
    return jobs


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


def _planner_ref():
    from services import firebase_service as fs
    return fs.db.collection(fs.ADMIN_SETTINGS_COLLECTION).document(fs.DAILY_PLANNER_DOC)


def get_planner_exclusions():
    """Giocatori esclusi dal planner delle sfide (#30): {player_id: {reason, until, excluded_at}}.

    Non e' la sospensione di /admin_block (dato sbagliato, fuori da tutto): e' una scelta
    editoriale sul calendario ("e' appena stato in tendenza, non programmarlo fino a
    giugno"), con una scadenza facoltativa."""
    doc = _planner_ref().get()
    if not doc.exists:
        return {}
    return dict(doc.to_dict().get("excluded") or {})


def set_planner_exclusion(player_id, exclusion):
    _planner_ref().set({"excluded": {player_id: dict(exclusion)}}, merge=True)
    logging.info(f"[ADMIN] Giocatore escluso dal planner: {player_id}")


def remove_planner_exclusion(player_id):
    ref = _planner_ref()
    if ref.get().exists:
        ref.update({f"excluded.{player_id}": firestore.DELETE_FIELD})
    logging.info(f"[ADMIN] Giocatore riammesso nel planner: {player_id}")


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

