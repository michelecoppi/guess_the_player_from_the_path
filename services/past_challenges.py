"""Le sfide gia' passate come materiale di gioco: allenamento e partite di gruppo.

**Perche' solo il passato.** Pescare un giocatore dal dataset mostrerebbe il percorso di
carriera di qualcuno che non e' ancora uscito: chi lo ha visto in allenamento, il giorno in
cui esce lo riconosce in due secondi e si prende pure il bonus del primo. E' un danno
diretto alla classifica. Le sfide gia' passate invece sono pubbliche per costruzione -
l'archivio le mostra, il broadcast di mezzanotte dice la risposta di ieri - quindi
rigiocarle non rivela niente che il gioco non riveli gia'.

**Perche' per id e non con una query.** L'id del documento *e'* la data, quindi per
prendere una sfida a caso basta estrarre una data a caso e leggere quel documento: una
lettura. Scaricare l'elenco dei giorni passati per sceglierne uno costerebbe fino a
trecento letture a partita, cioe' la differenza fra una funzione sostenibile e una da
spegnere a fine mese. Se il giorno estratto e' vuoto (il bot non c'era ancora, oppure la
pulizia ha tolto quel documento) si riprova; dopo qualche tentativo a vuoto si ripiega
sulla query dei giorni recenti, che e' una sola query.
"""
import logging
import random
from datetime import timedelta

from services import firebase_service
from services.daily_challenge import GAME_EPOCH_FALLBACK
from services.dates import parse_iso, shift_iso, to_iso, today_iso
from services.player_pool import load_config

# Quante date a vuoto accettare prima di ripiegare sulla query.
MAX_RANDOM_TRIES = 6
# Quante sfide recenti leggere nel ripiego.
FALLBACK_WINDOW = 20


def is_playable(challenge):
    """Una sfida si puo' riproporre solo se si puo' ridisegnare e si puo' rispondere.

    Sono gli stessi due requisiti che `scripts/cleanup_daily_paths.py` chiama
    "inservibile": i documenti scritti prima della migrazione non hanno il percorso, e
    senza risposte accettate non ci sarebbe modo di indovinare. L'archivio ne incontra
    pochi perche' guarda dieci giorni; qui si pesca in un anno, quindi il controllo serve
    per davvero."""
    if not challenge:
        return False
    return bool(challenge.get("career_path")) and bool(challenge.get("correct_answers"))


def past_days_span(today=None):
    """(primo giorno giocabile, ultimo giorno giocabile). None se non c'e' passato."""
    today = today or today_iso()
    epoch = load_config().get("game_epoch", GAME_EPOCH_FALLBACK)
    last = shift_iso(today, -1)
    if last < epoch:
        return None
    return epoch, last


def random_past_day(today=None, rng=None):
    """Una data a caso fra l'inizio del gioco e ieri. None se il gioco e' appena partito."""
    span = past_days_span(today)
    if not span:
        return None
    first, last = span
    days = (parse_iso(last) - parse_iso(first)).days
    offset = (rng or random).randint(0, days)
    return to_iso(parse_iso(first) + timedelta(days=offset))


def pick_past_challenge(exclude_days=(), today=None, rng=None, tries=MAX_RANDOM_TRIES):
    """Una sfida passata a caso: ritorna (giorno, sfida) oppure (None, None).

    `exclude_days` evita di riproporre subito quello che si e' appena giocato (nel gruppo,
    gli ultimi round; in allenamento, la sfida in corso)."""
    excluded = set(exclude_days or ())

    for _ in range(tries):
        day = random_past_day(today, rng)
        if not day or day in excluded:
            continue
        challenge = firebase_service.get_daily_path(day)
        if is_playable(challenge):
            return day, challenge

    return _fallback_recent(excluded, rng)


def _fallback_recent(excluded, rng=None):
    """Ripiego: i giorni recenti in una query sola.

    Serve quando il gioco e' giovane (poche date scritte in un intervallo grande) o quando
    la pulizia ha lasciato buchi: senza, l'allenamento risponderebbe "nessuna sfida
    disponibile" pur avendone."""
    recent = firebase_service.get_past_daily_paths(limit=FALLBACK_WINDOW)
    candidates = [
        doc for doc in recent
        if is_playable(doc) and doc.get("day") and doc["day"] not in excluded
    ]
    if not candidates:
        logging.info("[PAST] Nessuna sfida passata riutilizzabile")
        return None, None

    chosen = (rng or random).choice(candidates)
    return chosen["day"], chosen
