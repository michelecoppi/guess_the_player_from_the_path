# Agent workflow

Short, authoritative entrypoint for human and AI agents. Details live in the linked
documents; do not duplicate them here.

- **Where things are:** [`docs/README.md`](docs/README.md) (documentation index) →
  [`docs/architecture.md`](docs/architecture.md).
- **How to work:** [`docs/agent-protocol.md`](docs/agent-protocol.md).
- **Git/GitHub mechanics:** [`docs/github-workflow.md`](docs/github-workflow.md);
  Project fields and issue creation: [`docs/evolutive-tracking.md`](docs/evolutive-tracking.md).

## Rules

1. **GitHub Project #2** (**⚽ Guess the Player — Product & Development**) is the only
   operational source of truth for status, priority, dependencies and backlog. Read the
   assigned issue and its Project fields before starting. Do not invent tasks.
2. **Never trust stale state.** Fetch `origin/main`, inspect the exact PR head, its diff
   and CI for that SHA before modifying or reviewing anything. Earlier reports may be
   outdated.
3. Check Status, dependencies and the WIP limit (at most two evolutives `In Progress`
   unless the issue records a reason). `Backlog → Ready → In Progress → Review → Done`,
   `Blocked` is lateral; `Horizon = Now` does not by itself authorize starting.
4. Inspect the code and the primary doc for the area before editing. Current state and
   planned work (open issues) must never be mixed.
5. Work in a **dedicated worktree and branch** from the latest `origin/main`. Never touch
   another agent's worktree, commit to `main` or resolve conflicts by dropping someone
   else's work.
6. Make small, scoped changes; add or update tests; run focused tests early and
   `python -m tools.dev check` (plus the checks your area needs) before the PR. Size 8
   work is split before implementation.
7. One focused PR per issue: `Closes #<issue>` only when every completion criterion is
   met, otherwise `Refs #<issue>` with the remaining work. Move the item to `Review`,
   answer review on the same PR, verify CI on the exact head. **Do not merge without
   explicit human approval.**
8. Update the primary documentation when architecture, workflow, operations, cross-domain
   contracts, the data pipeline, deployment, security assumptions or important behavior
   change (policy in the agent protocol).
