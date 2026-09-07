from datetime import datetime

from services.dates import (
    is_iso,
    normalize_day,
    parse_iso,
    shift_iso,
    to_display,
    to_iso,
)


def test_iso_dates_sort_as_plain_strings():
    # E' il motivo per cui il database usa ISO: l'ordine alfabetico e' l'ordine cronologico,
    # quindi gli id documento sono ordinabili e si possono fare query di intervallo.
    days = ["2026-01-09", "2025-12-31", "2026-01-10"]
    assert sorted(days) == ["2025-12-31", "2026-01-09", "2026-01-10"]


def test_display_format_is_the_italian_one():
    assert to_display("2026-12-01") == "01/12/26"


def test_normalize_day_accepts_both_formats():
    assert normalize_day("01/12/26") == "2026-12-01"
    assert normalize_day("2026-12-01") == "2026-12-01"
    assert normalize_day(datetime(2026, 12, 1)) == "2026-12-01"


def test_normalize_day_leaves_unknown_values_alone():
    # Meglio un valore strano che un'eccezione in mezzo a una partita.
    assert normalize_day("non-una-data") == "non-una-data"
    assert normalize_day(None) is None
    assert normalize_day("") == ""


def test_to_display_tolerates_already_migrated_and_legacy_values():
    assert to_display("01/12/26") == "01/12/26"
    assert to_display(None) == ""


def test_shift_iso_crosses_month_and_year():
    assert shift_iso("2026-03-01", -1) == "2026-02-28"
    assert shift_iso("2025-12-31", 1) == "2026-01-01"


def test_round_trip():
    day = "2026-06-15"
    assert to_iso(parse_iso(day)) == day
    assert is_iso(day)
    assert not is_iso("15/06/26")
