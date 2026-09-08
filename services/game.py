"""Le regole di una partita, senza Telegram e senza HTTP.

Esiste perche' da oggi la stessa sfida si gioca in **due posti**: la chat del bot e la mini
app. Se il punteggio, il consumo dei tentativi e il costo degli indizi vivessero dentro
`handlers/guess_handler.py`, la mini app dovrebbe riscriverli - e due implementazioni delle
stesse regole divergono sempre, di solito su un caso limite che nessuno prova (il bonus del
primo, il pavimento dei punti dopo due indizi, la striscia).

Qui dentro non si costruisce nessun messaggio: si ritorna **cosa e' successo**, e chi chiama
decide come dirlo. Il bot lo traduce in un messaggio Telegram, la mini app in JSON.

L'unica cosa che questo modulo sa fare oltre alle regole e' scrivere su Firestore, perche'
consumare un tentativo e assegnare i punti sono per definizione scritture.
"""
import logging

from services import firebase_service
from services.daily_challenge import MAX_ATTEMPTS, get_today_challenge
from services.dates import today_iso
from services.difficulty import points_for_difficulty
from services.guess_feedback import build_comparison
from services.hints import MAX_HINTS, build_hints, points_after_hints
from services.matching import find_match
from services.player_pool import get_player_by_id


def hints_available(challenge, lang):
    """Gli indizi che questa sfida puo' davvero dare, gia' resi nella lingua richiesta.

    Il numero dipende dalla scheda del calciatore e non dal massimo teorico: senza `position`
    ce n'e' uno solo. Serve sia al bot (per decidere se mostrare il bottone) sia alla mini
    app (per disegnare le caselle vuote degli indizi)."""
    return build_hints(get_player_by_id((challenge or {}).get("player_id")), lang)


def max_hints_for(challenge, lang):
    return min(MAX_HINTS, len(hints_available(challenge, lang)))


def play_daily(user_id, user_data, answer, first_name=None, day_iso=None, challenge=None):
    """Un tentativo sulla sfida del giorno.

    Ritorna sempre un dizionario con `status`:

    - `no_challenge`: non c'e' una sfida per oggi;
    - `refused`: il tentativo non e' ammesso, e `reason` dice perche' (`not_registered`,
      `already_guessed`, `no_attempts`);
    - `wrong`: sbagliato, con `attempts_left` e `comparison` (il confronto con il calciatore
      che l'utente ha scritto, o None);
    - `correct`: giusto, con i punti effettivamente assegnati.

    `challenge` si passa solo per non rileggerla quando chi chiama ce l'ha gia'."""
    day_iso = day_iso or today_iso()
    challenge = challenge or get_today_challenge()
    if not challenge:
        return {"status": "no_challenge"}

    # Il tentativo si consuma in transazione: contatori corretti anche con due risposte
    # inviate nello stesso istante (due schede della mini app, o app e chat insieme).
    attempt = firebase_service.begin_guess_attempt(user_id, day_iso, MAX_ATTEMPTS)
    if not attempt["ok"]:
        return {
            "status": "refused",
            "reason": attempt["reason"],
            "attempts_used": attempt.get("attempts_used", MAX_ATTEMPTS),
            "hints_used": attempt.get("hints_used", 0),
        }

    # Il primo tentativo della giornata conta la persona fra quelle che ci hanno provato:
    # e' il denominatore della percentuale mostrata a giornata chiusa.
    if attempt["attempts_used"] == 1:
        firebase_service.register_daily_outcome(day_iso, solved=False)

    hints_used = attempt.get("hints_used", 0)
    logging.info(f"[GUESS] {user_id} su {day_iso}: {answer}")

    match = find_match(answer, challenge.get("correct_answers", []))
    if not match:
        result = {
            "status": "wrong",
            "attempts_used": attempt["attempts_used"],
            "attempts_left": attempt["attempts_left"],
            "hints_used": hints_used,
            "comparison": build_comparison(answer, challenge.get("player_id")),
        }
        if attempt["attempts_left"] == 0:
            # La giornata e' chiusa per questo utente: si registra com'e' andata, cosi'
            # l'archivio e il calendario della mini app sanno mostrarla come persa.
            firebase_service.record_daily_history(
                user_id, day_iso, solved=False, attempts=attempt["attempts_used"], hints=hints_used
            )
        return result

    firebase_service.register_daily_outcome(day_iso, solved=True)

    # Gli indizi si pagano solo se si indovina: su una sfida persa non c'era niente da
    # togliere. Il bonus del primo non viene scalato, e' un premio a parte.
    points = points_after_hints(points_for_difficulty(challenge.get("difficulty")), hints_used)
    bonus = 1 if firebase_service.claim_daily_first_correct(day_iso) else 0

    # I punti della striscia li calcola la transazione che la aggiorna: qui non sappiamo (e
    # non possiamo sapere senza leggere) a che giorno consecutivo siamo arrivati.
    registered = firebase_service.register_correct_guess(
        user_id, points + bonus, bonus, day_iso, attempts=attempt["attempts_used"]
    ) or {}
    awarded = registered.get("points_awarded", points + bonus)

    # Le leghe private tengono il loro punteggio: i codici sono gia' sul documento utente,
    # quindi non serve nessuna query per sapere dove sommarli.
    firebase_service.add_points_to_leagues(
        user_id, (user_data or {}).get("leagues", []), awarded, name=first_name
    )
    firebase_service.record_daily_history(
        user_id, day_iso, solved=True, attempts=attempt["attempts_used"], hints=hints_used
    )

    return {
        "status": "correct",
        "attempts_used": attempt["attempts_used"],
        "attempts_left": attempt["attempts_left"],
        "hints_used": hints_used,
        "typo": match["typo"],
        "points_awarded": awarded,
        "bonus": bonus,
        "streak": registered.get("current_streak", 0),
        "streak_bonus": registered.get("streak_bonus", 0),
    }


def play_archive(user_id, day_iso, answer, max_attempts):
    """Un tentativo su una sfida d'archivio: stessa forma di `play_daily`, senza punti.

    Rigiocare il passato non deve permettere di scalare la classifica, quindi qui non c'e'
    nessun punteggio: si tiene solo il conto delle giornate recuperate. In compenso la
    risposta si puo' rivelare (`answer` nel risultato quando i tentativi finiscono), perche'
    quella giornata e' gia' passata per tutti."""
    challenge = firebase_service.get_daily_path(day_iso)
    if not challenge:
        return {"status": "no_challenge"}

    attempt = firebase_service.begin_archive_attempt(user_id, day_iso, max_attempts)
    if not attempt["ok"]:
        return {"status": "refused", "reason": attempt["reason"]}

    if find_match(answer, challenge.get("correct_answers", [])):
        firebase_service.register_archive_solved(user_id, day_iso, attempt["attempts_used"])
        return {
            "status": "correct",
            "attempts_used": attempt["attempts_used"],
            "attempts_left": attempt["attempts_left"],
        }

    result = {
        "status": "wrong",
        "attempts_used": attempt["attempts_used"],
        "attempts_left": attempt["attempts_left"],
        # Stesso confronto della sfida di oggi: senza, l'archivio sarebbe piu' difficile del
        # gioco vero.
        "comparison": build_comparison(answer, challenge.get("player_id")),
    }
    if attempt["attempts_left"] == 0:
        result["answer"] = firebase_service.get_display_name_for_day(day_iso) or "?"
    return result


def take_hint(user_id, lang, day_iso=None, challenge=None):
    """Un indizio sulla sfida del giorno.

    Ritorna `{'status': 'ok', 'index', 'total', 'text', 'points', 'full_points'}` oppure
    `{'status': 'refused', 'reason': ...}` / `{'status': 'unavailable'}` / `{'status':
    'no_challenge'}`.

    Gli indizi si costruiscono **prima** di consumarne uno: se la scheda non ha niente da
    dire, nessuno deve pagare un punto per un messaggio vuoto."""
    day_iso = day_iso or today_iso()
    challenge = challenge or get_today_challenge()
    if not challenge:
        return {"status": "no_challenge"}

    hints = hints_available(challenge, lang)
    if not hints:
        return {"status": "unavailable"}

    total = min(MAX_HINTS, len(hints))
    taken = firebase_service.take_daily_hint(user_id, day_iso, total, MAX_ATTEMPTS)
    if not taken["ok"]:
        return {"status": "refused", "reason": taken["reason"], "total": total}

    index = taken["index"]
    full_points = points_for_difficulty(challenge.get("difficulty"))
    return {
        "status": "ok",
        "index": index,
        "total": total,
        "hints_used": taken["hints_used"],
        "text": hints[index - 1],
        "points": points_after_hints(full_points, index),
        "full_points": full_points,
    }
