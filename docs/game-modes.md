# Game modes: Daily, Archive, Training, Arena, Events

Authoritative **architectural** description of how game modes are created, stored and
played. Player-facing rules and wording live in the root [README](../README.md); the
difficulty formula lives in [difficolta.md](difficolta.md); Firestore collections are
mapped in [firestore.md](firestore.md). Everything here was verified against `main`.

## Shared building blocks

| Concern | Implementation | Used by |
| --- | --- | --- |
| Answer matching (accents, typos, ambiguous names) | [`services/matching.py`](../services/matching.py) | every mode |
| Wrong-guess comparison (nationality, role, age) | [`services/guess_feedback.py`](../services/guess_feedback.py) | Daily, Archive, Training, duels, `path`/`transfer_guess` events |
| Difficulty and points per difficulty | [`services/difficulty.py`](../services/difficulty.py) + `data/config.json` | Daily, events |
| Player pool loading, filters, blocked players | [`services/player_pool.py`](../services/player_pool.py), `admin_settings/dataset_overrides` | generators, practice content |
| Practice material (reserved `practice_only` pool + past days) | [`services/practice_content.py`](../services/practice_content.py), [`services/past_challenges.py`](../services/past_challenges.py) | Training, duels, group rounds |
| Localized career rendering | [`services/content_i18n.py`](../services/content_i18n.py), [`services/path_image.py`](../services/path_image.py) (chat PNG) | bot and Mini App |

Every “one attempt at a time” rule that can be retried (first-solver bonus, Mini App
moves, event attempts, purchases) is enforced with Firestore transactions and, for
Mini App moves, a client-supplied `revision` checked server-side. Retried Telegram
updates are deduplicated by work receipts ([runtime-hardening.md](runtime-hardening.md)).

## Daily challenge

**Current state.**

1. **Content creation.** `services/daily_generator.py::ensure_daily_buffer` writes
   missing `daily_path/{YYYY-MM-DD}` documents for the next `buffer_days_ahead` days
   (`data/config.json`, currently 3). Selection uses only verified, non-blocked,
   non-`practice_only` players with at least `min_teams_in_career` clubs, excludes players
   used in the last `history_days_no_repeat` days (falling back to repeats, with a
   warning, if the pool is exhausted), follows `difficulty_rotation` with nearest-band
   fallback, and seeds the RNG with the date so a rerun picks the same player for the
   same day.
2. **Triggers.** The nightly Cloud Scheduler call to `/internal/daily-job`
   ([`handlers/daily_job.py`](../handlers/daily_job.py)) runs the buffer; `/admin_regen`
   and `scripts/generate_content.py` run it on demand; if today's document is still
   missing, `services/daily_challenge.py::get_today_challenge` generates it on first use.
3. **Serving.** `services/daily_challenge.py` caches only the immutable part of today's
   challenge per process; mutable state (first-solver bonus) is always read from
   Firestore.
4. **Playing.** [`services/game.py`](../services/game.py) owns the rules for chat
   (`handlers/guess_handler.py`, free text in private chat) and Mini App
   (`/app/api/guess`, `/app/api/hint`): `MAX_ATTEMPTS = 3`, points from difficulty,
   first-correct bonus claimed in a transaction, hints (`services/hints.py`) reduce
   points, streaks (`services/streak.py`). The answer (`correct_answers`, `player_id`) is
   never serialized to the Mini App.
5. **Per-user state.** Counters on `users/{id}` are anchored to `last_played_day`, so
   there is no nightly reset; the result of a finished day is written once to
   `users/{id}/history/{day}`; `daily_path/{day}` keeps `players_count`/`solved_count`.
6. **Nightly side effects.** Broadcast to subscribed users, event trophies, and on the
   first of the month the season close ([operations.md](operations.md)).

**Admin/manual boundary.** The Admin “Sfide giornaliere” page and
`services/content_admin.py` can replace the player of a day, regenerate, edit accepted
answers/difficulty, reopen the bonus, delete or schedule a challenge on any date; rules
such as “today's challenge cannot be deleted” live in the service, not the UI.

**Planned evolution.** There is no long-horizon planner: the automatic 30–90-day Daily
planner is [#30](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/30)
(open). Admin Daily management beyond the current page is
[#34](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/34); a
data-driven difficulty model is
[#21](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/21).

## Archive

**Current state.** Past `daily_path` documents are replayable without points.
Chat: `handlers/archive_handler.py` (`/archive`, session tracked on the user as
`archive_day`). Mini App: `/app/api/calendar` builds a calendar
(`services/webapp_api.py::build_calendar`, `CALENDAR_DAYS = 30`) from
`users/{id}/history` and serves one day; guesses go through `/app/api/guess` with `day`
(`services/game.py::play_archive`). Old or unusable `daily_path` documents are removed
only manually with `scripts/cleanup_daily_paths.py`.

## Training

**Current state.** No points; material comes from `services/practice_content.py`
(reserved pool plus past challenges). Chat: `handlers/training_handler.py`. Mini App:
`/app/api/arena` with `mode: "training"` → `services/arena.py::training`, session stored
on the user document and revision-checked per move. The chat and Mini App sessions are
independent.

## Arena duels

**Current state.** Mini App only: `/app/api/arena` with `mode: "duel"` →
`services/arena.py::duel` / `list_duels`. A duel document in `app_duels/{code}` holds two
seats and five immutable puzzles (three attempts each), expires after seven days and is
updated transactionally. Finished results are copied to each profile
(`app_duel_record`, `app_duel_matches`). Invites are `t.me/<bot>?start=duel_<code>` links
and require `BOT_USERNAME` and `PUBLIC_BASE_URL`; nothing is sent to friends
automatically. Duels do not affect the global leaderboard.

## Group rounds

**Current state.** Chat only, in Telegram groups: `handlers/group_handler.py`
(`/round`, `/standings`) with `group_rounds/{chat_id}` and its `players` subcollection.
Points stay inside the group. Rules still live in the handler plus
`services/repos/groups.py`.

## Events

**Current state.**

- **Definition.** Event types are templates in
  [`data/event_templates.json`](../data/event_templates.json) (`path`, `career`,
  `transfer_guess`, `father_son`) with pool filters, duration, points and translated
  name/description; tuning keys (`event_min_gap_days`,
  `event_history_no_repeat_templates`, `event_default_duration_days`) are in
  `data/config.json`.
- **Generation.** `services/event_generator.py::maybe_generate_event`, called by the
  nightly job, rotates templates not used recently, respects the minimum gap and
  `weekend_only`, and writes an `events/{code}` document with per-day `daily_data`.
  Translated `name_i18n`/`description_i18n` are copied onto the event at generation time
  (Italian `name`/`description` stay as fallback), so a running event does not change if
  the template does; `tests/test_event_translations.py` fails if a template lacks
  translations. `career` events never store a career image, to avoid revealing the answer.
- **Manual events.** Templates marked `manual_only` (father/son pairs, which need a
  photo) are never generated automatically; admins create them with `/admin_fs_add` +
  `/admin_event_create` or from the Admin “Eventi” page
  (`services/manual_event_service.py`). `/admin_event_create` can also force any
  template to start on a chosen date.
- **Playing.** Answer evaluation is shared (`services/event_rules.py`). Chat:
  `handlers/events_handler.py`. Mini App: `/app/api/arena` with `mode: "events"` →
  `services/app_events.py` (transactional, revision-checked). Participants are
  `events/{code}/participants/{user_id}` documents; trophies are assigned by the
  nightly job the day after an event ends.

**Planned evolution.** Fully data-driven, automatable event configuration and
scheduling is [#31](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/31)
(open). Today scheduling is template rotation plus manual creation; the Mini App does
not change event scheduling.

## Leaderboards, seasons and leagues

**Current state.** Global and monthly leaderboards are ordered queries with `limit`
plus a `count()` for the caller's position (`services/repos/users.py`). Monthly seasons
are closed in pages by `services/monthly_closure.py` (podium frozen in
`monthly_closures/{YYYY-MM}` before counters are reset). Private leagues
(`services/leagues.py`, limits as constants there; `leagues/{code}/members`) are shared
by `/league_*` commands and `/app/api/league`.

## Referral

**Current state.** `services/referrals.py`: invite attribution via the `/start` payload,
qualification counted only from server-recorded daily finishes (`REQUIRED_DAYS`),
cosmetic rewards at fixed thresholds, stored in `referrals/{key}`; Mini App dashboard at
`/app/api/referrals` (higher rate-limit cost).
