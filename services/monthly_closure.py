"""Freeze podium before reset; persist each user's reset atomically for retries."""
from datetime import timedelta

from firebase_admin import firestore
from google.api_core.exceptions import AlreadyExists

from services import firebase_service as fs


def reset_user(ref, closure):
    @firestore.transactional
    def reset(tx):
        snap = ref.get(transaction=tx)
        if not snap.exists:
            return 0
        data = snap.to_dict()
        if data.get("last_monthly_reset", "") >= closure["closed_month"]:
            return 0
        earned = data.get("monthly_earned", {})
        tx.update(ref, {
            "monthly_points": sum(value for key, value in earned.items() if key >= closure["new_month"]),
            "monthly_earned": {key: value for key, value in earned.items() if key >= closure["new_month"]},
            "last_monthly_reset": closure["closed_month"],
        })
        return 1
    return reset(fs.db.transaction())


def close_batch(day, cursor=None):
    from services import broadcast_store, task_queue
    result = broadcast_store.get_job(day)["monthly_result"]
    for user in result["winners"]:
        fs.add_user_trophy(user["telegram_id"], user["trophy_code"])
    query = fs.db.collection(fs.USERS_COLLECTION).order_by("__name__").limit(100)
    if cursor:
        query = query.start_after({"__name__": fs.user_ref(cursor)})
    docs = list(query.stream())
    for doc in docs:
        reset_user(doc.reference, result)
    if len(docs) == 100:
        next_cursor = docs[-1].id
        task_queue.enqueue("/internal/monthly-close", {"day": day, "cursor": next_cursor},
                           f"monthly-{day}-{next_cursor}", broadcast=True)
    else:
        task_queue.enqueue("/internal/broadcast", {"day": day}, f"broadcast-{day}-start", broadcast=True)
    return {"processed": len(docs)}


def prepare(now):
    previous = now.replace(day=1) - timedelta(days=1)
    month = previous.strftime("%B")
    year = str(previous.year)
    key = previous.strftime("%Y-%m")
    ref = fs.db.collection("monthly_closures").document(key)
    snap = ref.get()
    if snap.exists:
        return snap.to_dict()
    season, _ = fs.get_or_create_season(month, year)
    # Exclude any new-month points already earned before Scheduler arrived.
    candidates = []
    for doc in fs.db.collection(fs.USERS_COLLECTION).where("monthly_points", ">", 0).stream():
        user = doc.to_dict()
        points = user.get("monthly_points", 0) - user.get("monthly_earned", {}).get(now.strftime("%Y-%m"), 0)
        if points > 0:
            candidates.append({"telegram_id": user.get("telegram_id", int(doc.id)),
                               "username": user.get("first_name", "?"), "monthly_points": points})
    top = sorted(candidates, key=lambda row: (-row["monthly_points"], row["telegram_id"]))[:3]
    result = {"month_name": month, "year": year, "winners": [
        {**user, "position": position,
         "trophy_code": f"MON_{month}_{season['season_number']}_{year}_{position}"}
        for position, user in enumerate(top, 1)
    ], "closed_month": key, "new_month": now.strftime("%Y-%m")}
    try:
        ref.create(result)
        return result
    except AlreadyExists:
        return ref.get().to_dict()


def close(now):
    if now.day != 1:
        return None
    result = prepare(now)
    for user in result["winners"]:
        fs.add_user_trophy(user["telegram_id"], user["trophy_code"])
    fs.reset_monthly_points(closure=result)
    return result if result["winners"] else None
