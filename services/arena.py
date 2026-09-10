"""Mini app practice and private duels. Only explicit public projections leave here.

Practice sessions live on the user; duels store two seats and five immutable puzzles.
Every move is transactional and revision checked, so retries cannot spend two attempts.

A finished duel also leaves a trace on both profiles: the running head to head score
against that opponent and the last matches, so "who won more" survives the seven days
of the duel document.
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
# How many finished duels the profile keeps in full (paths and answers included).
MATCHES = 10
OUTCOMES = {"win": "won", "loss": "lost", "draw": "drawn"}


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


def _outcome(seat, opponent):
    own = (seat["solved"], -seat["spent"])
    other = (opponent["solved"], -opponent["spent"])
    return "draw" if own == other else "win" if own > other else "loss"


def _rounds(doc, seat, opponent, complete):
    """The paths already closed, as `seat` is allowed to see them.

    Answers stay hidden until both players are done: the name of a path the opponent has
    not played yet would be worth telling them. Their own result on each path shows up as
    soon as their five paths are over, which reveals nothing but tells you how you stand.
    """
    rows = []
    for index, own in enumerate(seat["history"]):
        row = {"n": index + 1, "solved": own["solved"], "attempts": own["attempts"]}
        if complete:
            row["answer"] = doc["challenges"][index].get("answer", "")
        if opponent and opponent["finished"] and index < len(opponent["history"]):
            row["opponent"] = {k: opponent["history"][index][k] for k in ("solved", "attempts")}
        rows.append(row)
    return rows


def _duel_view(doc, uid, lang):
    seat = doc["seats"][uid]
    finished = len(doc["seats"]) == 2 and all(s["finished"] for s in doc["seats"].values())
    opponent = next((s for key, s in doc["seats"].items() if key != uid), None)
    result = {"code": doc["code"], "expires_at": doc["expires_at"].isoformat(),
              "session": _view(doc["challenges"], seat, lang, 3),
              "opponent": ({k: opponent[k] for k in ("name", "round", "finished")} if opponent else None),
              "complete": finished, "feedback": seat.get("feedback"),
              "rounds": _rounds(doc, seat, opponent, finished)}
    if finished:
        assert opponent is not None
        result["outcome"] = _outcome(seat, opponent)
        result["opponent"].update(solved=opponent["solved"], spent=opponent["spent"])
    return result


def _match(doc, uid):
    """The finished duel as it goes into a profile: scores, outcome and the five answers.

    It is a copy on purpose. The duel document lives seven days and then goes away, while
    this is what the player will still be able to read months later.
    """
    seat = doc["seats"][uid]
    key, opponent = next((key, other) for key, other in doc["seats"].items() if key != uid)
    return {"code": doc["code"], "opponent_id": int(key), "name": opponent["name"],
            "outcome": _outcome(seat, opponent), "ended_at": datetime.now(timezone.utc).isoformat(),
            "you": {"solved": seat["solved"], "spent": seat["spent"]},
            "them": {"solved": opponent["solved"], "spent": opponent["spent"]},
            "rounds": [{"answer": challenge.get("answer", ""),
                        "you": {k: own[k] for k in ("solved", "attempts")},
                        "them": {k: other[k] for k in ("solved", "attempts")}}
                       for challenge, own, other in
                       zip(doc["challenges"], seat["history"], opponent["history"])]}


def _remember(user_id, match):
    """File a finished duel on the profile and return the profile as it now stands.

    Each player files their own copy, once: the duel document carries the receipt
    (`recorded`), so a refresh cannot count the same match twice.
    """
    def change(user):
        if not user:
            return {}
        record = user.setdefault("app_duel_record", {})
        entry = record.setdefault(str(match["opponent_id"]), {"won": 0, "lost": 0, "drawn": 0})
        # The name lives here and nowhere else, so `/forgetme` of the other person can take
        # it away with a single field delete (services/repos/users.erase_user).
        entry["name"] = match["name"]
        entry[OUTCOMES[match["outcome"]]] = int(entry.get(OUTCOMES[match["outcome"]], 0)) + 1
        kept = [old for old in user.get("app_duel_matches") or [] if old.get("code") != match["code"]]
        user["app_duel_matches"] = [{k: v for k, v in match.items() if k != "name"}] + kept[:MATCHES - 1]
        return user
    return _run(fs.user_ref(user_id), change)


def ledger(profile, opponent_id=None):
    """The head to head panel: the running score against this opponent and the last
    matches. A projection of the profile; ids of other people stay on the server."""
    profile = profile or {}
    record = profile.get("app_duel_record") or {}
    entry = record.get(str(opponent_id)) if opponent_id is not None else None
    matches = []
    for match in (profile.get("app_duel_matches") or [])[:MATCHES]:
        row = {key: match.get(key) for key in ("code", "outcome", "ended_at", "you", "them", "rounds")}
        row["name"] = (record.get(str(match.get("opponent_id"))) or {}).get("name", "")
        matches.append(row)
    head_to_head = None
    if entry:
        head_to_head = {"name": entry.get("name", "")}
        head_to_head.update({key: int(entry.get(key, 0)) for key in ("won", "lost", "drawn")})
    return {"record": head_to_head, "matches": matches}


def _open_summary(doc, uid):
    """The little a duel list needs to show one row: who it's against (if anyone has
    joined), whether it still needs someone, and how far this player has gotten."""
    seat = doc["seats"][uid]
    opponent = next((s for key, s in doc["seats"].items() if key != uid), None)
    finished = len(doc["seats"]) == 2 and all(s["finished"] for s in doc["seats"].values())
    return {"code": doc["code"], "opponent": opponent["name"] if opponent else None,
            "complete": finished, "round": seat["round"], "total": len(doc["challenges"]),
            "expires_at": doc["expires_at"].isoformat()}


def list_duels(user_id, profile=None):
    """Every duel this player is still part of: waiting for an opponent, in progress, or
    finished but not yet filed on the profile (`_remember`). A filed duel already lives on
    as a match in the ledger, so it drops out here - otherwise it would show up twice."""
    uid = str(user_id)
    now = datetime.now(timezone.utc)
    open_duels = []
    query = fs.db.collection(DUELS).where("members", "array_contains", user_id)
    for snapshot in query.stream():
        doc = snapshot.to_dict()
        if not doc or doc["expires_at"] <= now or uid in (doc.get("recorded") or []):
            continue
        open_duels.append(_open_summary(doc, uid))
    open_duels.sort(key=lambda d: d["expires_at"], reverse=True)
    return {"open": open_duels,
            "ledger": ledger(profile if profile is not None else fs.get_user_data(user_id))}


def _delete_if_alone(user_id, code):
    """Withdraw an invitation nobody has taken yet. Once a second seat exists the duel
    belongs to both players, and only expiry or finishing it closes it."""
    uid = str(user_id)
    ref = fs.db.collection(DUELS).document(code)

    @firestore.transactional
    def commit(transaction):
        snapshot = ref.get(transaction=transaction)
        doc = snapshot.to_dict() if snapshot.exists else None
        if not doc or uid not in doc["seats"]:
            raise ArenaError("invalid")
        if len(doc["seats"]) > 1:
            raise ArenaError("full")
        transaction.delete(ref)
    commit(fs.db.transaction())


def duel(user_id, name, action="get", code=None, answer=None, revision=None, lang="it", profile=None):
    uid = str(user_id)
    if action == "delete":
        if not isinstance(code, str) or not CODE.fullmatch(code):
            raise ArenaError("invalid")
        _delete_if_alone(user_id, code)
        return {"deleted": code}
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
        result = _duel_view(doc, uid, lang)
        result["ledger"] = ledger(profile if profile is not None else fs.get_user_data(user_id))
        return result
    if action not in ("get", "join", "guess", "reveal") or not isinstance(code, str) or not CODE.fullmatch(code):
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
        if action in ("guess", "reveal"):
            # Chi crea non gioca da solo in vantaggio: i percorsi restano chiusi finche'
            # non arriva un avversario a occupare il secondo posto.
            if len(doc["seats"]) < 2:
                raise ArenaError("waiting_opponent")
            feedback = _move(doc["challenges"], doc["seats"][uid], action, answer, revision, 3)
            feedback.pop("answer", None)
            doc["seats"][uid]["feedback"] = feedback
        view = _duel_view(doc, uid, lang)
        opponent = next((key for key in doc["seats"] if key != uid), None)
        match = None
        if view["complete"] and uid not in (doc.get("recorded") or []):
            doc.setdefault("recorded", []).append(uid)
            match = _match(doc, uid)
        return {"view": view, "match": match, "opponent": opponent}
    outcome = _run(fs.db.collection(DUELS).document(code), change)
    if action == "join":
        fs.user_ref(user_id).update({"app_duel": code})
    if outcome["match"]:
        profile = _remember(user_id, outcome["match"])
    elif profile is None:
        profile = fs.get_user_data(user_id)
    result = outcome["view"]
    result["ledger"] = ledger(profile, outcome["opponent"])
    return result
