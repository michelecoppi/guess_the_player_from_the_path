# Agent protocol

How a human or AI agent should reason about and carry out repository work, from
picking an issue to closing it. [`AGENTS.md`](../AGENTS.md) is the short entrypoint;
this document owns the process discipline around it. It deliberately does not repeat:

- Project fields, status flow, WIP limit, issue creation and dependency modeling →
  [evolutive-tracking.md](evolutive-tracking.md);
- branch names, commit style, `Closes`/`Refs`, review and merge mechanics →
  [github-workflow.md](github-workflow.md);
- what the system is and where things live → [docs/README.md](README.md).

[GitHub Project #2](https://github.com/users/michelecoppi/projects/2) is the single
operational source of truth for status, priority, area, work type, horizon, size,
risk, release, dependencies and the active backlog. Documentation never replaces it.

## Never trust stale state

This repository routinely has several agents working in parallel. Anything you read
earlier — a completion report, a PR description, a summary in chat, a local branch,
this documentation — may already be outdated. **Before modifying or reviewing work:**

1. `git fetch origin` and compare with the latest `origin/main`; do not assume your
   local `main` or a remembered SHA is current. If the task gives an expected base SHA,
   verify it and stop to report if it differs.
2. Inspect the **exact current head** of any PR involved
   (`gh pr view <n> --json headRefOid,baseRefName,mergeStateStatus,state`).
3. Read the actual diff (`gh pr diff <n>` or `git diff origin/main...<head>`), not the
   description of it.
4. Check CI **for that exact head SHA** (`gh pr checks <n>`, or
   `gh run list --commit <sha>`). A green run on an earlier commit proves nothing about
   the current one.
5. Re-read the issue and its Project fields; another agent may have moved, split,
   closed or blocked it.
6. Do not assume a concurrent PR is still open or still unmerged — check. If `main`
   moved under your branch, rebase or merge `main` and re-run the relevant checks before
   asking for final approval.

## Choosing work without inventing it

- If a human assigned an issue, that issue is the task. Stay inside its scope.
- If asked what to do next, derive the answer from the Project, not from memory or
  documentation:
  ```bash
  gh project item-list 2 --owner michelecoppi --format json --limit 200
  ```
  Consider items in `Ready` first; respect the WIP limit (count `In Progress`); prefer
  higher Priority, then Horizon; exclude items with open hard blockers:
  ```bash
  gh api graphql -f query='query{repository(owner:"michelecoppi",name:"guess_the_player_from_the_path"){issue(number:<n>){state parent{number} subIssues(first:20){nodes{number state}} blockedBy(first:20){nodes{number state}}}}}'
  ```
- `Horizon = Now` alone does not authorize starting. If nothing is `Ready`, report the
  best candidates and why, and let a human promote one. Do not create issues, move items
  to `Ready` or start `Backlog` work on your own initiative.
- An issue that is clearly too large (Size 8, several independent deliverables) should
  be split into sub-issues before implementation; propose the split instead of
  implementing a giant PR.
- Real problems discovered along the way are reported (and, if asked, filed as new
  issues with all Project fields), not silently fixed inside an unrelated PR.

## Work sequence

| # | Step | What it means here |
| --- | --- | --- |
| 1 | Read `AGENTS.md` | Entry rules and links |
| 2 | Read Project #2 fields | Status, Priority, Area, Work Type, Horizon, Size, Risk, Release for the issue |
| 3 | Read the assigned issue | Goal, scope, completion criteria, comments, parent/sub-issues |
| 4 | Check WIP and dependencies | At most two evolutives `In Progress` unless the issue records a reason; open hard blockers mean `Blocked`, not “start anyway” |
| 5 | Inspect architecture and docs | Start at [docs/README.md](README.md); read the primary doc for the area and the relevant code. Treat docs as a map, the code as the truth |
| 6 | Inspect current `main` | Apply [Never trust stale state](#never-trust-stale-state) |
| 7 | Create a dedicated worktree and branch | One issue, one branch, one worktree (see below); move the issue to `In Progress` |
| 8 | Make incremental, scoped changes | Preserve behavior outside the scope; no drive-by refactors, reformatting or dependency bumps. Put code in the right domain and respect the dependency rules ([architecture.md § 3](architecture.md#3-composition-root-and-domain-boundaries)); a new module goes into `tools/architecture.py`; moving a domain into `domains/` follows [the migration procedure](architecture.md#moving-a-domain-into-its-package) |
| 9 | Run focused tests early | The tests closest to the change, before building on it |
| 10 | Run required regressions | `python -m tools.dev check` (environment, syntax, ruff, mypy, frontend typecheck/build/tests, dataset integrity and regression, pytest); `python -m tools.dev security-check` when dependencies or security-relevant code change; `git diff --check` always. CI additionally runs `npm audit`, the security suite, the Firestore emulator tests and the coverage threshold ([ci_cd_pipeline.md](ci_cd_pipeline.md)) |
| 11 | Open a focused PR | One issue per PR; fill the PR template with what was actually run |
| 12 | Use `Closes` vs `Refs` correctly | `Closes #n` only if every completion criterion of the issue is met; otherwise `Refs #n` and list what remains |
| 13 | Move the item to `Review` | Only when implementation and tests are ready |
| 14 | Respond to review on the same PR | Push follow-up commits to the same branch; do not open a replacement PR unless asked |
| 15 | Verify exact-head CI | After the last push, confirm CI passed for that SHA |
| 16 | Merge only after approval | Agents do not merge unless a human explicitly asks for it |
| 17 | Update issue and Project state | `Closes` moves the item to `Done` on merge; after a `Refs` PR or a split, update status and comment on the issue with what is done and what remains |

### Status situations

- **Complete PR** — `Closes #n`; the issue's completion criteria are all demonstrably
  satisfied.
- **Partial PR** — `Refs #n`; the PR body says what is left and the issue stays open.
- **Blocked** — set Project status `Blocked` and comment the concrete impediment (the
  blocking issue, decision or access needed). Do not work around a hard blocker.
- **Needs splitting** — propose sub-issues (with fields and hard/soft dependencies as
  in [evolutive-tracking.md](evolutive-tracking.md)) before implementing.
- **Needs a decision** — stop and ask; record the decision on the issue.

## Parallel agents

- Always work in a dedicated git worktree (for example `.worktrees/issue-<n>`, which is
  gitignored) on a dedicated branch cut from the latest `origin/main`.
- Never modify, reset, clean or check out branches in another agent's worktree, and
  never use shared stashes as a hand-off mechanism.
- Never casually reset, force-push or commit directly to `main`.
- Never merge unrelated work into your branch; never resolve a conflict by deleting or
  reverting the other feature. Understand both sides, keep both behaviors, and re-run
  both areas' tests.
- Respect the WIP limit; exceeding it needs an explicit reason recorded on the issue.
- When two issues touch the same architectural surface (same service module, API
  contract, dataset, CSS foundation, workflow file), **sequence them** instead of
  pretending they are independent: finish, review and merge one, then rebase the other.
  Record the ordering on the issues if it is not already a Project dependency.

## Documentation update policy

Update documentation in the same PR when the change alters:

- public or internal architecture, component responsibilities or module boundaries;
- the development or GitHub workflow;
- an operational procedure (jobs, deploy, backup, secrets, incident handling);
- an API contract used across domains (Mini App API, service interfaces other areas call);
- the player-data pipeline or dataset invariants;
- deployment topology or required configuration;
- security assumptions or trust boundaries;
- important user-visible or admin-visible behavior.

Update the **primary** document for the topic (see [docs/README.md](README.md)) and
link to it from elsewhere instead of copying. Small implementation fixes normally need
tests and issue/PR traceability, not documentation churn. Avoid writing values that go
stale on their own (test counts, dataset sizes, per-issue statuses); link to the
command or board that produces them. Never document planned work as implemented: label
it **Planned** and link its issue.

## Decision traceability

Architectural decisions are traced as **issue → PR → authoritative doc**:

1. the issue records the problem, options and the decision (or links the discussion);
2. the PR implements it and references the issue (`Closes`/`Refs`);
3. if the decision has lasting architectural impact, the primary document gains or
   updates a short section that states the decision and links the issue/PR.

There is no separate ADR framework. Point-in-time decision records (for example
[project-dependency-review.md](project-dependency-review.md)) are allowed but must say
they are historical and must not become a second live source of state.

## Finishing checklist

- [ ] Base verified against current `origin/main`; branch rebased if `main` moved
- [ ] Diff limited to the issue scope; no unrelated files
- [ ] Focused tests and required regressions run; results reported honestly
- [ ] Docs updated per the policy above, or explicitly not needed
- [ ] PR uses `Closes` or `Refs` correctly; remaining work listed for `Refs`
- [ ] Project status `Review`; CI green on the exact head SHA
- [ ] No merge without explicit human approval
