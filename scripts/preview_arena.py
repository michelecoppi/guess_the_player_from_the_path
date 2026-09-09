"""In-memory arena fixtures for the local preview only. No database or Telegram calls."""
from datetime import datetime, timedelta, timezone

from fastapi import Body, HTTPException

from services import arena, practice_content
from services.dates import today_iso
from services.event_rules import evaluate_event_guess
from services.i18n import t
from services.player_pool import get_practice_players


def install(app, state, lang):
    puzzles = [practice_content.from_player(p) for p in get_practice_players()[:5]]
    if not puzzles:
        return
    sessions = {}
    event_progress = {"attempts": 0, "finished": False, "solved": False, "points": 0}

    @app.post("/app/api/arena")
    def preview(payload: dict = Body(default={})):
        mode, action = payload.get("mode"), payload.get("action", "get")
        try:
            if mode in ("training", "duel"):
                if action in ("next", "create", "join"):
                    sessions[mode] = {"challenges": puzzles[:1] if mode == "training" else puzzles,
                                      "seat": arena._seat("Marco"), "feedback": None}
                session = sessions.get(mode)
                if not session:
                    return {"session": None}
                if action in ("guess", "reveal"):
                    session["feedback"] = arena._move(session["challenges"], session["seat"], action,
                                                       payload.get("answer"), payload.get("revision"), 5 if mode == "training" else 3)
                if mode == "training":
                    return {"session": arena._view(session["challenges"], session["seat"], lang(), 5), "feedback": session["feedback"]}
                seat = session["seat"]
                seat["feedback"] = dict(session["feedback"] or {})
                seat["feedback"].pop("answer", None)
                opponent = arena._seat("Giulia")
                opponent.update(round=5, solved=3, spent=11, finished=True,
                                history=[{"solved": i < 3, "attempts": n} for i, n in enumerate([1, 2, 2, 3, 3])])
                doc = {"code": "a" * 24, "expires_at": datetime.now(timezone.utc) + timedelta(days=7),
                       "challenges": puzzles, "seats": {"1": seat}}
                if action == "join" or seat["finished"]:
                    doc["seats"]["2"] = opponent
                result = arena._duel_view(doc, "1", lang())
                result["invite_url"] = "https://t.me/preview_bot?start=duel_" + "a" * 24
                return result
            if mode == "events":
                feedback = None
                if action == "guess" and not event_progress["finished"]:
                    correct, _, _ = evaluate_event_guess("path", payload.get("answer", ""), puzzles[0])
                    event_progress["attempts"] += 1
                    event_progress["solved"] = correct
                    event_progress["finished"] = correct or event_progress["attempts"] == 3
                    event_progress["points"] += 3 if correct else 0
                    feedback = {"status": "correct" if correct else "wrong", "points": 3 if correct else 0}
                titles = {"it": "Giramondo", "en": "Globetrotters", "es": "Trotamundos"}
                descriptions = {"it": "Una settimana sulle tracce dei calciatori che hanno girato il mondo.",
                                "en": "A week following the players who travelled the world.",
                                "es": "Una semana tras los pasos de los jugadores que recorrieron el mundo."}
                return {"feedback": feedback, "events": [{"code": "preview", "day": today_iso(),
                        "type": "path", "name": titles[lang()], "description": descriptions[lang()],
                        "rules": t(lang(), "app.event.path"), "dates": [today_iso()], "available": True, "points": 2,
                        "bonus_available": not event_progress["solved"], "player_name": "", "min_correct": 1,
                        "progress": event_progress, "leaderboard": [{"name": "Giulia", "points": 12}, {"name": "Marco", "points": event_progress["points"]}],
                        **arena._puzzle(puzzles[0], lang())}]}
            raise arena.ArenaError("invalid")
        except arena.ArenaError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
