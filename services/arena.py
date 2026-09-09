"""Mini app practice and private duels. Only explicit public projections leave here.

Practice sessions live on the user; duels store two seats and five immutable puzzles.
Every move is transactional and revision checked, so retries cannot spend two attempts.
"""
import copy
import re
import secrets
from datetime import datetime, timedelta, timezone

from firebase_admin import firestore

from services import firebase_service as fs
from services import practice_content
from services.career_order import order_career
from services.content_i18n import localize_career
from services.guess_feedback import build_comparison
from services.i18n import difficulty_label
from services.matching import find_match, looks_like_an_answer

DUELS = "app_duels"
CODE = re.compile(r"^[a-f0-9]{24}$")


class ArenaError(ValueError):
    pass


def _run(ref, change):
    @firestore.transactional
    def commit(transaction):
        snapshot = ref.get(transaction=transaction)
        data = snapshot.to_dict() if snapshot.exists else {}
        original = copy.deepcopy(data)
        result = change(data)
        if data != original:
            transaction.set(ref, data)
        return result
    return commit(fs.db.transaction())


def _seat(name):
    return {"name": name, "round": 0, "attempts": 0, "solved": 0,
            "spent": 0, "revision": 0, "finished": False, "history": []}


def _puzzle(challenge, lang):
    return {"career_path": localize_career(order_career(challenge.get("career_path")), lang),
            "difficulty_label": difficulty_label(lang, challenge.get("difficulty"))}


def _view(challenges, seat, lang, maximum):
    result = {k: copy.deepcopy(seat[k]) for k in
              ("round", "attempts", "solved", "spent", "revision", "finished", "history")}
    result.update(total=len(challenges), max_attempts=maximum)
    if not seat["finished"]:
        result.update(_puzzle(challenges[seat["round"]], lang))
    return result


def _move(challenges, seat, action, answer, revision, maximum):
    if type(revision) is not int or revision != seat["revision"]:
        raise ArenaError("stale")
    if seat["finished"]:
        raise ArenaError("finished")
    if action not in ("guess", "reveal"):
        raise ArenaError("invalid")
    if action == "guess" and (not isinstance(answer, str) or "," in answer or not looks_like_an_answer(answer)):
        raise ArenaError("invalid_answer")
    challenge = challenges[seat["round"]]
    correct = action == "guess" and bool(find_match(answer, challenge.get("correct_answers", [])))
    seat["attempts"] += 1
    seat["revision"] += 1
    done = correct or action == "reveal" or seat["attempts"] >= maximum
    result = {"status": "correct" if correct else "wrong", "done": done}
    if not correct and action == "guess":
        result["comparison"] = build_comparison(answer, challenge.get("player_id"))
    if done:
        cost = seat["attempts"] if correct else maximum
        seat["spent"] += cost
        seat["solved"] += int(correct)
        seat["history"].append({"solved": correct, "attempts": cost})
        seat["round"] += 1
        seat["attempts"] = 0
        seat["finished"] = seat["round"] == len(challenges)
        # Practice content is safe to reveal. Duels additionally hide names until both finish.
        result["answer"] = challenge.get("answer", "")
    return result


def training(user_id, action="get", answer=None, revision=None, lang="it"):
    if action not in ("get", "next", "guess", "reveal"):
        raise ArenaError("invalid")
    current = fs.get_user_data(user_id) if action == "next" else None
    previous = ((current or {}).get("app_training") or {}).get("challenges", [])
    candidate = practice_content.pick(exclude_keys=[c["key"] for c in previous]) if action == "next" else None
    if action == "next" and not candidate:
        raise ArenaError("empty")

    def change(user):
        if not user:
            raise ArenaError("invalid")
        session = user.get("app_training")
        if action == "next":
            session = {"challenges": [candidate], "seat": _seat("")}
            session["seat"]["revision"] = (user.get("app_training") or {}).get("seat", {}).get("revision", 0) + 1
            user["app_training"] = session
        if not session:
            return {"session": None}
        feedback = None
        if action in ("guess", "reveal"):
            feedback = _move(session["challenges"], session["seat"], action, answer, revision, 5)
            session["feedback"] = feedback
            if feedback["status"] == "correct":
                user["training_solved"] = user.get("training_solved", 0) + 1
                earned = fs._newly_earned(user)
                if earned:
                    cosmetic = user.setdefault("cosmetics", {})
                    cosmetic["earned"] = list(dict.fromkeys(cosmetic.get("earned", []) + earned))
        return {"session": _view(session["challenges"], session["seat"], lang, 5),
                "feedback": session.get("feedback")}
    return _run(fs.user_ref(user_id), change)


def _duel_view(doc, uid, lang):
    seat = doc["seats"][uid]
    finished = len(doc["seats"]) == 2 and all(s["finished"] for s in doc["seats"].values())
    opponent = next((s for key, s in doc["seats"].items() if key != uid), None)
    result = {"code": doc["code"], "expires_at": doc["expires_at"].isoformat(),
              "session": _view(doc["challenges"], seat, lang, 3),
              "opponent": ({k: opponent[k] for k in ("name", "round", "finished")} if opponent else None),
              "complete": finished, "feedback": seat.get("feedback")}
    if finished:
        assert opponent is not None
        own_score = (seat["solved"], -seat["spent"])
        other_score = (opponent["solved"], -opponent["spent"])
        result["outcome"] = "draw" if own_score == other_score else "win" if own_score > other_score else "loss"
        result["opponent"].update(solved=opponent["solved"], spent=opponent["spent"])
        result["recap"] = [{"answer": challenge.get("answer", ""), "you": own, "opponent": other}
                           for challenge, own, other in zip(doc["challenges"], seat["history"], opponent["history"])]
    return result


def duel(user_id, name, action="get", code=None, answer=None, revision=None, lang="it"):
    uid = str(user_id)
    if action == "create":
        challenges = []
        keys: list[str] = []
        for _ in range(5):
            challenge = practice_content.pick(exclude_keys=keys)
            if not challenge or challenge["key"] in keys:
                raise ArenaError("empty")
            challenges.append(challenge)
            keys.append(challenge["key"])
        code = secrets.token_hex(12)
        doc = {"code": code, "challenges": challenges, "members": [user_id],
               "seats": {uid: _seat(name)}, "expires_at": datetime.now(timezone.utc) + timedelta(days=7)}
        fs.db.collection(DUELS).document(code).create(doc)
        fs.user_ref(user_id).update({"app_duel": code})
        return _duel_view(doc, uid, lang)
    if action not in ("get", "join", "guess") or not isinstance(code, str) or not CODE.fullmatch(code):
        raise ArenaError("invalid")

    def change(doc):
        if not doc or doc["expires_at"] <= datetime.now(timezone.utc):
            raise ArenaError("expired")
        if uid not in doc["seats"]:
            if action != "join":
                raise ArenaError("join_required")
            if len(doc["seats"]) >= 2:
                raise ArenaError("full")
            doc["seats"][uid] = _seat(name)
            doc["members"].append(user_id)
        if action == "guess":
            feedback = _move(doc["challenges"], doc["seats"][uid], action, answer, revision, 3)
            feedback.pop("answer", None)
            doc["seats"][uid]["feedback"] = feedback
        return _duel_view(doc, uid, lang)
    result = _run(fs.db.collection(DUELS).document(code), change)
    if action == "join":
        fs.user_ref(user_id).update({"app_duel": code})
    return result
