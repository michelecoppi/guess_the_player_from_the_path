"""Modalita' Storia: livelli che si perdono (checkpoint sul livello, non sul capitolo) e
stelline per la run senza errori."""
import copy
from types import SimpleNamespace

import pytest

from services import story

PLAYERS = {
    "p1": {"id": "p1", "full_name": "Player One", "aliases": ["p1"],
           "career": [{"team": "Milan", "country": "Italia", "start_year": 1990, "end_year": 1995}]},
    "p2": {"id": "p2", "full_name": "Player Two", "aliases": ["p2"],
           "career": [{"team": "Roma", "country": "Italia", "start_year": 1991, "end_year": 1996}]},
    "p3": {"id": "p3", "full_name": "Player Three", "aliases": ["p3"],
           "career": [{"team": "Inter", "country": "Italia", "start_year": 1992, "end_year": 1997}]},
    "p4": {"id": "p4", "full_name": "Player Four", "aliases": ["p4"],
           "career": [{"team": "Lazio", "country": "Italia", "start_year": 1993, "end_year": 1998}]},
}

CHAPTER = {
    "id": "anni_90", "title": "Anni '90",
    "reward_item": "traguardo_anni_90", "perfect_reward_item": "traguardo_anni_90_perfetto",
    "levels": [
        {"id": 1, "theme": "Livello 1", "player_ids": ["p1", "p2"]},
        {"id": 2, "theme": "Livello 2", "player_ids": ["p3", "p4"]},
    ],
}


class MemoryRef:
    def __init__(self, store, key):
        self.store, self.key = store, key

    def get(self, transaction=None):
        data = copy.deepcopy(self.store.get(self.key))
        return SimpleNamespace(exists=data is not None, to_dict=lambda: data)


class MemoryTransaction:
    def set(self, ref, data, merge=False):
        ref.store[ref.key] = copy.deepcopy(data)


@pytest.fixture
def store(monkeypatch):
    values = {"users/1": {"first_name": "Anna"}}

    def ref(key):
        return MemoryRef(values, key)

    db = SimpleNamespace(
        collection=lambda collection: SimpleNamespace(document=lambda key: ref(f"{collection}/{key}")),
        transaction=MemoryTransaction,
    )
    monkeypatch.setattr(story.fs, "db", db)
    monkeypatch.setattr(story.fs, "user_ref", lambda uid: ref(f"users/{uid}"))
    monkeypatch.setattr(story.fs, "get_user_data", lambda uid: copy.deepcopy(values.get(f"users/{uid}")))
    monkeypatch.setattr(story.fs, "_newly_earned", lambda user: [])
    monkeypatch.setattr(story.firestore, "transactional", lambda fn: fn)
    monkeypatch.setattr(story, "chapters", lambda: [CHAPTER])
    monkeypatch.setattr(story, "get_chapter", lambda chapter_id: CHAPTER if chapter_id == "anni_90" else None)
    monkeypatch.setattr(story, "get_player_by_id", lambda pid: PLAYERS.get(pid))
    monkeypatch.setattr(story, "build_comparison", lambda answer, pid: {"name": answer, "clues": []})
    return values


def _guess(answer, revision, uid=1):
    return story.chapter(uid, "anni_90", "guess", answer, revision)


def test_wrong_answers_exhaust_and_fail_the_level_not_the_chapter(store):
    started = story.chapter(1, "anni_90")
    rev = started["chapter"]["revision"]
    assert started["chapter"]["level_number"] == 1

    for _ in range(3):
        result = _guess("nobody", rev)
        rev = result["chapter"]["revision"]

    assert result["feedback"]["level_failed"] is True
    assert result["chapter"]["level_number"] == 1
    assert result["chapter"]["step"] == 0
    assert result["chapter"]["stars"] == [False, False]


def test_perfect_level_earns_a_star_and_advances(store):
    started = story.chapter(1, "anni_90")
    rev = started["chapter"]["revision"]

    step1 = _guess("Player One", rev)
    assert step1["feedback"]["status"] == "correct"
    rev = step1["chapter"]["revision"]
    step2 = _guess("Player Two", rev)
    assert step2["feedback"]["level_cleared"] is True
    assert step2["feedback"]["starred"] is True
    assert step2["chapter"]["stars"] == [True, False]
    assert step2["chapter"]["level_number"] == 2


def test_a_wrong_guess_before_solving_loses_the_star_but_not_the_level(store):
    started = story.chapter(1, "anni_90")
    rev = started["chapter"]["revision"]

    wrong = _guess("nobody", rev)
    rev = wrong["chapter"]["revision"]
    right = _guess("Player One", rev)
    rev = right["chapter"]["revision"]
    right2 = _guess("Player Two", rev)

    assert right2["feedback"]["level_cleared"] is True
    assert right2["feedback"]["starred"] is False
    assert right2["chapter"]["stars"] == [False, False]


def test_clearing_every_level_finishes_the_chapter_and_grants_the_cosmetic(store):
    rev = story.chapter(1, "anni_90")["chapter"]["revision"]
    for answer in ("Player One", "Player Two", "Player Three", "Player Four"):
        result = _guess(answer, rev)
        rev = result["chapter"]["revision"]

    assert result["feedback"]["chapter_cleared"] is True
    assert result["chapter"]["finished"] is True
    assert result["chapter"]["stars"] == [True, True]
    assert store["users/1"]["story_chapters_cleared"] == 1
    assert store["users/1"]["story_perfect_chapters"] == 1

    with pytest.raises(story.StoryError, match="finished"):
        _guess("Player One", rev)


def test_stale_revision_is_rejected(store):
    started = story.chapter(1, "anni_90")
    rev = started["chapter"]["revision"]
    _guess("Player One", rev)
    with pytest.raises(story.StoryError, match="stale"):
        _guess("Player One", rev)


def test_levels_array_reports_locked_current_and_cleared_state(store):
    started = story.chapter(1, "anni_90")
    levels = started["chapter"]["levels"]
    assert [l["state"] for l in levels] == ["current", "locked"]
    assert levels[0]["theme"] == "Livello 1"

    rev = started["chapter"]["revision"]
    step1 = _guess("Player One", rev)
    step2 = _guess("Player Two", step1["chapter"]["revision"])
    assert [l["state"] for l in step2["chapter"]["levels"]] == ["cleared", "current"]
    assert step2["chapter"]["levels"][0]["starred"] is True


def test_list_chapters_reports_progress_before_and_after_playing(store):
    empty = story.list_chapters(1)
    assert empty["chapters"] == [{
        "chapter_id": "anni_90", "title": "Anni '90", "total_levels": 2,
        "levels_cleared": 0, "stars_earned": 0, "finished": False, "locked": False,
    }]

    rev = story.chapter(1, "anni_90")["chapter"]["revision"]
    for answer in ("Player One", "Player Two", "Player Three", "Player Four"):
        result = _guess(answer, rev)
        rev = result["chapter"]["revision"]

    after = story.list_chapters(1)["chapters"][0]
    assert after["levels_cleared"] == 2
    assert after["stars_earned"] == 2
    assert after["finished"] is True
