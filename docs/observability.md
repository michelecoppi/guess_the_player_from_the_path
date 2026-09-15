# Observability: structured logs and error tracking

Authoritative description of runtime observability for the backend (bot, FastAPI API, jobs,
Cloud Tasks workers, payments, broadcasts, Admin and the Candidate pipeline). Introduced by
[#18](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/18).

Out of scope here: product analytics ([#29](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/29)),
performance work ([#32](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/32)),
the Admin system-health view ([#38](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/38)),
the release process itself ([release-checklist.md](release-checklist.md), #49) and
frontend/Mini App error tracking (no browser SDK, no Session Replay).

## Release and build identity

Observability consumes the release model of [`services/version.py`](../services/version.py)
without redefining it (the policy lives in
[release-checklist.md § Canonical version source](release-checklist.md#2-canonical-version-source)):

| Field | Source | Where it appears |
| --- | --- | --- |
| `release` | `SENTRY_RELEASE` if set, otherwise the formal version `services.version.get_version()` (`VERSION`) | Sentry event `release`; `release` in every log record |
| `revision` | `services.version.get_build_revision()` (Cloud Run `K_REVISION`); absent outside Cloud Run | Sentry tag `revision`; `revision` in every log record on Cloud Run |

The two are never substituted for each other: `K_REVISION` is not used as a release, and
no revision is invented locally. Because continuous deployment ships untagged builds between
releases, several revisions can share one `release`; `revision` identifies the exact build.

## Architecture

Everything lives in [`services/observability.py`](../services/observability.py); handlers
never configure Sentry or log formatters themselves.

| Piece | What it does |
| --- | --- |
| `init(service, web=...)` | Idempotent. Configures the root log handler and, only if `SENTRY_DSN` is set, the Sentry SDK. Called by `bot.py` (`service="bot"`, `web=True`) and `admin_ui.py` (`service="admin"`). |
| `bind(**fields)` | Adds fields to a `ContextVar` for a block. Every log record emitted inside carries them, including work moved to threads (`asyncio.to_thread`, `run_in_threadpool` copy the context). |
| `log_event(event, level, exc_info=..., **fields)` | One structured record whose message is a stable event name. |
| `operation(name, component=..., retryable=...)` | Times a meaningful operation (monotonic clock) and emits `<name>.completed`, `<name>.retry` or `<name>.failed`. Exceptions are always re-raised unchanged. |
| `sanitize()` / `scrub_text()` | Redaction on copies (see [Redaction policy](#redaction-policy)). |
| `user_ref(user_id)` | Pseudonymous user reference (HMAC-SHA256 keyed with `OBSERVABILITY_USER_SALT`, 16 hex chars), or `None` when no salt is configured. |

**One path to Sentry.** Sentry's logging integration turns records at `ERROR` or above into
Sentry events; `WARNING`/`INFO` records become breadcrumbs only. `before_send` adds the
bound context as tags and sanitises the whole event. When a failure has been logged at
`ERROR`, the exception is marked as reported: the HTTP middleware, the Telegram error
handler and enclosing `operation()` blocks then write their own record at `WARNING` without
the exception, so one failure is
one Sentry event (Sentry's deduplication is a second safety net).

**Failure isolation.** A missing or malformed DSN, an SDK initialisation error or a
formatter error never stops the application; `log_event` never raises. If sanitising a
Sentry event fails, the event is dropped rather than sent unsanitised.

## Configuration

All variables are optional. Local development and tests need none of them.

| Variable | Default | Meaning |
| --- | --- | --- |
| `SENTRY_DSN` | empty | Enables Sentry. Without it the SDK is never initialised and no network call is made. Treat it as a secret (store it in Secret Manager on Cloud Run). |
| `SENTRY_ENVIRONMENT` | `production` when `K_SERVICE` is set (Cloud Run), otherwise `development` | Sentry environment and the `environment` log field. |
| `SENTRY_RELEASE` | the formal version from `VERSION` | Explicit override of the Sentry `release` and the `release` log field. Normally leave it unset (see [Release and build identity](#release-and-build-identity)). |
| `LOG_FORMAT` | `json` on Cloud Run, `text` elsewhere | `json` or `text`. |
| `LOG_LEVEL` | `INFO` | Root log level. |
| `OBSERVABILITY_USER_SALT` | empty | Optional secret key for `user_ref`. Absent or blank: observability works normally but records carry **no** `user_ref` (per-user correlation disabled); there is no built-in fallback key and raw ids are never used instead. If set: a strong random value (≥ 32 characters, e.g. `python -c "import secrets; print(secrets.token_urlsafe(32))"`), stored as a Cloud Run secret/env value, never committed or logged. Rotating it breaks correlation with older records. |

`python -m tools.check_environment` reports `SENTRY_DSN` as INFO when absent, PASS when it
looks like a DSN and WARN when malformed, and `OBSERVABILITY_USER_SALT` as INFO when absent,
WARN when shorter than 32 characters and PASS otherwise. Values are never printed, and a
missing value never fails the check.

To enable Sentry on the Cloud Run service (one-time, outside the repository), store the DSN
in Secret Manager (the runtime service account needs `roles/secretmanager.secretAccessor`
on it) and add it without touching the other variables, which survive deploys
([deploy.md](deploy.md)):

```bash
gcloud run services update guess-the-player --project guess-the-player-from-path-bot --region europe-west1 --update-secrets SENTRY_DSN=sentry-dsn:latest,OBSERVABILITY_USER_SALT=observability-user-salt:latest
```

## Local and production behaviour

- **Local** (`make api`, tests, `make admin`): readable lines such as
  `INFO gtp.payment: payment.refunded [environment=... component=payment charge_id=...]`.
  Sentry stays off unless you put a DSN in `.env`.
- **Cloud Run**: one JSON object per line on stdout. Cloud Logging maps `severity` and
  `message` natively and exposes the other keys under `jsonPayload`. `uvicorn` runs with
  `log_config=None` so its own messages use the same format, and without access logs
  (Cloud Run already records every request; API and worker requests also get
  `api.request.completed`).
- `httpx` is raised to `WARNING`: at `INFO` it logs full URLs, and Telegram API URLs contain
  the bot token.

JSON record example:

```json
{"severity": "ERROR", "message": "payment.delivery.failed", "time": "2026-09-14T20:49:56+00:00",
 "logger": "gtp.payment", "service": "bot", "environment": "production", "release": "0.1.0",
 "revision": "guess-the-player-00042-abc",
 "component": "payment", "request_id": "5f0c…", "task_name": "projects/…/tasks/…",
 "update_id": 812345, "update_type": "successful_payment", "event": "payment.delivery.failed",
 "status": "failed", "item_id": "neon", "charge_id": "…", "amount": 25, "duration_ms": 41.7,
 "error_type": "RuntimeError", "exception": "Traceback …"}
```

## Field vocabulary

Not every record has every field. Fields in **bold** are also Sentry tags; everything bound is
also attached to the Sentry event as the sanitised `observability` context.

| Field | Meaning |
| --- | --- |
| `service`, `environment`, `release` | Process identity (always present); `release` is the formal version. |
| **`revision`** | Exact Cloud Run build (`K_REVISION`); only on Cloud Run. |
| **`event`** | Stable event name (see [Event catalogue](#event-catalogue)). |
| **`component`** | Subsystem: `telegram`, `api`, `job`, `admin`, `ingestion`, `payment`, `broadcast`. |
| **`route`**, **`method`**, `status_code` | FastAPI route template (`/app/api/shop`, never the raw path with ids), HTTP method and status. |
| **`request_id`** | Server-generated correlation id per HTTP request. |
| **`task_name`**, **`task_retry_count`**, `task_execution_count`, `task_queue` | Cloud Tasks metadata from `X-CloudTasks-*` headers. |
| `trace_id` | Trace id from `X-Cloud-Trace-Context`, to jump to the Cloud Run request log. |
| **`update_type`**, **`command`**, **`handler`**, `update_id`, `chat_type` | Telegram context: update kind, command name or callback prefix (never message text or arguments), handler name. |
| **`job`**, **`operation`**, **`status`**, `duration_ms` | Job name, operation name, final status (`completed`, `retry`, `failed`, …) and monotonic duration. |
| **`source`**, `candidate_id`, `actor_ref` | Candidate pipeline: source name (`wikipedia`, `wikidata`), candidate id, pseudonymous admin reference. |
| `user_ref` | Pseudonymous user reference, only when `OBSERVABILITY_USER_SALT` is set; never a Sentry user. |
| `item_id`, `amount`, `charge_id`, `reason`, `outcome` | Payment context: internal product id, Stars amount, Telegram charge id (already the operational reference for `/admin_refund` and purchase history), refusal reason, delivery outcome. |
| `error_type` | Exception class name. |

## Event catalogue

| Event | Level | Where |
| --- | --- | --- |
| `api.request.completed` | INFO (WARNING for 5xx) | Every `/app/api/*`, `/internal/*` and `/webhook` request: route, status, duration. |
| `api.request.failed` | ERROR (WARNING if already reported) | Unhandled exception in a request. |
| `telegram.update.failed` | ERROR (WARNING if already reported) | PTB error handler. |
| `telegram.update.uncertain` | ERROR | Interrupted update (receipt `uncertain`), needs manual reconciliation; admins are also messaged. |
| `admin.command.unauthorized` | WARNING | Non-admin tried an `/admin_*` command. |
| `admin.action.failed` | ERROR | Unexpected exception in a Streamlit Admin action (domain refusals are not reported). |
| `daily.job.completed` / `daily.job.failed` | INFO / ERROR | `/internal/daily-job`: `day`, `resumed`, `generated_days`, `event_created`, `monthly`. |
| `broadcast.batch.completed` / `.retry` / `.failed` | INFO / WARNING→ERROR / ERROR | One broadcast page: `sent`, `errors`, `has_next_page`. `.retry` escalates to ERROR once `task_retry_count` ≥ 5. |
| `broadcast.delivery.failed` | WARNING | One notification failed (page will be retried). |
| `broadcast.delivery.uncertain` | ERROR | A notification may or may not have been delivered; not retried. |
| `broadcast.completed` | INFO | Last page sent: `sent_total`. |
| `monthly.close.batch.completed` / `.failed` | INFO / ERROR | One monthly-closure page: `processed`. |
| `cloud_task.enqueue.failed` | ERROR | Creating a Cloud Task failed (`task_path`, `queue_kind`; never the payload). |
| `payment.invoice.created` / `payment.invoice.refused` | INFO | Mini App invoice link created, or refused for a business reason. |
| `payment.precheckout.accepted` / `payment.precheckout.rejected` | INFO (WARNING for `invalid_payload`) | Pre-checkout decision and reason. |
| `payment.delivery.completed` / `payment.delivery.failed` | INFO / ERROR | `successful_payment` delivery; `outcome` is `delivered` or `duplicate`; `failed` also for an unknown item (Stars taken, nothing delivered). |
| `payment.refunded` / `payment.refund.rejected` | INFO / WARNING | `/admin_refund` result. |
| `candidate.approved`, `candidate.validation.failed`, `candidate.review.completed` | INFO / WARNING | One record per review action (`operation`, `status`, `error_count`, `duration_ms`). |
| `candidate.review.denied` / `candidate.review.failed` | WARNING / ERROR | Auth/stale refusal, or an unexpected exception in a review action. |
| `candidate.ingestion.source_failed` | ERROR | Source adapter raised during `retry_ingestion`. |
| `candidate.dataset.unreadable` | ERROR | Production dataset missing, corrupt or malformed during a mutation. |
| `candidate.approval.persistence_failed` / `.rolled_back` / `.rollback_failed` | ERROR / WARNING / CRITICAL | Approval write path. |

Existing plain `logging.exception(...)` calls (for example inside `/admin_*` commands or
`/forgetme`) still reach Sentry through the logging integration and carry the bound context
(`component=admin`, `handler=...`), just without an `event` tag.

Adding an event: pick `<domain>.<object>.<outcome>`, keep names stable (they are query keys),
log expected refusals at INFO/WARNING and only operator-actionable failures at ERROR, and
never pass raw payloads.

## Correlation

- **HTTP**: the middleware in `bot.py` generates `request_id` (uuid4) for every request and
  returns it as `X-Request-ID`. A client-supplied `X-Request-ID` is ignored. Cloud Tasks and
  trace headers are recorded for correlation only and are never used for authorisation
  (internal endpoints are still protected by `X-Task-Secret` / `x-cron-secret`).
- **Telegram updates**: the worker binds `update_id`, `update_type`, `command` and the
  component (`payment` for pre-checkout, successful payments and `/admin_refund`,
  `admin` for `/admin_*`), on top of the request's `request_id` and `task_name`.
- **Jobs**: `task_name` plus the business key (`day`) correlate a broadcast or monthly
  closure across its pages.

## Redaction policy

Applied to structured log fields, log messages and tracebacks, and to every Sentry event and
breadcrumb. It works on copies; application payloads are never mutated.

- **Sensitive keys** (case-insensitive, `-`/`_` ignored) are replaced by `[REDACTED]` at any
  depth: anything containing `token`, `secret`, `password`, `passwd`, `authorization`,
  `cookie`, `initdata`, `dsn`, `credential`, `apikey`, `privatekey`, `signature`,
  `invoicepayload`, `sessionid`, `salt`, and the exact keys `hash` and `auth`. This covers
  `initData`/`init_data`, `X-Task-Secret`, `x-cron-secret`,
  `X-Telegram-Bot-Api-Secret-Token`, `telegram_bot_token`, `webhook_secret`,
  `task_secret`, `generation_secret` and `sentry_dsn`.
- **Free text** is scrubbed of: Telegram bot tokens (also inside API URLs), credentials in
  URLs (including DSN keys), `Bearer` tokens, `hash=`/`signature=`/`token=`/`secret=` query
  values, whole Telegram `initData` strings, the user name in home-directory paths, and the
  literal values of `BOT_TOKEN`, `WEBHOOK_SECRET`, `TASK_SECRET`, `GENERATION_SECRET`,
  `SENTRY_DSN` and `OBSERVABILITY_USER_SALT`.
- **Never logged by design**: request bodies, Telegram message text and command arguments,
  answers typed by players (guess logs record only the length), invoice payloads (they carry
  a signature), Cloud Task payloads, full Candidate objects or provider payloads, dataset
  contents.
- **User references** exist only with a secret salt; without one there is no per-user field at
  all (no public default key, no unkeyed hash, no raw id).
- Values are truncated at 2000 characters and nesting at 12 levels.

## Sentry privacy configuration

`send_default_pii=False`, `include_local_variables=False` (frame locals could hold tokens or
user documents), `max_request_body_size="never"`, no tracing or profiling
(`traces_sample_rate=None`), `auto_enabling_integrations=False` (for example the httpx
integration would record Telegram URLs with the bot token). Enabled integrations: logging
(`INFO` breadcrumbs, `ERROR` events) and, for the bot, Starlette/FastAPI with
`failed_request_status_codes` empty, so only unhandled exceptions are captured: a deliberate
`503` for an update in progress, `401`/`403`/`404`/`409`/`429` are not errors. `before_send`
removes `user`, request `data`, `cookies` and `env`, and sanitises the rest (including
request headers). No user is ever set on the scope.

## Finding errors and logs

Cloud Logging (Logs Explorer, Cloud Run service):

```text
jsonPayload.event="payment.delivery.failed"
jsonPayload.component="payment" AND severity>=WARNING
jsonPayload.request_id="5f0c…"
jsonPayload.event="broadcast.batch.retry" AND jsonPayload.day="2026-09-14"
jsonPayload.event="api.request.completed" AND jsonPayload.duration_ms>1000
```

Sentry: filter issues by the tags `component`, `event`, `route`, `job`, `command`,
`revision` (exact build) and by environment/release (formal version); the `observability` context holds the remaining sanitised fields, and
`request_id` links an issue back to Cloud Logging.

The alerts recommended in [runtime-hardening.md](runtime-hardening.md) can be written as
log-based alerts on `telegram.update.uncertain`, `broadcast.delivery.uncertain`,
`cloud_task.enqueue.failed` and `severity>=ERROR`. Alert policies live in GCP/Sentry, not in
this repository.

## Tests

- [`tests/test_observability.py`](../tests/test_observability.py): record shape, context,
  redaction (nested keys, `initData`, Authorization/cookies, tokens in text), no-DSN
  behaviour, idempotent init, privacy options, Sentry tags/context through the real SDK with
  an in-memory transport (no network), API 500 vs expected 4xx/503, Telegram, jobs and retry
  escalation, Cloud Tasks, Candidate, payments and Admin; release (`VERSION`, `SENTRY_RELEASE`
  override) vs `revision` in logs and Sentry; `GET /` keeping `version`/`revision` next to
  the request middleware; `user_ref` only with a salt, and the salt never in logs or events.
- [`tests/test_internal_daily_job.py`](../tests/test_internal_daily_job.py): the
  `x-cron-secret` boundary of `POST /internal/daily-job` (missing, wrong, correct, fail
  closed without `GENERATION_SECRET`).

## Known limitations

- No performance tracing or metrics: `duration_ms` fields and `Server-Timing` only (#32).
- No alert policies or dashboards are defined in the repository.
- Many older plain log lines (`[ADMIN]`, `[SHOP]`, `[LEAGUE]`, …) still include raw Telegram
  user ids and are not event-named; they are formatted, context-enriched and scrubbed, but
  were not rewritten wholesale.
- Sentry stack frames include source-code context lines of the application code.
- Without `OBSERVABILITY_USER_SALT` there is no per-user correlation in logs or Sentry.
- The Streamlit Admin runs on an operator's machine: its events only reach Sentry if that
  machine's `.env` has a DSN, and it reports `environment=development` unless
  `SENTRY_ENVIRONMENT` is set.
- Offline scripts (`scripts/`) and the Mini App frontend are not instrumented.
