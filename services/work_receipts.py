"""Persist delivery state; never replay a possibly applied Telegram mutation."""
import time
from datetime import datetime, timedelta, timezone

from firebase_admin import firestore

from services import firebase_service as fs


def claim(key, lease_seconds=240, serial_key=None):
    ref = fs.db.collection("work_receipts").document(key)

    @firestore.transactional
    def take(tx):
        snap = ref.get(transaction=tx)
        previous = snap.to_dict() if snap.exists else {}
        if previous.get("status") in ("done", "uncertain"):
            return previous["status"]
        if previous.get("status") == "processing":
            if previous["expires"] > time.time():
                return "busy"
            tx.update(ref, {"status": "uncertain"})
            return "uncertain"
        lock = fs.db.collection("update_locks").document(serial_key) if serial_key else None
        if lock:
            locked = lock.get(transaction=tx)
            if locked.exists and locked.to_dict().get("expires", 0) > time.time():
                return "busy"
            tx.set(lock, {"owner": key, "expires": time.time() + lease_seconds})
        tx.set(ref, {"status": "processing", "expires": time.time() + lease_seconds,
                     "serial_key": serial_key,
                     "delete_after": datetime.now(timezone.utc) + timedelta(days=30)})
        return "claimed"

    return take(fs.db.transaction())


def finish(key):
    ref = fs.db.collection("work_receipts").document(key)

    @firestore.transactional
    def complete(tx):
        data = ref.get(transaction=tx).to_dict()
        lock = fs.db.collection("update_locks").document(data["serial_key"]) if data.get("serial_key") else None
        locked = lock.get(transaction=tx) if lock else None
        tx.update(ref, {"status": "done"})
        if locked and locked.exists and locked.to_dict().get("owner") == key:
            tx.delete(lock)
    complete(fs.db.transaction())


def release(key):
    """Only for errors that prove Telegram did not accept the message."""
    fs.db.collection("work_receipts").document(key).delete()
