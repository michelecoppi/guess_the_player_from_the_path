"""Regole della partita di gruppo provate senza Telegram (#147): `domains/groups/service.py`
decide, l'handler traduce. Qui non c'e' nessun Update, nessun messaggio e nessuna lingua."""
from types import SimpleNamespace

import pytest

from domains.groups import service as groups

CHAT_ID = -100777
CHALLENGE = {
    "key": "pool:pirlo",
    "player_id": "pirlo",
    "correct_answers": ["pirlo", "andrea pirlo"],
    "career_path": [{"team": "Brescia"}, {"team": "Milan"}],
    "difficulty": "medium",
}


@pytest.fixture
def repo(monkeypatch):
    state = SimpleNamespace(
        round={
            "number": 5, "key": "pool:pirlo", "player_id": "pirlo", "difficulty": "hard",
            "correct_answers": CHALLENGE["correct_answers"], "solved_by": None, "solved_name": None,
            "recent_keys": ["pool:a", "pool:b"],
        },
        attempt={"ok": True, "attempts_used": 1, "attempts_left": 2},
        claimable=True,
        picked_with=None,
        challenge=CHALLENGE,
        attempts=[], points=[], started=[],
        leaderboard=[],
    )

    def pick(exclude_keys=()):
        state.picked_with = list(exclude_keys)
        return state.challenge

    def claim(chat_id, number, user_id, name):
        won, state.claimable = state.claimable, False
        return won

    monkeypatch.setattr(groups.practice_content, "pick", pick)
    monkeypatch.setattr(groups.repository, "get_group_round", lambda chat_id: state.round)
    monkeypatch.setattr(
        groups.repository, "start_group_round",
        lambda chat_id, challenge: state.started.append(challenge["key"]) or {"number": 6},
    )
    monkeypatch.setattr(
        groups.repository, "begin_group_attempt",
        lambda chat_id, user_id, number, name, mx: state.attempts.append((user_id, number, mx)) or state.attempt,
    )
    monkeypatch.setattr(groups.repository, "claim_group_round", claim)
    monkeypatch.setattr(
        groups.repository, "add_group_points",
        lambda chat_id, user_id, name, points: state.points.append((user_id, points)),
    )
    monkeypatch.setattr(groups.repository, "get_group_leaderboard", lambda chat_id, limit: state.leaderboard[:limit])
    return state


def test_a_new_round_avoids_the_recent_ones_and_carries_what_the_image_needs(repo):
    opened = groups.open_round(CHAT_ID)

    assert repo.picked_with == ["pool:a", "pool:b"]
    assert repo.started == ["pool:pirlo"]
    assert opened == groups.OpenedRound(
        number=6, difficulty="medium", points=2, career_path=CHALLENGE["career_path"],
    )


@pytest.mark.parametrize("challenge", [None, {**CHALLENGE, "career_path": []}])
def test_no_material_opens_no_round(repo, challenge):
    repo.challenge = challenge

    assert groups.open_round(CHAT_ID) is None
    assert repo.started == []


def test_without_a_round_nothing_is_consumed(repo):
    repo.round = None

    assert groups.submit_answer(CHAT_ID, 1, "Anna", "Pirlo").status == "no_round"
    assert repo.attempts == []


def test_an_empty_answer_costs_no_attempt(repo):
    assert groups.submit_answer(CHAT_ID, 1, "Anna", "").status == "usage"
    assert repo.attempts == []


def test_a_solved_round_names_the_winner_without_consuming_attempts(repo):
    repo.round.update(solved_by=9, solved_name="Bruno")

    outcome = groups.submit_answer(CHAT_ID, 1, "Anna", "Pirlo")

    assert (outcome.status, outcome.winner) == ("already_solved", "Bruno")
    assert repo.attempts == []


def test_attempts_are_counted_per_round_and_capped(repo):
    repo.attempt = {"ok": False, "reason": "no_attempts"}

    assert groups.submit_answer(CHAT_ID, 1, "Anna", "Pirlo").status == "no_attempts"
    assert repo.attempts == [(1, 5, groups.MAX_GROUP_ATTEMPTS)]
    assert repo.points == []


def test_a_wrong_answer_reports_what_is_left_and_the_comparison(repo, monkeypatch):
    monkeypatch.setattr(groups, "build_comparison", lambda answer, player_id: {"name": answer, "target": player_id})

    outcome = groups.submit_answer(CHAT_ID, 1, "Anna", "Del Piero")

    assert outcome.status == "wrong"
    assert outcome.attempts_left == 2
    assert outcome.comparison == {"name": "Del Piero", "target": "pirlo"}
    assert repo.points == []


def test_the_first_correct_answer_takes_the_round_points(repo):
    outcome = groups.submit_answer(CHAT_ID, 1, "Anna", "andrea pirlo")

    # "hard" vale 3 punti, come sulla sfida del giorno.
    assert (outcome.status, outcome.points, outcome.number) == ("correct", 3, 5)
    assert repo.points == [(1, 3)]


def test_losing_the_claim_awards_nothing(repo):
    """Due risposte giuste nello stesso istante: il round va a chi vince la transazione."""
    groups.submit_answer(CHAT_ID, 1, "Anna", "Pirlo")
    outcome = groups.submit_answer(CHAT_ID, 2, "Bruno", "Pirlo")

    assert (outcome.status, outcome.winner) == ("already_solved", None)
    assert repo.points == [(1, 3)]


def test_standings_are_numbered_with_defaults(repo):
    repo.leaderboard = [{"name": "Anna", "points": 9, "rounds_won": 3}, {"name": "Bruno"}]

    assert groups.standings(CHAT_ID) == [
        {"position": 1, "name": "Anna", "points": 9, "rounds_won": 3},
        {"position": 2, "name": "Bruno", "points": 0, "rounds_won": 0},
    ]


def test_standings_respect_the_limit(repo):
    repo.leaderboard = [{"name": str(i), "points": 20 - i} for i in range(15)]

    assert len(groups.standings(CHAT_ID)) == groups.STANDINGS_SIZE
    assert len(groups.standings(CHAT_ID, limit=3)) == 3
