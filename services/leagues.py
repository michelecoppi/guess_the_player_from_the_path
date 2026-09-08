"""Le regole delle leghe private, senza Telegram e senza HTTP.

Stesso motivo di services/game.py: da oggi una lega si crea, si entra e si esce da **due
posti** (la chat e la mini app), e i limiti - cinque leghe a testa, cinquanta membri, trenta
caratteri di nome - devono essere gli stessi in entrambi. Scritti due volte, prima o poi
divergono.

Le funzioni qui ritornano uno **stato** (`'ok'`, `'full'`, `'limit'`...): il messaggio da
mostrare lo sceglie chi chiama, che e' l'unico a sapere in che lingua e su che schermo.
"""
import random
import string

from services import firebase_service

MAX_LEAGUES_PER_USER = 5
MAX_MEMBERS = 50
MAX_NAME_LENGTH = 30
CODE_LENGTH = 6

# Niente 0/O e 1/I: il codice si detta a voce e si copia a mano.
CODE_ALPHABET = "".join(c for c in string.ascii_uppercase + string.digits if c not in "O0I1")

# Quante volte riprovare con un codice diverso se quello estratto e' gia' preso. Due
# basterebbero: lo spazio dei codici e' enorme rispetto al numero di leghe.
CODE_ATTEMPTS = 5


def generate_code():
    return "".join(random.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def normalize_code(code):
    return (code or "").strip().upper()


def create(user_id, user_data, name, owner_name):
    """Crea una lega. Ritorna (stato, codice): 'ok' | 'no_name' | 'name_too_long' | 'limit' |
    'failed'."""
    name = (name or "").strip()
    if not name:
        return "no_name", None
    if len(name) > MAX_NAME_LENGTH:
        return "name_too_long", None
    if len((user_data or {}).get("leagues", [])) >= MAX_LEAGUES_PER_USER:
        return "limit", None

    for _ in range(CODE_ATTEMPTS):
        code = generate_code()
        if firebase_service.create_league(code, name, user_id, owner_name):
            return "ok", code
    return "failed", None


def join(user_id, user_data, code, name):
    """Entra in una lega. Ritorna (stato, lega): 'ok' | 'no_code' | 'limit' | 'not_found' |
    'already_member' | 'full'."""
    code = normalize_code(code)
    if not code:
        return "no_code", None
    if len((user_data or {}).get("leagues", [])) >= MAX_LEAGUES_PER_USER:
        return "limit", None

    result = firebase_service.join_league(code, user_id, name, MAX_MEMBERS)
    if result != "ok":
        return result, None
    return "ok", firebase_service.get_league(code) or {"code": code, "name": code}


def leave(user_id, code):
    """Esce da una lega. Ritorna (stato, lega): 'ok' | 'no_code' | 'not_found' |
    'not_member'.

    Chi esce perde i punti accumulati li' dentro: rientrando riparte da zero. E' voluto -
    altrimenti uscire e rientrare sarebbe il modo di azzerare una posizione scomoda tenendo
    i punti."""
    code = normalize_code(code)
    if not code:
        return "no_code", None

    league = firebase_service.get_league(code)
    if not league:
        return "not_found", None
    if not firebase_service.leave_league(code, user_id):
        return "not_member", league
    return "ok", league
