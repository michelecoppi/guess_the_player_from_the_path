"""Reset "pigro" dei contatori giornalieri e job di mezzanotte.

Il punto: non esiste piu' nessuna scrittura di azzeramento. Un contatore di ieri vale zero
oggi perche' il documento porta con se' il giorno a cui si riferisce.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from handlers import daily_job
from services import firebase_service

ITALY_TZ = ZoneInfo("Europe/Rome")


def test_yesterday_counters_count_as_zero_today(monkeypatch):
    monkeypatch.setattr(firebase_service, "get_user_data", lambda user_id: {
        "daily_attempts": 3,
        "has_guessed_today": True,
        "last_played_day": "2026-09-06",
    })

    attempts, guessed = firebase_service.get_user_daily_status(1, day_iso="2026-09-07")

    assert attempts == 0
    assert guessed is False


def test_today_counters_are_kept(monkeypatch):
    monkeypatch.setattr(firebase_service, "get_user_data", lambda user_id: {
        "daily_attempts": 2,
        "has_guessed_today": False,
        "last_played_day": "2026-09-07",
    })

    assert firebase_service.get_user_daily_status(1, day_iso="2026-09-07") == (2, False)


def test_legacy_display_dates_are_still_understood(monkeypatch):
    # Utente non ancora migrato: la data e' nel vecchio formato gg/mm/aa.
    monkeypatch.setattr(firebase_service, "get_user_data", lambda user_id: {
        "daily_attempts": 1,
        "has_guessed_today": True,
        "last_played_day": "07/09/26",
    })

    assert firebase_service.get_user_daily_status(1, day_iso="2026-09-07") == (1, True)


def test_unknown_user_has_no_attempts(monkeypatch):
    monkeypatch.setattr(firebase_service, "get_user_data", lambda user_id: None)
    assert firebase_service.get_user_daily_status(1, day_iso="2026-09-07") == (0, False)


# ---------------------------------------------------------------------------
# Reset mensile
# ---------------------------------------------------------------------------

def _monthly_fakes(monkeypatch, top_users, season_exists=True):
    calls = {"trophies": [], "reset": 0, "created_season": not season_exists}

    def get_or_create_season(month, year):
        return {"month": month, "year": year, "season_number": 4}, not season_exists

    monkeypatch.setattr(daily_job.firebase_service, "get_or_create_season", get_or_create_season)
    monkeypatch.setattr(daily_job.firebase_service, "get_top_users", lambda field, limit: top_users)
    monkeypatch.setattr(daily_job.firebase_service, "add_user_trophy",
                        lambda tid, code: calls["trophies"].append((tid, code)))
    monkeypatch.setattr(daily_job.firebase_service, "reset_monthly_points",
                        lambda: calls.__setitem__("reset", calls["reset"] + 1))
    return calls


def test_monthly_reset_only_on_the_first_day(monkeypatch):
    calls = _monthly_fakes(monkeypatch, [])
    assert daily_job.handle_monthly_reset(datetime(2026, 9, 15, tzinfo=ITALY_TZ)) is None
    assert calls["reset"] == 0


def test_monthly_reset_assigns_trophies_and_zeroes_points(monkeypatch):
    top = [
        {"telegram_id": 1, "username": "Anna", "monthly_points": 20},
        {"telegram_id": 2, "username": "Bruno", "monthly_points": 12},
    ]
    calls = _monthly_fakes(monkeypatch, top)

    message = daily_job.handle_monthly_reset(datetime(2026, 9, 1, tzinfo=ITALY_TZ))

    assert "Anna" in message and "Bruno" in message
    assert [t[0] for t in calls["trophies"]] == [1, 2]
    assert calls["trophies"][0][1].startswith("MON_August_4_2026_")
    assert calls["reset"] == 1


def test_monthly_reset_still_zeroes_points_without_participants(monkeypatch):
    # Prima, senza il documento della stagione, il reset usciva in silenzio e i punti
    # mensili restavano per sempre.
    calls = _monthly_fakes(monkeypatch, [], season_exists=False)

    message = daily_job.handle_monthly_reset(datetime(2026, 9, 1, tzinfo=ITALY_TZ))

    assert message is None
    assert calls["reset"] == 1


def test_users_with_zero_monthly_points_are_not_awarded(monkeypatch):
    top = [
        {"telegram_id": 1, "username": "Anna", "monthly_points": 5},
        {"telegram_id": 2, "username": "Bruno", "monthly_points": 0},
    ]
    calls = _monthly_fakes(monkeypatch, top)

    daily_job.handle_monthly_reset(datetime(2026, 9, 1, tzinfo=ITALY_TZ))

    assert [t[0] for t in calls["trophies"]] == [1]


# ---------------------------------------------------------------------------
# Broadcast di mezzanotte
# ---------------------------------------------------------------------------

def test_broadcast_congratulates_only_who_guessed_yesterday(monkeypatch):
    import asyncio

    sent = []

    class FakeBot:
        async def send_message(self, chat_id, text):
            sent.append((chat_id, text))

    monkeypatch.setattr(daily_job, "get_bot", lambda: FakeBot())
    monkeypatch.setattr(daily_job.asyncio, "sleep", _no_sleep)
    monkeypatch.setattr(daily_job.firebase_service, "get_broadcast_users", lambda day: [
        {"chat_id": 1, "has_guessed_today": True},
        {"chat_id": 2, "has_guessed_today": False},
    ])

    asyncio.run(daily_job._broadcast("2026-09-06", "Messi", None, None))

    assert "Complimenti per aver indovinato il calciatore Messi" in sent[0][1]
    assert "Non hai indovinato il calciatore Messi" in sent[1][1]


def test_broadcast_survives_a_blocked_user(monkeypatch):
    import asyncio

    class FakeBot:
        async def send_message(self, chat_id, text):
            if chat_id == 1:
                raise RuntimeError("bot bloccato dall'utente")

    monkeypatch.setattr(daily_job, "get_bot", lambda: FakeBot())
    monkeypatch.setattr(daily_job.asyncio, "sleep", _no_sleep)
    monkeypatch.setattr(daily_job.firebase_service, "get_broadcast_users", lambda day: [
        {"chat_id": 1, "has_guessed_today": True},
        {"chat_id": 2, "has_guessed_today": True},
    ])

    sent, errors = asyncio.run(daily_job._broadcast("2026-09-06", "Messi", None, None))

    assert (sent, errors) == (1, 1)


def test_broadcast_mentions_the_active_event(monkeypatch):
    import asyncio

    sent = []

    class FakeBot:
        async def send_message(self, chat_id, text):
            sent.append(text)

    monkeypatch.setattr(daily_job, "get_bot", lambda: FakeBot())
    monkeypatch.setattr(daily_job.asyncio, "sleep", _no_sleep)
    monkeypatch.setattr(daily_job.firebase_service, "get_broadcast_users", lambda day: [
        {"chat_id": 1, "has_guessed_today": False},
    ])

    asyncio.run(daily_job._broadcast("2026-09-06", "Messi", {"name": "Giramondo"}, None))

    assert "Giramondo" in sent[0]


async def _no_sleep(_seconds):
    return None
