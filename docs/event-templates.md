# Event templates

Authoritative reference for the configuration that defines a themed event
([#31](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/31)). How events
are generated, played and rewarded at runtime is in
[game-modes.md → Events](game-modes.md#events).

A new event is a new entry in [`data/event_templates.json`](../data/event_templates.json), not
new code. The schema and its validation live in
[`services/event_config.py`](../services/event_config.py), which is the only place that decides
what a valid template is. The same validation runs in three places:

| Where | What happens with an invalid template |
| --- | --- |
| CI: `scripts/dataset_report.py --strict` (in `python -m tools.dev dataset-check`) and `tests/test_event_config.py` | the build fails, with one line per error |
| Admin “🎊 Eventi → 📐 Template eventi” (`services/event_template_editor.py`) | it cannot be saved; the page lists the errors |
| Runtime (`event_generator.load_templates`) | the template is skipped and logged as an error; the nightly job keeps running |

## File

```json
{
  "_comment": "…",
  "schema_version": 2,
  "templates": [ { … }, { … } ]
}
```

## Template fields

```json
{
  "id": "leggende_mondiali",
  "name": "Leggende dei Mondiali",
  "description": "Campioni che il pubblico riconosce al volo.",
  "name_i18n": {"es": "Leyendas del Mundial", "en": "World Cup legends"},
  "description_i18n": {"es": "…", "en": "…"},
  "type": "path",
  "category": "stagionale",
  "difficulty": "medium",
  "duration_days": 5,
  "filters": {"min_popularity": 4, "min_teams": 3},
  "rules": {"attempts": 4},
  "rewards": {"points_per_day": 2, "first_correct_bonus": 1, "podium_trophies": 3},
  "schedule": {"mode": "fixed", "start": "2026-06-11"}
}
```

| Field | Required | Meaning |
| --- | --- | --- |
| `id` | yes | 3–40 characters: lowercase letters, digits, `_`. It is part of the event code (`<id>_<YYYYMMDD>`) and of trophy codes, so **it never changes** once events exist: the editor refuses a rename |
| `name`, `description` | yes | Italian text, also the fallback for other languages |
| `name_i18n`, `description_i18n` | yes | One non-empty translation per other supported language (`es`, `en`) |
| `type` | yes | The kind of game, see [Types](#types) |
| `category` | no | Free label for grouping |
| `difficulty` | yes | `easy` / `medium` / `hard` / `impossible` (label only; points come from `rewards`) |
| `duration_days` | yes | 1–30 |
| `filters` | no | Pool filters, see [Filters](#filters). Only for types that draw players from the dataset |
| `rules` | no | Game rules, see [Rules](#rules) |
| `rewards` | no | Points and trophies, see [Rewards](#rewards) |
| `schedule` | yes | When it starts, see [Schedule](#schedule) |

Any other key is an error, so a typo cannot be silently ignored. Schema v1 keys are rejected
with a message that names their v2 replacement: `rules` holding pool filters → `filters`,
`points_per_day` → `rewards.points_per_day`, `min_correct_ratio` →
`rules.min_correct_ratio`, `weekend_only` → `schedule.start_weekdays`, `manual_only` /
`manual_reason` → `schedule: {"mode": "manual", "reason": …}`.

## Types

The behaviour of a type stays in code; a template only chooses one. The table replaces the
`if type == "career"` branches that were spread across the chat handler, the Mini App and
the generator (`EVENT_TYPES` in `services/event_config.py`).

| `type` | Answer | Content | Shown |
| --- | --- | --- | --- |
| `path` | the player (typo-tolerant, with the nationality/role/age comparison after a wrong guess) | dataset | full career path |
| `blind_path` | the player (same matching and comparison as `path`) | dataset | one recent career stop at first; the Mini App reveals up to five distinct stops one at a time |
| `transfer_guess` | the player (with the comparison) | dataset | last career stop only |
| `career` | a comma-separated list of the named player's clubs, at most 5 per attempt | dataset | player name, no path image |
| `father_son` | the father/son pair | photos uploaded with `/admin_fs_add` | the photo; must use `schedule.mode: "manual"` and no `filters` |

`blind_path` (#128) is played in the Mini App. Chat shows a spoiler-free event banner
and a button to open the app; chat guesses are not accepted. The template must set
`rewards.points_per_day` to at least 5. Each reveal reduces the day's available base
points by one, to a minimum of 1. The first-correct bonus, when configured, is added
after that reduction. The server stores the full five-stop puzzle and exposes only the
stops that participant has revealed. A reveal and a guess share a per-day revision so
simultaneous actions cannot spend the same state twice.

## Filters

Applied by `player_pool.filter_players` on the selectable pool (verified, complete,
non-`practice_only`).

| Filter | Value | Keeps players with |
| --- | --- | --- |
| `min_teams` / `max_teams` | integer ≥ 1 | at least / at most N career stops |
| `min_popularity` / `max_popularity` | integer 1–5 | popularity at least / at most N ([difficolta.md](difficolta.md)) |
| `nationality_in` | non-empty list of strings | nationality among these, spelled as in the dataset |
| `leagues_only_top` | `true` | every stop in `top_leagues` |
| `requires_minor_league` | `true` | at least one stop outside `top_leagues` |

Contradictory combinations (`min_teams` > `max_teams`, `leagues_only_top` with
`requires_minor_league`) are errors. Too few candidates for `duration_days` is a warning in
the dataset report and in the editor preview, not an error: days would repeat.

## Rules

| Rule | Default | Range | Meaning |
| --- | --- | --- | --- |
| `attempts` | 3 | 1–10 | Attempts per user per day, in chat and Mini App |
| `min_correct_ratio` | 0.5 | 0.1–1.0 | `career` only: share of the clubs needed to solve the day (rounded up, at least 1) |

The 5-answer cap per attempt of `career` events is an anti-abuse limit, not a rule
(`MAX_ANSWERS_PER_ATTEMPT`).

## Rewards

| Reward | Default | Range | Meaning |
| --- | --- | --- | --- |
| `points_per_day` | 1 | 0–10 | Event points for solving a day |
| `first_correct_bonus` | 1 | 0–5 | Extra points for the first solver of the day; 0 disables the bonus and its message |
| `podium_trophies` | 3 | 0–3 | How many top positions receive a trophy the day after the event ends; 0 = none |

## Schedule

| `mode` | Other keys | Behaviour |
| --- | --- | --- |
| `rotation` | `start_weekdays` (optional list of `mon`…`sun`), `window` (optional `{"from": "MM-DD", "to": "MM-DD"}`, may cross the new year) | Candidate for the nightly rotation when no event is active, the last event ended at least `event_min_gap_days` ago, the template is not among the last `event_history_no_repeat_templates`, today is an allowed weekday and inside the window, and its days do not overlap a fixed-date event |
| `fixed` | `start` (`YYYY-MM-DD`) | Created by the nightly job up to 7 days ahead of `start`, ignoring the minimum gap, unless its dates overlap an existing event (logged as an error: move one of the two). Rotation never takes its days |
| `manual` | `reason` (required) | Never started automatically; created from the Admin or `/admin_event_create` |

Any template, whatever its mode, can still be started on a chosen date by hand (Admin
“Crea evento manuale” or `/admin_event_create <id> [gg/mm/aa]`).

## What is copied onto the event

When an event is created, `rules` and `rewards` (with defaults filled in), texts,
translations, type, category and difficulty are copied onto `events/{code}`. Editing a
template therefore changes **future** events only. Event documents created before #31 have
no `rules`/`rewards` and behave with the defaults above, which are the values that used to
be hard-coded.

## Creating or changing a template

1. Admin → 🎊 Eventi → 📐 Template eventi: choose “➕ Nuovo template” (a skeleton) or an
   existing one.
2. Edit the JSON. The page validates on every change and, when valid, shows the candidates,
   rules and rewards, the next possible starts and a sample event built from the real pool
   (nothing is written).
3. Save (with confirmation): a copy goes to `backup/event_templates-<timestamp>.json` and the
   file is rewritten atomically.
4. The change is in the local `data/event_templates.json`: commit and release it like any
   other `data/` change. CI validates it again.

Editing the file directly is equally supported; `python scripts/dataset_report.py --strict`
shows the same errors.
