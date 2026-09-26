# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). The
project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html); what MAJOR /
MINOR / PATCH mean in practice for this product, the canonical version source, and the
full release process live in
[docs/release-checklist.md](docs/release-checklist.md).

Entries accumulate under **Unreleased** as changes land on `main`. At release time,
`python -m tools.release bump <major|minor|patch>` moves the Unreleased content into a
new dated section below.

## [Unreleased]

- Shop: Away ticket set, backend-rendered card samples, referral decorations and targeted cosmetic prices (#122).

### Added

- Mini App Shop: a curated Discover page, searchable catalogue with visible categories,
  and product details showing the preview, where each item appears, bundle contents and
  the server-calculated price. Owned items and saved looks now have a dedicated view
  ([#153](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/153)).
- Shop: seven animated collections (Aurora boreale, Coreografia, Sala giochi, Hanami, Beach
  soccer, Pallone cosmico, Derby sotto il diluvio) with ambient theme motion, bounded frame
  flourishes (shine, pulse, orbit), three new card finishes (aurora, halftone, pixel), seven
  new celebrations, and single numbers, titles and badges; every Mini App tab now follows the
  worn theme (cards, nav, highlights) instead of stock slate and green
  ([miniapp-appearance.md](docs/miniapp-appearance.md)).
- Shared results end with an invitation line carrying the sharer's personal invite link
  (`?start=ref_…`), so a friend who joins from a shared result counts as their referral; the
  Mini App Daily page adds a "Copy" button for sharing outside Telegram
  ([#150](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/150)).
- `scripts/refresh_player_careers.py`: career refresh from Wikipedia for all active players
  (`--all`, resumable with `--resume`), for single players by id or name (`--player`) or from an
  id list, with `--dry-run` ([player-data-pipeline.md](docs/player-data-pipeline.md)).
- Optional Sentry error tracking for the backend (bot, API, jobs, Cloud Tasks workers,
  payments, broadcasts, Admin, Candidate pipeline), enabled only by `SENTRY_DSN`; the Sentry
  release is the `VERSION` release and the Cloud Run revision is a separate tag
  ([#18](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/18),
  [observability.md](docs/observability.md)).
- Structured runtime logs (JSON on Cloud Run) with stable event names, component tags,
  durations, server-generated `X-Request-ID` and Cloud Tasks correlation.
- HTTP regression tests for the `x-cron-secret` boundary of `POST /internal/daily-job`.
- Verified Firestore restore: `scripts/restore_firestore.py` (`validate`, `restore`, `verify`,
  `upgrade-v1`), emulator-by-default with explicit production guards and no deletes, a real
  emulator backup→restore→compare test, and the weekly `restore-verification.yml` workflow
  (a real target also requires a complete native v2 backup unless the separate
  `--allow-incomplete-or-lossy-backup` acknowledgement is given)
  ([#50](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/50),
  [backup-recovery.md](docs/backup-recovery.md)).
- Firestore-backed operational feature flags (`admin_settings/feature_flags`) for arena, shop,
  Daily UI, hints, player pipeline, Mini App events and leaderboard: server-side evaluation with
  kill switch, deterministic percentage rollout and user/group targeting, a TTL cache with
  last-known-good, `FEATURE_DISABLED` API responses and an operator CLI; every flag defaults to
  the current behaviour ([#51](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/51), [feature-flags.md](docs/feature-flags.md)).
- Data-driven difficulty: a 0-100 difficulty score with a tuning fingerprint, a
  `difficulty_prediction` snapshot on every new Daily, observed attempt/hint counters on
  `daily_path`, an Admin “Prevista vs osservata” comparison (rank correlation, per-band
  results, recurring deviations per career dimension) with its parameters in
  `data/config.json`, and `difficulty_band` on `daily_completed`
  ([#21](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/21),
  [difficolta.md](docs/difficolta.md)).
- Daily planner: 7–90-day calendar proposals with eligibility, difficulty rotation and streak
  limit, no-repeat in both directions, club/nationality diversity, recorded relaxations and a
  per-day `planner_audit`; Admin “Planner sfide” page to review, re-roll a day, exclude players
  (reason and expiry in `admin_settings/daily_planner`), lock days and apply; the nightly
  buffer and “Rigenera” use the same rules
  ([#30](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/30),
  [game-modes.md](docs/game-modes.md#daily-planner)).
- Data-driven events: event template schema v2 (`filters`, `rules`, `rewards`, `schedule` with
  rotation windows/weekdays, fixed dates and manual mode) validated in CI, Admin and at runtime;
  attempts, first-solver bonus and podium trophies come from the event instead of constants in
  chat, Mini App and trophies; fixed-date events are created ahead; Admin template editor with
  preview and backup
  ([#31](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/31),
  [event-templates.md](docs/event-templates.md)).
- Performance measurement: Firestore reads/queries/writes per request (log fields and
  `Server-Timing`), cold-start marking and startup phases, Telegram handler durations, a Mini
  App startup beacon (`POST /app/api/perf`, no Firestore read), latency/read budgets with
  `performance.budget.exceeded`, and `python -m tools.dev perf-report` for baseline and trend
  from Cloud Logging, with the first production baseline in `docs/performance-baselines/`
  ([#32](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/32),
  [performance.md](docs/performance.md)).
- Domain map and dependency boundaries: every Python module assigned to a composition root,
  app, domain or infrastructure in `tools/architecture.py`, with the dependency rules checked
  in CI on the real import graph and existing violations recorded as explicit debt
  (`python -m tools.dev architecture`)
  ([#109](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/109),
  [architecture.md](docs/architecture.md#3-composition-root-and-domain-boundaries)).

### Changed

- Removed the leftovers of the old Mini App: the `/app/v2` path (the Vite Mini App has been
  `/app` since #115), the `window.PlayerClient` legacy bridge, the `test-node` command for the
  deleted `tests/client.test.cjs`, and the `legacy` label of the startup beacon. The
  environment validator checks the Vite sources instead of the deleted HTML/JS files, and
  the docs describe one frontend
  ([#146](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/146)).
- Bot: `/info` is merged into `/help`, which now only explains the game (daily challenge,
  attempts, hints, points, streak, what's in the mini app) in IT/ES/EN and shows a single
  button to open the mini app, without the full menu keyboard or the command list. `/app`
  is removed too: `/start` already registers the user and shows the mini app button.
- The Candidate pipeline and its source adapters moved to `domains/players/`, the shop to
  `domains/shop/` (`service`, `repository`, `editor`) and referrals to
  `domains/referrals/service.py`; all importers updated, no compatibility shims, and
  `domains/` is compiled, type-checked and counted in coverage like `services/`. The
  procedure for the remaining domains is documented
  ([#111](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/111),
  [architecture.md](docs/architecture.md#moving-a-domain-into-its-package)).
- `bot.py` is now a pure composition root: the Telegram application and handler registration
  live in `apps/bot/`, the FastAPI factory, middleware, webhook/workers, Mini App API and
  static routes in `apps/api/`, connected by an injected `TelegramBridge`. Same routes, same
  handlers in the same order, same responses
  ([#110](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/110),
  [architecture.md](docs/architecture.md#3-composition-root-and-domain-boundaries)).
- The bot builds a single Telegram HTTP client instead of two (it never calls `getUpdates`),
  halving `ApplicationBuilder().build()` at startup (298 ms → 149 ms measured locally)
  ([#32](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/32)).

- Firestore backups use a typed, validated format v2 driven by one collection inventory; they
  now also cover `referrals`, `app_duels`, `group_rounds`, `monthly_closures`, `daily_jobs` and
  subcollections under missing parent documents, and the weekly workflow uploads only a
  validated file ([#50](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/50)).
- Group rounds: the rules (opening a round on training material, attempts, who wins,
  points, standings) moved from `handlers/group_handler.py` into `domains/groups/service.py`,
  and the repository from `services/repos/groups.py` to `domains/groups/repository.py`. The
  handler only renders replies; bot behaviour is unchanged
  ([#147](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/147)).

### Fixed

- Bulk career refresh no longer stops updating after Wikipedia timeouts: timeouts are retried,
  slow chunks are split, each chunk is saved once (one backup per run instead of one per
  player) and an unreachable source stops the run cleanly.
- Wikipedia scripts no longer end up rate limited (the "blacklist" after a few players): every
  Wikimedia call uses a policy-compliant User-Agent with a contact (`WIKIMEDIA_CONTACT` adds an
  email) and is spaced at most 60 requests/minute; the legacy career refresh no longer re-reads
  stale cached pages.
- Career refresh no longer adds a transfer without `country`/`league` (which silently dropped
  the player from the game): new clubs are resolved from the dataset, the manual table or the
  club's Wikipedia page, and unresolved ones are reported for manual completion. Returns to a
  former club are no longer merged into the old stop, curated team/country/league are kept, and
  goalkeepers' conceded goals are never written as goals.
- Mini App: on short pages (Daily before any guess) the bottom nav bar was cut off by a dark
  strip on mobile; Events and Archive now have a back link to the Arena hub.

### Security

- Observability redaction of tokens, secrets, cookies, Authorization and Telegram `initData`;
  raw player guesses, signed invoice payloads and admin command arguments are no longer
  logged; pseudonymous user references only with a secret `OBSERVABILITY_USER_SALT`.

## [0.1.0] - 2026-09-14

Baseline release marker, not a reconstruction of project history. Development before
this point was continuous deployment straight to `main` with no version numbers, tags,
or changelog (see
[operations.md § Release state](docs/operations.md#release-state) before this change).
This entry gives `0.1.0` a concrete meaning — "state of the product when release
management was formalized" — instead of being an arbitrary starting number. Individual
historical commits are not listed here; `git log` remains authoritative for that.

Notable state at this baseline (see the linked docs for detail, not repeated here):

- Telegram bot and Mini App: legacy `/app` in production, `/app/v2` functionally
  migrated and redesigned, rollout gated by
  [#81](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/81)
  (see [miniapp.md](docs/miniapp.md)).
- Daily challenge, Archive, Training, Arena duels, group rounds, themed Events,
  leaderboards, leagues, and referrals (see [game-modes.md](docs/game-modes.md)).
- Shop and Telegram Stars payments, Admin (Telegram commands and Streamlit dashboard).
- CI (`.github/workflows/ci.yml`), automatic Cloud Run deploy on green `main`
  (`.github/workflows/deploy.yml`), weekly Firestore JSON backup
  (`.github/workflows/backup.yml`) — restore is not yet proven, tracked in
  [#50](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/50).
