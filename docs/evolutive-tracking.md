# Evolutive tracking

This file is the repository-side index for the product and technical roadmap.
The canonical operational board is [GitHub Project #2](https://github.com/users/michelecoppi/projects/2): **⚽ Guess the Player — Product & Development**.

The roadmap was converted from `FUTURE_IMPROVEMENTS_GUESS_THE_PLAYER.md` into the following GitHub issues on 2026-09-11. The Project, not this index, is the canonical source for fields, statuses, priorities, release targets and dependencies.

| Issue | Work item |
| --- | --- |
| [#11](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/11) | Standardize the GitHub product/development workflow |
| [#24](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/24) | Local developer environment and configuration validator |
| [#12](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/12) | Admin Control Center (epic) |
| [#33](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/33) | ↳ Admin: dashboard overview and live metrics |
| [#34](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/34) | ↳ Admin: Daily Challenge management |
| [#35](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/35) | ↳ Admin: Review Queue integration |
| [#36](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/36) | ↳ Admin: users, groups and leagues |
| [#37](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/37) | ↳ Admin: shop and referral |
| [#38](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/38) | ↳ Admin: system health, logs and backup |
| [#39](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/39) | ↳ Admin: analytics view |
| [#25](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/25) | Dataset Health dashboard |
| [#13](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/13) | Candidate Player ingestion pipeline (epic) |
| [#14](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/14) | ↳ Multi-source player-data adapters |
| [#26](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/26) | ↳ Club normalization and career validation |
| [#15](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/15) | ↳ Player review queue and approval workflow |
| [#27](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/27) | ↳ Player-data provenance |
| [#16](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/16) | Vite + TypeScript Mini App foundation |
| [#17](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/17) | Incremental Mini App migration and frontend tests (epic) |
| [#40](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/40) | ↳ Migrate Daily feature |
| [#41](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/41) | ↳ Migrate Arena feature |
| [#42](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/42) | ↳ Migrate Profile feature |
| [#43](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/43) | ↳ Migrate Leaderboard feature |
| [#44](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/44) | ↳ Migrate Archive feature |
| [#45](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/45) | ↳ Migrate Shop feature |
| [#46](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/46) | ↳ Migrate Referral feature |
| [#47](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/47) | ↳ Migrate Events feature |
| [#48](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/48) | ↳ Shared components and frontend test infra |
| [#28](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/28) | Domain-oriented monorepo architecture |
| [#18](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/18) | Sentry and structured logging |
| [#29](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/29) | Product analytics and funnels |
| [#19](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/19) | CI security, frontend and dataset regression checks |
| [#20](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/20) | Release management and backup recovery (epic) |
| [#49](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/49) | ↳ Release management: versioning, changelog, deploy checklist |
| [#50](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/50) | ↳ Backup and disaster recovery |
| [#30](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/30) | Automated Daily Challenge planner |
| [#21](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/21) | Data-driven difficulty model |
| [#31](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/31) | Data-driven event automation |
| [#22](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/22) | Feature flags and experimentation (epic) |
| [#51](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/51) | ↳ Feature flags infrastructure |
| [#52](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/52) | ↳ Experimentation platform |
| [#32](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/32) | Performance measurement and targeted optimization |
| [#23](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/23) | Documentation and AI-agent protocol |

## Protocol for future agents

1. Before starting an evolutive, read the linked GitHub issue, inspect the current implementation, and check the Project's Status, Horizon, Priority and dependencies. Do not assume the roadmap still describes the exact code state.
2. Use `Backlog → Ready → In Progress → Review → Done`; use `Blocked` only for an active impediment. Horizon is strategic timing, not a status. Keep at most two evolutives in `In Progress` unless the issue records an explicit exception.
3. Work incrementally. Preserve existing behavior, avoid broad rewrites, add or update tests, and run the relevant test suite.
4. A PR that completes the whole issue must use `Closes #<issue>`; a partial PR only references it. Move the item to `Review` when implementation and tests are ready; use `Done` only after merge/verification.
5. Keep this index lightweight: update it when creating, splitting, closing or materially redefining roadmap work, but never copy all Project-field values here.

## Creating a new issue

An issue left in `Backlog` with unset Project fields is not usable roadmap
data — it's invisible to prioritization and to WIP tracking. Before moving on:

1. **Assign every Project field**: `Area` (one of the ten official values
   below — never a legacy aggregate), `Work Type`, `Priority`, `Horizon`,
   `Size`, `Risk`. `Status` defaults to `Backlog`, which is correct for a new
   issue; don't leave the rest blank "for later".
2. **Size the issue honestly.** If the scope genuinely needs `Size 8`, split it
   into sub-issues *before* starting implementation rather than after — see
   `project-dependency-review.md` for a worked example (#12, #17, #20, #22).
   A `Size 8` epic is fine as a parent; it should not itself carry
   implementation work.
3. **Model dependencies at the right strength**:
   - **Hard** (the child is technically impossible without the parent): create
     a real GitHub `sub-issue` and/or `blocked by` relation via the GraphQL
     `addSubIssue` / `addBlockedBy` mutations (the `gh` CLI has no built-in
     command for either as of this writing).
   - **Soft / related** (helpful ordering, not a technical blocker): do **not**
     create a GitHub relation. Add a short comment on the issue stating the
     relation and why it's soft, so the reasoning is visible without
     constraining the Project board's dependency view.
   - Don't invent a relation that isn't there — most issues have none.
4. **Apply cross-cutting labels only when the content actually earns them**:
   `security`, `breaking-change`, `needs-decision`, `data-risk` (defined in
   #11). Do not use labels to re-encode a Project field (e.g. don't add an
   `admin` label — that's what `Area` is for).
5. Update this index's table and, for anything non-trivial, add one line to
   the tracking log below with the date and the reasoning — not the full
   Project state, which lives on the board.

## Key delivery relationships

As of 2026-09-11 these are real GitHub sub-issue / `blocked by` relations, not
just prose — see [`project-dependency-review.md`](project-dependency-review.md)
for the full rationale and the soft/related dependencies that were deliberately
**not** turned into GitHub relations.

- #13 is the Player Data Pipeline epic, with #14, #26, #15, #27 as sub-issues. #15 is `blocked by` #26 (hard); #14 precedes #15 as a soft dependency (documented on the issue). #27 is related-only (soft), not blocked. #15 is also consumed by #12 (via sub-issue #35, which is `blocked by` #15) but retains #13 as its sole parent.
- #12 is the Admin Control Center epic, split into sub-issues #33–#39. #25 (Dataset Health) stays related, not a sub-issue — it's Area `Data` even though the admin hosts it.
- #17 is the Mini App migration epic, split into sub-issues #40–#48, all `blocked by` #16 (Vite/TS foundation). #19's frontend checks rely partly on the Vite toolchain (not modeled as a formal block).
- #20 is split into sub-issues #49 (release management) and #50 (backup/recovery) — two responsibilities, no shared completion criterion.
- #22 is split into sub-issues #51 (feature flags, no dependency) and #52 (experimentation, `blocked by` #29).
- #18 precedes #32 for telemetry-backed performance work (soft); #21 precedes #30 through a stable deterministic difficulty API (soft).
- #28 is intentionally later and has no dependency on or from #12, #13, #16. It has no pre-planned sub-issues, to avoid it becoming vague before the rest of the roadmap matures.

## Area taxonomy

Use one primary Project Area: Players, Data, Admin, Mini App, Bot, Analytics, Infrastructure, Documentation, Game or Growth. Do not use legacy aggregate names such as `Players/Data`, `Infra` or `Docs`.

## Tracking log

- 2026-09-11: created 22 roadmap issues (#11–#32) and added them to GitHub Project #2.
- 2026-09-11: began governance refinement: added `Horizon` and `Size`; codified the status flow, WIP limit and PR-closing convention.
- 2026-09-11: dependency/sub-issue review. Split #12, #17, #20, #22 into 20 skeleton sub-issues (#33–#52); formalized hard dependencies as GitHub sub-issue/`blocked by` relations for #13→(#14,#26,#15,#27), #26→#15, #15→#35, #16→#17 and its sub-issues, #29→#52; reconciled #14→#15 as soft; documented soft/related dependencies as issue comments instead of GitHub relations; created and applied `data-risk`/`security` labels. Full rationale in [`project-dependency-review.md`](project-dependency-review.md).
- 2026-09-11: classified #33–#52 on the Project (Area, Work Type, Priority, Horizon, Size, Risk), differentiated per sub-issue rather than copied from the parent — e.g. #51 (feature flags) pulled to P1/Next since it has no dependency on #29, while #52 (experimentation) stays P2/Later. Full table in [`project-dependency-review.md`](project-dependency-review.md). Status left at `Backlog` for all 20.

- 2026-09-12: #66 establishes the V2 dark-only appearance contract before #42/#45; backend cosmetic rules and legacy `/app` remain unchanged. See `miniapp-appearance.md`.
