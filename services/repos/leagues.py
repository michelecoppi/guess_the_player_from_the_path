"""Firestore leagues repository. Shared dependencies live in the compatibility facade."""
import logging

from firebase_admin import firestore
from google.api_core.exceptions import GoogleAPICallError


def league_ref(code):
    from services import firebase_service as fs
    return fs.db.collection(fs.LEAGUES_COLLECTION).document(code)


def member_ref(code, user_id):
    from services import firebase_service as fs
    return fs.league_ref(code).collection(fs.MEMBERS_SUBCOLLECTION).document(str(user_id))


def get_league(code):
    from services import firebase_service as fs
    snapshot = fs.league_ref(code).get()
    if not snapshot.exists:
        return None
    data = snapshot.to_dict()
    data["code"] = snapshot.id
    return data


def create_league(code, name, owner_id, owner_name):
    """Crea la lega solo se il codice e' libero: la verifica e la scrittura stanno nella
    stessa transazione, altrimenti due creazioni simultanee possono prendersi lo stesso
    codice e una delle due leghe sparisce dentro l'altra."""
    from services import firebase_service as fs
    ref = fs.league_ref(code)

    @firestore.transactional
    def _create(transaction):
        if ref.get(transaction=transaction).exists:
            return False
        transaction.set(ref, {
            "code": code,
            "name": name,
            "owner_id": owner_id,
            "created_at": firestore.SERVER_TIMESTAMP,
            "members_count": 1,
        })
        return True

    if not _create(fs.db.transaction()):
        return False

    fs.member_ref(code, owner_id).set({
        "telegram_id": owner_id,
        "name": owner_name,
        "points": 0,
        "joined_at": firestore.SERVER_TIMESTAMP,
    })
    fs.user_ref(owner_id).update({"leagues": firestore.ArrayUnion([code])})
    logging.info(f"[LEAGUE] Creata lega {code} da {owner_id}")
    return True


def join_league(code, user_id, name, max_members):
    """Iscrive a una lega. Il contatore dei membri si aggiorna in transazione, cosi' il
    limite tiene anche se due persone entrano nello stesso istante."""
    from services import firebase_service as fs
    ref = fs.league_ref(code)
    member = fs.member_ref(code, user_id)

    @firestore.transactional
    def _join(transaction):
        snapshot = ref.get(transaction=transaction)
        if not snapshot.exists:
            return "not_found"
        if member.get(transaction=transaction).exists:
            return "already_member"
        if snapshot.to_dict().get("members_count", 0) >= max_members:
            return "full"

        transaction.set(member, {
            "telegram_id": user_id,
            "name": name,
            "points": 0,
            "joined_at": firestore.SERVER_TIMESTAMP,
        })
        transaction.update(ref, {"members_count": firestore.Increment(1)})
        return "ok"

    result = _join(fs.db.transaction())
    if result == "ok":
        fs.user_ref(user_id).update({"leagues": firestore.ArrayUnion([code])})
    return result


def leave_league(code, user_id):
    from services import firebase_service as fs
    ref = fs.league_ref(code)
    member = fs.member_ref(code, user_id)

    @firestore.transactional
    def _leave(transaction):
        if not member.get(transaction=transaction).exists:
            return False
        transaction.delete(member)
        transaction.update(ref, {"members_count": firestore.Increment(-1)})
        return True

    left = _leave(fs.db.transaction())
    if left:
        fs.user_ref(user_id).update({"leagues": firestore.ArrayRemove([code])})
    return left


def get_league_leaderboard(code, limit=20):
    from services import firebase_service as fs
    query = fs.league_ref(code).collection(fs.MEMBERS_SUBCOLLECTION).order_by(
        "points", direction=firestore.Query.DESCENDING
    ).limit(limit)
    return [doc.to_dict() for doc in query.stream()]


def add_points_to_leagues(user_id, codes, points, name=None):
    """Somma i punti appena guadagnati nelle leghe dell'utente.

    I punti si tengono sul documento del membro (come per i partecipanti agli eventi):
    cosi' la classifica di una lega e' una query ordinata, invece di una lettura per ogni
    iscritto ad ogni /lega."""
    from services import firebase_service as fs
    if not codes or points <= 0:
        return 0

    updated = 0
    for code in codes:
        payload = {"points": firestore.Increment(points)}
        if name:
            payload["name"] = name
        try:
            fs.member_ref(code, user_id).set(payload, merge=True)
            updated += 1
        except GoogleAPICallError:
            logging.exception(f"[LEAGUE] Punti non aggiornati per la lega {code}")
    return updated


def list_leagues(limit=50):
    from services import firebase_service as fs
    query = fs.db.collection(fs.LEAGUES_COLLECTION).order_by(
        "members_count", direction=firestore.Query.DESCENDING
    ).limit(limit)
    leagues = []
    for doc in query.stream():
        data = doc.to_dict()
        data["code"] = doc.id
        leagues.append(data)
    return leagues

