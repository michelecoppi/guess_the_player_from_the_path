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
#12, #17, #20 or #22 as mapped above. They still need Project fields (Area,
Priority, Horizon, Size, Risk) assigned on the board before they're ready to
pick up.
