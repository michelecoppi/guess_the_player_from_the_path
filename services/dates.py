"""Un solo posto in cui si decide come si scrive una data.

Su Firestore le date sono salvate in **ISO `YYYY-MM-DD`**: e' l'unico formato ordinabile
lessicograficamente, quindi permette id documento ordinati, query di intervallo
("le sfide di questo mese") e confronti diretti fra stringhe.

All'utente le date si mostrano invece nel formato italiano `gg/mm/aa`, che e' quello che il
bot ha sempre usato nei messaggi.

`normalize_day()` accetta entrambi i formati: serve a leggere senza sorprese i documenti
scritti prima della migrazione a ISO (`scripts/migrate_firestore.py`).
"""
from datetime import datetime, timedelta

import pytz

ITALY_TZ = pytz.timezone("Europe/Rome")

ISO_FORMAT = "%Y-%m-%d"
DISPLAY_FORMAT = "%d/%m/%y"


def now_italy():
    return datetime.now(ITALY_TZ)


def to_iso(value):
    """Da datetime/date a stringa ISO."""
    return value.strftime(ISO_FORMAT)


def today_iso():
    return to_iso(now_italy())


def shift_iso(day_iso, days):
    return to_iso(parse_iso(day_iso) + timedelta(days=days))


def yesterday_iso():
    return shift_iso(today_iso(), -1)


def parse_iso(day_iso):
    return datetime.strptime(day_iso, ISO_FORMAT)


def parse_display(day_display):
    return datetime.strptime(day_display, DISPLAY_FORMAT)


def to_display(day_iso):
    """Da ISO al formato mostrato agli utenti (gg/mm/aa)."""
    if not day_iso:
        return ""
    try:
        return parse_iso(day_iso).strftime(DISPLAY_FORMAT)
    except ValueError:
        # gia' nel formato di visualizzazione (documento non ancora migrato)
        return day_iso


def normalize_day(value):
    """Ritorna sempre la forma ISO, accettando sia 'gg/mm/aa' sia 'YYYY-MM-DD'.
    Se il valore non e' una data riconoscibile lo ritorna invariato: meglio un dato strano
    che un'eccezione in mezzo a una partita."""
    if not value:
        return value
    if isinstance(value, datetime):
        return to_iso(value)
    for parser in (parse_iso, parse_display):
        try:
            return to_iso(parser(value))
        except (ValueError, TypeError):
            continue
    return value


def is_iso(value):
    try:
        parse_iso(value)
        return True
    except (ValueError, TypeError):
        return False
