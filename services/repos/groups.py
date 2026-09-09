"""Firestore groups repository. Shared dependencies live in the compatibility facade."""
import logging

from firebase_admin import firestore


def group_round_ref(chat_id):
    from services import firebase_service as fs
    return fs.db.collection(fs.GROUP_ROUNDS_COLLECTION).document(str(chat_id))


def group_player_ref(chat_id, user_id):
    from services import firebase_service as fs
    return fs.group_round_ref(chat_id).collection(fs.GROUP_PLAYERS_SUBCOLLECTION).document(str(user_id))


def get_group_round(chat_id):
    from services import firebase_service as fs
    snapshot = fs.group_round_ref(chat_id).get()
    return snapshot.to_dict() if snapshot.exists else None


def start_group_round(chat_id, challenge, recent_kept=30):
    """Apre un round nuovo e ritorna il documento salvato.

    Sul round si copiano le risposte accettate, la difficolta' e il `player_id`: cosi' ogni
    tentativo del gruppo costa la lettura del round e basta, invece di quella del round
    **piu'** quella della sfida originale. Il percorso di carriera invece non si copia: si
    ridisegna al momento, e duplicarlo farebbe crescere un documento che viene riletto ad
    ogni risposta.

    `number` e' il contatore dei round del gruppo: serve ad azzerare i tentativi dei
    giocatori senza scrivere su ogni loro documento (chi ha un numero vecchio riparte da
    zero da solo, come i contatori giornalieri con `last_played_day`)."""
    from services import firebase_service as fs
    previous = fs.get_group_round(chat_id) or {}
    key = challenge["key"]
    recent = [entry for entry in previous.get("recent_keys", []) if entry != key]
    recent.append(key)

    doc = {
        "chat_id": chat_id,
        "number": previous.get("number", 0) + 1,
        "key": key,
        "player_id": challenge.get("player_id"),
        "difficulty": challenge.get("difficulty"),
        "correct_answers": challenge.get("correct_answers", []),
        "solved_by": None,
        "solved_name": None,
        "started_at": firestore.SERVER_TIMESTAMP,
        "recent_keys": recent[-recent_kept:],
    }
    fs.group_round_ref(chat_id).set(doc)
    logging.info(f"[GROUP] Round {doc['number']} aperto in {chat_id} su {key}")
    return doc


def begin_group_attempt(chat_id, user_id, round_number, name, max_attempts):
    """Consuma un tentativo del giocatore in questo round.

    Un documento per giocatore (come i partecipanti a un evento) e non una mappa dentro il
    round: in un gruppo che risponde a raffica una mappa sola sarebbe un punto di contesa
    in scrittura, e prima o poi il limite di 1 MB."""
    from services import firebase_service as fs
    ref = fs.group_player_ref(chat_id, user_id)

    @firestore.transactional
    def _attempt(transaction):
        snapshot = ref.get(transaction=transaction)
        data = snapshot.to_dict() if snapshot.exists else {}

        # Tentativi di un round precedente: valgono zero senza averli azzerati.
        same_round = data.get("round") == round_number
        attempts = data.get("attempts", 0) if same_round else 0

        if attempts >= max_attempts:
            return {"ok": False, "reason": "no_attempts"}

        transaction.set(ref, {
            "telegram_id": user_id,
            "name": name,
            "round": round_number,
            "attempts": attempts + 1,
            "points": data.get("points", 0),
            "rounds_won": data.get("rounds_won", 0),
        }, merge=True)
        return {"ok": True, "attempts_used": attempts + 1, "attempts_left": max_attempts - (attempts + 1)}

    return _attempt(fs.db.transaction())


def claim_group_round(chat_id, round_number, user_id, name):
    """Assegna il round a chi ha risposto per primo, una volta sola.

    Stessa transazione del bonus del primo sulla sfida del giorno: in un gruppo due
    risposte giuste nello stesso istante sono la norma, non l'eccezione."""
    from services import firebase_service as fs
    ref = fs.group_round_ref(chat_id)

    @firestore.transactional
    def _claim(transaction):
        snapshot = ref.get(transaction=transaction)
        if not snapshot.exists:
            return False
        data = snapshot.to_dict()
        if data.get("number") != round_number or data.get("solved_by"):
            return False
        transaction.update(ref, {"solved_by": user_id, "solved_name": name})
        return True

    return _claim(fs.db.transaction())


def add_group_points(chat_id, user_id, name, points):
    """I punti restano dentro il gruppo: non toccano ne' la classifica generale ne' quella
    del mese. E' quello che rende la modalita' non farmabile - un gruppo con un account
    secondario non sposta niente di quello che conta."""
    from services import firebase_service as fs
    fs.group_player_ref(chat_id, user_id).set({
        "telegram_id": user_id,
        "name": name,
        "points": firestore.Increment(points),
        "rounds_won": firestore.Increment(1),
    }, merge=True)


def get_group_leaderboard(chat_id, limit=10):
    from services import firebase_service as fs
    query = (
        fs.group_round_ref(chat_id)
        .collection(fs.GROUP_PLAYERS_SUBCOLLECTION)
        .order_by("points", direction=firestore.Query.DESCENDING)
        .limit(limit)
    )
    return [doc.to_dict() for doc in query.stream()]

