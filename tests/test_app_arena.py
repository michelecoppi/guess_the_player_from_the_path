"""Game state, privacy projections and retries without a production database."""
import copy
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from services import app_events, arena


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
    assert "recap" not in own
    waiting = arena.duel(2, "Bea", "get", code)
    assert "solved" not in waiting["opponent"]
    assert "history" not in waiting["opponent"]
    for _ in range(15):
        other = arena.duel(2, "Bea", "guess", code, "Lionel Messi", other["session"]["revision"])
    assert other["outcome"] == "loss" and other["complete"]
    assert len(other["recap"]) == 5 and other["recap"][0]["answer"] == "Paolo Maldini"
    assert other["session"]["spent"] == 15
    assert arena.duel(1, "Anna", "get", code)["outcome"] == "win"
    assert store["users/1"]["points_totali"] == 42


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
