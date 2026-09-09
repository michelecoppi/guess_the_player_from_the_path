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
- Il documento utente ha **tutti** i campi fin dalla creazione, e `/start` completa quelli
  che mancano a chi si era registrato prima che esistessero (`USER_FIELD_DEFAULTS`): un campo
  assente non e' equivalente a uno a zero, perche' una query ordinata o di disuguaglianza
  salta i documenti in cui il campo non c'e'.
- I partecipanti a un evento sono documenti separati (`events/{code}/participants/{id}`), non
  una mappa dentro l'evento: niente limite di 1 MB e niente contesa in scrittura.
"""
import copy
import logging
import os
import time
from threading import Lock
from typing import Any

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
from services.i18n import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES
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
HISTORY_SUBCOLLECTION = "history"
LEAGUES_COLLECTION = "leagues"
MEMBERS_SUBCOLLECTION = "members"
# Gli acquisti in Stelle stanno in una collection loro, con l'id della transazione Telegram
# come id documento: e' l'unico dato che Telegram ci ridara' se un giorno bisogna rimborsare,
# e cercarlo dentro i documenti utente vorrebbe dire scorrerli tutti.
PURCHASES_COLLECTION = "purchases"
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
    _lock = Lock()

    def _ensure(self):
        if _LazyFirestoreClient._client is None:
            with _LazyFirestoreClient._lock:
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


# Il documento utente "completo", campo per campo, con il valore che vale come "non ha mai
# fatto niente". E' la sola definizione: la usano sia la creazione (/start di chi arriva
# adesso) sia il ripristino dei documenti vecchi, cosi' non possono divergere.
#
# Perche' serve un ripristino: i campi si sono aggiunti col tempo (la lingua, la striscia,
# le sessioni di archivio/allenamento/evento) e chi si era registrato prima e' rimasto senza.
# `save_user` sul documento gia' esistente non scriveva niente, quindi quei campi non
# comparivano **mai**: /start rispondeva in italiano a un utente inglese (lingua assente ->
# ripiego sul default) mentre i bottoni del menu uscivano nella lingua del client, e la
# lingua rilevata non veniva salvata nemmeno allora.
# L'annotazione serve a mypy: da quando c'e' `cosmetics` i valori non sono piu' tutti
# dello stesso tipo, e senza tipo esplicito l'inferenza si ferma.
USER_FIELD_DEFAULTS: dict[str, Any] = {
    "chat_id": -1,
    "notifications_enabled": False,
    "monthly_points": 0,
    "points_totali": 0,
    "daily_attempts": 0,
    "daily_hints": 0,
    "has_guessed_today": False,
    "last_played_day": None,
    "trophies": [],
    "players_guessed": 0,
    "bonus_first_guessed": 0,
    "solved_in": {},
    "last_correct_day": None,
    "current_streak": 0,
    "best_streak": 0,
    "archive_day": None,
    "archive_solved": 0,
    "training_key": None,
    "training_attempts": 0,
    "training_solved": 0,
    "event_key": None,
    "leagues": [],
    # Cosmetici comprati in Stelle, traguardi guadagnati giocando, trofei appesi al profilo,
    # e cosa ha addosso adesso.
    # `owned` non elenca gli oggetti gratuiti: quelli li hanno tutti per definizione
    # (services/shop.py), e scriverli qui vorrebbe dire ripassare su ogni utente ogni volta
    # che se ne aggiunge uno. `earned` invece si scrive, ed e' separato da `owned` perche' i
    # due rispondono a domande diverse: da `owned` si ritira quando si rimborsa un acquisto.
    "cosmetics": {"owned": [], "earned": [], "pinned": [], "equipped": {}},
}


def new_user_document(user_id, first_name, language=DEFAULT_LANGUAGE):
    """Il documento di un utente appena registrato."""
    document = copy.deepcopy(USER_FIELD_DEFAULTS)
    document.update({
        "first_name": first_name,
        "telegram_id": user_id,
        "date_created": firestore.SERVER_TIMESTAMP,
        "language": language,
    })
    return document


def missing_user_fields(data, user_id=None, first_name=None, language=None):
    """I campi da aggiungere a un documento utente gia' esistente, e nient'altro.

    Non tocca mai un campo che c'e': punti, trofei e lingua scelta a mano restano quelli.
    Un campo assente vale come "mai valorizzato", quindi scriverci il default non cambia il
    comportamento di nessuna funzione - le rende solo tutte interrogabili (un `order_by` su
    un campo assente salta il documento) e riporta l'utente vecchio allo stesso stato di uno
    appena registrato.

    `language` si passa solo quando si sa **quale** lingua scrivere, cioe' da /start, che ha
    sotto mano il client di chi lo sta eseguendo. Senza, il campo resta assente: indovinare
    una lingua a caso sarebbe peggio del ripiego che c'e' gia' (chi legge una lingua assente
    usa quella del client Telegram).

    Funzione pura: si prova senza Firestore.
    """
    missing = {
        field: copy.deepcopy(default)
        for field, default in USER_FIELD_DEFAULTS.items()
        if field not in data
    }

    if not data.get("first_name") and first_name:
        missing["first_name"] = first_name
    if data.get("telegram_id") is None and user_id is not None:
        missing["telegram_id"] = user_id
    # Una lingua fuori da quelle supportate (o vuota) e' come non averla: `t()` ci ripiega
    # comunque sul default ad ogni messaggio, tanto vale scrivere quella rilevata.
    if language and data.get("language") not in SUPPORTED_LANGUAGES:
        missing["language"] = language
    return missing


def save_user(user_id, first_name, language=DEFAULT_LANGUAGE):
    """Crea l'utente se non esiste, e completa il documento se gli mancano dei campi.

    E' una transazione: due /start ravvicinati non possono piu' creare due documenti per la
    stessa persona, ne' ripristinare gli stessi campi due volte.

    Se l'utente esiste gia', la lingua passata viene ignorata: resta quella salvata (es.
    cambiata a mano con /language), non quella rilevata dal client in quel momento. Viene
    usata solo se l'utente una lingua valida non ce l'ha, il che per i documenti vecchi era
    la norma.

    Ritorna {'created': bool, 'language': lingua effettiva dell'utente, 'repaired': campi
    aggiunti adesso}."""
    ref = user_ref(user_id)

    @firestore.transactional
    def _create(transaction):
        snapshot = ref.get(transaction=transaction)
        if not snapshot.exists:
            transaction.set(ref, new_user_document(user_id, first_name, language))
            return {"created": True, "language": language, "repaired": []}

        existing = snapshot.to_dict() or {}
        missing = missing_user_fields(
            existing, user_id=user_id, first_name=first_name, language=language
        )
        if missing:
            transaction.update(ref, missing)
            logging.info(f"[USERS] {user_id}: campi ripristinati {sorted(missing)}")
        return {
            "created": False,
            "language": missing.get("language") or existing.get("language", DEFAULT_LANGUAGE),
            "repaired": sorted(missing),
        }

    return _create(db.transaction())


def get_user_language(user_id):
    data = get_user_data(user_id)
    return (data or {}).get("language", DEFAULT_LANGUAGE)


def set_user_language(user_id, language):
    user_ref(user_id).update({"language": language})


def get_user_data(user_id):
    snapshot = user_ref(user_id).get()
    return snapshot.to_dict() if snapshot.exists else None


def delete_user_data(user_id):
    """Cancella dati personali e di gioco, conservando i registri degli acquisti."""
    user_id = int(user_id)
    ref = user_ref(user_id)
    snapshot = ref.get()
    user_data = snapshot.to_dict() if snapshot.exists else {}
    deleted = {"profile": 0, "archive": 0, "history": 0, "leagues": 0,
               "events": 0, "groups": 0}

    # Firestore non elimina le sotto-collezioni insieme al documento padre.
    for subcollection, key in (
        (ARCHIVE_SUBCOLLECTION, "archive"),
        (HISTORY_SUBCOLLECTION, "history"),
    ):
        for doc in ref.collection(subcollection).stream():
            doc.reference.delete()
            deleted[key] += 1

    # Uscire tramite la normale operazione mantiene corretto members_count.
    for code in dict.fromkeys(user_data.get("leagues") or []):
        league = get_league(code)
        if leave_league(code, user_id):
            deleted["leagues"] += 1
        if league and league.get("owner_id") == user_id:
            league_ref(code).update({"owner_id": None})

    # Elimina anche copie orfane o create prima dell'elenco users.leagues.
    for collection_name, key in (
        (PARTICIPANTS_SUBCOLLECTION, "events"),
        (GROUP_PLAYERS_SUBCOLLECTION, "groups"),
    ):
        query = db.collection_group(collection_name).where("telegram_id", "==", user_id)
        for doc in query.stream():
            doc.reference.delete()
            deleted[key] += 1

    # Per le iscrizioni orfane va corretto anche il contatore della lega.
    orphan_members = db.collection_group(MEMBERS_SUBCOLLECTION).where(
        "telegram_id", "==", user_id
    )
    for doc in orphan_members.stream():
        league = doc.reference.parent.parent
        doc.reference.delete()
        league.update({"members_count": firestore.Increment(-1)})
        deleted["leagues"] += 1

    # Il round corrente conserva sul padre nome e id dell'ultimo vincitore.
    query = db.collection(GROUP_ROUNDS_COLLECTION).where("solved_by", "==", user_id)
    for doc in query.stream():
        doc.reference.update({"solved_by": None, "solved_name": None})

    if snapshot.exists:
        ref.delete()
        deleted["profile"] = 1
    logging.info(f"[PRIVACY] Dati utente {user_id} cancellati: {deleted}")
    return deleted


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

    Fra i dati di ritorno c'e' anche `hints_used`, cioe' quanti indizi l'utente ha chiesto
    oggi: serve a scalare i punti se il tentativo e' quello giusto. Viene da qui e non da una
    lettura a parte perche' la transazione il documento lo sta gia' leggendo, e perche' un
    indizio preso **dopo** la lettura del chiamante non deve poter passare gratis.
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
        hints = data.get("daily_hints", 0) if same_day else 0

        if has_guessed:
            return {"ok": False, "reason": "already_guessed"}
        if attempts >= max_attempts:
            return {"ok": False, "reason": "no_attempts", "attempts_used": attempts, "hints_used": hints}

        transaction.update(ref, {
            "daily_attempts": attempts + 1,
            "has_guessed_today": False,
            "last_played_day": day_iso,
        })
        return {
            "ok": True,
            "attempts_used": attempts + 1,
            "attempts_left": max_attempts - (attempts + 1),
            "hints_used": hints,
        }

    return _attempt(db.transaction())


def take_daily_hint(user_id, day_iso, max_hints, max_attempts):
    """Consuma un indizio sulla sfida di oggi e dice quale spetta.

    Transazione per lo stesso motivo del tentativo: due tocchi rapidi sul bottone non devono
    valere un indizio solo (l'utente pagherebbe due punti per uno) ne' due volte lo stesso.

    Gli indizi si sbloccano **dopo** un tentativo sbagliato: senza questa condizione
    diventerebbero il modo piu' comodo per farsi dire nazionalita' e ruolo di ogni sfida
    senza mai giocarla. Come per i tentativi, il contatore si azzera da solo al cambio di
    giorno (`last_played_day`): non c'e' niente da ripulire a mezzanotte.

    Ritorna {'ok': True, 'index', 'hints_used'} oppure {'ok': False, 'reason'} con
    'not_registered' | 'needs_attempt' | 'already_guessed' | 'no_attempts' | 'no_more'.
    """
    ref = user_ref(user_id)

    @firestore.transactional
    def _take(transaction):
        snapshot = ref.get(transaction=transaction)
        if not snapshot.exists:
            return {"ok": False, "reason": "not_registered"}

        data = snapshot.to_dict()
        same_day = normalize_day(data.get("last_played_day")) == day_iso
        attempts = data.get("daily_attempts", 0) if same_day else 0
        has_guessed = data.get("has_guessed_today", False) if same_day else False
        hints = data.get("daily_hints", 0) if same_day else 0

        if has_guessed:
            return {"ok": False, "reason": "already_guessed"}
        if attempts <= 0:
            return {"ok": False, "reason": "needs_attempt"}
        if attempts >= max_attempts:
            # Bottone vecchio premuto a tentativi finiti: l'indizio non servirebbe a niente
            # e costerebbe comunque un punto.
            return {"ok": False, "reason": "no_attempts"}
        if hints >= max_hints:
            return {"ok": False, "reason": "no_more"}

        transaction.update(ref, {"daily_hints": hints + 1, "last_played_day": day_iso})
        return {"ok": True, "index": hints + 1, "hints_used": hints + 1}

    return _take(db.transaction())


# ---------------------------------------------------------------------------
# I traguardi del negozio
#
# Un traguardo (services/shop.py, gli oggetti con `achievement`) si ricava da un contatore.
# Finche' resta solo un calcolo e' anche reversibile: basta alzare un obiettivo in
# data/shop.json, o rinominare un id, e chi stava sotto la soglia nuova si ritrova senza un
# distintivo che aveva gia' guadagnato - senza aver fatto niente, e senza che nessuno se ne
# accorga, perche' e' una modifica a un file di dati e non a una riga di codice.
#
# Quindi si scrivono. Una volta sola, nel momento in cui il contatore che li fa scattare si
# muove: e' l'unico istante in cui puo' succedere, e in quell'istante stiamo gia' scrivendo.
# Vanno in `cosmetics.earned` e non in `cosmetics.owned` perche' i due elenchi rispondono a
# domande diverse: da `owned` si ritira quando si rimborsa un acquisto (`revoke_purchase`),
# e da un traguardo non c'e' niente da ritirare.
# ---------------------------------------------------------------------------

# I contatori su cui un traguardo puo' appoggiarsi: quelli che una delle scritture qui sotto
# raccoglie. Un obiettivo appeso a un campo che non e' in questa lista non verrebbe mai messo
# al sicuro, e resterebbe per sempre alla merce' del calcolo. C'e' un test che lo verifica.
HARVESTED_FIELDS = frozenset({
    "points_totali", "monthly_points", "players_guessed", "current_streak", "best_streak",
    "bonus_first_guessed", "archive_solved", "training_solved",
})


def _newly_earned(data, **after):
    """I traguardi che scattano con questi contatori aggiornati e non sono ancora scritti.

    L'import sta qui dentro e non in cima al modulo perche' services/shop.py importa questo:
    al momento della chiamata sono caricati tutti e due, all'import no."""
    from services import shop
    return shop.newly_earned({**(data or {}), **after})


def _bump_counters(user_id, updates, **deltas):
    """Muove dei contatori e, nella stessa scrittura, mette al sicuro i traguardi che questo
    fa scattare.

    Non e' una transazione e non serve che lo sia: `Increment` e `ArrayUnion` si applicano
    sul server e non si perdono se due scritture si accavallano. La lettura serve solo a
    sapere **quali** traguardi sono scattati; se torna leggermente vecchia il traguardo si
    scrive alla partita dopo, e nel frattempo `owned_ids` lo calcola comunque.

    Ritorna gli id appena messi al sicuro, cosi' chi chiama puo' dirlo all'utente."""
    ref = user_ref(user_id)
    snapshot = ref.get()
    data = snapshot.to_dict() if snapshot.exists else {}
    after = {field: int(data.get(field, 0) or 0) + delta for field, delta in deltas.items()}
    fresh = _newly_earned(data, **after)
    if fresh:
        updates = {**updates, "cosmetics.earned": firestore.ArrayUnion(fresh)}
        logging.info(f"[SHOP] {user_id} ha guadagnato {', '.join(fresh)}")
    ref.update(updates)
    return fresh


def register_correct_guess(user_id, points, bonus, day_iso=None, monthly=True, attempts=None):
    """Registra la risposta giusta e aggiorna la striscia di giorni consecutivi.

    E' una transazione perche' la striscia e' un leggi-e-scrivi: va calcolata sul valore
    che c'e' in quel momento, non su uno letto prima. I punti restano incrementi, cosi'
    due scritture ravvicinate non si sovrascrivono.

    `attempts` (in quanti tentativi ci e' arrivato) alimenta l'istogramma "di solito la
    prendo al secondo" della mini app. E' un contatore per valore dentro `solved_in`, non una
    lista di partite: costa niente da scrivere e niente da leggere, e non cresce mai.

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
        if attempts:
            update_data[f"solved_in.{attempts}"] = firestore.Increment(1)
        if monthly:
            update_data["monthly_points"] = firestore.Increment(awarded)

        # I traguardi che questa giocata fa scattare si scrivono qui dentro, insieme ai
        # contatori che li hanno mossi: sono lo stesso fatto, e separarli lascerebbe una
        # finestra in cui il contatore e' salito e il distintivo no. La lettura c'e' gia'
        # (`data`), quindi non costa niente.
        earned = _newly_earned(
            data,
            points_totali=int(data.get("points_totali", 0) or 0) + awarded,
            monthly_points=int(data.get("monthly_points", 0) or 0) + (awarded if monthly else 0),
            players_guessed=int(data.get("players_guessed", 0) or 0) + 1,
            bonus_first_guessed=int(data.get("bonus_first_guessed", 0) or 0) + (1 if bonus > 0 else 0),
            current_streak=streak,
            best_streak=best,
        )
        if earned:
            update_data["cosmetics.earned"] = firestore.ArrayUnion(earned)
            logging.info(f"[SHOP] {user_id} ha guadagnato {', '.join(earned)}")
        transaction.update(ref, update_data)

        return {
            "points_awarded": awarded,
            "streak_bonus": extra,
            "current_streak": streak,
            "best_streak": best,
            "earned": earned,
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
        # I cosmetici viaggiano con la classifica perche' e' li' che si vede il distintivo,
        # e il documento e' gia' stato letto per i punti: non costa una lettura in piu'.
        # Qui restano gli id grezzi, il simbolo lo ricava chi disegna (services/shop.py):
        # questo modulo non deve sapere niente del catalogo, o non potrebbe piu' essere
        # quello che il catalogo chiama per scrivere.
        "cosmetics": data.get("cosmetics") or {},
        "players_guessed": data.get("players_guessed", 0),
        "best_streak": data.get("best_streak", 0),
        "archive_solved": data.get("archive_solved", 0),
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


def register_daily_outcome(day_iso, solved):
    """Tiene il conto di quanti hanno **giocato** e quanti hanno **indovinato** una giornata.

    Serve alla riga "l'ha indovinato il 41%" che compare nella soluzione e nel messaggio di
    mezzanotte. E' la sola statistica del gioco che dice qualcosa sulla sfida invece che sul
    singolo, ed e' anche quella che rende interessante un risultato condiviso.

    Perche' due contatori sul documento della sfida e non una query sugli utenti: i contatori
    giornalieri dell'utente non vengono azzerati ma sovrascritti dal giorno dopo
    (`last_played_day`), quindi contarli a posteriori funziona **solo per oggi** - ed e'
    esattamente il giorno di cui non serve saperlo. Qui invece il numero resta scritto dove
    sta la sfida, e vale per sempre.

    `solved=None` conta solo il giocatore (primo tentativo della giornata), `solved=True`
    conta anche la risposta giusta. Sono due `Increment`: nessuna lettura, e due risposte
    nello stesso istante non si sovrascrivono."""
    fields = {}
    if solved:
        fields["solved_count"] = firestore.Increment(1)
    else:
        fields["players_count"] = firestore.Increment(1)
    try:
        daily_path_ref(day_iso).update(fields)
    except GoogleAPICallError as e:
        # Una statistica non deve mai far fallire una risposta giusta.
        logging.warning(f"[STATS] contatore di {day_iso} non aggiornato: {e}")


def get_daily_stats(day_iso):
    """Quanti hanno giocato e quanti hanno indovinato quella giornata: (players, solved).

    (0, 0) per le giornate precedenti all'introduzione dei contatori: chi mostra il dato
    deve trattarlo come "non lo sappiamo", non come "non l'ha indovinato nessuno"."""
    data = get_daily_path(day_iso) or {}
    return data.get("players_count", 0), data.get("solved_count", 0)


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

    Aprire una sfida d'archivio chiude l'allenamento e l'evento (e viceversa, vedi
    `set_training_key` e `set_event_key`): con due partite aperte insieme bisognerebbe
    decidere ad ogni messaggio a quale delle due risponde, che e' una regola che nessuno
    puo' indovinare."""
    user_ref(user_id).update({"archive_day": day_iso, "training_key": None, "event_key": None})


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
    passato. Si tiene solo il conto delle sfide recuperate, che finisce in /stats.

    Ritorna i traguardi che questa sfida recuperata ha fatto scattare."""
    archive_ref(user_id, day_iso).set(
        {"day": day_iso, "attempts": attempts, "solved": True}, merge=True
    )
    return _bump_counters(user_id, {"archive_solved": firestore.Increment(1)}, archive_solved=1)


def history_ref(user_id, day_iso):
    return user_ref(user_id).collection(HISTORY_SUBCOLLECTION).document(day_iso)


def record_daily_history(user_id, day_iso, solved, attempts, hints=0):
    """Com'e' andata **quella** giornata a **quell'** utente: un documento per giorno.

    Serve al calendario della mini app, che deve poter dire "questa l'hai presa al secondo,
    questa l'hai persa, questa non l'hai giocata". Dai contatori sul documento utente non si
    ricava: quelli portano un giorno solo (`last_played_day`) e il giorno dopo sono
    sovrascritti.

    Si scrive una volta sola per giornata, quando la giornata si **chiude** per quell'utente
    (indovinata o tentativi finiti): non ad ogni tentativo."""
    history_ref(user_id, day_iso).set({
        "day": day_iso,
        "solved": bool(solved),
        "attempts": attempts,
        "hints": hints,
    })


def get_daily_history(user_id, limit=60):
    """Lo storico dal giorno piu' recente. Il limite e' quello del calendario mostrato: e'
    una query sola, e la si fa solo quando la mini app apre la scheda dell'archivio."""
    query = (
        user_ref(user_id).collection(HISTORY_SUBCOLLECTION)
        .order_by("day", direction=firestore.Query.DESCENDING)
        .limit(limit)
    )
    return [doc.to_dict() for doc in query.stream()]


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
    l'archivio e l'evento (e viceversa): due partite aperte contemporaneamente vorrebbero
    dire decidere ad ogni messaggio a quale delle due risponde, che e' una regola che
    nessuno puo' indovinare."""
    user_ref(user_id).update({
        "training_key": key, "training_attempts": 0, "archive_day": None, "event_key": None,
    })


def clear_training_key(user_id):
    user_ref(user_id).update({"training_key": None, "training_attempts": 0})


def register_training_attempt(user_id):
    """Un tentativo di allenamento. Non e' una transazione perche' non c'e' niente da
    proteggere: nessun punto, nessun bonus, e chi si allena e' uno solo davanti alla
    propria chat."""
    user_ref(user_id).update({"training_attempts": firestore.Increment(1)})


def register_training_solved(user_id):
    """Nessun punto, come l'archivio: si tiene solo il conto, che finisce in /stats.

    Ritorna i traguardi che questo allenamento ha fatto scattare."""
    return _bump_counters(user_id, {
        "training_key": None,
        "training_attempts": 0,
        "training_solved": firestore.Increment(1),
    }, training_solved=1)


def set_event_key(user_id, key):
    """Apre una sessione sull'evento in corso, cosi' che i messaggi liberi valgano per la
    sfida dell'evento e non per quella del giorno.

    La chiave e' `<codice evento>:<giorno>`: porta con se' **quale** giornata dell'evento si
    sta giocando, quindi a mezzanotte la sessione di ieri non risponde piu' per quella di
    oggi e va riaperta - che e' esattamente quello che si vuole, perche' l'immagine da
    indovinare e' cambiata.

    Come archivio e allenamento chiude le altre due sessioni: le tre si escludono."""
    user_ref(user_id).update({
        "event_key": key, "archive_day": None, "training_key": None, "training_attempts": 0,
    })


def clear_event_key(user_id):
    user_ref(user_id).update({"event_key": None})


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
# Negozio (acquisti in Stelle di Telegram)
#
# Un acquisto lascia due tracce: gli oggetti sul documento utente (e' li' che il gioco li
# cerca) e una riga in `purchases` con l'id della transazione Telegram come id documento.
# La riga serve a due cose che il documento utente non sa fare: rimborsare (l'API vuole
# quell'id) e accorgersi che uno stesso pagamento sta arrivando due volte.
# ---------------------------------------------------------------------------

def purchase_ref(charge_id):
    return db.collection(PURCHASES_COLLECTION).document(str(charge_id))


def deliver_purchase(user_id, charge_id, item_id, granted_ids, stars, day_iso=None):
    """Consegna gli oggetti comprati e registra l'acquisto. Una volta sola.

    L'idempotenza non e' un lusso: se il webhook non risponde in tempo Telegram rispedisce
    l'update, e una consegna doppia lascerebbe due righe nel registro da cui si rimborsa.
    L'id documento e' `telegram_payment_charge_id`, quindi la seconda consegna trova la riga
    gia' scritta e non fa niente.

    `set(..., merge=True)` e non `update()`: fonde la mappa `cosmetics` campo per campo, cosi'
    quello che l'utente ha addosso resta dov'e' e non serve che il campo esista gia'.

    Ritorna True se ha consegnato adesso, False se era gia' stato consegnato."""
    ref = purchase_ref(charge_id)
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
            user_ref(user_id),
            {"cosmetics": {"owned": firestore.ArrayUnion(granted)}, "shop_checkout": None},
            merge=True,
        )
        return True

    delivered = _deliver(db.transaction())
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
    user_ref(user_id).set({"cosmetics": {"pinned": list(codes)}}, merge=True)


def equip_cosmetic(user_id, kind, item_id):
    """Cambia quello che l'utente ha addosso in uno slot. Non controlla se lo possiede: la
    regola sta in services/shop.py, qui si scrive e basta."""
    user_ref(user_id).set({"cosmetics": {"equipped": {kind: item_id}}}, merge=True)


def equip_look(user_id, slots):
    user_ref(user_id).set({"cosmetics": {"equipped": slots}}, merge=True)


def save_looks(user_id, looks):
    user_ref(user_id).set({"cosmetics": {"looks": looks}}, merge=True)


def reserve_checkout(user_id, query_id, expected_owned):
    """Serialize pre-checkouts across tabs/bot replicas. Abandoned checkouts expire."""
    ref = user_ref(user_id)

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

    return reserve(db.transaction())


def get_purchase(charge_id):
    snapshot = purchase_ref(charge_id).get()
    return snapshot.to_dict() if snapshot.exists else None


def get_user_purchases(user_id, limit=None):
    """Gli acquisti di un utente, dal piu' recente. Il filtro e' su un campo solo e
    l'ordinamento si fa qui: un `order_by` insieme al `where` vorrebbe un indice composito
    per una lista che non arriva a dieci righe."""
    query = db.collection(PURCHASES_COLLECTION).where("user_id", "==", user_id)
    purchases = [doc.to_dict() for doc in query.stream()]
    return sorted(purchases, key=lambda p: (p.get("day") or "", str(p.get("created_at") or "")), reverse=True)[:limit]


def revoke_purchase(charge_id):
    """Segna un acquisto come rimborsato e ritira quello che aveva consegnato.

    Ritira **solo** quello che nessun altro acquisto ancora valido gli ha dato: chi ha preso
    il tema Neon da solo e poi il Pacchetto Neon, e si fa rimborsare il pacchetto, il tema
    l'aveva gia' pagato e resta suo.

    Ritorna la lista degli id davvero ritirati, o None se l'acquisto non esiste."""
    purchase = get_purchase(charge_id)
    if not purchase:
        return None

    user_id = purchase.get("user_id")
    granted = set(purchase.get("granted") or [])
    kept = {
        item_id
        for other in get_user_purchases(user_id)
        if other.get("charge_id") != str(charge_id) and not other.get("refunded")
        for item_id in (other.get("granted") or [])
    }
    revoked = sorted(granted - kept)

    purchase_ref(charge_id).update({"refunded": True, "refunded_at": firestore.SERVER_TIMESTAMP})
    if revoked:
        user_ref(user_id).set(
            {"cosmetics": {"owned": firestore.ArrayRemove(revoked)}}, merge=True
        )
    logging.info(f"[SHOP] Rimborso {charge_id} a {user_id}: ritirati {revoked}")
    return revoked


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
