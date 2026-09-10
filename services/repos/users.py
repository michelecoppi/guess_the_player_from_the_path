"""Firestore users repository. Shared dependencies live in the compatibility facade."""
import copy
import logging

from firebase_admin import firestore

from services.dates import normalize_day, shift_iso, today_iso
from services.i18n import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES
from services.streak import next_streak, streak_bonus


def user_ref(user_id):
    from services import firebase_service as fs
    return fs.db.collection(fs.USERS_COLLECTION).document(str(user_id))


def new_user_document(user_id, first_name, language=DEFAULT_LANGUAGE):
    """Il documento di un utente appena registrato."""
    from services import firebase_service as fs
    document = copy.deepcopy(fs.USER_FIELD_DEFAULTS)
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
    from services import firebase_service as fs
    missing = {
        field: copy.deepcopy(default)
        for field, default in fs.USER_FIELD_DEFAULTS.items()
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


def save_user(user_id, first_name, language=DEFAULT_LANGUAGE, referral_code=None):
    """Crea l'utente se non esiste, e completa il documento se gli mancano dei campi.

    E' una transazione: due /start ravvicinati non possono piu' creare due documenti per la
    stessa persona, ne' ripristinare gli stessi campi due volte.

    Se l'utente esiste gia', la lingua passata viene ignorata: resta quella salvata (es.
    cambiata a mano con /language), non quella rilevata dal client in quel momento. Viene
    usata solo se l'utente una lingua valida non ce l'ha, il che per i documenti vecchi era
    la norma.

    Ritorna {'created': bool, 'language': lingua effettiva dell'utente, 'repaired': campi
    aggiunti adesso}."""
    from services import firebase_service as fs
    ref = fs.user_ref(user_id)

    @firestore.transactional
    def _create(transaction):
        snapshot = ref.get(transaction=transaction)
        if not snapshot.exists:
            attribution = None
            if referral_code:
                from services import referrals
                attribution = referrals.prepare_attribution(transaction, user_id, first_name, referral_code)
                if attribution:
                    transaction.set(referrals.ref(user_id), attribution)
            transaction.set(ref, fs.new_user_document(user_id, first_name, language))
            result = {"created": True, "language": language, "repaired": []}
            if attribution:
                result["referral_attached"] = True
            return result

        existing = snapshot.to_dict() or {}
        missing = fs.missing_user_fields(
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

    return _create(fs.db.transaction())


def get_user_language(user_id):
    from services import firebase_service as fs
    data = fs.get_user_data(user_id)
    return (data or {}).get("language", DEFAULT_LANGUAGE)


def set_user_language(user_id, language):
    from services import firebase_service as fs
    fs.user_ref(user_id).update({"language": language})


def get_user_data(user_id):
    from services import firebase_service as fs
    snapshot = fs.user_ref(user_id).get()
    return snapshot.to_dict() if snapshot.exists else None


def delete_user_data(user_id):
    """Cancella dati personali e di gioco, conservando i registri degli acquisti.

    L'ordine e' la parte che conta, e conta solo quando qualcosa si rompe a meta'. Prima le
    lapidi referral, l'uscita dalle leghe e il documento utente: sono le scritture che
    rendono il conto inutilizzabile e i dati non piu' riconducibili a una persona. Solo
    dopo lo sgombero del resto, che da quel punto in poi sono righe orfane di un utente che
    non c'e' piu'. Prima si faceva al contrario, con la delete del profilo per ultima: un
    guasto a meta' lasciava un account **vivo** con meta' della sua storia gia' cancellata,
    e l'utente si sentiva rispondere che la cancellazione non era riuscita.

    Ogni passo e' ripetibile e nessuno pretende che il documento utente esista ancora:
    rilanciarla dopo un guasto riprende da dov'era.

    Lo sgombero passa da `bulk.sweep` e non da un ciclo sullo stream della query: il perche'
    sta li'. Le sotto-collezioni di chi gioca da un anno sono centinaia di documenti.
    """
    from services import firebase_service as fs
    from services import referrals
    from services.repos import bulk
    user_id = int(user_id)
    ref = fs.user_ref(user_id)
    snapshot = ref.get()
    user_data = snapshot.to_dict() if snapshot.exists else {}
    deleted = {"profile": 0, "archive": 0, "history": 0, "leagues": 0,
               "events": 0, "groups": 0, "duels": 0}

    # Le righe referral portano il nome di chi e' stato invitato: restano le sole lapidi.
    referrals.erase_user(user_id)

    # Uscire tramite la normale operazione mantiene corretto members_count, ed e' una
    # transazione: va fatto finche' il documento utente c'e', perche' leave_league gli
    # toglie il codice dall'elenco. Le leghe di un utente sono poche e si contano.
    for code in dict.fromkeys(user_data.get("leagues") or []):
        league = fs.get_league(code)
        if fs.leave_league(code, user_id):
            deleted["leagues"] += 1
        if league and league.get("owner_id") == user_id:
            fs.league_ref(code).update({"owner_id": None})

    if snapshot.exists:
        ref.delete()
        deleted["profile"] = 1

    def drop(writer, doc):
        writer.delete(doc.reference)

    # Firestore non elimina le sotto-collezioni insieme al documento padre: restano al loro
    # posto anche dopo la delete qui sopra, ed e' per questo che si possono sgomberare dopo.
    for subcollection, key in (
        (fs.ARCHIVE_SUBCOLLECTION, "archive"),
        (fs.HISTORY_SUBCOLLECTION, "history"),
    ):
        deleted[key] = bulk.sweep(ref.collection(subcollection), drop)

    # Elimina anche copie orfane o create prima dell'elenco users.leagues.
    for collection_name, key in (
        (fs.PARTICIPANTS_SUBCOLLECTION, "events"),
        (fs.GROUP_PLAYERS_SUBCOLLECTION, "groups"),
    ):
        deleted[key] = bulk.sweep(
            fs.db.collection_group(collection_name).where("telegram_id", "==", user_id), drop)

    # Per le iscrizioni orfane va corretto anche il contatore della lega. Due iscrizioni
    # nella stessa lega sono due Increment sullo stesso documento, e il BulkWriter le puo'
    # mandare in parallelo: e' commutativo, il totale torna comunque.
    def leave(writer, doc):
        writer.delete(doc.reference)
        writer.update(doc.reference.parent.parent, {"members_count": firestore.Increment(-1)})

    deleted["leagues"] += bulk.sweep(
        fs.db.collection_group(fs.MEMBERS_SUBCOLLECTION).where("telegram_id", "==", user_id),
        leave)

    # Il round corrente conserva sul padre nome e id dell'ultimo vincitore.
    bulk.sweep(fs.db.collection(fs.GROUP_ROUNDS_COLLECTION).where("solved_by", "==", user_id),
               lambda writer, doc: writer.update(doc.reference,
                                                 {"solved_by": None, "solved_name": None}))

    # Anche i duelli privati contengono il nome del partecipante e le sue partite.
    deleted["duels"] = bulk.sweep(
        fs.db.collection("app_duels").where("members", "array_contains", user_id), drop)

    logging.info(f"[PRIVACY] Dati utente {user_id} cancellati: {deleted}")
    return deleted


def get_user_daily_status(user_id, day_iso=None):
    """Tentativi usati e se ha gia' indovinato **oggi**. I contatori di un giorno passato
    valgono zero senza bisogno di averli azzerati."""
    from services import firebase_service as fs
    day_iso = day_iso or today_iso()
    data = fs.get_user_data(user_id)
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
    from services import firebase_service as fs
    ref = fs.user_ref(user_id)

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

    return _attempt(fs.db.transaction())


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
    from services import firebase_service as fs
    ref = fs.user_ref(user_id)

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

    return _take(fs.db.transaction())


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
    from services import firebase_service as fs
    ref = fs.user_ref(user_id)
    snapshot = ref.get()
    data = snapshot.to_dict() if snapshot.exists else {}
    after = {field: int(data.get(field, 0) or 0) + delta for field, delta in deltas.items()}
    fresh = fs._newly_earned(data, **after)
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
    from services import firebase_service as fs
    day_iso = day_iso or today_iso()
    ref = fs.user_ref(user_id)

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
            update_data[f"monthly_earned.{day_iso[:7]}"] = firestore.Increment(awarded)

        # I traguardi che questa giocata fa scattare si scrivono qui dentro, insieme ai
        # contatori che li hanno mossi: sono lo stesso fatto, e separarli lascerebbe una
        # finestra in cui il contatore e' salito e il distintivo no. La lettura c'e' gia'
        # (`data`), quindi non costa niente.
        earned = fs._newly_earned(
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

    return _register(fs.db.transaction())


def set_user_notifications(user_id, chat_id, enabled):
    from services import firebase_service as fs
    fs.user_ref(user_id).update({
        "chat_id": chat_id if enabled else -1,
        "notifications_enabled": bool(enabled),
    })


def get_broadcast_users(reference_day_iso=None):
    """Utenti da avvisare al cambio di giornata, con l'informazione se avevano indovinato
    la sfida del giorno di riferimento (di norma ieri, perche' il messaggio parte a
    mezzanotte)."""
    from services import firebase_service as fs
    reference_day_iso = reference_day_iso or shift_iso(today_iso(), -1)
    query = fs.db.collection(fs.USERS_COLLECTION).where("notifications_enabled", "==", True)

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
    from services import firebase_service as fs
    query = fs.db.collection(fs.USERS_COLLECTION).order_by(
        field, direction=firestore.Query.DESCENDING
    ).limit(limit)
    return [fs._public_user(doc.to_dict()) for doc in query.stream()]


def count_users_ahead(field, value):
    """Quanti utenti hanno piu' punti di 'value': serve a mostrare la posizione di chi e'
    fuori dalla top 10 senza scaricare la classifica intera."""
    from services import firebase_service as fs
    query = fs.db.collection(fs.USERS_COLLECTION).where(field, ">", value)
    return fs._count_collection(query)


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
    from services import firebase_service as fs
    fs.user_ref(telegram_id).update({"trophies": firestore.ArrayUnion([trophy_code])})
    logging.info(f"Trofeo {trophy_code} aggiunto per l'utente {telegram_id}")


def reset_monthly_points(closure=None):
    """Azzera i punti mensili di chi ne ha: girata una volta al mese, in batch."""
    from services import firebase_service as fs
    query = fs.db.collection(fs.USERS_COLLECTION).where("monthly_points", ">", 0)
    if closure:
        from services.monthly_closure import reset_user
        return sum(reset_user(doc.reference, closure) for doc in query.stream())
    batch = fs.db.batch()
    count = 0
    for doc in query.stream():
        batch.update(doc.reference, {"monthly_points": 0})
        count += 1
        if count % 400 == 0:  # il limite di un batch Firestore e' 500 operazioni
            batch.commit()
            batch = fs.db.batch()
    if count % 400:
        batch.commit()
    logging.info(f"Punti mensili azzerati per {count} utenti")
    return count


def set_training_key(user_id, key):
    """Apre una sessione di allenamento sulla sfida indicata.

    La chiave dice anche da dove viene la sfida (`pool:maldini` o `day:2026-09-07`), quindi
    riprendere la sessione non richiede di indovinare la sorgente.

    Come per l'archivio lo stato sta sul documento utente e non in memoria: su Cloud Run
    l'istanza puo' sparire fra un messaggio e l'altro. Aprire l'allenamento chiude
    l'archivio e l'evento (e viceversa): due partite aperte contemporaneamente vorrebbero
    dire decidere ad ogni messaggio a quale delle due risponde, che e' una regola che
    nessuno puo' indovinare."""
    from services import firebase_service as fs
    fs.user_ref(user_id).update({
        "training_key": key, "training_attempts": 0, "archive_day": None, "event_key": None,
    })


def clear_training_key(user_id):
    from services import firebase_service as fs
    fs.user_ref(user_id).update({"training_key": None, "training_attempts": 0})


def register_training_attempt(user_id):
    """Un tentativo di allenamento. Non e' una transazione perche' non c'e' niente da
    proteggere: nessun punto, nessun bonus, e chi si allena e' uno solo davanti alla
    propria chat."""
    from services import firebase_service as fs
    fs.user_ref(user_id).update({"training_attempts": firestore.Increment(1)})


def register_training_solved(user_id):
    """Nessun punto, come l'archivio: si tiene solo il conto, che finisce in /stats.

    Ritorna i traguardi che questo allenamento ha fatto scattare."""
    from services import firebase_service as fs
    return fs._bump_counters(user_id, {
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
    from services import firebase_service as fs
    fs.user_ref(user_id).update({
        "event_key": key, "archive_day": None, "training_key": None, "training_attempts": 0,
    })


def clear_event_key(user_id):
    from services import firebase_service as fs
    fs.user_ref(user_id).update({"event_key": None})


def update_user_fields(user_id, fields):
    """Correzione manuale di un documento utente dalla dashboard (punti, striscia, lingua).
    Volutamente senza Increment: dalla dashboard si scrive il valore che si vuole vedere."""
    from services import firebase_service as fs
    fs.user_ref(user_id).update(dict(fields))
    logging.info(f"[ADMIN] utente {user_id} aggiornato: {sorted(fields)}")


def find_users_by_first_name(prefix, limit=20):
    """Ricerca per prefisso del nome: e' una query di intervallo su un solo campo, quindi
    costa come una lettura ordinata e non richiede indici aggiuntivi."""
    from services import firebase_service as fs
    if not prefix:
        return []
    query = (
        fs.db.collection(fs.USERS_COLLECTION)
        .order_by("first_name")
        .start_at([prefix])
        .end_at([prefix + ""])
        .limit(limit)
    )
    return [doc.to_dict() for doc in query.stream()]

