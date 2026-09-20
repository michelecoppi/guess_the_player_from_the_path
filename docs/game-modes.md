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
   (`data/config.json`). Player selection is owned by the Daily planner
   ([`services/daily_planner.py`](../services/daily_planner.py), see
   [Daily planner](#daily-planner)); the buffer only fills gaps and never touches an
   existing day.
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
   `users/{id}/history/{day}`; `daily_path/{day}` keeps `players_count`/`solved_count` and,
   for solvers, `solved_attempts_total`/`solved_hints_total` (observed difficulty,
   [difficolta.md §6](difficolta.md)).
6. **Nightly side effects.** Broadcast to subscribed users, event trophies, and on the
   first of the month the season close ([operations.md](operations.md)).

**Admin/manual boundary.** The Admin “Sfide giornaliere” page and
`services/content_admin.py` can replace the player of a day, regenerate, edit accepted
answers/difficulty, reopen the bonus, delete or schedule a challenge on any date; rules
such as “today's challenge cannot be deleted” live in the service, not the UI.

Every generated or manually set Daily carries a `difficulty_prediction` snapshot that the
Admin compares with observed results
([#21](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/21),
[difficolta.md §6](difficolta.md)).

**Planned evolution.** Admin Daily management beyond the current pages is
[#34](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/34).

### Daily planner

**Current state** ([#30](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/30)).
One module chooses every automatic Daily player: the nightly buffer, `/admin_regen`,
`get_today_challenge`, the “Rigenera” button (`content_admin.regenerate_daily`) and the
Admin “🗓️ Planner sfide” page, which proposes a 7–90-day calendar, lets the admin review it
and writes it only on *Applica*.

Rules, in priority order (parameters in `data/config.json`):

| Rule | Parameter |
| --- | --- |
| Eligible: verified, complete, non-`practice_only`, not blocked (`/admin_block`), not excluded from the planner | `admin_settings/daily_planner.excluded` (reason, optional `until` day) |
| No player repeated within N days **before or after** the day (future fixed days count) | `history_days_no_repeat` |
| Band from the rotation (by day of year), at most N consecutive days in the same band | `difficulty_rotation`, `daily_planner.max_same_band_streak` |
| No shared club / nationality with the neighbouring days | `daily_planner.club_cooldown_days`, `daily_planner.nationality_cooldown_days` |

Among the valid candidates the planner prefers players not present anywhere in the read
window, then picks with an RNG seeded by `day|variant`: the same state gives the same
calendar, and “another player” changes the variant, not the randomness. When the rules
cannot all hold, it relaxes them in this order instead of leaving a hole: nationality and
club, then band, then the band streak, and last the player repetition. Every relaxation is
recorded.

**Modes.** *Fill* creates only missing days. *Replan* also replaces future days that are
not locked and were not chosen by hand (`source: "manual"`). Today and past days are never
replaced, and a past day without a Daily is reported, not created. Days that will be
replaced do not constrain their neighbours.

**Audit.** Every planned Daily stores `planner_audit`: target band, chosen band, relaxed
rules, the candidate funnel (pool → not excluded → not repeated → no shared club → other
nationality → final candidates), variant, mode and `planned_at`. The Admin shows it per day
in the planner and in “Sfide giornaliere”.

**Review controls.** Per proposed day: another player (preview only), exclude the player
(with reason and expiry, then recompute); per existing future day: lock/unlock. *Applica*
re-reads each day just before writing and skips it if it was locked, created or changed
since the preview.

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

- **Definition.** Every event is a template in
  [`data/event_templates.json`](../data/event_templates.json) (schema v2): type, pool
  `filters`, game `rules` (attempts, `career` ratio), `rewards` (points per day,
  first-solver bonus, podium trophies), `schedule` and translated name/description.
  Schema, validation and examples: [event-templates.md](event-templates.md)
  ([#31](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/31)). Type
  behaviour is a registry in `services/event_config.py` (`EVENT_TYPES`), not branches per
  handler. Rotation tuning keys (`event_min_gap_days`, `event_history_no_repeat_templates`)
  are in `data/config.json`.
- **Validation.** `scripts/dataset_report.py --strict` (CI) and
  `tests/test_event_config.py` reject an invalid template file; at runtime an invalid
  template is skipped and logged, never fatal.
- **Generation.** `services/event_generator.py::maybe_generate_event`, called by the
  nightly job, first creates `fixed`-schedule events up to 7 days ahead (no minimum gap;
  skipped with an error if they would overlap an existing event), then, only when no event
  is active, rotates `rotation` templates that are allowed today (`start_weekdays`,
  recurring `window`), not used recently, past the minimum gap and not overlapping an
  upcoming fixed event. It writes `events/{code}` with per-day `daily_data` and copies
  texts, translations, `rules` and `rewards` onto the event, so a running event does not
  change if the template does. `career` events never store a career image, to avoid
  revealing the answer.
- **Manual events.** `manual`-schedule templates (father/son pairs, which need a photo)
  are never generated automatically; admins create them with `/admin_fs_add` +
  `/admin_event_create` or from the Admin “Eventi” page
  (`services/manual_event_service.py`). `/admin_event_create` can also force any
  template to start on a chosen date. Templates are created and edited, with validation,
  preview and backup, in Admin “Eventi → Template eventi”.
- **Playing.** Answer evaluation is shared (`services/event_rules.py`). Chat:
  `handlers/events_handler.py`. Mini App: `/app/api/arena` with `mode: "events"` →
  `services/app_events.py` (transactional, revision-checked; the card exposes
  `max_attempts`). Attempts and the first-solver bonus come from the event's `rules` and
  `rewards` (defaults 3 and +1 for events created before #31). Participants are
  `events/{code}/participants/{user_id}` documents; trophies for the top
  `rewards.podium_trophies` positions are assigned by the nightly job the day after an
  event ends.

**Planned evolution.** None tracked for event configuration; new filters, rules or event
types still need code (a filter in `player_pool.filter_players` and `event_config.FILTERS`,
a type in `EVENT_TYPES` plus its chat/Mini App rendering).

## Leaderboards, seasons and leagues

**Current state.** Global and monthly leaderboards are ordered queries with `limit`
plus a `count()` for the caller's position (`services/repos/users.py`). Monthly seasons
are closed in pages by `services/monthly_closure.py` (podium frozen in
`monthly_closures/{YYYY-MM}` before counters are reset). Private leagues
(`services/leagues.py`, limits as constants there; `leagues/{code}/members`) are shared
by `/league_*` commands and `/app/api/league`.

## Referral

**Current state.** `domains/referrals/service.py`: invite attribution via the `/start` payload,
qualification counted only from server-recorded daily finishes (`REQUIRED_DAYS`),
cosmetic rewards at fixed thresholds, stored in `referrals/{key}`; Mini App dashboard at
`/app/api/referrals` (higher rate-limit cost).

## Offline streak balance comparison (#123)

`python -m tools.streak_simulation --demo` replays a synthetic 30-day Daily calendar
under the current daily-tier bonus and a proposed one-off bonus at days 3, 7 and 30.
`--input path/to/normalized.json` instead reads a local normalized history. Neither
mode reads Firestore, calls external services or changes live scoring. Output defaults
to Markdown; `--format json` produces structured results with a `synthetic` flag.

Input shape (anonymous identifiers, one final Daily result per user/day):

```json
{
  "players": [{"id": "player_a", "initial_streak": 2, "last_correct_day": "2026-08-31"}],
  "results": [{"player": "player_a", "day": "2026-09-01", "solved": true,
    "difficulty": "hard", "hints_used": 1, "first_correct": false}]
}
```

For a new streak use `initial_streak: 0` and omit `last_correct_day`. A nonzero
streak requires its last correct date before that player's first input row. The
history must be complete for the selected window: missing dates break continuity,
just like not playing. Input order does not matter; duplicates, unknown difficulty,
ambiguous booleans, inconsistent Daily bands and multiple first winners are rejected.
Results include solves, base plus first-solver points, both streak bonuses, totals,
delta and competition ranks (ties 1, 1, 3). Ranks cover only the supplied period;
they do not include previously earned points or rebuild a production leaderboard.

Historical source limitations matter: user Daily history is not a ready-made input.
Difficulty must come from the Daily snapshot, and the per-result first-solver flag
must be known. `daily_path.first_correct_user` is only a boolean, not the winner's
ID; an aggregate user bonus count cannot reconstruct the winning dates. Do not
invent unknown values or label an approximate reconstruction as exact history.
Use the demo until a complete, appropriately anonymized input is available.

The proposed bonus pays once per uninterrupted streak. A loss or missing date
resets it; on day 31+ there is no recurring bonus. Initial streak continuity is
preserved across the input boundary, so an established player does not receive
old milestones again. Both policies use identical outcomes, hints and first bonuses.
This replay does not predict changes in participation, retention or purchases.
See [the synthetic report](streak-balance-report.md) for the checked example.
