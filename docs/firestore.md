# Firestore map

Authoritative map of **current** Firestore usage. The reasoning behind the data model
(lazy daily reset, user id as document id, participants as subcollection, ISO dates)
is recorded in the historical review [firebase_review.md](firebase_review.md); the
durable-work collections are explained in [runtime-hardening.md](runtime-hardening.md).
Collection names below were verified against `services/firebase_service.py`,
`services/repos/`, `services/arena.py`, `services/referrals.py`,
`services/work_receipts.py`, `services/broadcast_store.py` and
`services/monthly_closure.py`.

## What belongs where

| Store | Holds | Mutated by |
| --- | --- | --- |
| **Firestore** | All mutable game and user state: users, daily challenges, events and participants, leagues, seasons, purchases, duels, referrals, group rounds, admin overrides, feature flags, background-work state | Cloud Run service; local Admin/scripts with credentials |
| **Versioned JSON** (`data/`) | Curated players, game tuning, event templates, shop catalogue, dataset baseline | Git (PRs) only; see [player-data-pipeline.md](player-data-pipeline.md) |
| **Local, gitignored files** | Candidate pipeline (`data/candidates/`), import batches (`data/incoming/`), backups (`backup/`) | Local tools only |

Clients never access Firestore directly: [`firestore.rules`](../firestore.rules) denies
all client reads and writes, and the backend uses the Admin SDK, which bypasses rules.
Dates are stored as ISO `YYYY-MM-DD` (`services/dates.py`).

## Collections

| Path | Document id | Purpose |
| --- | --- | --- |
| `users/{telegram_id}` | Telegram user id | Profile, points (total/monthly), day counters anchored to `last_played_day`, streaks, trophies, cosmetics (`owned`, `earned`, `equipped`, looks), sessions (`archive_day`, `training_key`, `event_key`, `app_duel`), duel ledger, `shop_checkout` reservation |
| `users/{id}/history/{day}` | ISO day | One result per finished daily challenge (calendar) |
| `users/{id}/archive/{day}` | ISO day | Archive replay results |
| `daily_path/{day}` | ISO day | Daily challenge content, accepted answers, difficulty, `difficulty_prediction` snapshot, `planner_audit` (planned days), first-solver bonus state, `players_count`/`solved_count`/`solved_attempts_total`/`solved_hints_total` ([difficolta.md §6](difficolta.md)) |
| `events/{code}` | event code | Event definition and per-day `daily_data` |
| `events/{code}/participants/{telegram_id}` | user id | Event points and attempts |
| `seasons/{id}` | season | Monthly seasons |
| `leagues/{code}` and `leagues/{code}/members/{telegram_id}` | invite code / user id | Private leagues and member points |
| `group_rounds/{chat_id}` and `.../players/{telegram_id}` | chat id / user id | Current group round and in-group standings |
| `purchases/{telegram_payment_charge_id}` | Telegram charge id | Stars purchase ledger; idempotent delivery and refunds |
| `app_duels/{code}` | random code | Arena duels (two seats, five puzzles, `expires_at`) |
| `referrals/{key}` | SHA-256 of a user id (`services/referrals.py::referral_key`) | Referral attribution (`inviter_id`) and qualification |
| `admin_settings/dataset_overrides` | fixed | Players blocked with `/admin_block` |
| `admin_settings/daily_planner` | fixed | Players excluded from the Daily planner: `excluded.{player_id}` = `reason`, `until` (ISO day or null), `excluded_at` ([game-modes.md](game-modes.md#daily-planner)) |
| `admin_settings/feature_flags` | fixed | Operational feature flags: schema version, revision, per-flag master switch, rollout and user/group targeting ([feature-flags.md](feature-flags.md)) |
| `father_son_pairs/{auto}` | auto | Manual father/son event content (Telegram `file_id`) |
| `work_receipts/{key}` | e.g. `telegram-{update_id}`, `notify-{day}-{user}` | Deduplication/outcome of background work (`delete_after` for optional TTL) |
| `update_locks/{user_id}` | user id | Per-user serialization of updates across replicas |
| `daily_jobs/{day}` | ISO day | Immutable nightly broadcast payload and `sent_total` |
| `monthly_closures/{YYYY-MM}` | month | Frozen podium before monthly reset |

Backup coverage of each collection (durable, reconstructable or ephemeral, and why) is the
inventory in [backup-recovery.md § 3](backup-recovery.md#3-collection-inventory); a new
collection must be classified there (`services/firestore_backup/inventory.py`).

Composite indexes are in [`firestore.indexes.json`](../firestore.indexes.json).
Optional TTL policies (`app_duels.expires_at`, `work_receipts.delete_after`) are
described as optional in the code/docs and are not managed from this repository.

## Concurrency assumptions

- Operations whose double execution costs something are Firestore transactions:
  first-correct bonus, per-move revision checks (Training, duels, events), purchase
  reservation and delivery, monthly reset per user, league membership changes, work
  receipt claims.
- Telegram update retries and Cloud Tasks retries are deduplicated with deterministic
  task names plus `work_receipts`; this is *not* exactly-once delivery across Telegram
  and Firestore (see [performance.md](performance.md)).
- Leaderboard position uses a count query instead of reading all users; counters that
  must survive (`players_count`, `solved_count`, `sent_total`) use `Increment`.

## Credentials and environments

- `services/firebase_service.py` initializes lazily: a key file at
  `FIREBASE_CREDENTIALS_PATH` if it exists, otherwise Application Default Credentials
  (used by the backup workflow via Workload Identity Federation).
- Production credentials are provided to Cloud Run as a mounted secret / service
  identity ([deploy.md](deploy.md)). Never commit key files; `.env` and
  `firebase-key.json` are gitignored and guarded by detect-secrets
  ([security.md](security.md)).
- Local development should use the emulator (`FIRESTORE_EMULATOR_HOST=127.0.0.1:8571`,
  `python -m tools.dev emulator`); see [local-development.md](local-development.md).
  Unless `FIRESTORE_EMULATOR_HOST` is set, the Admin UI and scripts pointed at a real
  key file write to that real project.

## Test and emulator strategy

- Most tests use in-memory fakes and monkeypatching; they never touch a real database.
- `tests/test_firestore_transactions.py` runs against the emulator to prove the
  transactional invariants (at most one winner) for the first-solver bonus, Stars
  delivery and update receipts. Locally these tests skip without
  `FIRESTORE_EMULATOR_HOST`; in CI the emulator is started and the fixture fails
  instead of skipping.

## Schema changes

There is no automatic schema migration. Historical tools: `scripts/migrate_firestore.py`
(one-off model migration) and `scripts/backfill_users.py` (adds missing user fields
idempotently; `/start` also fills missing fields). New fields must tolerate absent
values on existing documents. Rules/indexes changes are deployed separately with
`firebase deploy --only firestore:rules,firestore:indexes`.
