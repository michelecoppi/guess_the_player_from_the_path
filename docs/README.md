# Documentation index

“I need to understand X — where do I go?” Each topic has **one primary document**;
other documents link to it instead of copying it. If two documents disagree, the
primary one wins and the other should be fixed. The code on `main` wins over any
document, and [GitHub Project #2](https://github.com/users/michelecoppi/projects/2) wins
for anything about issue status, priority, dependencies or backlog.

Some documents are written in Italian (the project's original language), newer ones in
English. Both are equally authoritative when listed as primary below.

## Start here

| If you are… | Read |
| --- | --- |
| An agent or contributor starting any task | [`AGENTS.md`](../AGENTS.md) → [agent-protocol.md](agent-protocol.md) |
| New to the system | [architecture.md](architecture.md) |
| Setting up a machine | [local-development.md](local-development.md) |
| Looking for the next task | Project #2, following [agent-protocol.md § Choosing work](agent-protocol.md#choosing-work-without-inventing-it) |

## Authoritative / current documents

| Topic | Primary document | Covers |
| --- | --- | --- |
| Architecture | [architecture.md](architecture.md) | Components, responsibility boundaries, composition root, who reads/writes what, deployment topology summary, roadmap items that change the picture |
| Agent process | [agent-protocol.md](agent-protocol.md) | Never trust stale state, choosing work, work sequence, parallel agents, documentation update policy, decision traceability |
| GitHub / product workflow | [evolutive-tracking.md](evolutive-tracking.md) | Project #2 fields, status flow, WIP limit, creating/splitting issues, dependency modeling, roadmap index |
| Git mechanics | [github-workflow.md](github-workflow.md) | Branch naming, commits, `Closes`/`Refs`, review, merge, templates |
| Local development | [local-development.md](local-development.md) | Prerequisites, `.env`, environment validator, `python -m tools.dev` / `make` / `dev.ps1` commands, emulator, API, Admin, Mini App dev servers, troubleshooting |
| Player data pipeline | [player-data-pipeline.md](player-data-pipeline.md) | Production dataset invariant, legacy import, Candidate pipeline FSM, approval boundary, SOURCE_WRONG/retry, #13 audit |
| Provenance | [provenance.md](provenance.md) | Field-level lineage model and public/internal boundary |
| Difficulty and popularity | [difficolta.md](difficolta.md) | Popularity scale, difficulty formula, checklist before adding players |
| Daily and game modes | [game-modes.md](game-modes.md) | Daily lifecycle, Archive, Training, Arena duels, group rounds, Events, leaderboards/leagues, referral |
| Player-facing rules and commands | [README](../README.md) | How to play, commands, shop, dataset schema, admin commands |
| Mini App | [miniapp.md](miniapp.md) | Legacy `/app` vs V2 `/app/v2`, API contract and auth, V2 structure, rollout gate (#81) |
| Mini App V2 appearance | [miniapp-appearance.md](miniapp-appearance.md) | Structural dark-only contract, token ownership, eight cosmetic slots |
| Admin | [admin.md](admin.md) | Telegram admin commands vs Streamlit Admin, boundaries, capabilities, open #12 sub-issues |
| Firestore | [firestore.md](firestore.md) | Collections, what belongs in Firestore, credentials, concurrency, emulator strategy |
| Deployment | [deploy.md](deploy.md) | Cloud Run, Workload Identity Federation, service env vars, Cloud Scheduler, backup workflow setup, manual deploy/rollback |
| Webhook, queues and retries | [runtime-hardening.md](runtime-hardening.md) | Required secrets, Cloud Tasks queues, receipts/locks, recovery rules, secret rotation |
| CI/CD | [ci_cd_pipeline.md](ci_cd_pipeline.md) | CI steps, deploy trigger, IAM roles, Dependabot |
| Release management | [release-checklist.md](release-checklist.md) | Versioning policy, canonical version source, CHANGELOG, release checklist, tag convention, exact-commit requirement, rollback, post-deploy smoke matrix |
| Security | [security.md](security.md) | Trust boundaries, payments, secrets, automated security checks, known limits |
| Operations | [operations.md](operations.md) | Scheduled/background work, manual responsibilities, backup and release state |
| Observability | [operations.md § Observability](operations.md#observability) | Current logging/alerts vs planned #18 |
| Analytics | [operations.md § Analytics](operations.md#analytics) | No product analytics today; planned #29 |
| Performance | [performance.md](performance.md) | Mini App API latency design, rate limiting, caching, `Server-Timing` |

## Historical and review evidence

These files are kept as evidence of how decisions were reached. They are **not** the
current specification; when they conflict with the documents above, the documents above
win.

| Document | What it is |
| --- | --- |
| [firebase_review.md](firebase_review.md) | Firestore data-model review and migration rationale (the “why”); current map is [firestore.md](firestore.md) |
| [project-dependency-review.md](project-dependency-review.md) | 2026-09-11 decision record for sub-issue/dependency structure; live state is Project #2 |
| [miniapp-visual-foundation.md](miniapp-visual-foundation.md) | #64 visual foundation design notes and review evidence; superseded in parts by #66 and #61 |
| [miniapp-61-review.md](miniapp-61-review.md) | #61 / PR #78 visual review log with screenshots references |
| [`review-evidence/`](../review-evidence/) | Screenshots from Mini App V2 visual reviews |
| Tracking log in [evolutive-tracking.md](evolutive-tracking.md#tracking-log) | Dated notes; not current status |

## Keeping this index honest

- Add a new document here in the same PR that creates it, as primary or historical.
- Prefer extending the primary document over creating a new one.
- `tests/test_docs_links.py` checks that relative Markdown links in `AGENTS.md`,
  `README.md` and `docs/` resolve to existing files.
