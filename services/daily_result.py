"""Il risultato di una Daily **come l'ha registrato il server**, per la figurina da condividere.

La figurina porta il nome di chi l'ha fatta e finisce in un gruppo: i numeri che disegna
(tentativi, esito, indizi, serie) non possono arrivare da chi la chiede. Qui si leggono dallo
storico salvato quando la giornata si e' chiusa (`record_daily_history`), con gli stessi
controlli per la Mini App (`/app/api/card`) e per il bottone del bot (#162, #222).
"""
from services import firebase_service
from services.daily_challenge import MAX_ATTEMPTS
from services.dates import parse_iso, to_iso
from services.hints import MAX_HINTS


class ResultUnavailable(Exception):
    """The result cannot be shown: `status` is the HTTP status, `detail` the reason."""

    def __init__(self, status, detail):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def checked(record, day):
    """Lo storico di `day` ridotto a {day, attempts, hints, solved}, o ResultUnavailable:
    409 se quella giornata non si e' chiusa, 422 se i numeri salvati sono fuori intervallo."""
    if not record or record.get("day") != day:
        raise ResultUnavailable(409, "partita non conclusa")
    attempts = record.get("attempts")
    hints = record.get("hints")
    if type(attempts) is not int or not 1 <= attempts <= MAX_ATTEMPTS:
        raise ResultUnavailable(422, "tentativi non validi")
    if type(hints) is not int or not 0 <= hints <= MAX_HINTS:
        raise ResultUnavailable(422, "indizi non validi")
    return {"day": day, "attempts": attempts, "hints": hints, "solved": record.get("solved") is True}


def result_for_day(user_id, day):
    """Il risultato salvato di una giornata precisa. `day` arriva da un bottone: se non e'
    una data valida si risponde come per una giornata non giocata."""
    try:
        day = to_iso(parse_iso(day))
    except (ValueError, TypeError):
        raise ResultUnavailable(409, "partita non conclusa") from None
    snapshot = firebase_service.history_ref(user_id, day).get()
    return checked(snapshot.to_dict() if snapshot.exists else None, day)


def latest_result(user_id):
    """L'ultima giornata chiusa, qualunque sia."""
    history = firebase_service.get_daily_history(user_id, limit=1)
    if not history:
        raise ResultUnavailable(409, "partita non conclusa")
    return checked(history[0], history[0].get("day"))


def card_streak(user_data, result):
    """La serie da mostrare accanto a quel risultato.

    `current_streak` sul documento utente vale per `last_correct_day`: e' la serie di quella
    giornata solo se quella giornata e' proprio l'ultima indovinata. Per una giornata persa o
    ormai superata non c'e' una serie da dire, e si tace invece di inventarla."""
    user_data = user_data or {}
    if not result["solved"] or user_data.get("last_correct_day") != result["day"]:
        return 0
    streak = user_data.get("current_streak")
    return streak if type(streak) is int and streak > 0 else 0
