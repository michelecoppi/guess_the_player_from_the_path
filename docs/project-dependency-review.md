# Project dependency review — 2026-09-11

This document records a review of the dependency/sub-issue structure proposed for
the evolutive backlog (#11–#32), the decisions taken, and the changes actually
applied to GitHub. It is a point-in-time decision record, not a live index —
[GitHub Project #2](https://github.com/users/michelecoppi/projects/2) remains the
canonical operational source for Status, Priority, Area, Type, Horizon, Size,
Risk and Release. [`evolutive-tracking.md`](evolutive-tracking.md) is the
lightweight repository-side index; this file explains *why* the relationships
below exist.

## Verified starting state

Before this review, a GraphQL check of the repository showed:

- **Zero** GitHub-native `parent`/`sub-issue` or `blocked-by` relations existed
  across all of #11–#32.
- **Zero** labels were applied to any of #11–#32, even though #11 already
  specified `security`, `breaking-change`, `needs-decision`, `data-risk` as the
  intended cross-cutting labels.

Everything below was applied on top of that empty state.

## Parent / sub-issue structure

| Parent | Sub-issues | Rationale |
| --- | --- | --- |
| #13 — Candidate Player pipeline | #14, #26, #15, #27 | All four are stages of the same discover→ingest→normalize→validate→review→approve pipeline described in #13. |
| #12 — Admin Control Center | #33–#39 | #12's original scope listed ~12 unrelated admin sections in one issue; split into dashboard/overview, daily challenge management, review-queue integration, users/groups/leagues, shop/referral, system health & backup, analytics view. |
| #17 — Mini App migration | #40–#48 | #17's own body already enumerated the features to migrate one at a time; each became its own sub-issue, plus one for shared components/test infra. |
| #20 — Release management + backup recovery | #49, #50 | Two distinct responsibilities (release process vs. disaster recovery) that don't share an owner or a completion criterion. |
| #22 — Feature flags + experimentation | #51, #52 | Feature flags are usable standalone; experimentation requires reliable metrics. Splitting avoids forcing a flags-only rollout to wait on analytics. |

`#15` intentionally has a single parent (#13). Its functional relationship with
#12 is documented as `related`, not a second parent (GitHub sub-issues support
only one parent).

## Hard dependencies (`blocked by`, enforced on GitHub)

| Blocked issue | Blocked by | Why it's hard, not soft |
| --- | --- | --- |
| #15 | #14, #26 | The review queue displays source, confidence and normalization warnings that #14/#26 must produce first. |
| #17 and its 9 sub-issues (#40–#48) | #16 | No migration work is possible before the Vite/TypeScript build foundation exists. |
| #52 (Experimentation platform) | #29 | An experiment can't be evaluated without the funnels/metrics #29 defines. |

`#51` (Feature flags) has **no** dependency on #29 — the split exists precisely
so the flag infrastructure isn't blocked by analytics work.

## Soft / related dependencies (documented in comments, not GitHub relations)

These were deliberately **not** modeled as `blocked by`, to avoid over-constraining
work that can start independently:

- **#27** (provenance) → related to #13: can start once the pipeline model is
  reasonably stable, not once #13 is formally closed.
- **#25** (Dataset Health) → related to #12 / #39: stays Area `Data`; the admin
  only hosts its UI.
- **#30** (Daily planner) → related to #21 (difficulty model): documented as
  "requires stable interface" — the planner can ship against a first
  deterministic API and adopt the calibrated model later.
- **#32** (performance) → related to #18 (observability): obvious bottlenecks
  can be fixed before full telemetry lands; systematic, data-driven work needs
  the #18 baseline.
- **#28** (monorepo architecture) → no relation to #12, #13, #16 or anything
  else. Stays a `Later` umbrella for incremental, trailing cleanup; deliberately
  has no pre-planned sub-issues so it doesn't calcify before the rest of the
  roadmap is more mature.

## Labels applied

- `data-risk` → #13, #14, #15, #25, #26, #27 (all touch production player
  dataset integrity).
- `security` → #19 (explicitly scopes pip-audit and secret scanning).
- `breaking-change` and `needs-decision` were created (per #11) but not force-applied
  anywhere yet — no existing issue currently carries an unambiguous signal for
  either; use them going forward as they arise.

## What was intentionally left alone

- Project field values (Status, Priority, Area, Type, Horizon, Size, Risk,
  Release) — untouched, as requested.
- #19 (CI) and #23 (documentation) were **not** split. #19's split was raised as
  an optional "evaluate" in the original review, not a firm recommendation; #23
  covers documentation debt more naturally addressed incrementally alongside
  the issues it describes.
- No issue body text was rewritten; soft/related notes were added as comments
  to preserve the original content and keep the reasoning auditable.

## New issues created by this review

#33–#52 (20 issues), all skeleton-sized (title + short scope), sub-issues of
#12, #17, #20 or #22 as mapped above.

## Project field classification for #33–#52

Classified on 2026-09-11, consistent with the parent's own values but
differentiated per sub-issue where the split itself justifies a different
call — most notably #51 vs #52 (see below).

| Issue | Area | Work Type | Priority | Horizon | Size | Risk |
| --- | --- | --- | --- | --- | --- | --- |
| #33 Admin dashboard overview | Admin | Feature | P1 | Next | 3 | Low |
| #34 Admin Daily Challenge mgmt | Admin | Feature | P1 | Next | 3 | Medium |
| #35 Admin Review Queue integration | Admin | Feature | P1 | Next | 2 | Low |
| #36 Admin users/groups/leagues | Admin | Feature | P2 | Later | 3 | Medium |
| #37 Admin shop/referral | Admin | Feature | P2 | Later | 3 | Medium |
| #38 Admin system health/log/backup | Admin | Feature | P1 | Next | 2 | Low |
| #39 Admin analytics view | Admin | Feature | P2 | Later | 2 | Low |
| #40 Mini App: Daily | Mini App | Refactor | P1 | Next | 3 | Medium |
| #41 Mini App: Arena | Mini App | Refactor | P1 | Next | 3 | Medium |
| #42 Mini App: Profilo | Mini App | Refactor | P2 | Next | 2 | Low |
| #43 Mini App: Leaderboard | Mini App | Refactor | P2 | Next | 2 | Low |
| #44 Mini App: Archivio | Mini App | Refactor | P2 | Later | 2 | Low |
| #45 Mini App: Shop | Mini App | Refactor | P2 | Later | 3 | Medium |
| #46 Mini App: Referral | Mini App | Refactor | P2 | Later | 2 | Low |
| #47 Mini App: Eventi | Mini App | Refactor | P2 | Later | 3 | Medium |
| #48 Mini App: shared components/test infra | Mini App | Refactor | P1 | Next | 3 | Medium |
| #49 Release management | Infrastructure | Infrastructure | P1 | Next | 3 | Low |
| #50 Backup & disaster recovery | Infrastructure | Infrastructure | P1 | Next | 3 | High |
| #51 Feature flags infra | Growth | Infrastructure | P1 | Next | 3 | Low |
| #52 Experimentation platform | Growth | Feature | P2 | Later | 3 | Medium |

Reasoning behind the notable deviations from a flat "copy the parent's values":

- **Sizes are smaller than the parent's `8`** (mostly 2–3) — that's the point of
  splitting: each piece should now fit in a single PR.
- **#48 (shared components/test infra) is P1/Next**, ahead of the individual
  feature migrations — the other 8 sub-issues of #17 build on it.
- **#38 (system health/log/backup) and #35 (Review Queue integration) are
  Low risk** — they're wiring/visibility work; the real risk lives in the
  systems they surface (#20, #15), not in the admin glue code.
- **#50 (backup/disaster recovery) is High risk**, higher than its parent
  (#20 was Medium) — an untested restore path is a correctness/data-loss risk
  in its own right, independent of the release-process half of #20.
- **#51 (feature flags) is Priority P1 / Horizon Next**, pulled forward from
  the parent's P2/Later — it has no dependency on #29 and is a cheap, reusable
  enabler; #52 (experimentation) keeps the parent's P2/Later since it's
  genuinely `blocked by` #29.
- Admin/shop/referral/users-groups-leagues (#36, #37) and the later Mini App
  migrations (#44, #46, #47) are pushed to **Horizon Later** — useful but not
  needed for the initial "run the game without touching JSON/scripts" goal
  that #33/#34/#35/#38 and #40/#41 (Daily, Arena) serve first.

Status was left at the board default (`Backlog`) for all 20 — moving any of
them to `Ready` is a Project decision, not something this review makes.
