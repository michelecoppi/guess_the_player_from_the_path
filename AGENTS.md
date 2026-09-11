# Agent workflow

For planned product or technical evolutives, GitHub Project #2 (**⚽ Guess the Player — Product & Development**) is the operational source of truth. Read `docs/evolutive-tracking.md`, then the assigned issue and its Project fields before starting work.

- Check Status, Horizon, Priority, dependencies and the WIP limit before starting; `Horizon = Now` does not itself authorize starting work.
- Use `Backlog → Ready → In Progress → Review → Done`; `Blocked` is lateral. Keep at most two evolutives in `In Progress` unless the issue records an explicit reason.
- Inspect the code first; work incrementally and add or update relevant tests. Size 8 work is normally split before implementation.
- A PR that fully completes an issue must contain `Closes #<issue>`; a partial PR must use `Refs #<issue>`. Update the Project, issue and lightweight documentation when needed.
- When creating a new issue, assign every Project field before leaving it in `Backlog` (Area, Work Type, Priority, Horizon, Size, Risk) and model dependencies as real GitHub relations only when they're hard blockers — see `docs/evolutive-tracking.md` for the full checklist and the reasoning behind it.
