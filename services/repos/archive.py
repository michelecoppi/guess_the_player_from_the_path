"""Firestore archive repository. Shared dependencies live in the compatibility facade."""
from firebase_admin import firestore


def archive_ref(user_id, day_iso):
    from services import firebase_service as fs
    return fs.user_ref(user_id).collection(fs.ARCHIVE_SUBCOLLECTION).document(day_iso)


def set_archive_day(user_id, day_iso):
    """Il giorno d'archivio che l'utente sta giocando, o None per tornare a oggi.

    Sta sul documento utente e non in memoria di processo perche' su Cloud Run l'istanza
    puo' sparire fra un messaggio e l'altro: la partita in corso deve sopravvivere.

    Aprire una sfida d'archivio chiude l'allenamento e l'evento (e viceversa, vedi
    `set_training_key` e `set_event_key`): con due partite aperte insieme bisognerebbe
    decidere ad ogni messaggio a quale delle due risponde, che e' una regola che nessuno
    puo' indovinare."""
    from services import firebase_service as fs
    fs.user_ref(user_id).update({"archive_day": day_iso, "training_key": None, "event_key": None})


def get_archive_result(user_id, day_iso):
    from services import firebase_service as fs
    snapshot = fs.archive_ref(user_id, day_iso).get()
    return snapshot.to_dict() if snapshot.exists else None


def get_solved_archive_days(user_id, limit=50):
    from services import firebase_service as fs
    query = fs.user_ref(user_id).collection(fs.ARCHIVE_SUBCOLLECTION).where("solved", "==", True).limit(limit)
    return {doc.id for doc in query.stream()}


def begin_archive_attempt(user_id, day_iso, max_attempts):
    """Come begin_guess_attempt, ma su un documento per (utente, giorno d'archivio): qui i
    tentativi non si azzerano a mezzanotte, la sfida e' gia' passata."""
    from services import firebase_service as fs
    ref = fs.archive_ref(user_id, day_iso)

    @firestore.transactional
    def _attempt(transaction):
        snapshot = ref.get(transaction=transaction)
        data = snapshot.to_dict() if snapshot.exists else {}

        if data.get("solved"):
            return {"ok": False, "reason": "already_solved"}
        attempts = data.get("attempts", 0)
        if attempts >= max_attempts:
            return {"ok": False, "reason": "no_attempts"}

        transaction.set(ref, {"day": day_iso, "attempts": attempts + 1, "solved": False}, merge=True)
        return {"ok": True, "attempts_used": attempts + 1, "attempts_left": max_attempts - (attempts + 1)}

    return _attempt(fs.db.transaction())


def register_archive_solved(user_id, day_iso, attempts):
    """Nessun punto: l'archivio non deve permettere di scalare la classifica rigiocando il
    passato. Si tiene solo il conto delle sfide recuperate, che finisce in /stats.

    Ritorna i traguardi che questa sfida recuperata ha fatto scattare."""
    from services import firebase_service as fs
    fs.archive_ref(user_id, day_iso).set(
        {"day": day_iso, "attempts": attempts, "solved": True}, merge=True
    )
    return fs._bump_counters(user_id, {"archive_solved": firestore.Increment(1)}, archive_solved=1)


def history_ref(user_id, day_iso):
    from services import firebase_service as fs
    return fs.user_ref(user_id).collection(fs.HISTORY_SUBCOLLECTION).document(day_iso)


def record_daily_history(user_id, day_iso, solved, attempts, hints=0):
    """Com'e' andata **quella** giornata a **quell'** utente: un documento per giorno.

    Serve al calendario della mini app, che deve poter dire "questa l'hai presa al secondo,
    questa l'hai persa, questa non l'hai giocata". Dai contatori sul documento utente non si
    ricava: quelli portano un giorno solo (`last_played_day`) e il giorno dopo sono
    sovrascritti.

    Si scrive una volta sola per giornata, quando la giornata si **chiude** per quell'utente
    (indovinata o tentativi finiti): non ad ogni tentativo."""
    from services import firebase_service as fs
    fs.history_ref(user_id, day_iso).set({
        "day": day_iso,
        "solved": bool(solved),
        "attempts": attempts,
        "hints": hints,
    })


def get_daily_history(user_id, limit=60):
    """Lo storico dal giorno piu' recente. Il limite e' quello del calendario mostrato: e'
    una query sola, e la si fa solo quando la mini app apre la scheda dell'archivio."""
    from services import firebase_service as fs
    query = (
        fs.user_ref(user_id).collection(fs.HISTORY_SUBCOLLECTION)
        .order_by("day", direction=firestore.Query.DESCENDING)
        .limit(limit)
    )
    return [doc.to_dict() for doc in query.stream()]


def get_upcoming_daily_paths(limit=7):
    """Le sfide gia' generate, dalla piu' lontana nel futuro: serve a /admin_next."""
    from services import firebase_service as fs
    docs = fs.db.collection(fs.DAILY_PATH_COLLECTION).order_by(
        "day", direction=firestore.Query.DESCENDING
    ).limit(limit).stream()
    return [doc.to_dict() for doc in docs]


def get_archive_days(user_id, limit=100):
    """Tutte le sfide d'archivio giocate da un utente (anche quelle non risolte)."""
    from services import firebase_service as fs
    query = fs.user_ref(user_id).collection(fs.ARCHIVE_SUBCOLLECTION).limit(limit)
    days = []
    for doc in query.stream():
        data = doc.to_dict()
        data["day"] = data.get("day") or doc.id
        days.append(data)
    return sorted(days, key=lambda d: d["day"], reverse=True)

