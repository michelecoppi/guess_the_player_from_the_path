"""Game state, privacy projections and retries without a production database."""
import copy
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from services import app_events, arena
from services import firebase_service as fs


class MemoryRef:
    def __init__(self, store, key):
        self.store, self.key = store, key

    def get(self, transaction=None):
        data = copy.deepcopy(self.store.get(self.key))
        return SimpleNamespace(exists=data is not None, to_dict=lambda: data)

    def create(self, data):
        assert self.key not in self.store
        self.store[self.key] = copy.deepcopy(data)

    def update(self, fields):
        for key, value in fields.items():
            target = self.store[self.key]
            parts = key.split(".")
            for part in parts[:-1]:
                target = target.setdefault(part, {})
            target[parts[-1]] = copy.deepcopy(value)


class MemoryTransaction:
    def set(self, ref, data, merge=False):
        if merge:
            ref.store.setdefault(ref.key, {}).update(copy.deepcopy(data))
        else:
            ref.store[ref.key] = copy.deepcopy(data)

    def update(self, ref, fields):
        ref.update(fields)


@pytest.fixture
def store(monkeypatch):
    values = {"users/1": {"first_name": "Anna", "points_totali": 42},
              "users/2": {"first_name": "Bea"}, "users/3": {"first_name": "Carlo"}}
    def ref(key):
        return MemoryRef(values, key)
    db = SimpleNamespace(collection=lambda collection: SimpleNamespace(document=lambda key: ref(f"{collection}/{key}")),
                         transaction=MemoryTransaction)
    monkeypatch.setattr(arena.fs, "db", db)
    monkeypatch.setattr(arena.fs, "user_ref", lambda uid: ref(f"users/{uid}"))
    monkeypatch.setattr(arena.fs, "get_user_data", lambda uid: copy.deepcopy(values[f"users/{uid}"]))
    monkeypatch.setattr(arena.fs, "_newly_earned", lambda user: [])
    monkeypatch.setattr(arena.firestore, "transactional", lambda fn: fn)
    monkeypatch.setattr(arena, "build_comparison", lambda answer, pid: {"name": answer, "clues": []})

    def pick(exclude_keys=()):
        number = next(i for i in range(10) if f"pool:p{i}" not in exclude_keys)
        return {"key": f"pool:p{number}", "player_id": f"secret-{number}",
                "correct_answers": ["paolo maldini"], "answer": "Paolo Maldini", "difficulty": "easy",
                "career_path": [{"team": "Milan", "country": "Italia", "start_year": 1985, "end_year": 2009}]}
    monkeypatch.setattr(arena.practice_content, "pick", pick)
    return values


def test_training_resumes_and_rejects_duplicate_guess_without_points(store):
    assert arena.training(1)["session"] is None
    first = arena.training(1, "next", lang="en")
    encoded = json.dumps(first)
    assert "secret-" not in encoded and "correct_answers" not in encoded and "Paolo Maldini" not in encoded
    assert first["session"]["career_path"][0]["country"] == "Italy"
    rev = first["session"]["revision"]
    wrong = arena.training(1, "guess", "Lionel Messi", rev)
    assert wrong["session"]["attempts"] == 1
    with pytest.raises(arena.ArenaError, match="stale"):
        arena.training(1, "guess", "Lionel Messi", rev)
    resumed = arena.training(1)
    assert resumed == wrong
    correct = arena.training(1, "guess", "Paolo Maldini", resumed["session"]["revision"])
    assert correct["session"]["finished"]
    assert correct["feedback"]["answer"] == "Paolo Maldini"
    assert store["users/1"]["training_solved"] == 1
    assert store["users/1"]["points_totali"] == 42


def test_training_exhaustion_reveal_and_next_clear_previous_feedback(store):
    current = arena.training(1, "next")
    for _ in range(5):
        current = arena.training(1, "guess", "Lionel Messi", current["session"]["revision"])
    assert current["session"]["finished"] and current["session"]["spent"] == 5
    previous_key = store["users/1"]["app_training"]["challenges"][0]["key"]
    current = arena.training(1, "next")
    assert current["feedback"] is None
    assert store["users/1"]["app_training"]["challenges"][0]["key"] != previous_key
    assert arena.training(1)["feedback"] is None
    current = arena.training(1, "reveal", revision=current["session"]["revision"])
    assert current["session"]["finished"] and current["session"]["solved"] == 0


@pytest.mark.parametrize("answer", [None, 7, "", "ciao", "https://example.com", "Messi, Ronaldo"])
def test_invalid_practice_answer_does_not_consume_attempt(store, answer):
    current = arena.training(1, "next")
    before = copy.deepcopy(store)
    with pytest.raises(arena.ArenaError, match="invalid_answer"):
        arena.training(1, "guess", answer, current["session"]["revision"])
    assert store == before


def test_duel_two_seats_identical_paths_private_until_both_finish(store):
    own = arena.duel(1, "Anna", "create")
    code = own["code"]
    assert len(code) == 24 and store["users/1"]["app_duel"] == code
    assert "challenges" not in own and "members" not in own
    with pytest.raises(arena.ArenaError, match="join_required"):
        arena.duel(2, "Bea", "get", code)
    other = arena.duel(2, "Bea", "join", code)
    assert other["session"]["career_path"] == own["session"]["career_path"]
    with pytest.raises(arena.ArenaError, match="full"):
        arena.duel(3, "Carlo", "join", code)
    for _ in range(5):
        own = arena.duel(1, "Anna", "guess", code, "Paolo Maldini", own["session"]["revision"])
        assert "Paolo Maldini" not in json.dumps(own)
    assert own["session"]["finished"] and not own["complete"]
    # I percorsi chiusi si vedono subito, i nomi no: e' l'avversario che non ha finito.
    assert [row["n"] for row in own["rounds"]] == [1, 2, 3, 4, 5]
    assert all(row["solved"] and "answer" not in row and "opponent" not in row for row in own["rounds"])
    waiting = arena.duel(2, "Bea", "get", code)
    assert "solved" not in waiting["opponent"]
    assert "history" not in waiting["opponent"]
    for _ in range(15):
        other = arena.duel(2, "Bea", "guess", code, "Lionel Messi", other["session"]["revision"])
    assert other["outcome"] == "loss" and other["complete"]
    assert len(other["rounds"]) == 5 and other["rounds"][0]["answer"] == "Paolo Maldini"
    assert other["rounds"][0]["opponent"] == {"solved": True, "attempts": 1}
    assert other["session"]["spent"] == 15
    assert arena.duel(1, "Anna", "get", code)["outcome"] == "win"
    assert store["users/1"]["points_totali"] == 42


def test_duel_skip_burns_the_path_without_showing_the_name(store):
    own = arena.duel(1, "Anna", "create")
    code = own["code"]
    arena.duel(2, "Bea", "join", code)
    own = arena.duel(1, "Anna", "reveal", code, revision=own["session"]["revision"])
    assert own["session"]["round"] == 1 and own["session"]["spent"] == 3 and own["session"]["solved"] == 0
    assert own["session"]["attempts"] == 0
    assert own["feedback"] == {"status": "wrong", "done": True}
    assert "Paolo Maldini" not in json.dumps(own)
    assert own["rounds"] == [{"n": 1, "solved": False, "attempts": 3}]


def test_duel_opponent_paths_show_up_only_once_they_are_done(store):
    own = arena.duel(1, "Anna", "create")
    code = own["code"]
    other = arena.duel(2, "Bea", "join", code)
    for _ in range(3):
        other = arena.duel(2, "Bea", "guess", code, "Lionel Messi", other["session"]["revision"])
    assert "opponent" not in arena.duel(2, "Bea", "get", code)["rounds"][0]
    for _ in range(5):
        own = arena.duel(1, "Anna", "guess", code, "Paolo Maldini", own["session"]["revision"])
    waiting = arena.duel(2, "Bea", "get", code)
    assert not waiting["complete"] and "answer" not in waiting["rounds"][0]
    assert waiting["rounds"][0]["opponent"] == {"solved": True, "attempts": 1}


def test_duel_ledger_keeps_the_score_against_the_same_opponent(store):
    def play(winner_answer):
        code = arena.duel(1, "Anna", "create")["code"]
        arena.duel(2, "Bea", "join", code)
        for uid, name, answer in ((1, "Anna", "Paolo Maldini"), (2, "Bea", winner_answer)):
            current = arena.duel(uid, name, "get", code)
            for _ in range(15):
                if current["session"]["finished"]:
                    break
                current = arena.duel(uid, name, "guess", code, answer, current["session"]["revision"])
        return code

    first = play("Lionel Messi")
    # Chi chiude per secondo registra subito; l'altro alla prima riapertura della partita.
    assert store["users/2"]["app_duel_record"] == {"1": {"won": 0, "lost": 1, "drawn": 0, "name": "Anna"}}
    anna = arena.duel(1, "Anna", "get", first)
    assert anna["ledger"]["record"] == {"name": "Bea", "won": 1, "lost": 0, "drawn": 0}
    assert [match["code"] for match in anna["ledger"]["matches"]] == [first]
    assert anna["ledger"]["matches"][0]["name"] == "Bea"
    assert anna["ledger"]["matches"][0]["rounds"][0]["answer"] == "Paolo Maldini"
    assert "opponent_id" not in anna["ledger"]["matches"][0]

    # Riaprire la stessa partita conclusa non la conta due volte.
    arena.duel(1, "Anna", "get", first)
    assert store["users/1"]["app_duel_record"]["2"]["won"] == 1

    second = play("Paolo Maldini")
    anna = arena.duel(1, "Anna", "get", second)
    assert anna["ledger"]["record"] == {"name": "Bea", "won": 1, "lost": 0, "drawn": 1}
    assert [match["code"] for match in anna["ledger"]["matches"]] == [second, first]
    assert arena.duel(1, "Anna", "create")["ledger"]["record"] is None


def test_duel_draw_expiry_and_revision_guard(store):
    first = arena.duel(1, "Anna", "create")
    code = first["code"]
    arena.duel(2, "Bea", "join", code)
    for uid in (1, 2):
        for revision in range(5):
            arena.duel(uid, "Name", "guess", code, "Paolo Maldini", revision)
    assert arena.duel(1, "Anna", "get", code)["outcome"] == "draw"
    with pytest.raises(arena.ArenaError, match="stale"):
        arena.duel(1, "Anna", "guess", code, "Paolo Maldini", 0)
    store[f"app_duels/{code}"]["expires_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    with pytest.raises(arena.ArenaError, match="expired"):
        arena.duel(1, "Anna", "get", code)


@pytest.fixture
def event(store, monkeypatch):
    day = "2026-09-09"
    store["events/week"] = {"code": "week", "dates": [day], "type": "path", "name": "Evento",
                            "name_i18n": {"en": "Event", "es": "Evento"},
                            "daily_data": {day: {"correct_answers": ["paolo maldini"], "player_id": "secret",
                                                 "career_path": [], "points": 2}}}
    monkeypatch.setattr(app_events, "today_iso", lambda: day)
    monkeypatch.setattr(app_events.fs, "event_ref", lambda code: MemoryRef(store, f"events/{code}"))
    monkeypatch.setattr(app_events.fs, "participant_ref", lambda code, uid: MemoryRef(store, f"events/{code}/{uid}"))
    monkeypatch.setattr(app_events.fs, "get_active_events", lambda day: [store["events/week"]])
    monkeypatch.setattr(app_events.fs, "get_event_participant", lambda code, uid: store.get(f"events/{code}/{uid}"))
    monkeypatch.setattr(app_events.fs, "get_event_leaderboard", lambda code, limit: [])
    monkeypatch.setattr(app_events, "build_comparison", lambda *args: None)
    return day


def test_events_hide_answers_and_share_bonus_and_attempts(store, event):
    listing = app_events.list_events(1, "en")
    assert listing["events"][0]["name"] == "Event"
    assert "correct_answers" not in json.dumps(listing) and "secret" not in json.dumps(listing)
    result = app_events.guess(1, "Anna", "week", event, "Paolo Maldini", 0)
    assert result["points"] == 3
    with pytest.raises(arena.ArenaError):
        app_events.guess(1, "Anna", "week", event, "Paolo Maldini", 0)
    assert app_events.guess(2, "Bea", "week", event, "Paolo Maldini", 0)["points"] == 2
    assert store["events/week/1"]["points"] == 3
    assert app_events.list_events(1, "es")["events"][0]["progress"]["finished"]


def test_events_exhaustion_and_stale_day_do_not_leak_solution(store, event):
    for revision in range(3):
        result = app_events.guess(1, "Anna", "week", event, "Lionel Messi", revision)
        assert "answer" not in result
    with pytest.raises(arena.ArenaError, match="finished"):
        app_events.guess(1, "Anna", "week", event, "Paolo Maldini", 3)
    with pytest.raises(arena.ArenaError, match="stale"):
        app_events.guess(2, "Bea", "week", "2026-09-08", "Paolo Maldini", 0)


def test_career_events_cap_guesses_without_spending_attempt(store, event):
    store["events/week"]["type"] = "career"
    data = store["events/week"]["daily_data"][event]
    data.update(correct_answers=["Milan", "Roma"], min_correct=2, player_name="Example player")
    with pytest.raises(arena.ArenaError, match="max_answers"):
        app_events.guess(1, "Anna", "week", event, "Milan,Roma,Ajax,Parma,Napoli,Inter", 0)
    assert "events/week/1" not in store
    assert app_events.guess(1, "Anna", "week", event, "Milan, Milan", 0)["status"] == "wrong"
    assert app_events.guess(1, "Anna", "week", event, "Milan, Roma", 1)["status"] == "correct"


# ---------------------------------------------------------------------------
# Su Firestore vero (l'emulatore), perche' un finto in memoria accetta qualunque cosa
# ---------------------------------------------------------------------------


def test_a_wrong_guess_on_a_name_in_the_dataset_is_actually_written(emulator_db):
    """Il confronto dopo un errore viene **salvato** dentro la sessione, e Firestore non
    accetta un array dentro un array.

    Con gli indizi come coppie (chiave, argomenti) la scrittura moriva a transazione
    aperta: il tentativo non veniva scalato, la mini app riceveva un 500 e chi giocava
    vedeva il contatore fermo. Capitava solo scrivendo un nome **presente nel dataset**,
    cioe' l'unico caso in cui un confronto c'e' - e i finti del resto di questo file non lo
    vedevano perche' sostituiscono `build_comparison`. Qui e' quello vero, su un database
    che rifiuta per davvero.
    """
    from services import practice_content
    from services.player_pool import get_practice_players

    # Sei schede vere: cinque fanno il duello, la sesta e' il nome da scrivere - dentro il
    # dataset (quindi con un confronto) ma diverso da ogni soluzione in gioco.
    puzzles = [practice_content.from_player(p) for p in get_practice_players()[:6]]
    other = puzzles[-1]
    fs.save_user(1, "Anna")
    fs.save_user(2, "Bea")

    def pick(exclude_keys=()):
        return copy.deepcopy(puzzles[len(exclude_keys)])

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(arena.practice_content, "pick", pick)
        session = arena.training(1, "next")
        wrong = arena.training(1, "guess", other["answer"], session["session"]["revision"])
        assert wrong["feedback"]["comparison"]["clues"], "senza confronto la prova non prova niente"
        assert wrong["session"]["attempts"] == 1
        assert fs.get_user_data(1)["app_training"]["seat"]["attempts"] == 1

        duel = arena.duel(1, "Anna", "create")
        arena.duel(2, "Bea", "join", duel["code"])
        moved = arena.duel(1, "Anna", "guess", duel["code"], other["answer"],
                           duel["session"]["revision"])
        assert moved["feedback"]["comparison"]["clues"]
        assert moved["session"]["attempts"] == 1


def test_duel_creator_cannot_play_alone_and_can_withdraw_before_anyone_joins(emulator_db):
    fs.save_user(1, "Anna")
    fs.save_user(2, "Bea")
    own = arena.duel(1, "Anna", "create")
    code = own["code"]
    with pytest.raises(arena.ArenaError, match="waiting_opponent"):
        arena.duel(1, "Anna", "guess", code, "Paolo Maldini", own["session"]["revision"])

    # Chi non e' seduto al tavolo non puo' ritirare l'invito di un altro.
    with pytest.raises(arena.ArenaError, match="invalid"):
        arena.duel(2, "Bea", "delete", code)
    assert arena.duel(1, "Anna", "delete", code) == {"deleted": code}
    with pytest.raises(arena.ArenaError, match="expired"):
        arena.duel(1, "Anna", "get", code)

    # Una volta che qualcuno e' entrato, la partita non e' piu' solo sua da cancellare.
    joined = arena.duel(1, "Anna", "create")["code"]
    arena.duel(2, "Bea", "join", joined)
    with pytest.raises(arena.ArenaError, match="full"):
        arena.duel(1, "Anna", "delete", joined)


def test_list_duels_shows_pending_and_active_and_drops_recorded_matches(emulator_db):
    fs.save_user(1, "Anna")
    fs.save_user(2, "Bea")
    fs.save_user(3, "Carlo")

    pending = arena.duel(1, "Anna", "create")["code"]
    active = arena.duel(1, "Anna", "create")["code"]
    arena.duel(2, "Bea", "join", active)
    finished = arena.duel(1, "Anna", "create")["code"]
    arena.duel(3, "Carlo", "join", finished)
    for uid, name in ((1, "Anna"), (3, "Carlo")):
        current = arena.duel(uid, name, "get", finished)
        for _ in range(15):
            if current["session"]["finished"]:
                break
            current = arena.duel(uid, name, "guess", finished, "Paolo Maldini",
                                 current["session"]["revision"])

    listing = arena.list_duels(1)
    rows = {row["code"]: row for row in listing["open"]}
    assert set(rows) == {pending, active, finished}
    assert rows[pending]["opponent"] is None and not rows[pending]["complete"]
    assert rows[active]["opponent"] == "Bea" and not rows[active]["complete"]
    assert rows[finished]["complete"]
    assert listing["ledger"]["matches"] == []

    # Riaprire quella conclusa la archivia sul profilo: da quel momento sta nello storico,
    # non piu' fra quelle aperte, altrimenti comparirebbe due volte.
    arena.duel(1, "Anna", "get", finished)
    listing = arena.list_duels(1)
    assert {row["code"] for row in listing["open"]} == {pending, active}
    assert listing["ledger"]["matches"][0]["code"] == finished
