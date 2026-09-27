from copy import deepcopy

import pytest

from tools.streak_simulation import demo, simulate


def one_player(days=30, initial=0, difficulty="easy"):
    data = demo()
    data["players"] = [{"id": "new_regular", "initial_streak": initial}]
    if initial:
        data["players"][0]["last_correct_day"] = "2026-08-31"
    data["results"] = [dict(r, difficulty=difficulty) for r in data["results"] if r["player"] == "new_regular"][:days]
    return data


def test_thirty_easy_days_expose_daily_bonus_weight_without_mutating_input():
    data = one_player()
    before = deepcopy(data)
    row = simulate(data)["players"][0]
    assert data == before
    assert (row["current_points"], row["milestone_points"], row["current_bonus"], row["milestone_bonus"]) == (83, 36, 53, 6)


def test_prior_streak_crosses_thirty_once_and_hints_and_first_bonus_are_preserved():
    data = one_player(days=2, initial=29, difficulty="hard")
    data["results"][0].update(hints_used=2, first_correct=True)
    row = simulate(data)["players"][0]
    assert row["base_and_first"] == 5
    assert row["current_bonus"] == 6
    assert row["milestone_bonus"] == 3


@pytest.mark.parametrize("gap", ["loss", "missing"])
def test_interrupted_streak_can_earn_a_milestone_again(gap):
    data = one_player(days=7)
    if gap == "loss":
        data["results"][3]["solved"] = False
    else:
        del data["results"][3]
    row = simulate(data)["players"][0]
    assert row["solved"] == 6
    assert row["current_bonus"] == row["milestone_bonus"] == 2


def test_order_independence_and_competition_ties():
    data = one_player(days=2)
    data["players"].append({"id": "other", "initial_streak": 0})
    data["results"] += [dict(r, player="other") for r in list(data["results"])]
    expected = simulate(data)
    data["results"].reverse()
    assert simulate(data) == expected
    assert {r["current_rank"] for r in expected["players"]} == {1}


@pytest.mark.parametrize("field,value", [("difficulty", "unknown"), ("hints_used", -1), ("hints_used", True),
                                         ("hints_used", 3), ("solved", "false"), ("first_correct", None),
                                         ("day", "20260901"), ("player", "missing")])
def test_rejects_ambiguous_history(field, value):
    data = one_player(days=1)
    data["results"][0][field] = value
    with pytest.raises(ValueError):
        simulate(data)


def test_duplicates_and_impossible_first_winners_are_rejected():
    data = one_player(days=1)
    data["results"].append(dict(data["results"][0]))
    with pytest.raises(ValueError, match="duplicate"):
        simulate(data)
    data["results"].pop()
    data["results"][0].update(solved=False, first_correct=True)
    with pytest.raises(ValueError, match="first_correct"):
        simulate(data)


def test_initial_state_cannot_overlap_results():
    data = one_player(days=1, initial=7)
    data["players"][0]["last_correct_day"] = "2026-09-01"
    with pytest.raises(ValueError, match="precede"):
        simulate(data)
