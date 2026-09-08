"""Confronto fra quello che l'utente scrive e le risposte accettate.

Prima il confronto era esatto (`answer in correct_answers`): chi scriveva "ibrahimovich" o
"mbappe'" si vedeva rifiutare una risposta che sapeva, e ci perdeva pure un tentativo. E'
il difetto piu' fastidioso in un gioco di nomi propri, per giunta stranieri.

Qui la risposta viene prima **normalizzata** (minuscole, accenti tolti, punteggiatura via)
e poi, se non combacia, confrontata con una soglia di somiglianza. La soglia e' alta di
proposito: deve perdonare il refuso, non indovinare al posto dell'utente. Il caso da
evitare e' accettare "ronaldinho" per "ronaldo", quindi la somiglianza va accompagnata da
un limite sulla differenza di lunghezza.

Non si suggerisce mai il nome giusto ("intendevi X?"): sarebbe rivelare la soluzione.
"""
import re
import unicodedata
from difflib import SequenceMatcher

# Somiglianza minima per considerare due stringhe "la stessa risposta scritta male".
MIN_RATIO = 0.87
# Differenza di lunghezza oltre la quale non e' piu' un refuso ma un'altra parola.
MAX_LENGTH_DELTA = 3
# Sotto questa lunghezza un carattere sbagliato cambia troppo: si accetta solo l'esatto.
MIN_FUZZY_LENGTH = 5

# Convenevoli: hanno la forma di un cognome ma non sono un tentativo. Chi scrive "ciao"
# non deve perderci un tentativo su tre.
NOT_ANSWERS = {
    "ciao", "ciao ciao", "grazie", "grazie mille", "ok", "okay", "va bene", "buongiorno",
    "buonasera", "buonanotte", "aiuto", "boh", "non lo so", "prego", "scusa",
    "hola", "gracias", "buenos dias", "buenas noches", "vale", "ayuda", "no lo se",
    "hi", "hello", "hey", "thanks", "thank you", "help", "no idea", "i dont know", "yes", "no",
}


def normalize(text):
    """Minuscole, accenti tolti, tutto cio' che non e' lettera o cifra ridotto a spazio.
    Cosi' "Mbappé", "MBAPPE" e "mbappe" sono la stessa risposta."""
    decomposed = unicodedata.normalize("NFKD", (text or "").strip().lower())
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    # Apostrofi, trattini e punti si tolgono senza lasciare spazio: "N'Golo" e "Ngolo",
    # "ibra-himovic" e "ibrahimovic" devono risultare la stessa risposta esatta.
    glued = re.sub(r"['’‘`.·–—-]", "", without_accents)
    cleaned = re.sub(r"[^a-z0-9]+", " ", glued)
    return re.sub(r"\s+", " ", cleaned).strip()


def similarity(first, second):
    return SequenceMatcher(None, first, second).ratio()


def find_match(guess, accepted_answers):
    """Cerca `guess` fra le risposte accettate.

    Ritorna None se non c'e' nessuna corrispondenza, altrimenti un dizionario con
    'answer' (la risposta accettata che ha fatto scattare il match) e 'typo' (True se ci
    siamo arrivati per somiglianza e non per uguaglianza)."""
    normalized_guess = normalize(guess)
    if not normalized_guess:
        return None

    candidates = {normalize(answer): answer for answer in accepted_answers or []}
    candidates.pop("", None)

    if normalized_guess in candidates:
        return {"answer": candidates[normalized_guess], "typo": False}

    if len(normalized_guess) < MIN_FUZZY_LENGTH:
        return None

    best = None
    for normalized_answer, original in candidates.items():
        if len(normalized_answer) < MIN_FUZZY_LENGTH:
            continue
        if abs(len(normalized_answer) - len(normalized_guess)) > MAX_LENGTH_DELTA:
            continue
        ratio = similarity(normalized_guess, normalized_answer)
        if ratio >= MIN_RATIO and (best is None or ratio > best[0]):
            best = (ratio, original)

    if best is None:
        return None
    return {"answer": best[1], "typo": True}


def looks_like_an_answer(text):
    """Filtro per la risposta libera (senza /guess): serve a distinguere un tentativo da un
    messaggio qualsiasi, cosi' un "grazie!" o un link non consumano un tentativo.

    Un nome di calciatore e' corto e fatto di poche parole: qui si accettano da 1 a 4
    parole, niente cifre isolate, niente link, niente a capo."""
    if not text:
        return False
    stripped = text.strip()
    if len(stripped) > 40 or "\n" in stripped or "://" in stripped or stripped.startswith("/"):
        return False

    normalized = normalize(stripped)
    if not normalized or len(normalized) < 3:
        return False
    if normalized in NOT_ANSWERS:
        return False

    words = normalized.split()
    if not 1 <= len(words) <= 4:
        return False

    letters = sum(1 for char in normalized if char.isalpha())
    return letters >= max(3, len(normalized) - 2)
