# GitHub workflow: issue → branch → PR → review → merge

This is the repository-side mechanics companion to
[`evolutive-tracking.md`](evolutive-tracking.md), which owns the roadmap index,
the Project field taxonomy and the protocol for creating/classifying issues.
This file owns the git/GitHub mechanics: how an issue becomes a branch, a PR,
and eventually a merge. It does not duplicate Project-field definitions. The
reasoning discipline around this workflow (stale-state checks, parallel agents,
documentation policy) is in [`agent-protocol.md`](agent-protocol.md).

## 1. Pick up an issue

- Read the issue and check its Project fields (Status, Horizon, Priority,
  dependencies) on [Project #2](https://github.com/users/michelecoppi/projects/2).
  `Horizon = Now` does not by itself authorize starting work — check WIP first.
- Respect the WIP limit: at most two evolutive issues in `In Progress` at once,
  unless the issue records an explicit reason.
- Move the issue's Status to `In Progress` when you start.

## 2. Branch

Branch names follow `<type>/<issue-number>-<short-slug>`, cut from `main`:

| Type | Use for |
| --- | --- |
| `feat/` | New product or technical capability |
| `fix/` | Bug fix |
| `refactor/` | Internal restructuring, no behavior change |
| `chore/` | Process, tooling, docs, dependency/config maintenance |
| `data/` | Dataset, ingestion or provenance work |

Example: `feat/45-migrate-shop`, `chore/11-github-workflow`.

Never commit directly to `main`.

## 3. Commit messages

[Conventional Commits](https://www.conventionalcommits.org/), scoped to the
affected area: `feat(webapp): migrate Shop feature to V2 (Closes #45)`. Keep the
issue reference in the final commit or the PR title/body — see §4.

## 4. Open the PR

- A PR that fully satisfies the issue's completion criteria must include
  `Closes #<issue>` in its title or body.
- A partial PR must use `Refs #<issue>` instead — this keeps the issue open
  and avoids GitHub auto-closing it on merge.
- Fill in the PR template (summary, issue reference, test plan, checklist).
- Move the issue's Project Status to `Review` once the PR is open and the
  implementation/tests are ready for review — not before.

## 5. Review

- Address review feedback with new commits; avoid force-pushing over a
  reviewer's in-progress comments.
- Cross-cutting labels (`security`, `breaking-change`, `needs-decision`,
  `data-risk`) belong on the issue, not re-derived as PR-only labels — they
  signal review focus, not roadmap classification (that's the Project's job).

## 6. Merge

- Squash, merge-commit and rebase merges are all permitted; pick whichever
  keeps history clearest for the change (prefer squash for many small fixup
  commits).
- Merging with `Closes #<issue>` auto-closes the issue and GitHub Projects'
  built-in workflow moves it to `Done`. If a PR used `Refs #<issue>` instead,
  update the issue's Status manually once the remaining work is scoped.
- Branches are not auto-deleted on merge; delete the branch once merged unless
  it's still needed for follow-up work.

## Templates

Issue forms live in [`.github/ISSUE_TEMPLATE/`](../.github/ISSUE_TEMPLATE/)
(feature, bug, refactor, data task) and the PR template in
[`.github/PULL_REQUEST_TEMPLATE.md`](../.github/PULL_REQUEST_TEMPLATE.md).
Every issue template points back to the Project and to
`evolutive-tracking.md` for field classification — it does not restate the
taxonomy.
