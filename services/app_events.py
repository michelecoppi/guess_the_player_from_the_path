"""Localized event cards and transactional mini app event attempts."""
from firebase_admin import firestore

from services import event_config
from services import firebase_service as fs
from services.arena import ArenaError
from services.career_order import order_career
from services.content_i18n import localize_career
from services.dates import normalize_day, today_iso
from services.event_rules import evaluate_event_guess
from services.guess_feedback import build_comparison
from services.i18n import content_text, t


def _progress(participant, day, max_attempts):
    same = normalize_day(participant.get("last_played_day")) == day
    attempts = participant.get("daily_attempts", 0) if same else 0
    return {"attempts": participant.get("daily_attempts", 0) if same else 0,
            "finished": bool(same and (participant.get("has_guessed_today") or participant.get("daily_attempts", 0) >= max_attempts)),
            "solved": bool(same and participant.get("has_guessed_today")),
            "points": participant.get("points", 0),
            "revealed": max(1, participant.get("daily_revealed", 1)) if same else 1,
            "revision": participant.get("daily_revision", attempts) if same else 0}


def list_events(user_id, lang):
    day = today_iso()
    cards = []
    for event in fs.get_active_events(day):
        data = (event.get("daily_data") or {}).get(day) or {}
        kind = event.get("type", "path")
        max_attempts = event_config.event_rules(event)["attempts"]
        participant = fs.get_event_participant(event["code"], user_id) or {}
        progress = _progress(participant, day, max_attempts)
        career = order_career(data.get("career_path"))
        if kind == "blind_path":
            career = career[-min(progress["revealed"], len(career)):]
        cards.append({
            "code": event["code"], "day": day, "type": kind,
            "name": content_text(event, "name", lang),
            "description": content_text(event, "description", lang),
            "dates": event.get("dates", []), "available": bool(data),
            "rules": t(lang, "app.event." + kind if kind in event_config.EVENT_TYPES else "app.event.default"),
            "player_name": data.get("player_name", "") if event_config.is_multi_answer(kind) or kind == "order_career" else "",
            "player_names": data.get("player_names", []) if kind == "link_club" else [],
            "shuffled_stops": data.get("shuffled_stops", []) if kind == "order_career" else [],
            "min_correct": data.get("min_correct", len(data.get("correct_answers", []))) if event_config.is_multi_answer(kind) else 1,
            "career_path": localize_career(career, lang),
            "total_stops": len(data.get("career_path") or []) if kind == "blind_path" else None,
            "image_url": data.get("image_url") if not data.get("career_path") else None,
            "points": max(1, data.get("points", 1) - progress["revealed"] + 1) if kind == "blind_path" else data.get("points", 1),
            "bonus_available": event_config.event_rewards(event)["first_correct_bonus"] > 0
            and not data.get("first_correct_user", False),
            "max_attempts": max_attempts,
            "progress": progress,
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
        max_attempts = event_config.event_rules(event)["attempts"]
        progress = _progress(player, day, max_attempts)
        kind = event.get("type", "path")
        expected_revision = progress["revision"] if kind == "blind_path" else progress["attempts"]
        if type(revision) is not int or revision != expected_revision:
            raise ArenaError("stale")
        if progress["finished"]:
            raise ArenaError("finished")
        if event_config.is_multi_answer(kind) and len([p for p in answer.split(",") if p.strip()]) > event_config.MAX_ANSWERS_PER_ATTEMPT:
            raise ArenaError("max_answers")
        correct, matched, _ = evaluate_event_guess(kind, answer.strip().lower(), data)
        bonus_value = event_config.event_rewards(event)["first_correct_bonus"]
        bonus = bonus_value if correct and bonus_value > 0 and not data.get("first_correct_user") else 0
        base_points = max(1, data.get("points", 1) - progress["revealed"] + 1) if kind == "blind_path" else data.get("points", 1)
        points = base_points + bonus if correct else 0
        transaction.set(player_ref, {"telegram_id": user_id, "name": name,
                                    "last_played_day": day, "daily_attempts": progress["attempts"] + 1,
                                    "daily_revision": progress["revision"] + 1,
                                    "daily_revealed": progress["revealed"] if kind == "blind_path" else 1,
                                    "has_guessed_today": correct, "points": progress["points"] + points}, merge=True)
        if bonus:
            transaction.update(event_ref, {f"daily_data.{day}.first_correct_user": True})
        return {"status": "correct" if correct else "wrong", "points": points, "matched": matched,
                "comparison": build_comparison(answer, data.get("player_id")) if not correct and event_config.answers_with_player(kind) else None}
    return commit(fs.db.transaction())


def reveal(user_id, code, day, revision):
    """Reveal exactly one earlier stop for this participant, with the guess revision lock."""
    if not isinstance(code, str) or not code or len(code) > 100 or "/" in code:
        raise ArenaError("invalid")
    if day != today_iso():
        raise ArenaError("stale")
    event_ref = fs.event_ref(code)
    player_ref = fs.participant_ref(code, user_id)

    @firestore.transactional
    def commit(transaction):
        event_snapshot = event_ref.get(transaction=transaction)
        player_snapshot = player_ref.get(transaction=transaction)
        event = event_snapshot.to_dict() if event_snapshot.exists else {}
        player = player_snapshot.to_dict() if player_snapshot.exists else {}
        data = (event.get("daily_data") or {}).get(day)
        if event.get("type") != "blind_path" or day not in event.get("dates", []) or not data:
            raise ArenaError("expired")
        progress = _progress(player, day, event_config.event_rules(event)["attempts"])
        if type(revision) is not int or revision != progress["revision"]:
            raise ArenaError("stale")
        if progress["finished"]:
            raise ArenaError("finished")
        if progress["revealed"] >= len(data.get("career_path") or []):
            raise ArenaError("finished")
        transaction.set(player_ref, {"telegram_id": user_id, "last_played_day": day,
                                     "daily_revealed": progress["revealed"] + 1,
                                     "daily_revision": progress["revision"] + 1}, merge=True)
        return {"status": "revealed"}

    return commit(fs.db.transaction())
