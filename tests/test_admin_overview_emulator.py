"""Admin overview (#33) on a real Firestore (the emulator).

What a fake cannot prove: that the aggregation queries (count/where) and the streamed
average over `daily_attempts`/`daily_hints` actually talk to Firestore and only include
today's players, not the whole user collection.
"""
from services import firebase_service as fs
from services.dates import shift_iso, today_iso


def make_user(user_id, *, last_played_day=None, has_guessed_today=False, daily_attempts=0, daily_hints=0):
    data = dict(fs.USER_FIELD_DEFAULTS)
    data.update(
        last_played_day=last_played_day,
        has_guessed_today=has_guessed_today,
        daily_attempts=daily_attempts,
        daily_hints=daily_hints,
    )
    fs.db.collection(fs.USERS_COLLECTION).document(user_id).set(data)


def test_overview_averages_only_todays_players(emulator_db):
    today = today_iso()
    yesterday = shift_iso(today, -1)

    make_user("u1", last_played_day=today, has_guessed_today=True, daily_attempts=1, daily_hints=0)
    make_user("u2", last_played_day=today, has_guessed_today=False, daily_attempts=3, daily_hints=2)
    make_user("u3", last_played_day=yesterday, has_guessed_today=True, daily_attempts=5, daily_hints=5)

    overview = fs.get_admin_overview()

    assert overview["users_total"] == 3
    assert overview["users_guessed_today"] == 1
    assert overview["active_users_today"] == 2
    assert overview["avg_attempts_today"] == 2.0
    assert overview["avg_hints_today"] == 1.0


def test_overview_counts_uncertain_work_receipts_as_failed_jobs(emulator_db):
    receipts = fs.db.collection("work_receipts")
    receipts.document("daily-job-2026-01-01").set({"status": "uncertain"})
    receipts.document("daily-job-2026-01-02").set({"status": "done"})
    receipts.document("broadcast-2026-01-03").set({"status": "processing", "expires": 9999999999})

    overview = fs.get_admin_overview()

    assert overview["failed_jobs_recent"] == 1


def test_overview_with_no_active_users_today_has_zero_averages(emulator_db):
    overview = fs.get_admin_overview()

    assert overview["users_total"] == 0
    assert overview["active_users_today"] == 0
    assert overview["avg_attempts_today"] == 0.0
    assert overview["avg_hints_today"] == 0.0
    assert overview["failed_jobs_recent"] == 0
