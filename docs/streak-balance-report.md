# Streak scoring comparison

Synthetic demonstration — not production data.

Daily points in supplied period only; identical outcomes under both rules

| Player | Solves | Base + first | Current bonus | Milestone bonus | Current points | Proposed points | Delta | Rank current → proposed |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| veteran | 30 | 73 | 90 | 3 | 163 | 76 | -87 | 1 → 2 |
| new_regular | 30 | 73 | 53 | 6 | 126 | 79 | -47 | 2 → 1 |
| weekly_gap | 26 | 63 | 16 | 4 | 79 | 67 | -12 | 3 → 3 |

Milestones pay once per uninterrupted streak at days 3, 7 and 30. No bonus on day 31+ until a new streak reaches a milestone.
Missing dates break continuity. A missing history record cannot be distinguished from not playing: use a complete input window.
This replay cannot estimate retention, spending or conversion. Live rules and existing points are unchanged.
