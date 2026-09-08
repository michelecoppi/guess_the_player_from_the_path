"""Accesso alla sfida del giorno, con una cache di processo per la sola parte immutabile.

La distinzione e' il punto importante: il percorso di carriera, le risposte accettate e la
difficolta' di un giorno **non cambiano piu** una volta generati, quindi tenerli in memoria
fa risparmiare letture. Il flag "il bonus del primo e' ancora libero" invece cambia durante
la giornata: quello si legge sempre da Firestore, e si assegna in transazione
(`claim_daily_first_correct`), altrimenti due istanze del bot - o due utenti simultanei -
lo assegnerebbero due volte.
"""
import logging

from services import firebase_service
from services.dates import parse_iso, today_iso
from services.player_pool import load_config

_cache = {"day": None, "data": None}

# Usata se manca `game_epoch` in data/config.json: e' il giorno da cui si contano le sfide.
GAME_EPOCH_FALLBACK = "2025-06-08"

# Tentativi al giorno sulla sfida principale.
MAX_ATTEMPTS = 3


def get_today_challenge(generate_if_missing=True):
    """La sfida di oggi. Se manca (es. la GitHub Action non e' stata eseguita) la genera al
    volo, cosi' il gioco non si blocca mai."""
    day_iso = today_iso()

    if _cache["day"] == day_iso and _cache["data"]:
        return _cache["data"]

    data = firebase_service.get_daily_path(day_iso)

    if not data and generate_if_missing:
        logging.info(f"[DAILY] Nessuna sfida per {day_iso}: generazione al volo")
        from services.daily_generator import ensure_daily_buffer

        ensure_daily_buffer(days_ahead=1)
        data = firebase_service.get_daily_path(day_iso)

    if data:
        _cache["day"] = day_iso
        _cache["data"] = data
    return data


def bonus_available(day_iso=None):
    """Se il bonus 'primo che indovina' e' ancora da assegnare. Sempre letto da Firestore:
    e' stato mutabile e condiviso fra le istanze del bot."""
    day_iso = day_iso or today_iso()
    data = firebase_service.get_daily_path(day_iso)
    if not data:
        return False
    return not data.get("first_correct_user", False)


def invalidate():
    """Usata al cambio di giornata e dai test."""
    _cache["day"] = None
    _cache["data"] = None


def challenge_number(day_iso=None):
    """Numero progressivo della sfida ("#142"), contato dai giorni trascorsi da `game_epoch`
    (data/config.json). Serve alla card condivisibile e al piede dell'immagine: e' calcolato,
    non letto da Firestore, cosi' non costa niente e resta uguale per tutti."""
    day_iso = day_iso or today_iso()
    epoch = load_config().get("game_epoch", GAME_EPOCH_FALLBACK)
    try:
        return (parse_iso(day_iso) - parse_iso(epoch)).days + 1
    except (ValueError, TypeError):
        return 0
