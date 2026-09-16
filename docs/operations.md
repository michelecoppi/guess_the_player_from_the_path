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
| Firestore backup | GitHub Actions `backup.yml`, Mondays 03:30 UTC, or manual dispatch | `scripts/backup_firestore.py`, `services/firestore_backup/` | Typed v2 JSON, validated before upload, artifact kept 365 days ([backup-recovery.md](backup-recovery.md)) |
| Restore verification | GitHub Actions `restore-verification.yml`, Tuesdays 05:00 UTC, or manual dispatch; also every CI run | `tests/test_backup_restore_emulator.py` | Synthetic backup→restore→compare on the emulator; no credentials |
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

**Current state.** Authoritative description: [backup-recovery.md](backup-recovery.md) (#50).

- Weekly typed JSON export (format v2) of every durable collection in the inventory
  (`services/firestore_backup/inventory.py`), subcollections included, validated before upload and
  stored as a GitHub Actions artifact for 365 days. Maximum expected data loss with the
  schedule alone: up to 7 days.
- Deliberately excluded: `work_receipts`, `update_locks` (ephemeral dedup/lock state).
- `scripts/restore_firestore.py` validates, restores (emulator by default; a real project
  needs explicit guards; never deletes) and verifies. The full backup→restore→compare path
  runs on the emulator in every CI run and weekly (`restore-verification.yml`), with
  synthetic data. A restore of a real artifact is a manual drill.
- Local dataset edits and candidate approvals write file backups to `backup/`
  (gitignored, local only).

**Planned evolution.** Admin visibility of backups/system health is
[#38](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/38).

## Release state

**Current state.** Continuous deployment of `main` (unchanged by #49 — see
[release-checklist.md § Deploy procedure](release-checklist.md#6-deploy-procedure)).
Versioning, CHANGELOG, a release checklist, and rollback guidance now exist in
[release-checklist.md](release-checklist.md) ([`VERSION`](../VERSION),
[`CHANGELOG.md`](../CHANGELOG.md), `python -m tools.release`); adoption is opt-in going
forward (see [release-checklist.md § Adopting this process](release-checklist.md#adopting-this-process)),
so most deploys so far still have no tag. Cloud-side configuration (env vars, queues,
scheduler, IAM) is set with `gcloud` as documented and is not reconciled from the
repository.

Data migrations use the backup gate in [release-checklist.md § 8.2](release-checklist.md#82-backup-gate),
which relies on the verified procedure in [backup-recovery.md](backup-recovery.md).

## Observability

**Current state.** Authoritative description: [observability.md](observability.md).

- Structured logs (JSON on Cloud Run, readable text locally) with stable event names and
  `component`/`route`/`request_id`/`task_name` fields, and optional Sentry error tracking
  enabled by `SENTRY_DSN` (#18). Records carry the formal `release` (`VERSION`) and, on
  Cloud Run, the exact build `revision`. No log-based metrics are defined in this repository.
- `/app/api/*` requests also return a `Server-Timing: app;dur=<ms>` header. See
  [performance.md](performance.md).
- Telegram messages to admins (`ADMIN_TELEGRAM_IDS`) for: unhandled handler errors
  (`handlers/error_handler.py`), `uncertain` interrupted updates
  (`services/alerts.py`), broadcast completion summary and broadcast problems
  (`handlers/daily_job.py`).
- [runtime-hardening.md](runtime-hardening.md) recommends Cloud Logging alerts for
  `uncertain`, worker errors and exhausted task retries. Whether they are configured
  lives in GCP, not in this repository, and is not verified here.
- No uptime checks, alert policies or dashboards are part of the codebase.

**Planned evolution.**
[#32](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/32) —
performance measurement (soft dependency on #18, see [evolutive-tracking.md](evolutive-tracking.md)).
[#38](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/38) — Admin
system health and logs.

## Analytics

**Current state.** Product analytics ([#29](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/29))
is implemented: a typed event taxonomy sent to PostHog through
[`services/product_analytics.py`](../services/product_analytics.py), off by default and
requiring an operator-supplied `POSTHOG_API_KEY` to send anything. Full contract - event
list, pseudonymous identity, privacy review, funnels, metric definitions, how to disable it
- is authoritative in [product-analytics.md](product-analytics.md). It is a strictly
separate system from the operational aggregates below and from
[observability.md](observability.md) (#18).

Operational aggregates stored as part of game state (not analytics, must not be described
as funnels):

- `daily_path/{day}.players_count`, `solved_count`, `solved_attempts_total` and
  `solved_hints_total` (Increment counters; observed difficulty, [difficolta.md §6](difficolta.md));
- `/admin_stats` (registered users, notifications enabled, solved today) and the
  Admin overview/leaderboards;
- per-user attempt histogram `solved_in`, streaks and referral qualification counts;
- `daily_jobs/{day}.sent_total` for broadcasts.

**Related, not implemented here.**
[#39](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/39) (Admin
analytics view, to be built on top of the #29 event schema) and
[#52](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/52)
(experimentation - variants, assignment, statistical significance - explicitly out of scope
for #29 and still blocked by it). Any further analytics change must keep the privacy page
(`webapp/privacy.html`) accurate.
