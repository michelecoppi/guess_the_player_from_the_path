"""Referral attribution and qualification. Only server-recorded daily finishes count."""
import hashlib
import hmac
import logging
import re

from firebase_admin import firestore

from config import BOT_TOKEN, BOT_USERNAME
from services import firebase_service as fs
from services.dates import today_iso
from services.repos import bulk

COLLECTION = "referrals"
REQUIRED_DAYS = 5
REWARDS = {3: ["referral_intesa"], 5: ["referral_lavagna"],
           10: ["referral_undici", "referral_undici_frame", "referral_undici_card"]}


def referral_key(user_id):
    return hashlib.sha256(f"gtp-referral:{user_id}".encode()).hexdigest()


def ref(user_id):
    return fs.db.collection(COLLECTION).document(referral_key(user_id))


def code_for(user_id):
    if not BOT_TOKEN:
        raise ValueError("Referral links require a bot token")
    signature = hmac.new(BOT_TOKEN.encode(), f"ref:{user_id}".encode(), hashlib.sha256).hexdigest()[:20]
    return f"ref_{user_id}_{signature}"


def inviter_from_code(code):
    match = re.fullmatch(r"ref_([1-9][0-9]{0,15})_([a-f0-9]{20})", code or "")
    if not match or not BOT_TOKEN:
        return None
    user_id = int(match[1])
    return user_id if user_id <= 2**52 and hmac.compare_digest(code, code_for(user_id)) else None


def prepare_attribution(transaction, user_id, name, code):
    """Read before any registration writes; an existing ledger entry cannot be reused."""
    inviter = inviter_from_code(code)
    if inviter is None or inviter == user_id:
        return None
    prior = ref(user_id).get(transaction=transaction)
    owner = fs.user_ref(inviter).get(transaction=transaction)
    if prior.exists or not owner.exists:
        return None
    return {"inviter_id": inviter, "invitee_id": user_id, "name": name,
            "joined_day": today_iso(), "joined_at": firestore.SERVER_TIMESTAMP,
            "days": [], "status": "pending", "qualified_at": None}


def credit_day(user_id, day):
    """Atomically update unique dates, inviter count and permanent rewards.

    The history record is durable evidence. A retry or reconciliation can safely replay it.
    """
    from services import shop
    ledger_ref = ref(user_id)

    @firestore.transactional
    def commit(transaction):
        snapshot = ledger_ref.get(transaction=transaction)
        entry = snapshot.to_dict() or {}
        if entry.get("status") != "pending" or day < entry.get("joined_day", day):
            return False
        days = entry.get("days", [])
        if day in days:
            return False
        history = fs.history_ref(user_id, day).get(transaction=transaction).to_dict() or {}
        from services.daily_challenge import MAX_ATTEMPTS
        if not history or not (history.get("solved") or history.get("attempts", 0) >= MAX_ATTEMPTS):
            return False
        owner_ref = fs.user_ref(entry["inviter_id"])
        owner_snapshot = owner_ref.get(transaction=transaction)
        if not owner_snapshot.exists:
            return False
        days = sorted(set(days + [day]))
        update = {"days": days, "updated_at": firestore.SERVER_TIMESTAMP}
        if len(days) >= REQUIRED_DAYS:
            owner = owner_snapshot.to_dict()
            count = int(owner.get("referral_qualified", 0)) + 1
            owner["referral_qualified"] = count
            earned = shop.newly_earned(owner)
            fields = {"referral_qualified": count}
            if earned:
                fields["cosmetics.earned"] = firestore.ArrayUnion(sorted(earned))
            transaction.update(owner_ref, fields)
            update.update(status="qualified", qualified_at=firestore.SERVER_TIMESTAMP)
        transaction.update(ledger_ref, update)
        return True

    return commit(fs.db.transaction())


def record_completion(user_id, day):
    # The history commit survives a temporary referral failure. The club view replays it.
    try:
        # Almost nobody has a pending ledger, and this runs on every finished daily: a plain
        # read costs one call, the transaction three. The transaction re-checks anyway.
        if (ref(user_id).get().to_dict() or {}).get("status") == "pending":
            credit_day(user_id, day)
    except Exception:
        logging.exception("[REFERRAL] pending recovery: ledger=%s day=%s", referral_key(user_id), day)


def reconcile(entry):
    """True only when a day was really credited: that is the caller's cue to re-read."""
    if entry.get("status") != "pending" or not entry.get("invitee_id"):
        return False
    credited = False
    # Five latest distinct finishes suffice: only the first five are required.
    for history in fs.get_daily_history(entry["invitee_id"], limit=REQUIRED_DAYS):
        if history["day"] >= entry["joined_day"] and history["day"] not in entry.get("days", []):
            credited = credit_day(entry["invitee_id"], history["day"]) or credited
    return credited


def dashboard(user_id, lang="it", cursor=None, user=None):
    """A private, paginated projection; never expose identifiers of invited players.

    The caller already authenticated, and that cost it a read of the user document: passing
    it back in spares a second one for the counter and the reward cards."""
    from services import shop
    query = fs.db.collection(COLLECTION).where("inviter_id", "==", user_id).order_by("__name__")
    if cursor and re.fullmatch(r"[a-f0-9]{64}", cursor):
        query = query.start_after({"__name__": fs.db.collection(COLLECTION).document(cursor)})
    snapshots = list(query.limit(21).stream())
    rows = []
    for snapshot in snapshots[:20]:
        entry = snapshot.to_dict()
        if reconcile(entry):
            # Only a recovered day makes the query snapshot stale, and it is the rare case:
            # re-reading every row turned a page of the club into twenty extra reads.
            entry = snapshot.reference.get().to_dict() or {}
            if entry.get("inviter_id") != user_id:
                continue  # Account removal erased the association during this request.
        rows.append({"name": entry.get("name", ""), "days": len(entry.get("days", [])),
                     "status": entry.get("status"), "joined_day": entry.get("joined_day")})
    user = user if user is not None else fs.get_user_data(user_id) or {}
    return {"qualified": user.get("referral_qualified", 0), "required_days": REQUIRED_DAYS,
            "link": f"https://t.me/{BOT_USERNAME}?start={code_for(user_id)}" if BOT_USERNAME and BOT_TOKEN else None,
            "friends": rows, "next_cursor": snapshots[19].id if len(snapshots) > 20 else None,
            "rewards": [{"target": target, "items": [shop._card(shop.get_item(i), user, lang, shop.equipped(user)) for i in ids]}
                        for target, ids in REWARDS.items()]}


def erase_user(user_id):
    """Remove referral personal data, retaining only a pseudonymous no-reuse marker.

    A `set` and not an `update`: the marker is what the whole document must be reduced to.
    Dropping `inviter_id` is also what unlinks the row from the erased inviter, so a row
    already swept stops matching the query - but the sweep advances by cursor and does not
    rely on that.

    Rows can be many: an inviter who shared the link widely has one per friend.
    """
    own = ref(user_id)
    if own.get().exists:
        own.set({"status": "deleted"})
    return bulk.sweep(fs.db.collection(COLLECTION).where("inviter_id", "==", user_id),
                      lambda writer, snapshot: writer.set(snapshot.reference, {"status": "deleted"}))
