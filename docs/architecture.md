# Architecture overview

Authoritative, conceptual map of the system **as it exists on `main`**. It explains
what the components are, where each responsibility lives and which trust boundaries
separate them. Details belong to the focused documents linked from each section; this
file should change only when the architecture changes (see
[agent-protocol.md § Documentation update policy](agent-protocol.md#documentation-update-policy)).

Every section separates **Current state** (verified in code) from **Planned evolution**
(open roadmap issues on [Project #2](https://github.com/users/michelecoppi/projects/2)).
Do not treat a planned item as implemented.

## 1. What the system is

*Guess the Player from the Path* is a Telegram football guessing game: every day players
see the career path (clubs, seasons, appearances) of an unnamed footballer and try to
name them. It is played in the Telegram bot chat and in a Telegram Mini App, with the
same rules, points, leaderboards, events, cosmetics shop (Telegram Stars) and referrals.
Gameplay rules as seen by a player are described in the root [README](../README.md).

## 2. Components

```text
                    Telegram (users, groups, payments)
                      │ webhook               ▲ Bot API calls
                      ▼                       │
┌──────────────────────────── Cloud Run service (one container) ─────────────────────────┐
│ bot.py  — FastAPI app + python-telegram-bot Application (composition root)            │
│   /webhook ──enqueue──► Cloud Tasks ──► /internal/telegram-update ──► handlers/*       │
│   /internal/daily-job  (Cloud Scheduler)   /internal/broadcast, /internal/monthly-close │
│   /app      legacy Mini App (webapp/index.html + *.js)     ← production default        │
│   /app/v2   Mini App V2 (Vite build in webapp/dist)        ← available, not default    │
│   /app/api/* Mini App JSON API (initData-authenticated)                                │
│   /terms, /privacy  static legal pages                                                 │
│                    │                                                                   │
│        handlers/  (Telegram adapters)   services/  (game, content, shop, API builders) │
│                    └──────────────► services/firebase_service.py + services/repos/     │
└────────────────────────────────────────────┬───────────────────────────────────────────┘
                                             ▼
                                   Firebase Firestore (all mutable game state)

Versioned in Git and baked into the image (read-only at runtime):
  data/players.json, data/config.json, data/event_templates.json, data/shop.json

Runs on a maintainer machine (files are copied into the image but never run by the service):
  admin_ui.py + admin_pages/ (Streamlit Admin Control Center)
  scripts/ (imports, reports, backups, migrations, previews)
  Candidate ingestion pipeline (services/candidate_*.py, services/adapters/) → data/candidates/

GitHub Actions: ci.yml (checks) → deploy.yml (Cloud Run) ; backup.yml (weekly Firestore JSON export)
```

| Component | Where it lives | Responsibility |
| --- | --- | --- |
| Composition root | [`bot.py`](../bot.py), [`config.py`](../config.py) | Builds the FastAPI app and the PTB `Application`, registers every Telegram handler, defines all HTTP routes (webhook, workers, Mini App API, static pages) and validates required secrets at startup |
| Telegram handlers | [`handlers/`](../handlers/) | Translate Telegram updates/callbacks into service calls and localized replies; some flows (for example group rounds in `handlers/group_handler.py`) still keep rules here |
| Application services | [`services/`](../services/) | Game rules ([`game.py`](../services/game.py), [`matching.py`](../services/matching.py), [`hints.py`](../services/hints.py), [`streak.py`](../services/streak.py)), content generation, Mini App projections ([`webapp_api.py`](../services/webapp_api.py)), arena/events, shop, trophies, referrals, leagues, i18n, image rendering |
| Persistence | [`services/firebase_service.py`](../services/firebase_service.py) (client, collection names, facade/re-exports) + [`services/repos/`](../services/repos/) (per-area repositories) | All Firestore reads/writes and transactions |
| Durable background work | [`services/task_queue.py`](../services/task_queue.py), [`services/work_receipts.py`](../services/work_receipts.py), [`services/broadcast_store.py`](../services/broadcast_store.py), [`handlers/daily_job.py`](../handlers/daily_job.py), [`services/monthly_closure.py`](../services/monthly_closure.py) | Cloud Tasks enqueueing with deterministic names, per-update receipts/locks, paged broadcast and monthly close |
| Player datasets | [`data/`](../data/) | Curated production players, game tuning, event templates, shop catalogue, dataset regression baseline |
| Candidate ingestion pipeline | `services/candidate_*.py`, [`services/adapters/`](../services/adapters/), [`services/repos/candidates.py`](../services/repos/candidates.py) | External-source acquisition, normalization, validation, provenance and human review before promotion to `data/players.json` |
| Admin Control Center | [`admin_ui.py`](../admin_ui.py), [`admin_pages/`](../admin_pages/) | Local Streamlit UI over the same services; see [admin.md](admin.md) |
| Telegram admin commands | [`handlers/admin_handler.py`](../handlers/admin_handler.py), `/admin_refund` in [`handlers/shop_handler.py`](../handlers/shop_handler.py) | In-chat operations restricted to `ADMIN_TELEGRAM_IDS` |
| Legacy Mini App (`/app`) | `webapp/index.html`, `webapp/client.js`, `webapp/strings.js`, `webapp/arena.*`, `webapp/referrals.*` | Current production Mini App, plain HTML/JS without bundler |
| Mini App V2 (`/app/v2`) | [`webapp/src/`](../webapp/src/), [`vite.config.ts`](../vite.config.ts) | Vite + TypeScript Mini App; see [miniapp.md](miniapp.md) |
| Tooling | [`tools/`](../tools/), [`Makefile`](../Makefile), [`dev.ps1`](../dev.ps1) | Environment validator, dev runner, security audit |
| CI/CD | [`.github/workflows/`](../.github/workflows/) | See [ci_cd_pipeline.md](ci_cd_pipeline.md) and [deploy.md](deploy.md) |

## 3. Composition root and service boundaries

**Current state.**

- `bot.py` is the single process entrypoint (`CMD ["python", "bot.py"]`). It is a
  composition root *and* an HTTP adapter: route functions authenticate, rate-limit and
  delegate, but some small behaviors are still inline (for example the `/app/api/arena`
  mode dispatch and `/app/api/shop/look` delete branch).
- Game rules shared by chat and Mini App live in services — `services/game.py` is used
  by both `handlers/guess_handler.py` and `/app/api/guess`, so there is one scoring
  implementation. The same holds for leagues (`services/leagues.py`) and the shop
  catalogue/prices (`services/shop.py`).
- The code is organized by technical layer (`handlers/`, `services/`, `admin_pages/`),
  not by domain. `services/` is a flat package of several dozen modules; `services/repos/` was
  extracted from `firebase_service.py`, which still re-exports repository functions so
  existing imports and test monkeypatches keep working. Handlers may call
  `firebase_service` directly.
- There is no dependency-injection container; modules import each other and tests
  replace collaborators with in-memory fakes or monkeypatching.

**Planned evolution.** [#28](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/28)
(Horizon: Later) will reorganize the monorepo by domain. Until it lands, follow the
existing layer layout and keep new domain logic in `services/`, not in `bot.py`,
handlers or Admin pages.

## 4. Who reads and writes what

| Component | Reads Firestore | Mutates Firestore | Mutates versioned datasets (`data/*.json`) | Calls external sources | Exposes authenticated API |
| --- | --- | --- | --- | --- | --- |
| Cloud Run service (`bot.py`, handlers, services) | yes | yes | **no** (image is read-only by design; runs as non-root) | Telegram Bot API, Cloud Tasks | `/webhook` (Telegram secret token), `/internal/*` (task/cron secrets), `/app/api/*` (Telegram `initData`) |
| Admin Streamlit (local) | yes | yes, on the project its credentials point to | yes: `data/players.json`, `data/config.json` via `services/dataset_editor.py` and the candidate review service; writes backups to `backup/` | adapters, only on explicit candidate retry | no network API; local UI |
| Candidate pipeline services | no | no | only on explicit approval/merge through `CandidateReviewService`; otherwise writes only `data/candidates/` | Wikipedia, Wikidata | no |
| `scripts/` | depends on script | some (`migrate_firestore.py`, `backfill_users.py`, `cleanup_daily_paths.py`, `generate_content.py`) | `import_players.py`, `reserve_practice_players.py`, `scripts/wikipedia/*` produce/modify datasets | Wikipedia (`scripts/wikipedia/`) | no |
| GitHub Actions | `backup.yml` (read-only role) | no | no | GCP | no |

Consequence: a change to `data/players.json` (import, Admin edit, candidate approval)
reaches production only through a commit → PR → CI → deploy, never by writing a live
container. Firestore-backed switches such as `/admin_block`
(`admin_settings/dataset_overrides`) take effect immediately.

## 5. Main runtime flows

**Telegram update.** Telegram → `POST /webhook` (checks `X-Telegram-Bot-Api-Secret-Token`,
validates `update_id`) → Cloud Tasks queue `TASKS_QUEUE` with a name derived from
`update_id` → `POST /internal/telegram-update` (checks `X-Task-Secret`) →
`work_receipts.claim` (dedupe + per-user serialization) → PTB handler. An interrupted
update becomes `uncertain` and is reported to admins rather than replayed. Details:
[runtime-hardening.md](runtime-hardening.md).

**Mini App request.** Browser inside Telegram → `POST /app/api/<endpoint>` with
`initData` in the JSON body → `services/webapp_auth.py` verifies the HMAC signature and
age → per-process token bucket (`services/rate_limit.py`) → user document read →
service call → explicit JSON projection. The client never sends a user id.

**Nightly job.** Cloud Scheduler → `POST /internal/daily-job` (checks `x-cron-secret`
against `GENERATION_SECRET`) → content buffer, events, trophies, monthly preparation,
immutable broadcast payload in `daily_jobs/{day}` → paged broadcast/monthly-close tasks
on `BROADCAST_QUEUE`. See [game-modes.md](game-modes.md#daily-challenge) and
[operations.md](operations.md).

**Payments.** Invoice (`XTR`, empty provider token) → `PreCheckoutQuery` validated
against the server-side catalogue and current ownership → `successful_payment` delivered
idempotently keyed by the Telegram charge id (`purchases/{charge_id}`). See
[security.md](security.md#telegram-stars-payments).

## 6. Domain areas (where to read more)

| Area | Current implementation | Primary document |
| --- | --- | --- |
| Daily challenge, Archive | `services/daily_generator.py`, `services/daily_challenge.py`, `services/game.py`, `services/past_challenges.py`, `handlers/guess_handler.py`, `handlers/archive_handler.py` | [game-modes.md](game-modes.md) |
| Training, Arena duels, group rounds | `services/arena.py`, `services/practice_content.py`, `handlers/training_handler.py`, `handlers/group_handler.py` | [game-modes.md](game-modes.md) |
| Events | `services/event_generator.py`, `services/event_rules.py`, `services/app_events.py`, `services/manual_event_service.py`, `handlers/events_handler.py` | [game-modes.md](game-modes.md#events) |
| Difficulty | `services/difficulty.py`, `data/config.json` | [difficolta.md](difficolta.md) |
| Leaderboard, seasons, private leagues | `services/repos/users.py`, `services/repos/seasons.py`, `services/leagues.py`, `services/monthly_closure.py`, `handlers/top_users_handler.py`, `handlers/league_handler.py` | [game-modes.md](game-modes.md#leaderboards-seasons-and-leagues) |
| Shop, cosmetics, trophies | `services/shop.py`, `data/shop.json`, `services/trophies.py`, `handlers/shop_handler.py` | README “Negozio”, [miniapp-appearance.md](miniapp-appearance.md) |
| Referral | `services/referrals.py`, `/app/api/referrals` | README “Mini app”, [game-modes.md](game-modes.md#referral) |
| Player data | `data/players.json`, `services/player_pool.py`, candidate pipeline | [player-data-pipeline.md](player-data-pipeline.md) |
| Mini App | `webapp/` | [miniapp.md](miniapp.md) |
| Admin | `admin_ui.py`, `admin_pages/`, `handlers/admin_handler.py` | [admin.md](admin.md) |
| Firestore | `services/firebase_service.py`, `services/repos/` | [firestore.md](firestore.md) |
| Security | cross-cutting | [security.md](security.md) |
| Operations, analytics | cross-cutting | [operations.md](operations.md) |
| Observability (implemented, #18) | `services/observability.py`: structured JSON logs, optional Sentry, request/task correlation, redaction; `release` from `VERSION`, `revision` from Cloud Run | [observability.md](observability.md) |

## 7. Deployment topology (summary)

| Stage | Current state | Primary document |
| --- | --- | --- |
| Build | `gcloud run deploy --source .` builds the [`Dockerfile`](../Dockerfile) with Cloud Build: stage 1 `npm ci && npm run build` (V2 bundle), stage 2 Python 3.11 runtime with `requirements.txt` | [deploy.md](deploy.md) |
| Test | `ci.yml` on every PR and push to `main` | [ci_cd_pipeline.md](ci_cd_pipeline.md) |
| Deploy | `deploy.yml` runs only after a successful CI run on `main`, via Workload Identity Federation, `--max-instances 10` | [deploy.md](deploy.md) |
| Runtime | One Cloud Run service (`europe-west1`), Firestore, two Cloud Tasks queues, one Cloud Scheduler job; env vars/secrets set on the service, not in the workflow | [deploy.md](deploy.md), [runtime-hardening.md](runtime-hardening.md) |
| Rollback | Manual: route traffic to a previous revision or redeploy an earlier commit. No one-command rollback | [release-checklist.md § Rollback](release-checklist.md#10-rollback) |

**Planned evolution.** Versioning, CHANGELOG and a release checklist now exist
([release-checklist.md](release-checklist.md), [#49](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/49));
adoption is opt-in going forward, so this table's "manual, no one-command rollback"
still describes today's default. Backup retention and a *tested* restore procedure
remain [#50](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/50)
(both under epic [#20](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/20)).
A weekly backup export exists today; restore has not been verified.

## 8. Roadmap items that change this picture

| Issue | Topic | Status of the capability today |
| --- | --- | --- |
| [#20](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/20) / [#49](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/49) / [#50](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/50) | Release management, backup recovery | Automated deploy + weekly export exist; no versioning, no tested restore |
| [#21](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/21) | Data-driven difficulty | Rule-based difficulty from popularity + career path |
| [#22](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/22) / [#51](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/51) / [#52](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/52) | Feature flags, experimentation | Not implemented; behavior toggles are env vars (`PUBLIC_BASE_URL`, `BOT_USERNAME`) and Firestore admin overrides |
| [#25](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/25) | Dataset Health dashboard | A health report exists (`services/dataset_health.py`, `/admin_pool`, Admin “Dataset”); the dedicated dashboard does not |
| [#28](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/28) | Domain-oriented monorepo | Layered layout described in §3 |
| [#29](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/29) | Product analytics and funnels | Not implemented |
| [#30](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/30) | Automatic Daily planner | Rolling buffer of `buffer_days_ahead` days only |
| [#31](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/31) | Data-driven, automatable events | Template rotation + manual creation |
| [#32](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/32) | Performance measurement | `Server-Timing` header and `api.request.completed` duration logs only ([observability.md](observability.md)) |
| [#12](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/12) sub-issues #33, #34, #36–#39 | Admin expansion | See [admin.md](admin.md) |
| [#81](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/81) | Final V2 review before switch | `/app` is still the default; see [miniapp.md](miniapp.md) |

The Project board, not this table, is authoritative for status, priority and
dependencies.
