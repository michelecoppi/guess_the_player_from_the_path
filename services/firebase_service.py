"""Accesso a Firestore.

Convenzioni del modello dati (vedi docs/firebase_review.md per il perche'):

- `users/{telegram_id}`: l'id Telegram e' l'id del documento, quindi ogni accesso e' una
  lettura diretta e la creazione e' un upsert atomico (niente utenti duplicati).
- I contatori giornalieri non vengono azzerati da un job notturno: ogni documento porta con
  se' il giorno a cui si riferisce (`last_played_day`), e i contatori valgono zero appena il
  giorno cambia. Costo del reset: nessuno.
- Le date sono salvate in ISO `YYYY-MM-DD` (services/dates.py), cosi' gli id documento sono
  ordinabili e si possono fare query di intervallo.
- Quello che deve essere assegnato "una volta sola" (il bonus al primo che indovina) passa
  da una transazione, non da un controllo seguito da una scrittura.
- I partecipanti a un evento sono documenti separati (`events/{code}/participants/{id}`), non
  una mappa dentro l'evento: niente limite di 1 MB e niente contesa in scrittura.
"""
import logging
import os

import firebase_admin
from firebase_admin import credentials, firestore
from google.api_core.exceptions import GoogleAPICallError

from config import FIREBASE_CREDENTIALS_PATH
from services.dates import (
    normalize_day,
    now_italy,
    parse_iso,
    shift_iso,
    today_iso,
)
from services.i18n import DEFAULT_LANGUAGE
from services.streak import next_streak, streak_bonus

USERS_COLLECTION = "users"
DAILY_PATH_COLLECTION = "daily_path"
EVENTS_COLLECTION = "events"
PARTICIPANTS_SUBCOLLECTION = "participants"
SEASONS_COLLECTION = "seasons"
ADMIN_SETTINGS_COLLECTION = "admin_settings"
DATASET_OVERRIDES_DOC = "dataset_overrides"
FATHER_SON_COLLECTION = "father_son_pairs"
ARCHIVE_SUBCOLLECTION = "archive"
LEAGUES_COLLECTION = "leagues"
MEMBERS_SUBCOLLECTION = "members"
GROUP_ROUNDS_COLLECTION = "group_rounds"
GROUP_PLAYERS_SUBCOLLECTION = "players"


def _credentials():
    """Il file di chiave se c'e', altrimenti le credenziali di default dell'ambiente.

    Il file resta il modo normale (sviluppo e Cloud Run). Il ripiego serve a chi gira senza
    chiave perche' l'identita' gliela da' l'ambiente: il workflow di backup su GitHub
    Actions si autentica con Workload Identity Federation, e una chiave di servizio in un
    secret sarebbe esattamente il file che quel meccanismo esiste per non avere."""
    if FIREBASE_CREDENTIALS_PATH and os.path.exists(FIREBASE_CREDENTIALS_PATH):
        return credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
    logging.info("[FIREBASE] Nessun file di credenziali: uso le credenziali di default dell'ambiente")
    return credentials.ApplicationDefault()


class _LazyFirestoreClient:
    """Inizializza Firebase/Firestore solo al primo utilizzo reale (non all'import del
    modulo). Permette di importare services.firebase_service e i moduli che ne dipendono
    (es. nei test) senza dover avere per forza le credenziali configurate."""

    _client = None

    def _ensure(self):
        if _LazyFirestoreClient._client is None:
            if not firebase_admin._apps:
                firebase_admin.initialize_app(_credentials())
            _LazyFirestoreClient._client = firestore.client()
        return _LazyFirestoreClient._client

    def __getattr__(self, name):
        return getattr(self._ensure(), name)


db = _LazyFirestoreClient()


# ---------------------------------------------------------------------------
# Utenti
# ---------------------------------------------------------------------------

def user_ref(user_id):
    return db.collection(USERS_COLLECTION).document(str(user_id))


def save_user(user_id, first_name, language=DEFAULT_LANGUAGE):
    """Crea l'utente se non esiste. E' una transazione: due /start ravvicinati non possono
    piu' creare due documenti per la stessa persona.

    Se l'utente esiste gia', la lingua passata viene ignorata: resta quella salvata (es.
    cambiata a mano con /language), non quella rilevata dal client in quel momento.
    Ritorna {'created': bool, 'language': lingua effettiva dell'utente}."""
    ref = user_ref(user_id)

    @firestore.transactional
    def _create(transaction):
        snapshot = ref.get(transaction=transaction)
        if snapshot.exists:
            existing = snapshot.to_dict()
            return {"created": False, "language": existing.get("language", DEFAULT_LANGUAGE)}
        transaction.set(ref, {
            "first_name": first_name,
            "telegram_id": user_id,
            "date_created": firestore.SERVER_TIMESTAMP,
            "chat_id": -1,
            "notifications_enabled": False,
            "monthly_points": 0,
            "points_totali": 0,
            "daily_attempts": 0,
            "has_guessed_today": False,
            "last_played_day": None,
            "trophies": [],
            "players_guessed": 0,
            "bonus_first_guessed": 0,
            "last_correct_day": None,
            "current_streak": 0,
            "best_streak": 0,
            "language": language,
        })
        return {"created": True, "language": language}

    return _create(db.transaction())


def get_user_language(user_id):
    data = get_user_data(user_id)
    return (data or {}).get("language", DEFAULT_LANGUAGE)


def set_user_language(user_id, language):
    user_ref(user_id).update({"language": language})


def get_user_data(user_id):
    snapshot = user_ref(user_id).get()
    return snapshot.to_dict() if snapshot.exists else None


def get_user_daily_status(user_id, day_iso=None):
    """Tentativi usati e se ha gia' indovinato **oggi**. I contatori di un giorno passato
    valgono zero senza bisogno di averli azzerati."""
    day_iso = day_iso or today_iso()
    data = get_user_data(user_id)
    if not data:
        return 0, False
    if normalize_day(data.get("last_played_day")) != day_iso:
        return 0, False
    return data.get("daily_attempts", 0), data.get("has_guessed_today", False)


def begin_guess_attempt(user_id, day_iso, max_attempts):
    """Consuma un tentativo in modo atomico e dice se il tentativo e' ammesso.

    Ritorna un dizionario con 'ok' e, quando ok e' False, il motivo:
    'not_registered' | 'already_guessed' | 'no_attempts'.
    """
    ref = user_ref(user_id)

    @firestore.transactional
    def _attempt(transaction):
        snapshot = ref.get(transaction=transaction)
        if not snapshot.exists:
            return {"ok": False, "reason": "not_registered"}

        data = snapshot.to_dict()
        same_day = normalize_day(data.get("last_played_day")) == day_iso
        attempts = data.get("daily_attempts", 0) if same_day else 0
        has_guessed = data.get("has_guessed_today", False) if same_day else False

        if has_guessed:
            return {"ok": False, "reason": "already_guessed"}
        if attempts >= max_attempts:
            return {"ok": False, "reason": "no_attempts", "attempts_used": attempts}

        transaction.update(ref, {
            "daily_attempts": attempts + 1,
            "has_guessed_today": False,
            "last_played_day": day_iso,
        })
        return {
            "ok": True,
            "attempts_used": attempts + 1,
            "attempts_left": max_attempts - (attempts + 1),
        }

    return _attempt(db.transaction())


def register_correct_guess(user_id, points, bonus, day_iso=None, monthly=True):
    """Registra la risposta giusta e aggiorna la striscia di giorni consecutivi.

    E' una transazione perche' la striscia e' un leggi-e-scrivi: va calcolata sul valore
    che c'e' in quel momento, non su uno letto prima. I punti restano incrementi, cosi'
    due scritture ravvicinate non si sovrascrivono.

    Ritorna quanto e' stato assegnato davvero: {'points_awarded', 'streak_bonus',
    'current_streak', 'best_streak'}."""
    day_iso = day_iso or today_iso()
    ref = user_ref(user_id)

    @firestore.transactional
    def _register(transaction):
        snapshot = ref.get(transaction=transaction)
        data = snapshot.to_dict() if snapshot.exists else {}

        streak = next_streak(data.get("last_correct_day"), day_iso, data.get("current_streak", 0))
        extra = streak_bonus(streak)
        awarded = points + extra
        best = max(data.get("best_streak", 0), streak)

        update_data = {
            "points_totali": firestore.Increment(awarded),
            "players_guessed": firestore.Increment(1),
            "has_guessed_today": True,
            "last_played_day": day_iso,
            "last_correct_day": day_iso,
            "current_streak": streak,
            "best_streak": best,
        }
        if bonus > 0:
            update_data["bonus_first_guessed"] = firestore.Increment(1)
        if monthly:
            update_data["monthly_points"] = firestore.Increment(awarded)
        transaction.update(ref, update_data)

        return {
            "points_awarded": awarded,
            "streak_bonus": extra,
            "current_streak": streak,
            "best_streak": best,
        }

    return _register(db.transaction())


def set_user_notifications(user_id, chat_id, enabled):
    user_ref(user_id).update({
        "chat_id": chat_id if enabled else -1,
        "notifications_enabled": bool(enabled),
    })


def get_broadcast_users(reference_day_iso=None):
    """Utenti da avvisare al cambio di giornata, con l'informazione se avevano indovinato
    la sfida del giorno di riferimento (di norma ieri, perche' il messaggio parte a
    mezzanotte)."""
    reference_day_iso = reference_day_iso or shift_iso(today_iso(), -1)
    query = db.collection(USERS_COLLECTION).where("notifications_enabled", "==", True)

    users = []
    for doc in query.stream():
        data = doc.to_dict()
        guessed = (
            data.get("has_guessed_today", False)
            and normalize_day(data.get("last_played_day")) == reference_day_iso
        )
        users.append({
            "chat_id": data.get("chat_id"),
            "has_guessed_today": guessed,
            "language": data.get("language", DEFAULT_LANGUAGE),
        })
    return users


def get_top_users(field="points_totali", limit=10):
    """Solo i primi N, ordinati da Firestore: una manciata di letture invece dell'intera
    collection ad ogni /top."""
    query = db.collection(USERS_COLLECTION).order_by(
        field, direction=firestore.Query.DESCENDING
    ).limit(limit)
    return [_public_user(doc.to_dict()) for doc in query.stream()]


def count_users_ahead(field, value):
    """Quanti utenti hanno piu' punti di 'value': serve a mostrare la posizione di chi e'
    fuori dalla top 10 senza scaricare la classifica intera."""
    query = db.collection(USERS_COLLECTION).where(field, ">", value)
    return _count_collection(query)


def _public_user(data):
    return {
        "telegram_id": data.get("telegram_id"),
        "username": data.get("first_name", "Sconosciuto"),
        "points": data.get("points_totali", 0),
        "monthly_points": data.get("monthly_points", 0),
        "language": data.get("language", DEFAULT_LANGUAGE),
    }


def add_user_trophy(telegram_id, trophy_code):
    user_ref(telegram_id).update({"trophies": firestore.ArrayUnion([trophy_code])})
    logging.info(f"Trofeo {trophy_code} aggiunto per l'utente {telegram_id}")


def reset_monthly_points():
    """Azzera i punti mensili di chi ne ha: girata una volta al mese, in batch."""
    query = db.collection(USERS_COLLECTION).where("monthly_points", ">", 0)
    batch = db.batch()
    count = 0
    for doc in query.stream():
        batch.update(doc.reference, {"monthly_points": 0})
        count += 1
        if count % 400 == 0:  # il limite di un batch Firestore e' 500 operazioni
            batch.commit()
            batch = db.batch()
    if count % 400:
        batch.commit()
    logging.info(f"Punti mensili azzerati per {count} utenti")
    return count


# ---------------------------------------------------------------------------
# Sfida giornaliera
# ---------------------------------------------------------------------------

def daily_path_ref(day_iso):
    return db.collection(DAILY_PATH_COLLECTION).document(day_iso)


def daily_path_exists(day_iso):
    return daily_path_ref(day_iso).get().exists


def get_daily_path(day_iso):
    """La sfida di un giorno, letta direttamente per id documento (la data ISO)."""
    snapshot = daily_path_ref(day_iso).get()
    if not snapshot.exists:
        logging.info(f"Nessuna daily challenge trovata per il giorno {day_iso}")
        return None
    return snapshot.to_dict()


def save_daily_path(day_iso, doc):
    doc = dict(doc)
    doc["day"] = day_iso
    daily_path_ref(day_iso).set(doc)
    logging.info(f"[GENERATOR] Salvata daily_path per {day_iso} (player_id={doc.get('player_id')})")


def get_recent_player_ids(days):
    """Gli id dei giocatori usati (o gia' programmati) nella finestra di anti-ripetizione.
    Query di intervallo sulla data: possibile solo perche' le date sono ISO."""
    start_day = shift_iso(today_iso(), -days)
    docs = db.collection(DAILY_PATH_COLLECTION).where("day", ">=", start_day).stream()

    ids = []
    for doc in docs:
        player_id = doc.to_dict().get("player_id")
        if player_id:
            ids.append(player_id)
    return ids


def claim_daily_first_correct(day_iso):
    """Assegna il bonus 'primo che indovina' a un solo utente, anche se due rispondono
    nello stesso istante. Ritorna True se il bonus spetta a chi ha appena chiamato."""
    ref = daily_path_ref(day_iso)

    @firestore.transactional
    def _claim(transaction):
        snapshot = ref.get(transaction=transaction)
        if not snapshot.exists or snapshot.to_dict().get("first_correct_user"):
            return False
        transaction.update(ref, {"first_correct_user": True})
        return True

    return _claim(db.transaction())


def get_display_name_for_day(day_iso):
    data = get_daily_path(day_iso)
    if not data:
        return None

    solutions = data.get("correct_answers", [])
    full_names = [s for s in solutions if " " in s]
    if full_names:
        return full_names[0].title()
    if solutions:
        return solutions[0].title()
    return None


def get_past_daily_paths(limit=10, before_day_iso=None):
    """Le sfide gia' passate, dalla piu' recente: e' l'elenco dell'archivio.

    L'ordinamento e il filtro sono sullo stesso campo (`day`), quindi non serve nessun
    indice composito: e' possibile solo perche' le date sono ISO."""
    before = before_day_iso or today_iso()
    query = db.collection(DAILY_PATH_COLLECTION).where("day", "<", before).order_by(
        "day", direction=firestore.Query.DESCENDING
    ).limit(limit)
    return [doc.to_dict() for doc in query.stream()]


# ---------------------------------------------------------------------------
# Archivio (sfide passate rigiocate, senza punti)
# ---------------------------------------------------------------------------

def archive_ref(user_id, day_iso):
    return user_ref(user_id).collection(ARCHIVE_SUBCOLLECTION).document(day_iso)


def set_archive_day(user_id, day_iso):
    """Il giorno d'archivio che l'utente sta giocando, o None per tornare a oggi.

    Sta sul documento utente e non in memoria di processo perche' su Cloud Run l'istanza
    puo' sparire fra un messaggio e l'altro: la partita in corso deve sopravvivere.

    Aprire una sfida d'archivio chiude l'allenamento (e viceversa, vedi
    `set_training_day`): con due partite aperte insieme bisognerebbe decidere ad ogni
    messaggio a quale delle due risponde, che e' una regola che nessuno puo' indovinare."""
    user_ref(user_id).update({"archive_day": day_iso, "training_key": None})


def get_archive_result(user_id, day_iso):
    snapshot = archive_ref(user_id, day_iso).get()
    return snapshot.to_dict() if snapshot.exists else None


def get_solved_archive_days(user_id, limit=50):
    query = user_ref(user_id).collection(ARCHIVE_SUBCOLLECTION).where("solved", "==", True).limit(limit)
    return {doc.id for doc in query.stream()}


def begin_archive_attempt(user_id, day_iso, max_attempts):
    """Come begin_guess_attempt, ma su un documento per (utente, giorno d'archivio): qui i
    tentativi non si azzerano a mezzanotte, la sfida e' gia' passata."""
    ref = archive_ref(user_id, day_iso)

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

    return _attempt(db.transaction())


def register_archive_solved(user_id, day_iso, attempts):
    """Nessun punto: l'archivio non deve permettere di scalare la classifica rigiocando il
    passato. Si tiene solo il conto delle sfide recuperate, che finisce in /stats."""
    archive_ref(user_id, day_iso).set(
        {"day": day_iso, "attempts": attempts, "solved": True}, merge=True
    )
    user_ref(user_id).update({"archive_solved": firestore.Increment(1)})


def get_upcoming_daily_paths(limit=7):
    """Le sfide gia' generate, dalla piu' lontana nel futuro: serve a /admin_next."""
    docs = db.collection(DAILY_PATH_COLLECTION).order_by(
        "day", direction=firestore.Query.DESCENDING
    ).limit(limit).stream()
    return [doc.to_dict() for doc in docs]


# ---------------------------------------------------------------------------
# Allenamento (sfide passate, infinite, senza punti)
# ---------------------------------------------------------------------------

def set_training_key(user_id, key):
    """Apre una sessione di allenamento sulla sfida indicata.

    La chiave dice anche da dove viene la sfida (`pool:maldini` o `day:2026-09-07`), quindi
    riprendere la sessione non richiede di indovinare la sorgente.

    Come per l'archivio lo stato sta sul documento utente e non in memoria: su Cloud Run
    l'istanza puo' sparire fra un messaggio e l'altro. Aprire l'allenamento chiude
    l'archivio (e viceversa): due partite aperte contemporaneamente vorrebbero dire
    decidere ad ogni messaggio a quale delle due risponde, che e' una regola che nessuno
    puo' indovinare."""
    user_ref(user_id).update({"training_key": key, "training_attempts": 0, "archive_day": None})


def clear_training_key(user_id):
    user_ref(user_id).update({"training_key": None, "training_attempts": 0})


def register_training_attempt(user_id):
    """Un tentativo di allenamento. Non e' una transazione perche' non c'e' niente da
    proteggere: nessun punto, nessun bonus, e chi si allena e' uno solo davanti alla
    propria chat."""
    user_ref(user_id).update({"training_attempts": firestore.Increment(1)})


def register_training_solved(user_id):
    """Nessun punto, come l'archivio: si tiene solo il conto, che finisce in /stats."""
    user_ref(user_id).update({
        "training_key": None,
        "training_attempts": 0,
        "training_solved": firestore.Increment(1),
    })


# ---------------------------------------------------------------------------
# Partite di gruppo (sfide passate, punteggio solo dentro il gruppo)
# ---------------------------------------------------------------------------

def group_round_ref(chat_id):
    return db.collection(GROUP_ROUNDS_COLLECTION).document(str(chat_id))


def group_player_ref(chat_id, user_id):
    return group_round_ref(chat_id).collection(GROUP_PLAYERS_SUBCOLLECTION).document(str(user_id))


def get_group_round(chat_id):
    snapshot = group_round_ref(chat_id).get()
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
    previous = get_group_round(chat_id) or {}
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
    group_round_ref(chat_id).set(doc)
    logging.info(f"[GROUP] Round {doc['number']} aperto in {chat_id} su {key}")
    return doc


def begin_group_attempt(chat_id, user_id, round_number, name, max_attempts):
    """Consuma un tentativo del giocatore in questo round.

    Un documento per giocatore (come i partecipanti a un evento) e non una mappa dentro il
    round: in un gruppo che risponde a raffica una mappa sola sarebbe un punto di contesa
    in scrittura, e prima o poi il limite di 1 MB."""
    ref = group_player_ref(chat_id, user_id)

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

    return _attempt(db.transaction())


def claim_group_round(chat_id, round_number, user_id, name):
    """Assegna il round a chi ha risposto per primo, una volta sola.

    Stessa transazione del bonus del primo sulla sfida del giorno: in un gruppo due
    risposte giuste nello stesso istante sono la norma, non l'eccezione."""
    ref = group_round_ref(chat_id)

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

    return _claim(db.transaction())


def add_group_points(chat_id, user_id, name, points):
    """I punti restano dentro il gruppo: non toccano ne' la classifica generale ne' quella
    del mese. E' quello che rende la modalita' non farmabile - un gruppo con un account
    secondario non sposta niente di quello che conta."""
    group_player_ref(chat_id, user_id).set({
        "telegram_id": user_id,
        "name": name,
        "points": firestore.Increment(points),
        "rounds_won": firestore.Increment(1),
    }, merge=True)


def get_group_leaderboard(chat_id, limit=10):
    query = (
        group_round_ref(chat_id)
        .collection(GROUP_PLAYERS_SUBCOLLECTION)
        .order_by("points", direction=firestore.Query.DESCENDING)
        .limit(limit)
    )
    return [doc.to_dict() for doc in query.stream()]


# ---------------------------------------------------------------------------
# Eventi
# ---------------------------------------------------------------------------

def event_ref(event_code):
    return db.collection(EVENTS_COLLECTION).document(event_code)


def get_event(event_code):
    snapshot = event_ref(event_code).get()
    if not snapshot.exists:
        return None
    data = snapshot.to_dict()
    data["code"] = snapshot.id
    return data


def event_exists(event_code):
    return event_ref(event_code).get().exists


def save_event(event_code, doc):
    doc = dict(doc)
    doc["code"] = event_code
    event_ref(event_code).set(doc)
    logging.info(f"[GENERATOR] Salvato evento {event_code} ({doc.get('name')})")


def get_active_events(day_iso=None):
    day_iso = day_iso or today_iso()
    query = db.collection(EVENTS_COLLECTION).where("dates", "array_contains", day_iso)
    events = []
    for doc in query.stream():
        data = doc.to_dict()
        data["code"] = doc.id
        events.append(data)
    return events


def get_current_event(day_iso=None):
    events = get_active_events(day_iso)
    return events[0] if events else None


def get_recent_event_template_ids(limit):
    docs = db.collection(EVENTS_COLLECTION).order_by(
        "generated_at", direction=firestore.Query.DESCENDING
    ).limit(limit).stream()

    ids = []
    for doc in docs:
        template_id = doc.to_dict().get("template_id")
        if template_id:
            ids.append(template_id)
    return ids


def get_last_event_end_date():
    docs = db.collection(EVENTS_COLLECTION).order_by(
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
    docs = db.collection(EVENTS_COLLECTION).order_by(
        "generated_at", direction=firestore.Query.DESCENDING
    ).limit(limit).stream()

    events = []
    for doc in docs:
        data = doc.to_dict()
        data["code"] = doc.id
        data["participants_count"] = _count_collection(doc.reference.collection(PARTICIPANTS_SUBCOLLECTION))
        events.append(data)
    return events


def participant_ref(event_code, user_id):
    return event_ref(event_code).collection(PARTICIPANTS_SUBCOLLECTION).document(str(user_id))


def get_event_participant(event_code, user_id):
    snapshot = participant_ref(event_code, user_id).get()
    return snapshot.to_dict() if snapshot.exists else None


def begin_event_attempt(event_code, user_id, name, day_iso, max_attempts):
    """Come begin_guess_attempt ma per l'evento: ogni partecipante ha il suo documento,
    quindi due utenti che rispondono insieme non si contendono lo stesso documento."""
    ref = participant_ref(event_code, user_id)

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

    return _attempt(db.transaction())


def register_event_correct_guess(event_code, user_id, points, day_iso):
    participant_ref(event_code, user_id).update({
        "points": firestore.Increment(points),
        "has_guessed_today": True,
        "last_played_day": day_iso,
    })


def claim_event_first_correct(event_code, day_iso):
    ref = event_ref(event_code)
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

    return _claim(db.transaction())


def get_event_leaderboard(event_code, limit=3):
    query = event_ref(event_code).collection(PARTICIPANTS_SUBCOLLECTION).order_by(
        "points", direction=firestore.Query.DESCENDING
    ).limit(limit)
    return [doc.to_dict() for doc in query.stream()]


def get_event_trophy_day(day_iso=None):
    day_iso = day_iso or today_iso()
    query = db.collection(EVENTS_COLLECTION).where("trophy_day", "==", day_iso)
    for doc in query.stream():
        data = doc.to_dict()
        data["code"] = doc.id
        return data
    return None


def update_users_trophies(event_doc):
    """Assegna il trofeo ai primi tre dell'evento."""
    event_code = event_doc.get("code")
    podium = get_event_leaderboard(event_code, limit=3)

    assigned = []
    for position, participant in enumerate(podium, start=1):
        telegram_id = participant.get("telegram_id")
        if not telegram_id:
            continue
        trophy_code = f"{position}_{event_code}"
        add_user_trophy(telegram_id, trophy_code)
        assigned.append((telegram_id, trophy_code))
    return assigned


# ---------------------------------------------------------------------------
# Leghe private
# ---------------------------------------------------------------------------

def league_ref(code):
    return db.collection(LEAGUES_COLLECTION).document(code)


def member_ref(code, user_id):
    return league_ref(code).collection(MEMBERS_SUBCOLLECTION).document(str(user_id))


def get_league(code):
    snapshot = league_ref(code).get()
    if not snapshot.exists:
        return None
    data = snapshot.to_dict()
    data["code"] = snapshot.id
    return data


def create_league(code, name, owner_id, owner_name):
    """Crea la lega solo se il codice e' libero: la verifica e la scrittura stanno nella
    stessa transazione, altrimenti due creazioni simultanee possono prendersi lo stesso
    codice e una delle due leghe sparisce dentro l'altra."""
    ref = league_ref(code)

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

    if not _create(db.transaction()):
        return False

    member_ref(code, owner_id).set({
        "telegram_id": owner_id,
        "name": owner_name,
        "points": 0,
        "joined_at": firestore.SERVER_TIMESTAMP,
    })
    user_ref(owner_id).update({"leagues": firestore.ArrayUnion([code])})
    logging.info(f"[LEAGUE] Creata lega {code} da {owner_id}")
    return True


def join_league(code, user_id, name, max_members):
    """Iscrive a una lega. Il contatore dei membri si aggiorna in transazione, cosi' il
    limite tiene anche se due persone entrano nello stesso istante."""
    ref = league_ref(code)
    member = member_ref(code, user_id)

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

    result = _join(db.transaction())
    if result == "ok":
        user_ref(user_id).update({"leagues": firestore.ArrayUnion([code])})
    return result


def leave_league(code, user_id):
    ref = league_ref(code)
    member = member_ref(code, user_id)

    @firestore.transactional
    def _leave(transaction):
        if not member.get(transaction=transaction).exists:
            return False
        transaction.delete(member)
        transaction.update(ref, {"members_count": firestore.Increment(-1)})
        return True

    left = _leave(db.transaction())
    if left:
        user_ref(user_id).update({"leagues": firestore.ArrayRemove([code])})
    return left


def get_league_leaderboard(code, limit=20):
    query = league_ref(code).collection(MEMBERS_SUBCOLLECTION).order_by(
        "points", direction=firestore.Query.DESCENDING
    ).limit(limit)
    return [doc.to_dict() for doc in query.stream()]


def add_points_to_leagues(user_id, codes, points, name=None):
    """Somma i punti appena guadagnati nelle leghe dell'utente.

    I punti si tengono sul documento del membro (come per i partecipanti agli eventi):
    cosi' la classifica di una lega e' una query ordinata, invece di una lettura per ogni
    iscritto ad ogni /lega."""
    if not codes or points <= 0:
        return 0

    updated = 0
    for code in codes:
        payload = {"points": firestore.Increment(points)}
        if name:
            payload["name"] = name
        try:
            member_ref(code, user_id).set(payload, merge=True)
            updated += 1
        except GoogleAPICallError:
            logging.exception(f"[LEAGUE] Punti non aggiornati per la lega {code}")
    return updated


# ---------------------------------------------------------------------------
# Stagioni mensili
# ---------------------------------------------------------------------------

def get_or_create_season(month_name, year):
    """La stagione mensile serve a numerare i trofei. Se manca, il reset mensile non deve
    saltare in silenzio (era il comportamento precedente): la creiamo noi, numerandola
    dopo l'ultima esistente."""
    query = db.collection(SEASONS_COLLECTION).where("month", "==", month_name).where("year", "==", year).limit(1)
    for doc in query.stream():
        return doc.to_dict(), False

    existing = db.collection(SEASONS_COLLECTION).order_by(
        "season_number", direction=firestore.Query.DESCENDING
    ).limit(1).stream()
    last = next(existing, None)
    next_number = (last.to_dict().get("season_number", 0) + 1) if last else 1

    season = {
        "month": month_name,
        "year": year,
        "season_number": next_number,
        "created_at": firestore.SERVER_TIMESTAMP,
    }
    db.collection(SEASONS_COLLECTION).document(f"{year}-{month_name}").set(season)
    logging.info(f"[SEASON] Creata stagione mancante {month_name} {year} (numero {next_number})")
    return season, True


# ---------------------------------------------------------------------------
# Amministrazione via Telegram (nessuna dashboard web)
# ---------------------------------------------------------------------------

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
    users_ref = db.collection(USERS_COLLECTION)
    return {
        "users_total": _count_collection(users_ref),
        "users_with_notifications": _count_collection(users_ref.where("notifications_enabled", "==", True)),
        "users_guessed_today": _count_collection(
            users_ref.where("last_played_day", "==", today_iso()).where("has_guessed_today", "==", True)
        ),
    }


def get_blocked_player_ids():
    """Giocatori sospesi a mano dall'admin (dato sbagliato segnalato): esclusi dalla
    selezione automatica senza dover ridistribuire il bot."""
    doc = db.collection(ADMIN_SETTINGS_COLLECTION).document(DATASET_OVERRIDES_DOC).get()
    if not doc.exists:
        return []
    return doc.to_dict().get("blocked_player_ids", [])


def block_player_id(player_id):
    db.collection(ADMIN_SETTINGS_COLLECTION).document(DATASET_OVERRIDES_DOC).set(
        {"blocked_player_ids": firestore.ArrayUnion([player_id])}, merge=True
    )
    logging.info(f"[ADMIN] Giocatore sospeso dalla selezione automatica: {player_id}")


def unblock_player_id(player_id):
    db.collection(ADMIN_SETTINGS_COLLECTION).document(DATASET_OVERRIDES_DOC).set(
        {"blocked_player_ids": firestore.ArrayRemove([player_id])}, merge=True
    )
    logging.info(f"[ADMIN] Giocatore riammesso nella selezione automatica: {player_id}")


def add_father_son_pair(pair):
    """Salva una coppia padre/figlio inviata dall'admin via Telegram (foto + risposte).
    Il campo 'file_id' e' l'identificativo della foto su Telegram: puo' essere rispedito
    come immagine senza doverla ospitare da nessuna parte."""
    doc_ref = db.collection(FATHER_SON_COLLECTION).document()
    payload = dict(pair)
    payload["created_at"] = now_italy()
    payload["used_in_events"] = payload.get("used_in_events", [])
    doc_ref.set(payload)
    logging.info(f"[ADMIN] Coppia padre/figlio salvata: {doc_ref.id}")
    return doc_ref.id


def list_father_son_pairs(limit=50, only_unused=False):
    query = db.collection(FATHER_SON_COLLECTION).limit(limit)
    pairs = []
    for doc in query.stream():
        data = doc.to_dict()
        data["id"] = doc.id
        if only_unused and data.get("used_in_events"):
            continue
        pairs.append(data)
    return pairs


def delete_father_son_pair(pair_id):
    doc_ref = db.collection(FATHER_SON_COLLECTION).document(pair_id)
    if not doc_ref.get().exists:
        return False
    doc_ref.delete()
    logging.info(f"[ADMIN] Coppia padre/figlio eliminata: {pair_id}")
    return True


def mark_father_son_pairs_used(pair_ids, event_code):
    for pair_id in pair_ids:
        db.collection(FATHER_SON_COLLECTION).document(pair_id).update(
            {"used_in_events": firestore.ArrayUnion([event_code])}
        )


# ---------------------------------------------------------------------------
# Amministrazione contenuti (dashboard locale admin_ui.py)
#
# Lettura e modifica dei documenti gia' scritti: la dashboard deve poter correggere una
# sfida sbagliata o spostare un evento senza aprire la console di Firebase. Le scritture
# usano update() e non set(): se il documento non esiste e' un errore da mostrare, non un
# documento nuovo mezzo vuoto creato per sbaglio.
# ---------------------------------------------------------------------------

def get_daily_paths_range(start_day_iso, end_day_iso, limit=180):
    """Le sfide di una finestra di date, in ordine cronologico. Filtro e ordinamento sono
    sullo stesso campo (`day`), quindi non serve nessun indice composito."""
    query = (
        db.collection(DAILY_PATH_COLLECTION)
        .where("day", ">=", start_day_iso)
        .where("day", "<=", end_day_iso)
        .order_by("day")
        .limit(limit)
    )
    return [doc.to_dict() for doc in query.stream()]


def update_daily_path(day_iso, fields):
    """Modifica parziale di una sfida esistente (risposte, difficolta', flag del bonus)."""
    daily_path_ref(day_iso).update(dict(fields))
    logging.info(f"[ADMIN] daily_path {day_iso} aggiornata: {sorted(fields)}")


def delete_daily_path(day_iso):
    ref = daily_path_ref(day_iso)
    if not ref.get().exists:
        return False
    ref.delete()
    logging.info(f"[ADMIN] daily_path {day_iso} eliminata")
    return True


def count_day_winners(day_iso):
    """Quanti utenti hanno indovinato la sfida di quel giorno.

    I contatori giornalieri non vengono azzerati (portano con se' `last_played_day`), quindi
    il numero e' attendibile solo per il giorno corrente: per i giorni passati i documenti
    sono gia' stati sovrascritti dal gioco dei giorni successivi."""
    query = (
        db.collection(USERS_COLLECTION)
        .where("last_played_day", "==", day_iso)
        .where("has_guessed_today", "==", True)
    )
    return _count_collection(query)


def update_event(event_code, fields):
    event_ref(event_code).update(dict(fields))
    logging.info(f"[ADMIN] evento {event_code} aggiornato: {sorted(fields)}")


def delete_event(event_code):
    """Elimina l'evento e i suoi partecipanti: Firestore non cancella le sottocollection
    insieme al documento padre, altrimenti resterebbero documenti orfani."""
    ref = event_ref(event_code)
    if not ref.get().exists:
        return False
    for participant in ref.collection(PARTICIPANTS_SUBCOLLECTION).stream():
        participant.reference.delete()
    ref.delete()
    logging.info(f"[ADMIN] evento {event_code} eliminato (con i partecipanti)")
    return True


def get_event_participants(event_code, limit=200):
    query = event_ref(event_code).collection(PARTICIPANTS_SUBCOLLECTION).order_by(
        "points", direction=firestore.Query.DESCENDING
    ).limit(limit)
    participants = []
    for doc in query.stream():
        data = doc.to_dict()
        data["id"] = doc.id
        participants.append(data)
    return participants


def list_leagues(limit=50):
    query = db.collection(LEAGUES_COLLECTION).order_by(
        "members_count", direction=firestore.Query.DESCENDING
    ).limit(limit)
    leagues = []
    for doc in query.stream():
        data = doc.to_dict()
        data["code"] = doc.id
        leagues.append(data)
    return leagues


def update_user_fields(user_id, fields):
    """Correzione manuale di un documento utente dalla dashboard (punti, striscia, lingua).
    Volutamente senza Increment: dalla dashboard si scrive il valore che si vuole vedere."""
    user_ref(user_id).update(dict(fields))
    logging.info(f"[ADMIN] utente {user_id} aggiornato: {sorted(fields)}")


def find_users_by_first_name(prefix, limit=20):
    """Ricerca per prefisso del nome: e' una query di intervallo su un solo campo, quindi
    costa come una lettura ordinata e non richiede indici aggiuntivi."""
    if not prefix:
        return []
    query = (
        db.collection(USERS_COLLECTION)
        .order_by("first_name")
        .start_at([prefix])
        .end_at([prefix + ""])
        .limit(limit)
    )
    return [doc.to_dict() for doc in query.stream()]


def get_archive_days(user_id, limit=100):
    """Tutte le sfide d'archivio giocate da un utente (anche quelle non risolte)."""
    query = user_ref(user_id).collection(ARCHIVE_SUBCOLLECTION).limit(limit)
    days = []
    for doc in query.stream():
        data = doc.to_dict()
        data["day"] = data.get("day") or doc.id
        days.append(data)
    return sorted(days, key=lambda d: d["day"], reverse=True)
