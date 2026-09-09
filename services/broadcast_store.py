"""Daily payload snapshots and bounded recipient pages."""
from firebase_admin import firestore
from google.api_core.exceptions import AlreadyExists

from services import firebase_service as fs
from services.dates import normalize_day


def get_job(day):
    snapshot = fs.db.collection("daily_jobs").document(day).get()
    return snapshot.to_dict() if snapshot.exists else None


def save_job(day, payload):
    ref = fs.db.collection("daily_jobs").document(day)
    try:
        ref.create(payload)
        return payload
    except AlreadyExists:
        return ref.get().to_dict()


def page(reference_day, cursor=None, size=100):
    """Una pagina di destinatari, in ordine di documento cosi' il cursore e' stabile.

    Il filtro sulle notifiche sta nella query e non in Python: chi le ha spente non deve
    costare una lettura. L'indice a campo singolo che Firestore crea da solo copre
    "uguaglianza + ordine per __name__", quindi non serve un indice composito."""
    query = (fs.db.collection(fs.USERS_COLLECTION)
             .where("notifications_enabled", "==", True)
             .order_by("__name__").limit(size))
    if cursor:
        query = query.start_after({"__name__": fs.user_ref(cursor)})
    docs = list(query.stream())
    users = []
    for doc in docs:
        data = doc.to_dict()
        # Il documento e' gia' filtrato sulle notifiche: qui resta solo chi non ha una chat
        # dove scrivere (utenti importati senza `chat_id`).
        if data.get("chat_id", -1) == -1:
            continue
        users.append({"user_id": doc.id, "chat_id": data["chat_id"],
                      "language": data.get("language") or fs.DEFAULT_LANGUAGE,
                      "has_guessed_today": bool(data.get("has_guessed_today") and
                                                normalize_day(data.get("last_played_day")) == reference_day),
                      "last_notification_day": data.get("last_notification_day")})
    return users, docs[-1].id if len(docs) == size else None


def mark_sent(user_id, day):
    fs.user_ref(user_id).update({"last_notification_day": day})


def add_sent(day, count):
    """Somma gli invii di una pagina sul documento del giorno.

    E' un `Increment`, quindi due pagine che finiscono insieme non si sovrascrivono, e il
    riepilogo agli admin puo' leggere un totale invece di contare i messaggi a mano."""
    if count:
        fs.db.collection("daily_jobs").document(day).update({"sent_total": firestore.Increment(count)})
