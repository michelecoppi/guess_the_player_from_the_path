from datetime import datetime
from zoneinfo import ZoneInfo

from services import daily_generator

ITALY_TZ = ZoneInfo("Europe/Rome")


def test_buffer_dates_are_sequential_and_unique(monkeypatch):
    seen_dates = []

    def fake_exists(date_str):
        return False

    def fake_save(date_str, doc):
        seen_dates.append(date_str)

    monkeypatch.setattr(daily_generator.firebase_service, "daily_path_exists", fake_exists)
    monkeypatch.setattr(daily_generator.firebase_service, "get_recent_player_ids", lambda days: [])
    monkeypatch.setattr(daily_generator.firebase_service, "save_daily_path", fake_save)
    monkeypatch.setattr(daily_generator.firebase_service, "get_blocked_player_ids", lambda: [])

    daily_generator.ensure_daily_buffer(days_ahead=5)

    assert len(seen_dates) == 5
    assert len(set(seen_dates)) == 5  # nessuna data duplicata


def test_buffer_generation_across_dst_change(monkeypatch):
    """Il cambio di orario legale/solare non deve rompere la generazione del buffer
    (verifica solo la data di calendario, non l'orario esatto)."""
    seen_dates = []
    monkeypatch.setattr(daily_generator.firebase_service, "daily_path_exists", lambda date_str: False)
    monkeypatch.setattr(daily_generator.firebase_service, "get_recent_player_ids", lambda days: [])
    monkeypatch.setattr(daily_generator.firebase_service, "save_daily_path", lambda day_iso, doc: seen_dates.append(day_iso))
    monkeypatch.setattr(daily_generator.firebase_service, "get_blocked_player_ids", lambda: [])

    # 29/30 marzo 2026: passaggio all'ora legale in Europa
    fixed_now = datetime(2026, 3, 28, 23, 30, tzinfo=ITALY_TZ)
    monkeypatch.setattr(daily_generator, "datetime", _FixedDatetime(fixed_now))

    daily_generator.ensure_daily_buffer(days_ahead=4)
    assert len(seen_dates) == 4
    # Le date ISO sono ordinabili come stringhe: e' il motivo per cui sono state adottate.
    assert seen_dates == sorted(seen_dates)
    assert seen_dates[0] == "2026-03-28"


class _FixedDatetime:
    """Sostituto minimale di datetime.datetime che fissa .now() ma lascia invariati
    gli altri usi (strptime, ecc.) tramite delega alla classe reale."""

    def __init__(self, fixed_value):
        self._fixed_value = fixed_value

    def now(self, tz=None):
        return self._fixed_value

    def __getattr__(self, name):
        return getattr(datetime, name)
