# Operations, observability and analytics

Authoritative overview of what runs on its own, what a maintainer does by hand, and
what monitoring and analytics exist **today**. Step-by-step infrastructure setup lives
in [deploy.md](deploy.md) and [runtime-hardening.md](runtime-hardening.md). This
document does not introduce procedures that have not been exercised; where a
capability is missing it says so and links the roadmap issue.

## Scheduled and background work

| What | Trigger | Implementation | Notes |
| --- | --- | --- | --- |
| Nightly content job | Cloud Scheduler, `15 23 * * *` UTC → `POST /internal/daily-job` | `handlers/daily_job.py::update_daily_challenge` | Fills the Daily buffer, may generate an event, assigns trophies of events that ended yesterday, prepares the monthly close on day 1, stores the immutable payload in `daily_jobs/{day}`, enqueues the broadcast. Re-running the same day reuses the stored payload |
| Daily broadcast | Cloud Tasks `BROADCAST_QUEUE` (concurrency 1) → `POST /internal/broadcast` | `handlers/daily_job.py::broadcast_batch` | Pages of 100 subscribed users, per-recipient work receipts, `Forbidden` disables notifications, `RetryAfter` re-queues; the last page sends the admin summary |
| Monthly close | Cloud Tasks → `POST /internal/monthly-close` | `services/monthly_closure.py` | Podium frozen in `monthly_closures/{YYYY-MM}`, per-user transactional reset in pages |
| Telegram updates | Cloud Tasks `TASKS_QUEUE` → `POST /internal/telegram-update` | `bot.py`, `services/work_receipts.py` | Deduplicated and serialized per user; `uncertain` updates alert admins and are not replayed |
| Deploy | GitHub Actions `deploy.yml` after successful CI on `main` | [ci_cd_pipeline.md](ci_cd_pipeline.md) | Every merge to `main` that passes CI is deployed |
| Firestore backup | GitHub Actions `backup.yml`, Mondays 03:30 UTC, or manual dispatch | `scripts/backup_firestore.py` | JSON artifact kept 365 days |
| Dependency updates | Dependabot, weekly | `.github/dependabot.yml` | PRs go through normal CI |

If the scheduler does not run, today's challenge is generated on first use, but the
broadcast, trophies and monthly close do not happen until the job runs.

## Manual operational responsibilities

| Responsibility | Tools |
| --- | --- |
| Check the Daily buffer and upcoming answers | `/admin_status`, `/admin_next`, Admin “Stato generale” / “Sfide giornaliere”; `/admin_regen` to fill gaps |
| Watch player-pool autonomy and difficulty coverage | `/admin_pool`, `python scripts/dataset_report.py`, Admin “Dataset” |
| React to wrong player data reported by users | `/admin_block` (immediate), then fix the dataset through a PR |
| Grow the dataset | [player-data-pipeline.md](player-data-pipeline.md) (legacy import or Review Queue), then PR |
| Manual events (father/son) | `/admin_fs_add`, `/admin_event_create`, Admin “Eventi” |
| Payment support and refunds | `/paysupport` requests → `/admin_support_reply`; `/admin_refund <charge_id>` |
| Reconcile `uncertain` updates or broadcast pages | Cloud Run logs + user history; never delete an uncertain receipt blindly ([runtime-hardening.md](runtime-hardening.md)) |
| Prune old challenges | `scripts/cleanup_daily_paths.py` (manual on purpose, dry-run first) |
| Backfill/migrate user documents | `scripts/backfill_users.py`, `scripts/migrate_firestore.py` (historical) |
| Rotate secrets | Procedure in [runtime-hardening.md](runtime-hardening.md) |

## Backup and recovery state

**Current state.**

- Weekly JSON export of `users`, `daily_path`, `events`, `seasons`, `leagues`,
  `father_son_pairs`, `admin_settings`, `purchases`, including their subcollections,
  stored as a GitHub Actions artifact for 365 days.
- Not in the export list: `referrals`, `app_duels`, `group_rounds`, and operational
  collections (`work_receipts`, `update_locks`, `daily_jobs`, `monthly_closures`).
- There is no documented or tested restore procedure. Having an export is not a
  verified recovery capability.
- Local dataset edits and candidate approvals write file backups to `backup/`
  (gitignored, local only).

**Planned evolution.** [#50](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/50)
— retention, restore test and documentation (epic
[#20](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/20)). Admin
visibility of backups/system health is
[#38](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/38).

## Release state

**Current state.** Continuous deployment of `main`; no version numbers, tags,
changelog or deploy checklist. Rollback is manual (route traffic to a previous Cloud
Run revision or redeploy an earlier commit). Cloud-side configuration (env vars,
queues, scheduler, IAM) is set with `gcloud` as documented and is not reconciled from
the repository.

**Planned evolution.** [#49](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/49)
— versioning, changelog and deploy checklist.

## Observability

**Current state.**

- Python standard `logging` (`logging.basicConfig(level=INFO)`, plain text) to stdout,
  read in Cloud Run logs. No structured/JSON logging, correlation ids or log-based
  metrics are defined in this repository.
- `/app/api/*` requests emit a `[WEBAPP] <route> status=<code> duration_ms=<ms>` log
  line and a `Server-Timing: app;dur=<ms>` header (no request bodies, signatures or
  answers are logged). See [performance.md](performance.md).
- Telegram messages to admins (`ADMIN_TELEGRAM_IDS`) for: unhandled handler errors
  (`handlers/error_handler.py`), `uncertain` interrupted updates
  (`services/alerts.py`), broadcast completion summary and broadcast problems
  (`handlers/daily_job.py`).
- [runtime-hardening.md](runtime-hardening.md) recommends Cloud Logging alerts for
  `uncertain`, worker errors and exhausted task retries. Whether they are configured
  lives in GCP, not in this repository, and is not verified here.
- No error tracking service (Sentry or similar), no uptime checks and no dashboards are
  part of the codebase.

**Planned evolution.** [#18](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/18)
— Sentry and structured logging (open, not implemented).
[#32](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/32) —
performance measurement (soft dependency on #18, see [evolutive-tracking.md](evolutive-tracking.md)).
[#38](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/38) — Admin
system health and logs.

## Analytics

**Current state.** There is **no product analytics**: no event tracking SDK, no event
schema, no funnels and no analytics dashboards. The privacy page states that the Mini
App has no analytics or third-party trackers. What exists are operational aggregates
stored as part of game state:

- `daily_path/{day}.players_count` and `solved_count` (Increment counters);
- `/admin_stats` (registered users, notifications enabled, solved today) and the
  Admin overview/leaderboards;
- per-user attempt histogram `solved_in`, streaks and referral qualification counts;
- `daily_jobs/{day}.sent_total` for broadcasts.

These are not a substitute for analytics and must not be described as funnels.

**Planned evolution.** [#29](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/29)
— product analytics and funnel definition. Related work:
[#39](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/39) (Admin
analytics view) and [#52](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/52)
(experimentation, blocked by #29). Feature flags
([#51](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/51)) are
also not implemented. Any analytics change must update the privacy page.
