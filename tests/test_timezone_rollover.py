from datetime import datetime
from zoneinfo import ZoneInfo

from services import daily_generator, dates
from tests import planner_fakes

ITALY_TZ = ZoneInfo("Europe/Rome")


def test_buffer_dates_are_sequential_and_unique(monkeypatch):
    store = planner_fakes.install(monkeypatch)

    daily_generator.ensure_daily_buffer(days_ahead=5)

    assert len(store.saved) == 5
    assert len(set(store.saved)) == 5  # nessuna data duplicata


def test_buffer_generation_across_dst_change(monkeypatch):
    """Il cambio di orario legale/solare non deve rompere la generazione del buffer
    (verifica solo la data di calendario, non l'orario esatto)."""
    store = planner_fakes.install(monkeypatch)

    # 29/30 marzo 2026: passaggio all'ora legale in Europa
    monkeypatch.setattr(dates, "now_italy", lambda: datetime(2026, 3, 28, 23, 30, tzinfo=ITALY_TZ))

    daily_generator.ensure_daily_buffer(days_ahead=4)
    assert len(store.saved) == 4
    # Le date ISO sono ordinabili come stringhe: e' il motivo per cui sono state adottate.
    assert store.saved == sorted(store.saved)
    assert store.saved[0] == "2026-03-28"
    assert store.saved[-1] == "2026-03-31"
