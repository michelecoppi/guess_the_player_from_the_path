"""Modalita' Storia della mini app: capitoli a tema, giocabili al proprio ritmo (#story).

Un capitolo e' una sequenza fissa di livelli (`data/story.json`), ognuno 5 calciatori legati
da un evento o un'epoca in comune, non solo dalla difficolta'. Tre tentativi per calciatore,
come nel duello. La differenza con allenamento e duello e' lo scopo: qui un livello si puo'
**perdere**. Sforare i tentativi (o rivelare) su uno dei cinque manda a monte il livello
intero e si riparte dal suo primo calciatore - non dall'inizio del capitolo, quello resta un
checkpoint. Un livello superato senza mai sbagliare un colpo vale una stellina; il capitolo
completato (tutti i livelli superati, anche in run separate) sblocca un cosmetico guadagnato,
non comprabile (domains/shop/service.py), esattamente come il traguardo di allenamento.
"""
import copy
import json
import os

from firebase_admin import firestore

from services import firebase_service as fs
from services import practice_content
from services.career_order import order_career
from services.content_i18n import localize_career
from services.guess_feedback import build_comparison
from services.i18n import difficulty_label
from services.matching import find_match, looks_like_an_answer
from services.player_pool import get_player_by_id

STORY_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "story.json")
MAX_ATTEMPTS = 3

_catalogue = None


class StoryError(ValueError):
    pass


def _run(ref, change):
    """Stessa forma di services/arena.py::_run: legge, muta, scrive solo se e' cambiato
    qualcosa - cosi' una `get` che non tocca lo stato non genera una scrittura a vuoto."""
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


def _load():
    global _catalogue
    if _catalogue is None:
        with open(STORY_PATH, encoding="utf-8") as f:
            _catalogue = json.load(f)
    return _catalogue


def reload_catalogue():
    """Rilegge data/story.json. Serve ai test; in produzione si carica una volta sola."""
    global _catalogue
    _catalogue = None
    return _load()


def chapters():
    return _load().get("chapters", [])


def get_chapter(chapter_id):
    return next((c for c in chapters() if c["id"] == chapter_id), None)


def _theme_i18n(node, lang):
    if lang and lang != "it":
        translated = (node.get("theme_i18n") or {}).get(lang)
        if translated:
            return translated
    return node.get("theme")


def _title_i18n(node, lang):
    if lang and lang != "it":
        translated = (node.get("title_i18n") or {}).get(lang)
        if translated:
            return translated
    return node.get("title")


def _new_session(chapter):
    return {
        "level": 0, "step": 0, "attempts": 0, "revision": 0,
        "level_perfect": True, "finished": False, "history": [],
        "stars": [False] * len(chapter["levels"]),
    }


def _challenge_for(player_id):
    player = get_player_by_id(player_id)
    if not player:
        raise StoryError("missing_player")
    return practice_content.from_player(player)


def _puzzle(player_id, lang):
    challenge = _challenge_for(player_id)
    return {
        "career_path": localize_career(order_career(challenge.get("career_path")), lang),
        "difficulty_label": difficulty_label(lang, challenge.get("difficulty")),
    }


def _level_state(index, session):
    if session["finished"] or index < session["level"]:
        return "cleared"
    if index == session["level"]:
        return "current"
    return "locked"


def _level_entries(chapter, session, lang):
    """Un livello per la schermata di selezione: titolo (la sua categoria), se e' gia'
    sbloccato/superato e se porta la stellina - tutto quello che serve senza dover giocare
    per scoprirlo."""
    return [
        {"id": level["id"], "theme": _theme_i18n(level, lang),
         "state": _level_state(index, session), "starred": session["stars"][index]}
        for index, level in enumerate(chapter["levels"])
    ]


def _summary(chapter, session, lang):
    levels = chapter["levels"]
    return {
        "chapter_id": chapter["id"],
        "title": _title_i18n(chapter, lang),
        "total_levels": len(levels),
        "level": session["level"],
        "step": session["step"],
        "steps_per_level": len(levels[0]["player_ids"]) if levels else 0,
        "attempts": session["attempts"],
        "max_attempts": MAX_ATTEMPTS,
        "revision": session["revision"],
        "finished": session["finished"],
        "stars": list(session["stars"]),
        "history": copy.deepcopy(session["history"]),
        "levels": _level_entries(chapter, session, lang),
    }


def _view(chapter, session, lang):
    result = _summary(chapter, session, lang)
    if session["finished"]:
        return result
    level = chapter["levels"][session["level"]]
    result["theme"] = _theme_i18n(level, lang)
    result["level_number"] = level["id"]
    result.update(_puzzle(level["player_ids"][session["step"]], lang))
    return result


def _grant_completion(user, chapter, session):
    """Sblocca il cosmetico del capitolo (e quello per la run perfetta) la prima volta che
    scattano, dentro la stessa transazione del checkpoint: non deve poter succedere due
    volte, e non deve poter restare a meta'."""
    user["story_chapters_cleared"] = int(user.get("story_chapters_cleared", 0) or 0) + 1
    if all(session["stars"]):
        user["story_perfect_chapters"] = int(user.get("story_perfect_chapters", 0) or 0) + 1
    earned = fs._newly_earned(user)
    if earned:
        cosmetics = user.setdefault("cosmetics", {})
        cosmetics["earned"] = list(dict.fromkeys(cosmetics.get("earned", []) + earned))


def _move(user, chapter, session, action, answer, revision):
    if type(revision) is not int or revision != session["revision"]:
        raise StoryError("stale")
    if session["finished"]:
        raise StoryError("finished")
    if action not in ("guess", "reveal"):
        raise StoryError("invalid")
    if action == "guess" and (not isinstance(answer, str) or "," in answer or not looks_like_an_answer(answer)):
        raise StoryError("invalid_answer")

    level = chapter["levels"][session["level"]]
    player_id = level["player_ids"][session["step"]]
    challenge = _challenge_for(player_id)
    correct = action == "guess" and bool(find_match(answer, challenge.get("correct_answers", [])))

    if action == "guess" and not correct:
        session["attempts"] += 1
        session["revision"] += 1
        session["level_perfect"] = False
        if session["attempts"] < MAX_ATTEMPTS:
            return {"status": "wrong", "level_failed": False,
                    "comparison": build_comparison(answer, challenge.get("player_id"))}
        # Tentativi esauriti sull'ultimo calciatore utile: il livello e' perso, si riparte
        # dal suo primo calciatore. Il checkpoint (session["level"]) non si tocca.
        session["step"] = 0
        session["attempts"] = 0
        session["level_perfect"] = True
        session["history"] = []
        return {"status": "wrong", "level_failed": True, "answer": challenge.get("answer", "")}

    if action == "reveal":
        # Una rivelazione vale come un fallimento: niente scorciatoie per superare un
        # livello senza averlo davvero giocato.
        session["revision"] += 1
        session["step"] = 0
        session["attempts"] = 0
        session["level_perfect"] = True
        session["history"] = []
        return {"status": "revealed", "level_failed": True, "answer": challenge.get("answer", "")}

    # Risposta corretta: il calciatore e' fatto, si avanza.
    session["revision"] += 1
    session["history"].append({"solved": True, "attempts": session["attempts"] + 1})
    session["attempts"] = 0
    session["step"] += 1
    result = {"status": "correct", "level_failed": False, "answer": challenge.get("answer", "")}

    if session["step"] < len(level["player_ids"]):
        return result

    # Livello completato: stellina se non si e' mai sbagliato un colpo, poi si avanza.
    session["stars"][session["level"]] = session["stars"][session["level"]] or session["level_perfect"]
    result["level_cleared"] = True
    result["starred"] = session["level_perfect"]
    session["level"] += 1
    session["step"] = 0
    session["level_perfect"] = True
    session["history"] = []

    if session["level"] >= len(chapter["levels"]):
        session["finished"] = True
        result["chapter_cleared"] = True
        _grant_completion(user, chapter, session)

    return result


def chapters_progress(user, lang="it"):
    """Il progresso di un utente in ogni capitolo, dal documento che ha gia' in mano.

    Pura: non legge Firestore. E' quello che serve sia al menu degli episodi (via
    `list_chapters`, che aggiunge la lettura) sia alla dashboard admin, che il documento
    lo ha gia' letto e non deve rifarne una copia solo per contare le stelline."""
    progress = (user or {}).get("app_story") or {}
    result = []
    previous_finished = True
    for definition in chapters():
        session = progress.get(definition["id"])
        total = len(definition["levels"])
        cleared = min(session["level"], total) if session else 0
        finished = bool(session and session["finished"])
        result.append({
            "chapter_id": definition["id"],
            "title": _title_i18n(definition, lang),
            "total_levels": total,
            "levels_cleared": cleared,
            "stars_earned": sum(1 for s in (session or {}).get("stars", []) if s),
            "finished": finished,
            # Il primo episodio e' sempre aperto; i successivi si sbloccano finendo quello
            # prima - una campagna, non un buffet.
            "locked": not previous_finished,
        })
        previous_finished = finished
    return result


def list_chapters(user_id, lang="it"):
    """Il menu degli episodi: uno per capitolo in data/story.json, con il progresso di questo
    utente se ne ha gia' uno. Una sola lettura, niente transazione: non si muove nulla."""
    user = fs.get_user_data(user_id) or {}
    return {"chapters": chapters_progress(user, lang)}


def _is_locked(user, chapter_id):
    """Stessa regola di list_chapters: aperto se e' il primo, o se il precedente e' finito."""
    progress = (user or {}).get("app_story") or {}
    for definition in chapters():
        if definition["id"] == chapter_id:
            return False
        if not (progress.get(definition["id"]) or {}).get("finished"):
            return True
    return False


def chapter(user_id, chapter_id, action="get", answer=None, revision=None, lang="it"):
    definition = get_chapter(chapter_id)
    if not definition:
        raise StoryError("invalid")
    if action not in ("get", "guess", "reveal"):
        raise StoryError("invalid")

    def change(user):
        if not user:
            raise StoryError("invalid")
        if _is_locked(user, chapter_id):
            raise StoryError("locked")
        story = user.setdefault("app_story", {})
        session = story.get(chapter_id)
        if not session:
            session = _new_session(definition)
            story[chapter_id] = session
        feedback = None
        if action in ("guess", "reveal"):
            feedback = _move(user, definition, session, action, answer, revision)
        return {"chapter": _view(definition, session, lang), "feedback": feedback}

    return _run(fs.user_ref(user_id), change)
