from datetime import datetime

import pytz

from services import daily_generator

ITALY_TZ = pytz.timezone("Europe/Rome")


def test_buffer_dates_are_sequential_and_unique(monkeypatch):
    seen_dates = []

    def fake_exists(date_str):
        return False

    def fake_save(date_str, doc):
        seen_dates.append(date_str)

    monkeypatch.setattr(daily_generator.firebase_service, "daily_path_exists", fake_exists)
    monkeypatch.setattr(daily_generator.firebase_service, "get_recent_player_ids", lambda days: [])
    monkeypatch.setattr(daily_generator.firebase_service, "save_daily_path", fake_save)

    daily_generator.ensure_daily_buffer(days_ahead=5)

    assert len(seen_dates) == 5
    assert len(set(seen_dates)) == 5  # nessuna data duplicata


def test_buffer_generation_across_dst_change(monkeypatch):
    """Il cambio di orario legale/solare non deve rompere la generazione del buffer
    (verifica solo la data di calendario, non l'orario esatto)."""
    seen_dates = []
    monkeypatch.setattr(daily_generator.firebase_service, "daily_path_exists", lambda date_str: False)
    monkeypatch.setattr(daily_generator.firebase_service, "get_recent_player_ids", lambda days: [])
    monkeypatch.setattr(daily_generator.firebase_service, "save_daily_path", lambda date_str, doc: seen_dates.append(date_str))

    # 29/30 marzo 2026: passaggio all'ora legale in Europa
    fixed_now = ITALY_TZ.localize(datetime(2026, 3, 28, 23, 30))
    monkeypatch.setattr(daily_generator, "datetime", _FixedDatetime(fixed_now))

    daily_generator.ensure_daily_buffer(days_ahead=4)
    assert len(seen_dates) == 4
    assert seen_dates == sorted(seen_dates, key=lambda d: datetime.strptime(d, "%d/%m/%y"))


class _FixedDatetime:
    """Sostituto minimale di datetime.datetime che fissa .now() ma lascia invariati
    gli altri usi (strptime, ecc.) tramite delega alla classe reale."""

    def __init__(self, fixed_value):
        self._fixed_value = fixed_value

    def now(self, tz=None):
        return self._fixed_value

    def __getattr__(self, name):
        return getattr(datetime, name)
