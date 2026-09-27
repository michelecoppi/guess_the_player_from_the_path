# Admin architecture

Authoritative description of the administration surfaces. How to start them locally is
in [local-development.md](local-development.md); the player-facing command list is in
the root [README](../README.md) (“Comandi amministrativi”, “Dashboard locale”).

## Two surfaces, same services

| Surface | Where | Identity / access | Typical use |
| --- | --- | --- | --- |
| Telegram admin commands | [`handlers/admin_handler.py`](../handlers/admin_handler.py) (`/admin_*`), `/admin_refund` in [`handlers/shop_handler.py`](../handlers/shop_handler.py) | Telegram user id must be in `ADMIN_TELEGRAM_IDS`; permission tests in `tests/test_admin_permissions.py` | Status, pool health, next challenges, regenerate buffer, block/unblock players, father/son pairs, manual events, refunds, support replies |
| Admin Control Center (Streamlit) | [`admin_ui.py`](../admin_ui.py) + [`admin_pages/`](../admin_pages/) | Runs only on a maintainer machine; not served by Cloud Run (Streamlit is a dev dependency) and no login. Starts only with `BOT_TOKEN` and an existing `FIREBASE_CREDENTIALS_PATH` file; whoever holds those credentials has database access. The candidate Review Queue additionally requires `ADMIN_TELEGRAM_IDS` and acts as the first configured id | Detailed inspection and corrections that are awkward in chat |

**It writes to whatever Firestore project the credentials point to — normally
production.** Dataset edits and candidate approvals change local `data/*.json` files,
which reach production only through a PR and deploy.

## Boundaries

- The Admin is a UI, **not the owner of domain logic**. Pages call services:
  `services/content_admin.py` (challenge/event rules, e.g. today's challenge cannot be
  deleted, a running event is deactivated rather than deleted, moving an event moves
  its contents and trophy day), `services/dataset_editor.py` (validated dataset edits
  with backups), `domains/players/candidates/review.py` (Review Queue), plus the same
  generators, `firebase_service` and `manual_event_service` used by the bot.
- New Admin features must add or reuse a service function and test it there; the
  Streamlit page should only collect input, confirm, call the service and render the
  result.
- Destructive production operations (deleting challenges/events, editing users,
  approving players) must go through a service that enforces invariants, backups or
  revision checks — never through ad-hoc Firestore or file writes in a page.
- Reads are cached for 45 s (`CACHE_TTL_SECONDS` in `admin_pages/shared.py`); every
  write clears the cache.

## Current capabilities

| Page | Shows | Can change |
| --- | --- | --- |
| 📊 Stato generale (`overview.py`) | Today's challenge with solution, buffer coverage, current event, dataset health and live user metrics | Generate missing challenges/events |
| 🗓️ Planner sfide (`planner.py`) | Proposed 7–90-day calendar with actions, bands, relaxed rules, per-day candidate funnel, planner exclusions | Another player for a day (preview), exclude/readmit players, lock/unlock future days, apply the plan ([game-modes.md](game-modes.md#daily-planner)) |
| 📅 Sfide giornaliere (`challenges.py`) | Every day in a window including gaps, solution, difficulty, career, origin, bonus state, image preview | Replace player, regenerate, accepted answers, difficulty, bonus, delete, schedule on a date |
| 🎊 Eventi (`events.py`) | Status, per-day content (for `link_club` the player pair, for `order_career` the correct club order), missing days, participants ranking; event templates with validity, schedule and candidates | Activate/deactivate, move dates, answers, bonus, delete, create manual event; create/edit a template as JSON with validation, preview and backup ([event-templates.md](event-templates.md)) |
| 👤 Utenti (`users.py`) | Leaderboards, search, full user sheet | Points, streak, language, notifications, reset today's attempts |
| 👥 Gruppi (`groups.py`) | Group search, members and round state | Group moderation actions |
| 🏆 Leghe (`leagues.py`) | Leagues, members, rankings | — |
| 🛍️ Shop & Referral (`shop.py`) | Cosmetic catalogue, referral overview and top inviters | Item price, Italian name and separate-sale lock |
| 📈 Analytics (`analytics.py`) | Core PostHog metrics when configured; metric errors are shown explicitly | — |
| 🩺 Salute sistema (`system.py`) | Sentry configuration, stuck jobs and backup status | — |
| 📚 Dataset (`dataset.py`) | Health, full player list with difficulty breakdown, single player (0-100 score), tuning, predicted vs observed difficulty per closed Daily ([difficolta.md §6](difficolta.md)) | Popularity, verified, practice-only, career-stop league, difficulty weights (with preview of band changes) |
| 🔎 Review giocatori (`player_review.py`) | Candidate queue with filters, validation findings, provenance/conflicts, duplicates, history | Edit, approve, reject, merge, mark source wrong, retry ingestion (see [player-data-pipeline.md](player-data-pipeline.md)) |
| 🔄 Refresh carriera (`career_refresh.py`) | Player career refresh preview and source results | Apply a reviewed refresh |
| 🚫 Giocatori sospesi (`blocked.py`) | Blocked players | Block / unblock |
| 👨‍👦 Coppie padre/figlio (`father_son.py`) | Saved pairs and their use | Delete (photos are added via the bot) |

## Delivery and remaining work

The Admin expansion epic [#12](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/12)
and its sub-issues #33–#39 have been delivered. The table above describes the current pages; consult
[Project #2](https://github.com/users/michelecoppi/projects/2) for live issue status.
Dataset Health ([#25](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/25))
is a related Data area capability shown in the Dataset page. Product analytics
([#29](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/29))
supplies the Admin Analytics page when PostHog is configured.
