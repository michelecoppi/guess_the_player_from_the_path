"""Admin system health (#38): failed/stuck job visibility, on a real Firestore (the
emulator).

What a fake cannot prove: that `list_failed_jobs` really filters `work_receipts` by
`status == "uncertain"` with a real `where()` query and decodes the lease expiry.
"""
import time

from services import firebase_service as fs


def test_list_failed_jobs_reports_only_uncertain_receipts(emulator_db):
    receipts = fs.db.collection("work_receipts")
    expires = time.time() - 30
    receipts.document("daily-job-2026-01-01-start").set(
        {"status": "uncertain", "expires": expires, "serial_key": "daily-2026-01-01"}
    )
    receipts.document("daily-job-2026-01-02-start").set({"status": "done"})
    receipts.document("broadcast-2026-01-03-page-1").set({"status": "processing", "expires": time.time() + 240})

    jobs = fs.list_failed_jobs(limit=10)

    assert [job["key"] for job in jobs] == ["daily-job-2026-01-01-start"]
    assert jobs[0]["serial_key"] == "daily-2026-01-01"
    assert jobs[0]["expired_at"] is not None


def test_list_failed_jobs_on_an_empty_collection(emulator_db):
    assert fs.list_failed_jobs(limit=10) == []


def test_list_failed_jobs_respects_the_limit(emulator_db):
    receipts = fs.db.collection("work_receipts")
    for i in range(3):
        receipts.document(f"job-{i}").set({"status": "uncertain", "expires": time.time() - 1})

    assert len(fs.list_failed_jobs(limit=2)) == 2
