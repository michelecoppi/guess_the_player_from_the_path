"""Unit tests must never fall through to the configured production database."""
import os

import pytest

from services import firebase_service

# Il progetto usato dall'emulatore. Non esiste su GCP e non deve esistere: se una di queste
# prove finisse per sbaglio su un progetto vero, cancellerebbe i dati fra un test e l'altro.
EMULATOR_PROJECT = "guess-the-player-emulator"


@pytest.fixture(autouse=True)
def no_live_firestore(request, monkeypatch):
    """Nessun test tocca il database configurato.

    L'unica eccezione sono i test che chiedono `emulator_db`: quelli un database vero lo
    vogliono, ma e' l'emulatore in locale, non il progetto di produzione."""
    if "emulator_db" in request.fixturenames:
        return

    def forbidden(self):
        raise AssertionError("Live Firestore access in unit test: provide a fake repository/client")
    monkeypatch.setattr(firebase_service._LazyFirestoreClient, "_ensure", forbidden)


@pytest.fixture
def emulator_db(monkeypatch):
    """Un Firestore vero, in locale, per le sole cose che un finto non puo' dimostrare.

    I test normali girano su un dizionario in memoria, ed e' giusto cosi': sono veloci e non
    dipendono da niente. Ma un finto non prova quello che qui conta davvero, cioe' che una
    **transazione** faccia il suo mestiere quando due richieste arrivano insieme - il finto
    fa succedere quello che gli abbiamo detto di far succedere, compreso il caso in cui la
    transazione non serva a niente. Il bonus al primo che indovina, la consegna di un
    acquisto in Stelle e la ricevuta di un update sono i tre punti in cui una doppia
    esecuzione costa punti, soldi o un messaggio ripetuto: quelli si provano qui.

    L'emulatore si avvia con:

        gcloud emulators firestore start --host-port=127.0.0.1:8571

    e si dichiara con FIRESTORE_EMULATOR_HOST. Senza quella variabile il test si salta, cosi'
    `pytest` resta verde su una macchina che l'emulatore non ce l'ha - **tranne in CI**, dove
    invece fallisce. La differenza e' il punto: un test che si salta da solo perche' manca un
    servizio e' comodo in locale ed e' un verde bugiardo in CI, che e' l'unico posto dove
    qualcuno si fida del risultato senza guardarlo."""
    host = os.environ.get("FIRESTORE_EMULATOR_HOST")
    if not host:
        # GitHub Actions imposta CI=true su ogni runner.
        if os.environ.get("CI"):
            pytest.fail("FIRESTORE_EMULATOR_HOST non impostata: in CI l'emulatore deve esserci")
        pytest.skip("FIRESTORE_EMULATOR_HOST non impostata: emulatore Firestore non disponibile")

    from google.cloud import firestore as google_firestore

    # Non si passa da firebase_admin: con FIRESTORE_EMULATOR_HOST impostata il client di
    # google-cloud usa credenziali anonime e parla con l'emulatore, e non serve nessuna
    # chiave. E' anche il modo di non toccare lo stato globale di firebase_admin.
    client = google_firestore.Client(project=EMULATOR_PROJECT)
    _wipe(client, host)
    monkeypatch.setattr(firebase_service._LazyFirestoreClient, "_ensure", lambda self: client)
    yield client


def _wipe(client, host):
    """Ogni test parte da un database vuoto.

    L'emulatore ha una rotta apposta che cancella tutto in un colpo: farlo documento per
    documento vorrebbe dire che un test dimenticato dietro si porta dietro i suoi dati."""
    # urllib e non requests: `requests` arriva solo di rimbalzo da firebase-admin, e una
    # dipendenza presa in prestito e' quella che sparisce senza preavviso.
    import urllib.request

    url = f"http://{host}/emulator/v1/projects/{client.project}/databases/(default)/documents"
    urllib.request.urlopen(urllib.request.Request(url, method="DELETE"), timeout=10).close()
