"""Firestore events repository. Shared dependencies live in the compatibility facade."""
import logging

from firebase_admin import firestore

from services.dates import normalize_day, parse_iso, today_iso


def event_ref(event_code):
    from services import firebase_service as fs
    return fs.db.collection(fs.EVENTS_COLLECTION).document(event_code)


def get_event(event_code):
    from services import firebase_service as fs
    snapshot = fs.event_ref(event_code).get()
    if not snapshot.exists:
        return None
    data = snapshot.to_dict()
    data["code"] = snapshot.id
    return data


def event_exists(event_code):
    from services import firebase_service as fs
    return fs.event_ref(event_code).get().exists


def save_event(event_code, doc):
    from services import firebase_service as fs
    doc = dict(doc)
    doc["code"] = event_code
    fs.event_ref(event_code).set(doc)
    logging.info(f"[GENERATOR] Salvato evento {event_code} ({doc.get('name')})")


def get_active_events(day_iso=None):
    from services import firebase_service as fs
    day_iso = day_iso or today_iso()
    query = fs.db.collection(fs.EVENTS_COLLECTION).where("dates", "array_contains", day_iso)
    events = []
    for doc in query.stream():
        data = doc.to_dict()
        data["code"] = doc.id
        events.append(data)
    return events


def get_current_event(day_iso=None):
    from services import firebase_service as fs
    events = fs.get_active_events(day_iso)
    return events[0] if events else None


def get_recent_event_template_ids(limit):
    from services import firebase_service as fs
    docs = fs.db.collection(fs.EVENTS_COLLECTION).order_by(
        "generated_at", direction=firestore.Query.DESCENDING
    ).limit(limit).stream()

    ids = []
    for doc in docs:
        template_id = doc.to_dict().get("template_id")
        if template_id:
            ids.append(template_id)
    return ids


def get_last_event_end_date():
    from services import firebase_service as fs
    docs = fs.db.collection(fs.EVENTS_COLLECTION).order_by(
        "generated_at", direction=firestore.Query.DESCENDING
    ).limit(1).stream()
    doc = next(docs, None)
    if not doc:
        return None
    dates = doc.to_dict().get("dates", [])
    if not dates:
        return None
    return parse_iso(normalize_day(dates[-1]))


def get_recent_events(limit=5):
    from services import firebase_service as fs
    docs = fs.db.collection(fs.EVENTS_COLLECTION).order_by(
        "generated_at", direction=firestore.Query.DESCENDING
    ).limit(limit).stream()

    events = []
    for doc in docs:
        data = doc.to_dict()
        data["code"] = doc.id
        data["participants_count"] = fs._count_collection(doc.reference.collection(fs.PARTICIPANTS_SUBCOLLECTION))
        events.append(data)
    return events


def participant_ref(event_code, user_id):
    from services import firebase_service as fs
    return fs.event_ref(event_code).collection(fs.PARTICIPANTS_SUBCOLLECTION).document(str(user_id))


def get_event_participant(event_code, user_id):
    from services import firebase_service as fs
    snapshot = fs.participant_ref(event_code, user_id).get()
    return snapshot.to_dict() if snapshot.exists else None


def begin_event_attempt(event_code, user_id, name, day_iso, max_attempts):
    """Come begin_guess_attempt ma per l'evento: ogni partecipante ha il suo documento,
    quindi due utenti che rispondono insieme non si contendono lo stesso documento."""
    from services import firebase_service as fs
    ref = fs.participant_ref(event_code, user_id)

    @firestore.transactional
    def _attempt(transaction):
        snapshot = ref.get(transaction=transaction)
        data = snapshot.to_dict() if snapshot.exists else {}

        same_day = normalize_day(data.get("last_played_day")) == day_iso
        attempts = data.get("daily_attempts", 0) if same_day else 0
        has_guessed = data.get("has_guessed_today", False) if same_day else False

        if has_guessed:
            return {"ok": False, "reason": "already_guessed"}
        if attempts >= max_attempts:
            return {"ok": False, "reason": "no_attempts", "attempts_used": attempts}

        transaction.set(ref, {
            "telegram_id": user_id,
            "name": name,
            "points": data.get("points", 0),
            "daily_attempts": attempts + 1,
            "has_guessed_today": False,
            "last_played_day": day_iso,
        }, merge=True)
        return {
            "ok": True,
            "attempts_used": attempts + 1,
            "attempts_left": max_attempts - (attempts + 1),
        }

    return _attempt(fs.db.transaction())


def register_event_correct_guess(event_code, user_id, points, day_iso):
    from services import firebase_service as fs
    fs.participant_ref(event_code, user_id).update({
        "points": firestore.Increment(points),
        "has_guessed_today": True,
        "last_played_day": day_iso,
    })


def claim_event_first_correct(event_code, day_iso):
    from services import firebase_service as fs
    ref = fs.event_ref(event_code)
    field = f"daily_data.{day_iso}.first_correct_user"

    @firestore.transactional
    def _claim(transaction):
        snapshot = ref.get(transaction=transaction)
        if not snapshot.exists:
            return False
        day_data = (snapshot.to_dict().get("daily_data") or {}).get(day_iso) or {}
        if day_data.get("first_correct_user"):
            return False
        transaction.update(ref, {field: True})
        return True

    return _claim(fs.db.transaction())


def get_event_leaderboard(event_code, limit=3):
    from services import firebase_service as fs
    query = fs.event_ref(event_code).collection(fs.PARTICIPANTS_SUBCOLLECTION).order_by(
        "points", direction=firestore.Query.DESCENDING
    ).limit(limit)
    return [doc.to_dict() for doc in query.stream()]


def get_event_trophy_day(day_iso=None):
    from services import firebase_service as fs
    day_iso = day_iso or today_iso()
    query = fs.db.collection(fs.EVENTS_COLLECTION).where("trophy_day", "==", day_iso)
    for doc in query.stream():
        data = doc.to_dict()
        data["code"] = doc.id
        return data
    return None


def update_users_trophies(event_doc):
    """Assegna il trofeo ai primi tre dell'evento."""
    from services import firebase_service as fs
    event_code = event_doc.get("code")
    podium = fs.get_event_leaderboard(event_code, limit=3)

    assigned = []
    for position, participant in enumerate(podium, start=1):
        telegram_id = participant.get("telegram_id")
        if not telegram_id:
            continue
        trophy_code = f"{position}_{event_code}"
        fs.add_user_trophy(telegram_id, trophy_code)
        assigned.append((telegram_id, trophy_code))
    return assigned


def update_event(event_code, fields):
    from services import firebase_service as fs
    fs.event_ref(event_code).update(dict(fields))
    logging.info(f"[ADMIN] evento {event_code} aggiornato: {sorted(fields)}")


def delete_event(event_code):
    """Elimina l'evento e i suoi partecipanti: Firestore non cancella le sottocollection
    insieme al documento padre, altrimenti resterebbero documenti orfani."""
    from services import firebase_service as fs
    ref = fs.event_ref(event_code)
    if not ref.get().exists:
        return False
    for participant in ref.collection(fs.PARTICIPANTS_SUBCOLLECTION).stream():
        participant.reference.delete()
    ref.delete()
    logging.info(f"[ADMIN] evento {event_code} eliminato (con i partecipanti)")
    return True


def get_event_participants(event_code, limit=200):
    from services import firebase_service as fs
    query = fs.event_ref(event_code).collection(fs.PARTICIPANTS_SUBCOLLECTION).order_by(
        "points", direction=firestore.Query.DESCENDING
    ).limit(limit)
    participants = []
    for doc in query.stream():
        data = doc.to_dict()
        data["id"] = doc.id
        participants.append(data)
    return participants

