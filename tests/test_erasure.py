"""La cancellazione dei dati: quello che deve restare e quello che non deve restare.

Il grosso gira sull'emulatore e non sui finti che usa il resto della suite, perche' qui
l'unica domanda e' "e' rimasto qualcosa?" e un finto risponde quello che gli abbiamo detto
di rispondere, compreso "no". Servono le query di collection group vere, la paginazione
vera e il BulkWriter vero.

Le uniche due prove che restano su un finto sono quelle in fondo, ed e' l'eccezione che
conferma la regola: non provano Firestore, provano la **nostra** politica su un errore di
scrittura, e per vederla serve un errore di scrittura a comando.
"""
from types import SimpleNamespace

import pytest

from services import firebase_service as fs
from services import referrals
from services.repos import bulk

DAYS = [f"2026-09-{n:02}" for n in range(1, 8)]


@pytest.fixture
def small_pages(monkeypatch):
    """Pagine da tre documenti: il cursore si vede girare senza doverne scrivere duecento."""
    monkeypatch.setattr(bulk, "PAGE", 3)


def populate(user_id, chat_id=-100, league="LEG", event="EV1"):
    """Un utente con addosso una copia di ogni cosa che lo nomina."""
    fs.save_user(user_id, "Da cancellare")
    for day in DAYS:
        fs.history_ref(user_id, day).set({"day": day, "solved": True, "attempts": 1})
        fs.archive_ref(user_id, day).set({"day": day, "solved": True})
    fs.create_league(league, "Lega", user_id, "Da cancellare")
    fs.participant_ref(event, user_id).set({"telegram_id": user_id, "name": "Da cancellare"})
    fs.group_round_ref(chat_id).set({"chat_id": chat_id, "solved_by": user_id,
                                     "solved_name": "Da cancellare"})
    fs.group_player_ref(chat_id, user_id).set({"telegram_id": user_id, "points": 3})
    fs.db.collection("app_duels").document(f"duel-{user_id}").set(
        {"members": [user_id, 999], "names": {str(user_id): "Da cancellare"}})


# ---------------------------------------------------------------------------
# Il giro completo, sull'emulatore
# ---------------------------------------------------------------------------


def test_a_page_is_not_the_end_of_the_sweep(emulator_db, small_pages):
    """Sette documenti e pagine da tre: la spazzata deve arrivare in fondo.

    E li tocca con una scrittura che **non** li toglie dalla query, che e' il caso per cui
    il cursore esiste: senza, la pagina dopo sarebbe di nuovo la prima e il ciclo non
    finirebbe mai. Oggi nessun chiamante fa cosi' - ognuno scrive qualcosa che smaterializza
    il filtro - ma e' un'invariante che nessuno di loro dichiara."""
    collection = emulator_db.collection("scratch")
    for n in range(7):
        collection.document(f"doc-{n}").set({"n": n})

    swept = bulk.sweep(collection, lambda writer, doc: writer.update(doc.reference, {"seen": True}))

    assert swept == 7
    assert all(doc.to_dict()["seen"] for doc in collection.stream())


def test_erasing_an_inviter_sweeps_every_row_they_signed(emulator_db, small_pages, monkeypatch):
    monkeypatch.setattr(referrals, "BOT_TOKEN", "test-secret")
    fs.save_user(1, "Owner")
    for uid in range(2, 9):
        fs.save_user(uid, f"Friend {uid}", referral_code=referrals.code_for(1))

    assert referrals.erase_user(1) == 7

    assert not list(emulator_db.collection(referrals.COLLECTION).where("inviter_id", "==", 1).stream())
    for uid in range(2, 9):
        # Resta la lapide, che e' quello che impedisce di farsi attribuire da capo.
        assert referrals.ref(uid).get().to_dict() == {"status": "deleted"}


def test_deletion_leaves_nothing_that_names_the_person(emulator_db, small_pages, monkeypatch):
    monkeypatch.setattr(referrals, "BOT_TOKEN", "test-secret")
    # L'attribuzione e' first-touch: il codice va speso alla creazione, non dopo.
    fs.save_user(7, "Inviter")
    fs.save_user(42, "Da cancellare", referral_code=referrals.code_for(7))
    populate(42)
    fs.save_user(8, "Altro")
    fs.join_league("LEG", 8, "Altro", 10)

    deleted = fs.delete_user_data(42)

    assert deleted == {"profile": 1, "archive": 7, "history": 7, "leagues": 1,
                       "events": 1, "groups": 1, "duels": 1}
    assert not fs.user_ref(42).get().exists
    for subcollection in (fs.ARCHIVE_SUBCOLLECTION, fs.HISTORY_SUBCOLLECTION):
        assert not list(fs.user_ref(42).collection(subcollection).stream())
    assert not fs.member_ref("LEG", 42).get().exists
    assert not fs.participant_ref("EV1", 42).get().exists
    assert not fs.group_player_ref(-100, 42).get().exists
    assert not fs.db.collection("app_duels").document("duel-42").get().exists
    assert referrals.ref(42).get().to_dict() == {"status": "deleted"}
    # Chi resta nella lega non deve accorgersi di niente, a parte il posto libero.
    league = fs.get_league("LEG")
    assert league["members_count"] == 1 and league["owner_id"] is None
    round_doc = fs.get_group_round(-100)
    assert round_doc["solved_by"] is None and round_doc["solved_name"] is None


def test_deletion_resumes_on_what_a_broken_run_left_behind(emulator_db, small_pages):
    """Il profilo se ne va per primo, quindi il seguito non puo' pretendere che ci sia.

    E' il caso che l'ordine nuovo rende normale invece che eccezionale: se qualcosa si
    rompe a meta', l'account e' gia' sparito e a terra restano solo righe orfane. Chi
    rilancia deve trovarle e portarle via, non fermarsi perche' il documento utente non
    c'e' piu'."""
    populate(43, chat_id=-101, league="LEG2", event="EV2")
    fs.user_ref(43).delete()

    deleted = fs.delete_user_data(43)

    assert deleted["profile"] == 0
    assert (deleted["archive"], deleted["history"], deleted["duels"]) == (7, 7, 1)
    assert deleted["leagues"] == 1 and deleted["events"] == 1 and deleted["groups"] == 1
    assert not list(fs.user_ref(43).collection(fs.HISTORY_SUBCOLLECTION).stream())
    assert not fs.member_ref("LEG2", 43).get().exists
    # E rilanciarla ancora non trova piu' niente e non si lamenta.
    assert fs.delete_user_data(43) == {"profile": 0, "archive": 0, "history": 0,
                                       "leagues": 0, "events": 0, "groups": 0, "duels": 0}


# ---------------------------------------------------------------------------
# La politica sugli errori di scrittura, su un BulkWriter finto
#
# Un BulkWriter vero non fallisce a comando, e queste due righe di codice esistono solo per
# quando fallisce. Il finto qui non prova Firestore: prova cosa decidiamo noi.
# ---------------------------------------------------------------------------


class Writer:
    """Un BulkWriter che fallisce ogni scrittura con il codice che gli si dice."""

    def __init__(self, code):
        self.code = code
        self.on_error = None
        self.attempts = 0

    def on_write_error(self, callback):
        self.on_error = callback

    def delete(self, reference, **kwargs):
        while True:
            # La stessa forma di BulkWriteFailure: `attempts` sta sull'errore ma vive
            # sull'operazione, che e' quella che si porta dietro i tentativi gia' fatti.
            operation = SimpleNamespace(reference=reference, attempts=self.attempts)
            failure = SimpleNamespace(code=self.code, message="finto", operation=operation,
                                      attempts=operation.attempts)
            self.attempts += 1
            if not self.on_error(failure, self):
                return

    def flush(self):
        pass

    def close(self):
        pass


@pytest.fixture
def failing_writer(monkeypatch):
    def install(code):
        writer = Writer(code)
        monkeypatch.setattr(fs, "db", SimpleNamespace(bulk_writer=lambda: writer))
        return writer
    return install


def one_document():
    """Una query da una pagina sola: qui interessa solo cosa succede alla scrittura."""
    reference = SimpleNamespace(path="leagues/LEG")
    page = SimpleNamespace(stream=lambda: iter([SimpleNamespace(reference=reference)]))
    page.start_after = lambda cursor: page
    return SimpleNamespace(order_by=lambda field: SimpleNamespace(limit=lambda n: page))


def test_a_dropped_write_is_an_error_and_not_a_clean_return(failing_writer):
    """Il BulkWriter non solleva: riprova e poi scarta, in silenzio. Un conteggio che
    ignorasse lo scarto direbbe "cancellati sette documenti" avendone cancellati tre, e in
    una cancellazione per privacy quella riga di registro e' l'unica prova che resta."""
    writer = failing_writer(13)  # INTERNAL: uno di quelli per cui riprovare ha senso

    with pytest.raises(RuntimeError, match="1 scritture perse"):
        bulk.sweep(one_document(), lambda w, doc: w.delete(doc.reference))

    assert writer.attempts == bulk.RETRIES + 1


def test_a_target_that_is_already_gone_is_the_result_we_wanted(failing_writer):
    """Sistemare un documento che non c'e' piu' non e' una scrittura persa: e' lo sgombero
    gia' fatto. Se contasse come errore, chi era in una lega poi cancellata non riuscirebbe
    a chiudere la richiesta a nessun tentativo, per sempre."""
    writer = failing_writer(bulk.GONE)

    assert bulk.sweep(one_document(), lambda w, doc: w.delete(doc.reference)) == 1
    assert writer.attempts == 1  # nemmeno riprovata
