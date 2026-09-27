"""Offline counterfactual Daily scoring. Reads normalized JSON, never Firestore."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

from services.difficulty import points_for_difficulty
from services.hints import MAX_HINTS, points_after_hints
from services.streak import STREAK_BONUS_THRESHOLDS, next_streak, streak_bonus


def _integer(value, label, minimum=0, maximum=None):
    if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
        raise ValueError(f"{label}: expected integer in [{minimum}, {maximum or 'unbounded'}]")
    return value


def _day(value):
    if not isinstance(value, str):
        raise ValueError("day: expected YYYY-MM-DD")
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError("day: expected YYYY-MM-DD")
    return value


def simulate(document):
    """Compare identical outcomes under daily-tier and one-off milestone bonuses.

    Ranks cover the supplied period only, with competition ties (1, 1, 3).
    Initial streaks affect continuity, but points before the window are not included.
    Every counted outcome must be a Daily result, not an Archive/Event result.
    """
    if not isinstance(document, dict) or not isinstance(document.get("players"), list) or not isinstance(document.get("results"), list):
        raise ValueError("expected players and results arrays")
    players = {}
    for player in document["players"]:
        if not isinstance(player, dict):
            raise ValueError("player must be an object")
        identity = player.get("id")
        if not isinstance(identity, str) or not identity or len(identity) > 80 or not all(c.isalnum() or c in '_-' for c in identity):
            raise ValueError("player id: use an anonymous alphanumeric identifier")
        if identity in players:
            raise ValueError(f"duplicate player: {identity}")
        initial = _integer(player.get("initial_streak"), "initial_streak")
        previous = player.get("last_correct_day")
        if initial:
            previous = _day(previous)
        elif previous is not None:
            raise ValueError("last_correct_day must be null for a zero initial streak")
        players[identity] = {"player": identity, "streak": initial, "last_correct_day": previous,
                             "solved": 0, "base_and_first": 0, "current_bonus": 0, "milestone_bonus": 0}
    if not players:
        raise ValueError("at least one player is required")
    seen = set()
    firsts = set()
    difficulties = {}
    results = []
    for result in document["results"]:
        if not isinstance(result, dict):
            raise ValueError("result must be an object")
        identity = result.get("player")
        if not isinstance(identity, str) or identity not in players:
            raise ValueError("result references an unknown player")
        day = _day(result.get("day"))
        if (identity, day) in seen:
            raise ValueError(f"duplicate Daily result: {identity} {day}")
        seen.add((identity, day))
        prior = players[identity]["last_correct_day"]
        if prior and day <= prior:
            raise ValueError("initial last_correct_day must precede the input window")
        difficulty = result.get("difficulty")
        if difficulty not in ("easy", "medium", "hard", "impossible"):
            raise ValueError("difficulty must be the recorded Daily band")
        if day in difficulties and difficulties[day] != difficulty:
            raise ValueError(f"inconsistent Daily difficulty on {day}")
        difficulties[day] = difficulty
        if type(result.get("solved")) is not bool or type(result.get("first_correct")) is not bool:
            raise ValueError("solved and first_correct must be explicit booleans")
        _integer(result.get("hints_used"), "hints_used", maximum=MAX_HINTS)
        if result["first_correct"]:
            if not result["solved"] or day in firsts:
                raise ValueError("first_correct requires a solve and only one winner per day")
            firsts.add(day)
        results.append(result)
    milestones = dict(STREAK_BONUS_THRESHOLDS)
    for result in sorted(results, key=lambda row: (row["day"], row["player"])):
        player = players[result["player"]]
        if not result["solved"]:
            player["streak"] = 0
            player["last_correct_day"] = None
            continue
        streak = next_streak(player["last_correct_day"], result["day"], player["streak"])
        player["streak"], player["last_correct_day"] = streak, result["day"]
        player["solved"] += 1
        player["base_and_first"] += points_after_hints(points_for_difficulty(result["difficulty"]), result["hints_used"]) + int(result["first_correct"])
        player["current_bonus"] += streak_bonus(streak)
        player["milestone_bonus"] += milestones.get(streak, 0)
    rows = []
    for player in players.values():
        row = {key: value for key, value in player.items() if key not in ("streak", "last_correct_day")}
        row["current_points"] = row["base_and_first"] + row["current_bonus"]
        row["milestone_points"] = row["base_and_first"] + row["milestone_bonus"]
        row["delta"] = row["milestone_points"] - row["current_points"]
        rows.append(row)
    for mode in ("current", "milestone"):
        ranks = {}
        for index, row in enumerate(sorted(rows, key=lambda row: -row[f"{mode}_points"]), 1):
            ranks.setdefault(row[f"{mode}_points"], index)
            row[f"{mode}_rank"] = ranks[row[f"{mode}_points"]]
    return {"scope": "Daily points in supplied period only; identical outcomes under both rules",
            "results": len(results), "days": len(difficulties),
            "players": sorted(rows, key=lambda row: (row["current_rank"], row["player"]))}


def demo():
    """Synthetic cohort: same Daily calendar, no hints or first-solver bonuses."""
    start = date(2026, 9, 1)
    players = [{"id": "new_regular", "initial_streak": 0},
               {"id": "veteran", "initial_streak": 29, "last_correct_day": "2026-08-31"},
               {"id": "weekly_gap", "initial_streak": 0}]
    results = []
    for offset in range(30):
        for player in players:
            results.append({"player": player["id"], "day": (start + timedelta(days=offset)).isoformat(),
                            "difficulty": ("easy", "medium", "hard", "impossible")[offset % 4],
                            "solved": player["id"] != "weekly_gap" or (offset + 1) % 7 != 0,
                            "hints_used": 0, "first_correct": False})
    return {"players": players, "results": results}


def markdown(report, synthetic=False):
    lines = ["# Streak scoring comparison", "", "Synthetic demonstration — not production data." if synthetic else
             "Normalized input replay — not a forecast of player behaviour.", "", report["scope"], "",
             "| Player | Solves | Base + first | Current bonus | Milestone bonus | Current points | Proposed points | Delta | Rank current → proposed |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |"]
    for row in report["players"]:
        lines.append(f"| {row['player']} | {row['solved']} | {row['base_and_first']} | {row['current_bonus']} | {row['milestone_bonus']} | {row['current_points']} | {row['milestone_points']} | {row['delta']:+} | {row['current_rank']} → {row['milestone_rank']} |")
    lines += ["", "Milestones pay once per uninterrupted streak at days 3, 7 and 30. No bonus on day 31+ until a new streak reaches a milestone.",
              "Missing dates break continuity. A missing history record cannot be distinguished from not playing: use a complete input window.",
              "This replay cannot estimate retention, spending or conversion. Live rules and existing points are unchanged."]
    return "\n".join(lines) + "\n"


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path, help="normalized local Daily JSON")
    source.add_argument("--demo", action="store_true", help="run a clearly labelled synthetic scenario")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    args = parser.parse_args()
    try:
        document = demo() if args.demo else json.loads(args.input.read_text(encoding="utf-8-sig"))
        report = simulate(document)
    except (ValueError, TypeError, OSError) as error:
        parser.error(str(error))
    if args.format == "json":
        print(json.dumps({"synthetic": args.demo, **report}, ensure_ascii=False, indent=2))
    else:
        print(markdown(report, args.demo), end="")


if __name__ == "__main__":
    main()
