# Security boundaries and tooling

Authoritative overview of the trust boundaries and the security checks that exist
**today**. It only claims what code and tests enforce; operational secret setup is in
[runtime-hardening.md](runtime-hardening.md) and [deploy.md](deploy.md). Never put real
secrets, tokens, key files or production identifiers that grant access in issues, PRs,
docs or tests.

## Trust boundaries

| Boundary | Enforcement (current) | Tests |
| --- | --- | --- |
| **Telegram → `/webhook`** | `X-Telegram-Bot-Api-Secret-Token` compared in constant time with `WEBHOOK_SECRET` (32–256 URL-safe chars, required at startup); rejected with 403 before the body is parsed; malformed updates 400; 200 only after durable enqueue | `tests/test_runtime_hardening.py` |
| **Cloud Tasks → `/internal/telegram-update`, `/internal/broadcast`, `/internal/monthly-close`** | `X-Task-Secret` = `TASK_SECRET` (separate from the webhook secret); declarative `X-CloudTasks-*` headers are not trusted | `tests/test_runtime_hardening.py` |
| **Cloud Scheduler → `/internal/daily-job`** | `x-cron-secret` = `GENERATION_SECRET`, constant-time, 403 otherwise | `tests/test_internal_daily_job.py` |
| **Mini App → `/app/api/*`** | Identity comes only from Telegram `initData` (HMAC-SHA256 with a key derived from the bot token, `auth_date` max 24 h) in `services/webapp_auth.py`; the client never sends a user id; per-user token bucket before any Firestore read (429 + `Retry-After`, per process, capped by `--max-instances 10`); the `/app/api/perf` timing beacon stops after signature and rate limit, reads nothing and logs only a closed set of bounded numbers ([performance.md](performance.md)) | `tests/test_webapp_auth.py`, `tests/test_runtime_hardening.py`, `tests/test_webapp_performance.py` |
| **Server → Mini App data** | Explicit response projections; answers, accepted aliases and `player_id` never leave the server; hints only after payment of their point cost; duel solutions only after both players finish; public profiles expose a restricted projection | `tests/test_webapp_api.py::test_the_answer_never_reaches_the_page`, `tests/test_public_profiles.py`, `tests/test_app_arena.py` |
| **Clients → Firestore** | `firestore.rules` denies all client access; only the Admin SDK on the server/local tools accesses data | rules file |
| **Admin commands** | `/admin_*` and `/admin_refund` check `ADMIN_TELEGRAM_IDS` | `tests/test_admin_permissions.py` |
| **Admin Control Center** | Not deployed, no login: access equals possession of the machine, `.env` and Firebase key. Candidate review mutations additionally verify an `AdminIdentity` in `ADMIN_TELEGRAM_IDS` inside `CandidateReviewService` | `tests/test_candidate_review.py`, `tests/test_admin_player_review.py` |
| **Candidate/provenance → production** | Candidate data and provenance stay in `data/candidates/`; only authorized approval writes `data/players.json`; production never contains source URLs, raw payloads or lineage | [player-data-pipeline.md](player-data-pipeline.md), candidate tests |
| **Filesystem containment** | `/app/assets/{path}` resolves the path and requires it to stay inside `webapp/dist/assets` (403/404 otherwise); the legal pages are a fixed set of routes; the review service rejects unsafe backup paths | `tests/test_webapp_serving.py` |
| **Container** | Runs as non-root user `app` (uid 1001); no runtime writes needed | `tests/test_docker_packaging.py` |

### Telegram Stars payments

- Invoices use currency `XTR` with an empty provider token; the price and granted
  items always come from `domains/shop/service.py` and `data/shop.json`, never from the client.
- `precheckout_callback` rejects unknown payloads, a payer different from the payload
  user, already-owned items, and any mismatch of currency, amount or quoted grants; it
  reserves the checkout in a transaction.
- `successful_payment_callback` delivers idempotently keyed by
  `telegram_payment_charge_id` in `purchases/`; refunds are admin-only
  (`/admin_refund`) and withdraw delivered cosmetics.
- Tests: `tests/test_shop*.py`, `tests/test_firestore_transactions.py` (emulator).

### Referral integrity

Referral codes are HMAC-signed with the bot token (`domains/referrals/service.py`), self-referral
and reuse are rejected, and qualification counts only server-recorded daily finishes.

### Personal data

`/forgetme DELETE` erases the account and related documents, including duel and
referral traces (`tests/test_forgetme.py`, `tests/test_erasure.py`). The legal pages
(`webapp/terms.html`, `webapp/privacy.html`) must be updated when stored data changes;
tests only check language parity, not truthfulness.

## Secret handling

- Secrets are environment variables on Cloud Run (Secret Manager for key material):
  `BOT_TOKEN`, `WEBHOOK_SECRET`, `TASK_SECRET`, `GENERATION_SECRET`, Firebase
  credentials. Replicas must share the same values; they are never generated at startup.
- `.env`, `firebase-key.json`, `backup/`, `restore-work/`, `data/incoming/` and `data/candidates/` are
  gitignored. `.env.example` contains placeholders only.
- CI/CD authenticates to GCP with Workload Identity Federation; no service-account key
  is stored in GitHub secrets.
- `httpx` logging is raised to `WARNING` by `services/observability.py` (initialised by `bot.py`) because Telegram URLs contain the
  bot token; the PTB error handler logs only the exception type and update id.

## Automated checks

| Check | Command | Where |
| --- | --- | --- |
| Python dependency advisories | `pip-audit`, with time-boxed exceptions in [`security-exceptions.json`](../security-exceptions.json) (each needs `package`, `advisory_id`, `reason`, non-expired `review_by`) | `python -m tools.security` (CI) |
| Secret scanning | `detect-secrets` against [`.secrets.baseline`](../.secrets.baseline) | `python -m tools.security` (CI) |
| Node dependency advisories | `npm audit --audit-level=high` | CI step and `tools.security` |
| Dataset integrity | `python scripts/dataset_report.py --strict` | CI |
| Dataset regression | `python -m scripts.dataset_regression --check` against `data/dataset_baseline.json` | CI |
| Dependency updates | Dependabot (pip, GitHub Actions) | [`.github/dependabot.yml`](../.github/dependabot.yml) |

Locally: `python -m tools.dev security-check`. Tooling tests: `tests/test_security_tooling.py`.
Updating a baseline or adding an exception is a reviewed change with a stated reason,
never a way to make CI green.

## Known limits (not guarantees)

- Rate limiting is in-memory per process; there is no global limit.
- An `uncertain` background update is not retried and needs manual reconciliation.
- Error tracking (Sentry) is optional and off without `SENTRY_DSN`; there is no security
  alerting beyond Telegram admin messages, Cloud Run logs and Sentry
  ([observability.md](observability.md), including its redaction policy).
- Backups contain personal data; they are GitHub Actions artifacts readable by anyone with
  access to the repository's Actions, for 365 days. A restore re-creates users erased after
  the backup, so erasures must be re-applied
  ([backup-recovery.md § 4](backup-recovery.md#4-what-these-backups-do-not-protect)).
