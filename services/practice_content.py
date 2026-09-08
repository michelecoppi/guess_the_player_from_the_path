"""Il materiale di allenamento e dei round di gruppo: due sorgenti, una forma sola.

Nessuna delle due puo' spoilerare la sfida del giorno, e per ragioni diverse:

1. **il pool riservato** (`"practice_only": true` in data/players.json): quei calciatori non
   escono mai come sfida del giorno ne' dentro un evento, quindi allenarsi su di loro non
   da' nessun vantaggio. E' materiale infinito e disponibile subito, e non costa **nessuna**
   lettura: le schede sono nel file, dentro il container;
2. **le sfide gia' passate** (services/past_challenges.py): sono pubbliche per costruzione -
   l'archivio le mostra, il broadcast di mezzanotte dice la risposta di ieri.

Il pool e' la sorgente principale perche' e' gratis e c'e' sempre; le sfide passate entrano
ogni tanto (`practice_past_challenge_ratio` in data/config.json) perche' sono le partite
vere, e ritrovarne una ha un sapore diverso da un esercizio.

Le due sorgenti escono di qui con **la stessa forma**, chiave compresa: chi le usa
(allenamento e gruppo) non deve sapere da dove vengono. La chiave (`pool:maldini`,
`day:2026-09-07`) e' quello che si salva sul documento utente o sul round per riprendere la
partita dopo che l'istanza Cloud Run e' sparita.
"""
import random

from services import firebase_service
from services.difficulty import compute_difficulty
from services.past_challenges import pick_past_challenge
from services.player_pool import get_answer_aliases, get_player_by_id, get_practice_players, load_config

POOL_PREFIX = "pool:"
DAY_PREFIX = "day:"

DEFAULT_PAST_RATIO = 0.25


def _display_answer(answers):
    """Il nome da mostrare quando la sfida e' finita, ricavato dagli alias.

    Si prende il piu' lungo fra quelli con uno spazio, cioe' il nome piu' completo
    ("matthijs de ligt" e non "de ligt", "lionel messi" e non "messi"). Serve solo quando la
    scheda non c'e' piu' nel dataset: e' un ripiego, ma un ripiego leggibile."""
    full = [answer for answer in answers if " " in answer]
    if full:
        return max(full, key=len).title()
    return (answers or ["?"])[0].title()


def from_player(player):
    """Una scheda del dataset come sfida di allenamento."""
    return {
        "key": POOL_PREFIX + player["id"],
        "player_id": player["id"],
        "career_path": player.get("career", []),
        "correct_answers": get_answer_aliases(player),
        "difficulty": compute_difficulty(player),
        "answer": player.get("full_name") or player["id"],
        "day": None,
    }


def from_daily(day_iso, challenge):
    """Una sfida gia' giocata come sfida di allenamento.

    Il nome da rivelare si ricava dalla scheda locale quando c'e' (`player_id`), altrimenti
    dalle risposte accettate: in nessuno dei due casi serve una lettura in piu'."""
    player = get_player_by_id(challenge.get("player_id")) or {}
    return {
        "key": DAY_PREFIX + day_iso,
        "player_id": challenge.get("player_id"),
        "career_path": challenge.get("career_path", []),
        "correct_answers": challenge.get("correct_answers", []),
        "difficulty": challenge.get("difficulty"),
        "answer": player.get("full_name") or _display_answer(challenge.get("correct_answers", [])),
        "day": day_iso,
    }


def pick(exclude_keys=(), rng=None):
    """Una sfida di allenamento, o None se non c'e' proprio materiale.

    `exclude_keys` serve a non riproporre quello che si e' appena giocato: in allenamento la
    sfida in corso, in un gruppo gli ultimi round."""
    rng = rng or random
    excluded = set(exclude_keys or ())
    ratio = load_config().get("practice_past_challenge_ratio", DEFAULT_PAST_RATIO)

    if rng.random() < ratio:
        challenge = _from_past(excluded, rng)
        if challenge:
            return challenge

    return _from_pool(excluded, rng)


def _from_past(excluded, rng):
    days = [key[len(DAY_PREFIX):] for key in excluded if key.startswith(DAY_PREFIX)]
    day_iso, challenge = pick_past_challenge(exclude_days=days, rng=rng)
    return from_daily(day_iso, challenge) if challenge else None


def _from_pool(excluded, rng):
    reserved = get_practice_players()
    if not reserved:
        return None

    ids = {key[len(POOL_PREFIX):] for key in excluded if key.startswith(POOL_PREFIX)}
    candidates = [player for player in reserved if player["id"] not in ids]
    # Se l'esclusione ha svuotato il pool (succede solo con un pool minuscolo) e' meglio
    # ripetere una sfida che non darne nessuna.
    return from_player(rng.choice(candidates or reserved))


def load(key):
    """Ricostruisce la sfida da una chiave salvata. None se non esiste piu'.

    Per il pool e' una lettura del file locale, cioe' gratis; per una sfida passata e' una
    lettura di Firestore, la stessa che farebbe l'archivio."""
    if not key:
        return None

    if key.startswith(POOL_PREFIX):
        player = get_player_by_id(key[len(POOL_PREFIX):])
        return from_player(player) if player else None

    if key.startswith(DAY_PREFIX):
        day_iso = key[len(DAY_PREFIX):]
        challenge = firebase_service.get_daily_path(day_iso)
        return from_daily(day_iso, challenge) if challenge else None

    return None
