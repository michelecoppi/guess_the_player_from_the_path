"""Le transazioni, provate su un Firestore vero (l'emulatore).

Perche' non bastano i finti che usa il resto della suite: un finto fa succedere quello che
gli abbiamo detto di far succedere. Se una transazione fosse scritta male - o non ci fosse
affatto - il finto non se ne accorgerebbe, perche' non c'e' nessuna concorrenza da gestire.
Qui invece piu' thread partono davvero insieme contro lo stesso documento, e chi perde lo
perde per davvero.

Sono i tre punti in cui una doppia esecuzione **costa qualcosa**:

- il bonus al primo che indovina: due bonus per la stessa giornata sono punti dal nulla;
- la consegna di un acquisto in Stelle: due consegne lasciano due righe nel registro da cui
  si rimborsa, per una stella sola incassata;
- la ricevuta di un update Telegram: due esecuzioni sono un tentativo consumato due volte e
  un messaggio ripetuto in chat.

Girano solo con FIRESTORE_EMULATOR_HOST impostata (vedi la fixture in tests/conftest.py):
in CI c'e' sempre, in locale si saltano se l'emulatore non e' acceso.
"""
from concurrent.futures import ThreadPoolExecutor

import pytest
from google.api_core.exceptions import Aborted

from services import firebase_service, work_receipts

pytestmark = pytest.mark.usefixtures("emulator_db")

# Quello che torna una chiamata che non e' nemmeno riuscita a decidere.
#
# Sull'emulatore due transazioni che partono nello stesso millisecondo sullo stesso documento
# si annullano a vicenda finche' si rinuncia. La rinuncia arriva in due forme, a seconda di
# chi molla per primo: il client dopo i suoi tentativi (`ValueError: Failed to commit
# transaction in 5 attempts`) oppure l'emulatore stesso (`Aborted: 409 Transaction lock
# timeout`). Vanno trattate uguale: sono la stessa cosa vista da due punti diversi.
#
# Non e' contesa da smaltire: alzare il limite a 50 tentativi non cambia niente, mentre
# bastano 150 ms di sfasamento perche' vada sempre a buon fine. E' l'emulatore che non ha
# la messa in fila delle transazioni del servizio vero, e non e' nemmeno lo scenario di
# produzione: Telegram rispedisce un update
# dopo secondi, Cloud Tasks riprova dopo un backoff.
#
# Quindi qui non si pretende che i perdenti ricevano una risposta pulita. Si pretende
# **l'invariante**, che e' l'unica cosa che conta e che vale in tutti e due i mondi: non piu'
# di uno vince, e il database non contiene mai piu' di quello che e' stato vinto.
GAVE_UP = "gave-up"


def test_referral_fifth_finish_and_reward_are_atomic_under_retries(emulator_db, monkeypatch):
    from services import referrals

    monkeypatch.setattr(referrals, "BOT_TOKEN", "test-secret")
    monkeypatch.setattr(referrals, "today_iso", lambda: "2026-09-01")
    firebase_service.save_user(1, "Owner")
    firebase_service.user_ref(1).update({"referral_qualified": 2})
    firebase_service.save_user(2, "Friend", referral_code=referrals.code_for(1))
    for n in range(1, 5):
        firebase_service.record_daily_history(2, f"2026-09-{n:02}", True, 1)
    # Durable completion already exists when concurrent credit/recovery calls arrive.
    firebase_service.history_ref(2, "2026-09-05").set({"day": "2026-09-05", "solved": False, "attempts": 3})
    run_together(lambda _: referrals.credit_day(2, "2026-09-05"), 4)
    referrals.credit_day(2, "2026-09-05")  # Retry a possible emulator lock timeout.
    user = firebase_service.get_user_data(1)
    assert user["referral_qualified"] == 3
    assert user["cosmetics"]["earned"].count("referral_intesa") == 1
    assert len(referrals.ref(2).get().to_dict()["days"]) == 5


def test_referral_registration_only_one_inviter_wins(emulator_db, monkeypatch):
    from services import referrals

    monkeypatch.setattr(referrals, "BOT_TOKEN", "test-secret")
    for uid in (1, 2):
        firebase_service.save_user(uid, str(uid))
    run_together(lambda n: firebase_service.save_user(3, "Friend", referral_code=referrals.code_for(n % 2 + 1)), 4)
    firebase_service.save_user(3, "Friend", referral_code=referrals.code_for(1))
    entry = referrals.ref(3).get().to_dict()
    assert entry["inviter_id"] in (1, 2)
    original = entry["inviter_id"]
    firebase_service.save_user(3, "Friend", referral_code=referrals.code_for(3 - original))
    assert referrals.ref(3).get().to_dict()["inviter_id"] == original


def test_referral_dashboard_pagination_recovery_and_erasure(emulator_db, monkeypatch):
    from services import referrals

    monkeypatch.setattr(referrals, "BOT_TOKEN", "test-secret")
    monkeypatch.setattr(referrals, "today_iso", lambda: "2026-09-01")
    firebase_service.save_user(1, "Owner")
    for uid in range(2, 24):
        firebase_service.save_user(uid, f"Friend {uid}", referral_code=referrals.code_for(1))
    for n in range(1, 6):
        firebase_service.history_ref(2, f"2026-09-{n:02}").set({"day": f"2026-09-{n:02}", "solved": True, "attempts": 1})
    first = referrals.dashboard(1)
    second = referrals.dashboard(1, cursor=first["next_cursor"])
    assert len(first["friends"]) == 20 and len(second["friends"]) == 2
    assert second["next_cursor"] is None
    assert len({row["name"] for row in first["friends"] + second["friends"]}) == 22
    assert firebase_service.get_user_data(1)["referral_qualified"] == 1
    assert all(set(row) == {"name", "days", "status", "joined_day"} for row in first["friends"])
    referrals.erase_user(2)
    assert referrals.ref(2).get().to_dict() == {"status": "deleted"}
    firebase_service.user_ref(2).delete()
    firebase_service.save_user(2, "Recreated", referral_code=referrals.code_for(1))
    assert referrals.ref(2).get().to_dict() == {"status": "deleted"}
    referrals.erase_user(1)
    assert not list(emulator_db.collection(referrals.COLLECTION).where("inviter_id", "==", 1).stream())


def test_arena_duplicate_submission_spends_one_attempt(emulator_db, monkeypatch):
    from services import arena

    firebase_service.user_ref(1).set({"first_name": "Anna", "points_totali": 42})
    challenge = {"key": "pool:test", "career_path": [], "correct_answers": ["Paolo Maldini"],
                 "answer": "Paolo Maldini", "difficulty": "easy"}
    monkeypatch.setattr(arena.practice_content, "pick", lambda **kwargs: challenge)
    current = arena.training(1, "next")
    revision = current["session"]["revision"]
    run_together(lambda _: arena.training(1, "guess", "Lionel Messi", revision), 4)
    resumed = arena.training(1)
    assert resumed["session"]["attempts"] <= 1
    if resumed["session"]["attempts"] == 0:
        # The emulator may abort every contender (see GAVE_UP). Retry the same
        # revision after contention, as a client would after a temporary failure.
        arena.training(1, "guess", "Lionel Messi", revision)
        resumed = arena.training(1)
    assert resumed["session"]["attempts"] == 1
    assert firebase_service.get_user_data(1)["points_totali"] == 42


def test_arena_second_seat_has_only_one_winner(emulator_db, monkeypatch):
    from services import arena

    for uid in range(1, 6):
        firebase_service.user_ref(uid).set({"first_name": str(uid)})

    def pick(exclude_keys=()):
        return {"key": f"pool:{len(exclude_keys)}", "career_path": [],
                "correct_answers": ["Paolo Maldini"], "answer": "Paolo Maldini", "difficulty": "easy"}

    monkeypatch.setattr(arena.practice_content, "pick", pick)
    code = arena.duel(1, "Anna", "create")["code"]
    run_together(lambda n: arena.duel(n + 2, str(n), "join", code), 4)
    doc = emulator_db.collection(arena.DUELS).document(code).get().to_dict()
    assert len(doc["members"]) == len(doc["seats"]) == 2


def test_app_event_winner_is_recorded_once(emulator_db, monkeypatch):
    from services import app_events

    day = "2026-09-09"
    monkeypatch.setattr(app_events, "today_iso", lambda: day)
    firebase_service.event_ref("test-week").set({"dates": [day], "type": "path", "daily_data": {
        day: {"points": 2, "correct_answers": ["Paolo Maldini"]}
    }})
    run_together(lambda _: app_events.guess(1, "Anna", "test-week", day, "Paolo Maldini", 0), 4)
    participant = firebase_service.get_event_participant("test-week", 1)
    if participant is None:
        # All emulator contenders can time out before committing. The same request
        # must still succeed on retry; a committed result is never replayed here.
        app_events.guess(1, "Anna", "test-week", day, "Paolo Maldini", 0)
        participant = firebase_service.get_event_participant("test-week", 1)
    assert participant["points"] == 3
    assert participant["daily_attempts"] == 1


def run_together(call, times):
    """`times` chiamate davvero in parallelo, tutte contro lo stesso documento."""
    def guarded(n):
        try:
            return call(n)
        except (ValueError, Aborted):
            return GAVE_UP

    with ThreadPoolExecutor(max_workers=times) as pool:
        return [future.result() for future in [pool.submit(guarded, n) for n in range(times)]]


# ---------------------------------------------------------------------------
# Il bonus al primo che indovina
# ---------------------------------------------------------------------------

def test_ten_simultaneous_winners_never_get_two_bonuses(emulator_db):
    """Il bonus e' un punto in piu' dal nulla: assegnarlo due volte e' un punto regalato che
    nessuna classifica sa piu' spiegare."""
    firebase_service.save_daily_path("2026-09-09", {"player_id": "messi", "difficulty": "easy"})

    claims = run_together(lambda _: firebase_service.claim_daily_first_correct("2026-09-09"), 10)

    assert claims.count(True) <= 1, f"il bonus e' stato assegnato {claims.count(True)} volte"
    challenge = emulator_db.collection("daily_path").document("2026-09-09").get().to_dict()
    # Il documento e' segnato se e solo se qualcuno ha vinto: una transazione annullata non
    # lascia niente dietro di se'.
    assert bool(challenge.get("first_correct_user")) is (True in claims)


def test_the_bonus_is_not_assigned_twice_on_a_later_day():
    """Il secondo giro non deve trovare il bonus di nuovo libero: e' il caso di chi indovina
    domani su una giornata che qualcuno ha gia' vinto oggi."""
    firebase_service.save_daily_path("2026-09-09", {"player_id": "messi"})
    assert firebase_service.claim_daily_first_correct("2026-09-09") is True
    assert firebase_service.claim_daily_first_correct("2026-09-09") is False


def test_a_challenge_that_does_not_exist_gives_no_bonus():
    assert firebase_service.claim_daily_first_correct("2099-01-01") is False


# ---------------------------------------------------------------------------
# La consegna di un acquisto in Stelle
# ---------------------------------------------------------------------------

def test_the_same_payment_is_never_delivered_twice(emulator_db):
    """Il registro `purchases` e' quello da cui si rimborsa: due righe per una stella sola
    incassata vorrebbero dire rimborsare il doppio di quanto e' entrato."""
    firebase_service.save_user(1, "Marco")

    delivered = run_together(
        lambda _: firebase_service.deliver_purchase(1, "charge-abc", "tema_neon", ["tema_neon"], 25),
        5,
    )

    assert delivered.count(True) <= 1, f"consegnato {delivered.count(True)} volte"
    purchases = [doc.to_dict() for doc in emulator_db.collection("purchases").stream()]
    assert len(purchases) == delivered.count(True), "il registro non corrisponde alle consegne"
    assert all(p["stars"] == 25 for p in purchases)


def test_a_resent_payment_is_recognised_and_ignored(emulator_db):
    """Lo scenario vero: Telegram rispedisce l'update dopo secondi, non nello stesso
    millisecondo. La seconda consegna trova la riga gia' scritta e non fa niente."""
    firebase_service.save_user(1, "Marco")

    assert firebase_service.deliver_purchase(1, "charge-abc", "tema_neon", ["tema_neon"], 25) is True
    assert firebase_service.deliver_purchase(1, "charge-abc", "tema_neon", ["tema_neon"], 25) is False

    assert len(firebase_service.get_user_purchases(1)) == 1
    # L'oggetto compare una volta sola anche nell'armadio.
    owned = emulator_db.collection("users").document("1").get().to_dict()["cosmetics"]["owned"]
    assert owned == ["tema_neon"]


def test_two_different_payments_are_both_delivered():
    """Il controllo e' sull'id della transazione, non sull'utente o sull'oggetto: chi compra
    due cose diverse le riceve entrambe."""
    firebase_service.save_user(1, "Marco")
    assert firebase_service.deliver_purchase(1, "charge-1", "tema_neon", ["tema_neon"], 25) is True
    assert firebase_service.deliver_purchase(1, "charge-2", "cornice_oro", ["cornice_oro"], 55) is True
    assert len(firebase_service.get_user_purchases(1)) == 2


def test_only_one_checkout_at_a_time_reserves_the_user():
    """Due schede aperte sullo stesso negozio, o due repliche del bot: solo una prenota, le
    altre si sentono dire che c'e' gia' un pagamento in corso."""
    firebase_service.save_user(1, "Marco")

    outcomes = run_together(lambda n: firebase_service.reserve_checkout(1, f"query-{n}", []), 6)

    assert outcomes.count("ok") <= 1, outcomes
    assert set(outcomes) <= {"ok", "checkout_busy", GAVE_UP}, outcomes


def test_the_same_checkout_can_be_retried_by_its_owner():
    """Chi ha gia' prenotato deve poter riprovare: e' lo stesso `query_id`, non un secondo
    pagamento."""
    firebase_service.save_user(1, "Marco")
    assert firebase_service.reserve_checkout(1, "query-a", []) == "ok"
    assert firebase_service.reserve_checkout(1, "query-a", []) == "ok"
    assert firebase_service.reserve_checkout(1, "query-b", []) == "checkout_busy"


def test_a_checkout_on_stale_prices_is_refused():
    """Se quello che l'utente possiede non e' piu' quello che il client credeva, il prezzo
    che ha visto puo' essere sbagliato: i pacchetti costano meno a chi ha gia' dei pezzi."""
    firebase_service.save_user(1, "Marco")
    firebase_service.deliver_purchase(1, "charge-1", "tema_neon", ["tema_neon"], 25)
    assert firebase_service.reserve_checkout(1, "query-a", []) == "price_changed"
    assert firebase_service.reserve_checkout(1, "query-a", ["tema_neon"]) == "ok"


# ---------------------------------------------------------------------------
# Le ricevute degli update
# ---------------------------------------------------------------------------

def test_only_one_worker_claims_an_update(emulator_db):
    """Cloud Tasks puo' consegnare lo stesso task due volte, e le repliche del bot sono piu'
    di una: senza questa transazione lo stesso tentativo verrebbe consumato due volte."""
    outcomes = run_together(lambda _: work_receipts.claim("telegram-1", serial_key="42"), 8)

    assert outcomes.count("claimed") <= 1, outcomes
    assert set(outcomes) <= {"claimed", "busy", GAVE_UP}, outcomes
    receipt = emulator_db.collection("work_receipts").document("telegram-1").get()
    assert receipt.exists is ("claimed" in outcomes)


def test_a_finished_update_is_never_replayed():
    work_receipts.claim("telegram-1", serial_key="42")
    work_receipts.finish("telegram-1")
    assert work_receipts.claim("telegram-1", serial_key="42") == "done"


def test_two_updates_from_the_same_user_are_serialised():
    """Due messaggi ravvicinati dello stesso utente non si sovrappongono: il secondo aspetta,
    altrimenti i due tentativi leggerebbero lo stesso contatore."""
    assert work_receipts.claim("telegram-1", serial_key="42") == "claimed"
    assert work_receipts.claim("telegram-2", serial_key="42") == "busy"
    # Un altro utente non e' bloccato da questo.
    assert work_receipts.claim("telegram-3", serial_key="43") == "claimed"


def test_the_lock_is_released_when_the_first_update_finishes():
    work_receipts.claim("telegram-1", serial_key="42")
    work_receipts.finish("telegram-1")
    assert work_receipts.claim("telegram-2", serial_key="42") == "claimed"


def test_an_expired_lease_becomes_uncertain_and_is_never_retried():
    """Il caso che richiede un intervento umano: l'update si e' fermato dopo aver iniziato,
    quindi il tentativo puo' essere gia' stato consumato e il messaggio gia' partito. Non si
    riprova - si segnala (services/alerts.py)."""
    assert work_receipts.claim("telegram-1", serial_key="42", lease_seconds=-1) == "claimed"
    assert work_receipts.claim("telegram-1", serial_key="42") == "uncertain"
    assert work_receipts.claim("telegram-1", serial_key="42") == "uncertain"
