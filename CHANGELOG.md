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

### Added

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

### Changed

- Firestore backups use a typed, validated format v2 driven by one collection inventory; they
  now also cover `referrals`, `app_duels`, `group_rounds`, `monthly_closures`, `daily_jobs` and
  subcollections under missing parent documents, and the weekly workflow uploads only a
  validated file ([#50](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/50)).

### Fixed

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
