"""Localized event cards and transactional mini app event attempts."""
from firebase_admin import firestore

from services import firebase_service as fs
from services.arena import ArenaError
from services.career_order import order_career
from services.content_i18n import localize_career
from services.dates import normalize_day, today_iso
from services.event_rules import evaluate_event_guess
from services.guess_feedback import build_comparison
from services.i18n import content_text, t


def _progress(participant, day):
    same = normalize_day(participant.get("last_played_day")) == day
    return {"attempts": participant.get("daily_attempts", 0) if same else 0,
            "finished": bool(same and (participant.get("has_guessed_today") or participant.get("daily_attempts", 0) >= 3)),
            "solved": bool(same and participant.get("has_guessed_today")),
            "points": participant.get("points", 0)}


def list_events(user_id, lang):
    day = today_iso()
    cards = []
    for event in fs.get_active_events(day):
        data = (event.get("daily_data") or {}).get(day) or {}
        kind = event.get("type", "path")
        participant = fs.get_event_participant(event["code"], user_id) or {}
        cards.append({
            "code": event["code"], "day": day, "type": kind,
            "name": content_text(event, "name", lang),
            "description": content_text(event, "description", lang),
            "dates": event.get("dates", []), "available": bool(data),
            "rules": t(lang, "app.event." + kind if kind in ("path", "career", "father_son", "transfer_guess") else "app.event.default"),
            "player_name": data.get("player_name", "") if kind == "career" else "",
            "min_correct": data.get("min_correct", len(data.get("correct_answers", []))) if kind == "career" else 1,
            "career_path": localize_career(order_career(data.get("career_path")), lang),
            "image_url": data.get("image_url") if not data.get("career_path") else None,
            "points": data.get("points", 1), "bonus_available": not data.get("first_correct_user", False),
            "progress": _progress(participant, day),
            "leaderboard": [{"name": row.get("name", "?"), "points": row.get("points", 0)}
                            for row in fs.get_event_leaderboard(event["code"], limit=10)],
        })
    return {"events": cards}


def guess(user_id, name, code, day, answer, revision):
    if not isinstance(code, str) or not code or len(code) > 100 or "/" in code:
        raise ArenaError("invalid")
    if day != today_iso():
        raise ArenaError("stale")
    if not isinstance(answer, str) or not answer.strip() or len(answer) > 220:
        raise ArenaError("invalid_answer")
    event_ref = fs.event_ref(code)
    player_ref = fs.participant_ref(code, user_id)

    @firestore.transactional
    def commit(transaction):
        event_snapshot = event_ref.get(transaction=transaction)
        player_snapshot = player_ref.get(transaction=transaction)
        event = event_snapshot.to_dict() if event_snapshot.exists else {}
        player = player_snapshot.to_dict() if player_snapshot.exists else {}
        data = (event.get("daily_data") or {}).get(day)
        if day not in event.get("dates", []) or not data:
            raise ArenaError("expired")
        progress = _progress(player, day)
        if type(revision) is not int or revision != progress["attempts"]:
            raise ArenaError("stale")
        if progress["finished"]:
            raise ArenaError("finished")
        kind = event.get("type", "path")
        if kind == "career" and len([p for p in answer.split(",") if p.strip()]) > 5:
            raise ArenaError("max_answers")
        correct, matched, _ = evaluate_event_guess(kind, answer.strip().lower(), data)
        bonus = int(correct and not data.get("first_correct_user"))
        points = data.get("points", 1) + bonus if correct else 0
        transaction.set(player_ref, {"telegram_id": user_id, "name": name,
                                    "last_played_day": day, "daily_attempts": progress["attempts"] + 1,
                                    "has_guessed_today": correct, "points": progress["points"] + points}, merge=True)
        if bonus:
            transaction.update(event_ref, {f"daily_data.{day}.first_correct_user": True})
        return {"status": "correct" if correct else "wrong", "points": points, "matched": matched,
                "comparison": build_comparison(answer, data.get("player_id")) if not correct and kind in ("path", "transfer_guess") else None}
    return commit(fs.db.transaction())
