"""Firestore challenges repository. Shared dependencies live in the compatibility facade."""
import logging

from firebase_admin import firestore
from google.api_core.exceptions import GoogleAPICallError

from services.dates import shift_iso, today_iso


def daily_path_ref(day_iso):
    from services import firebase_service as fs
    return fs.db.collection(fs.DAILY_PATH_COLLECTION).document(day_iso)


def daily_path_exists(day_iso):
    from services import firebase_service as fs
    return fs.daily_path_ref(day_iso).get().exists


def get_daily_path(day_iso):
    """La sfida di un giorno, letta direttamente per id documento (la data ISO)."""
    from services import firebase_service as fs
    snapshot = fs.daily_path_ref(day_iso).get()
    if not snapshot.exists:
        logging.info(f"Nessuna daily challenge trovata per il giorno {day_iso}")
        return None
    return snapshot.to_dict()


def save_daily_path(day_iso, doc):
    from services import firebase_service as fs
    doc = dict(doc)
    doc["day"] = day_iso
    fs.daily_path_ref(day_iso).set(doc)
    logging.info(f"[GENERATOR] Salvata daily_path per {day_iso} (player_id={doc.get('player_id')})")


def get_recent_player_ids(days):
    """Gli id dei giocatori usati (o gia' programmati) nella finestra di anti-ripetizione.
    Query di intervallo sulla data: possibile solo perche' le date sono ISO."""
    from services import firebase_service as fs
    start_day = shift_iso(today_iso(), -days)
    docs = fs.db.collection(fs.DAILY_PATH_COLLECTION).where("day", ">=", start_day).stream()

    ids = []
    for doc in docs:
        player_id = doc.to_dict().get("player_id")
        if player_id:
            ids.append(player_id)
    return ids


def claim_daily_first_correct(day_iso):
    """Assegna il bonus 'primo che indovina' a un solo utente, anche se due rispondono
    nello stesso istante. Ritorna True se il bonus spetta a chi ha appena chiamato."""
    from services import firebase_service as fs
    ref = fs.daily_path_ref(day_iso)

    @firestore.transactional
    def _claim(transaction):
        snapshot = ref.get(transaction=transaction)
        if not snapshot.exists or snapshot.to_dict().get("first_correct_user"):
            return False
        transaction.update(ref, {"first_correct_user": True})
        return True

    return _claim(fs.db.transaction())


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
    from services import firebase_service as fs
    fields = {}
    if solved:
        fields["solved_count"] = firestore.Increment(1)
    else:
        fields["players_count"] = firestore.Increment(1)
    try:
        fs.daily_path_ref(day_iso).update(fields)
    except GoogleAPICallError as e:
        # Una statistica non deve mai far fallire una risposta giusta.
        logging.warning(f"[STATS] contatore di {day_iso} non aggiornato: {e}")


def get_daily_stats(day_iso):
    """Quanti hanno giocato e quanti hanno indovinato quella giornata: (players, solved).

    (0, 0) per le giornate precedenti all'introduzione dei contatori: chi mostra il dato
    deve trattarlo come "non lo sappiamo", non come "non l'ha indovinato nessuno"."""
    from services import firebase_service as fs
    data = fs.get_daily_path(day_iso) or {}
    return data.get("players_count", 0), data.get("solved_count", 0)


def get_display_name_for_day(day_iso):
    from services import firebase_service as fs
    data = fs.get_daily_path(day_iso)
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
    from services import firebase_service as fs
    before = before_day_iso or today_iso()
    query = fs.db.collection(fs.DAILY_PATH_COLLECTION).where("day", "<", before).order_by(
        "day", direction=firestore.Query.DESCENDING
    ).limit(limit)
    return [doc.to_dict() for doc in query.stream()]


def get_daily_paths_range(start_day_iso, end_day_iso, limit=180):
    """Le sfide di una finestra di date, in ordine cronologico. Filtro e ordinamento sono
    sullo stesso campo (`day`), quindi non serve nessun indice composito."""
    from services import firebase_service as fs
    query = (
        fs.db.collection(fs.DAILY_PATH_COLLECTION)
        .where("day", ">=", start_day_iso)
        .where("day", "<=", end_day_iso)
        .order_by("day")
        .limit(limit)
    )
    return [doc.to_dict() for doc in query.stream()]


def update_daily_path(day_iso, fields):
    """Modifica parziale di una sfida esistente (risposte, difficolta', flag del bonus)."""
    from services import firebase_service as fs
    fs.daily_path_ref(day_iso).update(dict(fields))
    logging.info(f"[ADMIN] daily_path {day_iso} aggiornata: {sorted(fields)}")


def delete_daily_path(day_iso):
    from services import firebase_service as fs
    ref = fs.daily_path_ref(day_iso)
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
    from services import firebase_service as fs
    query = (
        fs.db.collection(fs.USERS_COLLECTION)
        .where("last_played_day", "==", day_iso)
        .where("has_guessed_today", "==", True)
    )
    return fs._count_collection(query)

