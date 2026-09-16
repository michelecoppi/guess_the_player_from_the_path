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
  with backups), `services/candidate_review.py` (Review Queue), plus the same
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
| 📊 Stato generale (`overview.py`) | Today's challenge with solution, buffer coverage, current event, dataset health, users | Generate missing challenges/events |
| 📅 Sfide giornaliere (`challenges.py`) | Every day in a window including gaps, solution, difficulty, career, origin, bonus state, image preview | Replace player, regenerate, accepted answers, difficulty, bonus, delete, schedule on a date |
| 🎊 Eventi (`events.py`) | Status, per-day content, missing days, participants ranking | Activate/deactivate, move dates, answers, bonus, delete, create manual event |
| 👤 Utenti (`users.py`) | Leaderboards, search, full user sheet | Points, streak, language, notifications, reset today's attempts |
| 🏆 Leghe (`leagues.py`) | Leagues, members, rankings | — |
| 📚 Dataset (`dataset.py`) | Health, full player list with difficulty breakdown, single player (0-100 score), tuning, predicted vs observed difficulty per closed Daily ([difficolta.md §6](difficolta.md)) | Popularity, verified, practice-only, career-stop league, difficulty weights (with preview of band changes) |
| 🔎 Review giocatori (`player_review.py`) | Candidate queue with filters, validation findings, provenance/conflicts, duplicates, history | Edit, approve, reject, merge, mark source wrong, retry ingestion (see [player-data-pipeline.md](player-data-pipeline.md)) |
| 🚫 Giocatori sospesi (`blocked.py`) | Blocked players | Block / unblock |
| 👨‍👦 Coppie padre/figlio (`father_son.py`) | Saved pairs and their use | Delete (photos are added via the bot) |

## Planned evolution

Epic [#12](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/12) is
open. Done: [#35](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/35)
(Review Queue integration). Still open, and **not** implied by the table above:

- [#33](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/33) — dashboard overview and live metrics
- [#34](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/34) — Daily Challenge management
- [#36](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/36) — users, groups and leagues management
- [#37](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/37) — shop and referral management
- [#38](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/38) — system health, logs and backup
- [#39](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/39) — analytics view (no product analytics exist yet; see [#29](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/29))

Related but separate: [#25](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/25)
Dataset Health dashboard (Area `Data`).
