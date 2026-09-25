# Feature flags

Authoritative description of the operational feature flags introduced by
[#51](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/51) (sub-issue of
[#22](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/22)). They allow a
gradual rollout and an emergency disable **without a deploy**, evaluated only on the server.

Out of scope, deliberately: experiments, variants, conversion metrics and A/B reporting
([#52](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/52)), product
analytics and cohorts ([#29](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/29)),
and an Admin UI for flags ([#38](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/38)
and the other Admin issues).

## Architecture

| Layer | Where | Responsibility |
| --- | --- | --- |
| Registry, schema, evaluation, cache | [`services/feature_flags.py`](../services/feature_flags.py) | Supported keys and defaults (`Flag`, `REGISTRY`), validation (`parse_document`), pure evaluation (`evaluate`, `bucket`), `FeatureFlagService` (TTL cache + last-known-good), entry points `is_enabled`, `ensure_enabled`, `resolved_features` |
| Firestore I/O | [`services/repos/feature_flags.py`](../services/repos/feature_flags.py) | `load_document` (bounded read), `update_flag` (transactional single-flag change), `plan_update` (pure planning) |
| Telegram boundary | [`handlers/feature_gate.py`](../handlers/feature_gate.py) | `@feature_gate(Flag.X)` decorator and `flag_enabled` helper |
| API boundary | [`apps/api/miniapp.py`](../apps/api/miniapp.py), [`apps/api/app.py`](../apps/api/app.py) | `_require_feature` and the `/app/api/*` guards; the `FeatureDisabled` exception handler |
| Operator tool | [`scripts/feature_flags.py`](../scripts/feature_flags.py) | List, inspect and change flags |

Mini App clients never read Firestore (see [`firestore.rules`](../firestore.rules)); they
receive only resolved booleans for the authenticated user.

The document lives next to `admin_settings/dataset_overrides` (`/admin_block`), the existing
immediate runtime switch. The backup inventory classifies the whole `admin_settings`
collection as durable and recovery-critical, so this document is exported and restored with
it without any flag-specific handling ([backup-recovery.md](backup-recovery.md)).

## Supported keys and defaults

Every key defaults to **enabled**, because every one of these features exists today:
deploying with no document (or an empty one) changes nothing.

| Key | Default | Gates |
| --- | --- | --- |
| `arena` | on | Mini App Arena: `/app/api/arena` with `mode` `training` or `duel` (all actions) |
| `shop` | on | Shop browsing, equipping and purchase initiation: `/app/api/shop`, `/shop/buy`, `/shop/equip`, `/shop/look`; chat `/shop` and shop buttons; Stars pre-checkout |
| `daily_ui` | on | Mini App Daily surface: `/app/api/guess` for today's challenge (no `day`, or `day` = today) |
| `hints` | on | Daily hint acquisition: `/app/api/hint`, chat hint button (`hint_daily`) |
| `player_pipeline` | on | New external-source ingestion: `CandidateReviewService.retry_ingestion` |
| `events_v2` | on | Mini App events experience: `/app/api/arena` with `mode: "events"` |
| `leaderboard` | on | Global/monthly rankings: `leaderboard` in `/app/api/me`, chat `/top` and its buttons |

Keys are stable machine names; they are Firestore keys and API field names. Adding a key
means adding it to `Flag` and `REGISTRY` with a default, in a PR.

## Firestore schema

`admin_settings/feature_flags`:

```json
{
  "schema_version": 1,
  "revision": 12,
  "updated_at": "<server timestamp>",
  "updated_by": "operator-cli",
  "flags": {
    "shop": {
      "enabled": true,
      "rollout_percentage": 100,
      "allow_users": ["123456789"],
      "deny_users": [],
      "allow_groups": [],
      "deny_groups": ["-1001234567890"]
    }
  }
}
```

| Field | Type | Rules |
| --- | --- | --- |
| `schema_version` | int | Must be `1`; anything else rejects the whole document |
| `revision` | int ≥ 0 | Incremented by every write (optional when edited by hand) |
| `updated_at`, `updated_by` | timestamp, string | Written by the tool; admin metadata, never exposed |
| `flags` | map | Keys must be registry keys; unknown keys are ignored |
| `flags.<key>.enabled` | bool | Master kill switch. Missing → the registry default |
| `flags.<key>.rollout_percentage` | int 0–100 | Missing → 100 |
| `flags.<key>.allow_users`, `deny_users` | list of ids | Telegram user ids as digit strings (ints accepted), at most 1000 each |
| `flags.<key>.allow_groups`, `deny_groups` | list of ids | Telegram group/supergroup chat ids (negative), at most 1000 each |

A missing flag entry means "no stored rule": the repository default applies. Unknown
fields inside an entry make the entry invalid (a typo such as `rollout_percent` must not
silently mean 100 %).

## Evaluation precedence

For a flag with a stored rule, in this order:

1. `enabled` is `false` → **off**. The emergency kill switch beats everything, including
   allow lists.
2. The user is in `deny_users` **or** the group is in `deny_groups` → **off**. Deny beats
   allow across users and groups.
3. The user is in `allow_users` **or** the group is in `allow_groups` → **on**.
4. `rollout_percentage` is 100 → on; 0 → off; otherwise the deterministic bucket of the
   subject decides (below).
5. Without a stored rule: the repository default.

Context ids are normalized to strings (`42` and `"42"` match). A missing or unparseable id
counts as "no subject"; evaluation never raises.

### Percentage bucketing

`bucket = int.from_bytes(sha256(f"{flag}:{subject_type}:{subject_id}")[:8], "big") % 10000`,
enabled when `bucket < percentage × 100`.

- SHA-256, never Python's process-salted `hash()`: the same subject lands in the same bucket
  on every request, process, Cloud Run replica and deploy.
- The flag key is part of the input, so being early in one rollout says nothing about
  another; raising a percentage only adds subjects.
- Subject: the user if there is one, otherwise the group (`subject_type` `user` / `group`).
- **No subject with 0 < percentage < 100 → off.** Conservative and deterministic: a partial
  rollout never applies to contexts it cannot identify.
- Ids are hashed, never logged.

### Users and groups at each boundary

| Boundary | `user_id` | `group_id` |
| --- | --- | --- |
| Mini App API | from verified `initData` only (`_webapp_user`) | none |
| Telegram handlers | `effective_user.id` | `effective_chat.id` in `group`/`supergroup` chats only |
| Pre-checkout | `effective_user.id` | none |
| Candidate pipeline | none (operator action; only the master switch, 0 % and 100 % are meaningful) | none |

## Cache, propagation and failures

Each process holds one `FeatureFlagService`:

- **TTL:** `FEATURE_FLAGS_CACHE_TTL_SECONDS`, default **30 s**, clamped to 1–300 s. One
  Firestore read per replica per TTL, not one per request.
- **Maximum propagation delay** of a change: TTL + one read (≈ 30 s by default) on every
  replica, since replicas refresh independently. New instances read on their first request.
- **Stale-while-refreshing:** while one thread refreshes, others keep serving the current
  snapshot; only a cold process with no snapshot waits for the first read. The read has a
  5 s timeout and no client-side retry.
- **Last-known-good:** after a successful read the configuration is retained. If a later
  read fails (timeout, permission, outage) or returns an unusable document, evaluation
  continues with the last-known-good configuration, so an emergency disable is never undone
  by a Firestore problem. The next attempt waits another TTL.
- **Cold start without Firestore:** repository defaults (all on).
- **Document deleted:** a valid state meaning "no stored rules" → defaults.

### Internal failures

Evaluation never raises into a request, and **a switch-off this process has already seen
stays off** even if the flag code itself fails. The configuration used, in order:

1. the snapshot returned by the cache (normal path);
2. if the cache path raises: the last snapshot already built (validated, even if expired),
   otherwise the last-known-good configuration — read directly, without re-entering the
   failing refresh;
3. repository defaults only if the process never had a usable configuration.

If evaluation of one flag raises, only that flag gets a conservative answer without
targeting: no stored rule → its default; stored `enabled: false` → off; stored rule at 100 %
with empty deny lists → on (it could not have refused anyone); any other stored rule
(partial rollout or deny lists) → off. If even that inspection fails, the answer is off once
a configuration has been seen, the default otherwise. Unknown keys are always off.
`resolved()` uses one configuration for all flags, so a failing cache path is not retried
once per flag. Each distinct failure (stage, flag, source, error type) is logged once per
process as `feature_flags.evaluation.fallback` at ERROR, without ids, targets or exception
text.

### Malformed configuration

Firestore content is untrusted operational input.

| Problem | Effect |
| --- | --- |
| Not a map, `schema_version` ≠ 1, `flags` not a map, bad `revision` | Whole fetch rejected; last-known-good (or defaults) kept |
| One flag entry malformed (wrong type, percentage out of range, bad id, unknown field, too many ids) | That entry is ignored; that flag keeps its last-known-good rule, or its default on cold start; other flags apply normally |
| …but the entry has a valid `enabled: false` | The kill switch is honoured anyway |
| Unknown flag key | Ignored; it can never become a feature |

Problems are logged once per distinct problem (not per TTL) at WARNING — flag and field
names only, never values or ids. WARNING records do not create Sentry events.

## Observability

| Event | Level | When |
| --- | --- | --- |
| `feature_flags.config.loaded` | INFO | First load, and whenever the stored `revision` or the source changes (`revision`, `stored_flags`, `source`) |
| `feature_flags.refresh.failed` | WARNING | A read failed (`error_type`, `source` = `last_known_good`/`default`) |
| `feature_flags.config.rejected` | WARNING | The document was unusable as a whole (`reason`) |
| `feature_flags.config.invalid` | WARNING | Malformed entries or unknown keys (`flags`, `fields`, `kill_switch_kept`, `unknown_count`, `revision`) |
| `feature_flags.change.applied` | INFO | A change made with the operator tool (`flag`, `operation`, `revision`) |
| `feature_flags.evaluation.fallback` | ERROR (once per distinct failure per process) | Unexpected internal failure in the cache path or in evaluation (`stage` = `snapshot`/`evaluate`, `flag`, `source` = `current_snapshot`/`last_known_good`/`default`/`conservative`, `error_type`) — see [Internal failures](#internal-failures) |
| `payment.invoice.refused` / `payment.precheckout.rejected` with `reason=feature_disabled` | INFO | Shop disabled at purchase initiation |

Individual evaluations are never logged. A refused API call is visible as
`api.request.completed` with `status_code=403`.

## Runtime integration and disabled behaviour

**Mini App API.** Guards run after authentication and rate limiting, so an unauthenticated
caller gets 401 and learns nothing about flags. A disabled feature answers:

```http
HTTP/1.1 403
{"detail": "feature_disabled", "code": "FEATURE_DISABLED", "feature": "shop"}
```

The exception is handled, so it produces no traceback and no Sentry event. The Mini App client
exposes it as `ApiError.code` / `isFeatureDisabled` (`webapp/src/api`).

| Flag | When off | Deliberately **not** gated |
| --- | --- | --- |
| `arena` | 403 for every `training`/`duel` action (get, list, next, guess, create, join, delete) | Stored duels, sessions and ledgers are untouched and reappear when re-enabled; chat `/training` and group rounds (`/round`) are separate modes |
| `shop` | 403 on catalogue, buy (no invoice link is created), equip, look; chat `/shop` and shop buttons show a notice; pre-checkout is refused **before** any reservation, so nothing is charged | `successful_payment` delivery (Stars already taken; idempotent on the charge id), `/admin_refund`, `/paysupport`, `/app/api/shop/history` (the charge id for refunds), owned cosmetics in profiles and cards |
| `daily_ui` | 403 on `/app/api/guess` for today | Archive guesses through the same route, `/me` `today` block, the chat Daily (`/guess`, free text, `/show`), challenge generation. No challenge is deleted or regenerated |
| `hints` | 403 on `/app/api/hint`; the chat hint button shows an alert and takes nothing | Hints already paid for (still shown); attempts and challenge state |
| `player_pipeline` | `retry_ingestion` returns `ReviewStatus.FEATURE_DISABLED` before any adapter call or candidate write (Admin shows a warning) | Queue, detail, edit, approve, reject, merge, source-wrong on existing candidates; `players.json` is never written by flags |
| `events_v2` | 403 on `/app/api/arena` `mode: "events"` (list and guess) | Chat `/events`, event generation, participants, trophies |
| `leaderboard` | `/me` returns `"leaderboard": []`; chat `/top` and its buttons show a notice | Points, monthly points, rankings data, monthly closure, private leagues, public profiles and profile search |

**Resolved exposure.** `/app/api/me` includes `"features": {"arena": true, …}` for the
authenticated user: seven booleans, nothing else. `isFeatureEnabled(profile, key)` in
`webapp/src/api` treats a missing block or key as enabled. The server remains the
authority; the Mini App Daily page shows a localized notice on `FEATURE_DISABLED`.

**Telegram.** `@feature_gate(Flag.X)` wraps the handler object itself, so a command and the
menu button that calls it cannot disagree. The notice is `feature.disabled` in
[`services/i18n.py`](../services/i18n.py).

## Operator procedure

Run from a machine with the same Firestore credentials as the other scripts
(`FIREBASE_CREDENTIALS_PATH` or Application Default Credentials for the production project):

```bash
python scripts/feature_flags.py list
```

| Command | Effect |
| --- | --- |
| `list` | Every flag: default, stored rule, enabled, rollout, **counts** of targets, document revision |
| `show <flag> [--show-targets]` | One flag; ids are printed only with `--show-targets` |
| `disable <flag>` / `enable <flag>` | Master switch |
| `rollout <flag> <0-100>` | Percentage |
| `allow <flag> --user ID` / `--group ID` | Add to the allow list (and remove from deny) |
| `deny <flag> --user ID` / `--group ID` | Add to the deny list (and remove from allow) |
| `untarget <flag> --user ID` / `--group ID` | Remove from both lists |
| `reset <flag>` | Remove the stored rule → repository default |

Every change validates input before touching Firestore, prints the flag with a
before/after summary and the revision, asks for confirmation (`--yes` for scripts; without a
terminal `--yes` is required) and records `--actor` (default `operator-cli`) in `updated_by`.
Options: `--expected-revision N` refuses if the document is not at that revision;
`--replace-invalid-document` replaces a stored document that is invalid as a whole.

**Concurrency.** A change is applied inside a Firestore transaction to the entry as it is
at commit time and bumps `revision`; the rest of the document is not rewritten. Two
operators changing flags at the same time both land (or one gets an error after retries);
neither erases the other. If the document changed between the preview and the write, the
tool says so and prints the resulting state.

### Emergency disable

1. `python scripts/feature_flags.py disable <flag> --actor "<incident ref>"` and confirm.
2. Wait for the cache TTL (≈ 30 s) and verify: the API returns 403 `FEATURE_DISABLED` for the
   feature, logs show `feature_flags.config.loaded` with the new `revision`.
3. Leave the switch in place while fixing; stored data (duels, purchases, candidates,
   rankings) is untouched.
4. Recover with `enable <flag>` (or `reset <flag>` to return to the default).

If Firestore itself is unavailable, replicas keep their last-known-good configuration; a
disable written before the outage stays in force. Replicas that start during the outage use
the defaults (on): if a feature must stay off across a cold start without Firestore, roll back
traffic instead ([release-checklist.md § Rollback](release-checklist.md#10-rollback)).

### Gradual rollout

`rollout <flag> 5` → observe → `rollout <flag> 25` → … → `rollout <flag> 100` (or `reset`).
Use `allow --user` for testers and `deny --user`/`--group` to exclude someone. Subjects already
in the rollout stay in it as the percentage grows.

## Tests

- [`tests/test_feature_flags.py`](../tests/test_feature_flags.py): registry, precedence,
  bucketing (including across processes), schema validation, cache TTL, last-known-good,
  failures, internal-failure fallbacks that keep known kill switches, stampede, change
  planning and revision safety.
- [`tests/test_feature_flags_runtime.py`](../tests/test_feature_flags_runtime.py): API
  contract per flag, `/me` exposure, Telegram gates, Stars pre-checkout/delivery regressions.
- [`tests/test_feature_flags_cli.py`](../tests/test_feature_flags_cli.py): operator tool.
- [`tests/test_feature_flags_emulator.py`](../tests/test_feature_flags_emulator.py): the real
  document, transactions, two replicas, a live API boundary and the CLI on the emulator.
- `player_pipeline` regressions in [`tests/test_candidate_review.py`](../tests/test_candidate_review.py);
  Mini App contract in `tests/frontend/api.test.ts` and `tests/frontend/daily.test.ts`.
- Unit tests get a default-only flag service from `tests/conftest.py`; emulator tests read
  the stored document without cache.

## Limitations

- Per-replica caches: during the TTL different replicas may briefly disagree.
- A replica that cold-starts while Firestore is unreachable uses defaults (on).
- No Admin UI and no Telegram command for flags; the CLI needs Firestore credentials.
- Targeting is by explicit ids and percentage only: no attributes, segments, schedules,
  variants or metrics (#52).
- No history of past values beyond `revision`, `updated_at`, `updated_by` (the weekly backup
  holds older snapshots).
- The Mini App does not hide navigation entries based on flags.
- Offline scripts (`scripts/wikipedia/`, `scripts/import_players.py`) are not gated; they do
  not touch the Candidate pipeline runtime and only produce files reviewed through Git.
