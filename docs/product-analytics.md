# Product analytics

Authoritative description of product analytics for Guess the Player. Introduced by
[#29](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/29).

Out of scope here: **operational observability** (structured logs, Sentry, request/task
correlation — [observability.md](observability.md), #18), **Admin Analytics UI** (#39, not
built here — this document defines the event schema it will read), and
**experimentation** (variants, assignment, statistical significance — #52, explicitly
blocked by this issue and not implemented).

## 1. Why this is a separate system from observability

Observability (#18) answers *"is the app healthy?"*. Product analytics answers *"how are
people actually using the product?"*. They must never merge:

- Sentry is never used as a product analytics sink, and PostHog is never used for error
  tracking or session replay (redundant with #18, and explicitly excluded from this issue).
- Operational logs are never repurposed as a fake analytics database — a product event is a
  typed, curated fact ("a Daily was completed"), not a log line with a timestamp.
- A product event never goes through `logging`/Sentry's `ERROR` path, and an operational
  error is never reported as a product event.
- The two modules do not import each other's internal state. `services/product_analytics.py`
  only reuses two small, genuinely shared things from `services/observability.py`: the
  release/revision fields (`services/version.py`, the same #49 source every subsystem
  reports) and the redaction helpers (`is_sensitive_key`, `sanitize`), so a mistyped property
  name is caught by the same denylist as everything else instead of a second, slightly
  different one.

## 2. Provider

[PostHog](https://posthog.com), via the official `posthog-python` client
(`posthog==7.54.0`, pinned in `requirements.txt`), using
`Posthog(project_api_key=..., host=...).capture(event=..., distinct_id=..., properties=...)`.
The client batches events and flushes them on its own background thread; this codebase does
not build a second queue or thread pool around it.

**Version currency, and what changed between 3.x and 7.x (both re-verified live, not
assumed):** an earlier draft of this document pinned `posthog==3.7.4`, checked against
`pip install` at the time. That was wrong to treat as "current" — re-checking directly
against PyPI (`pip index versions posthog`, and `https://pypi.org/pypi/posthog/json`)
showed `7.54.0` as the actual current stable release (published 2026-09-15, the day this
was re-verified), supporting Python 3.10+, compatible with this repository's 3.11 baseline.
The pin was updated to `7.54.0` and the adapter (`services/product_analytics.py`) was
updated for two breaking changes found by inspecting the installed package's real
constructor/method signatures (`inspect.signature`), not by reading changelogs alone:

1. `Posthog.__init__`'s first argument was renamed from `api_key` to `project_api_key`.
   Calling with the old `api_key=` keyword now raises `TypeError` (verified: it does).
   `services/product_analytics.py::_build_client` uses `project_api_key=`.
2. `Posthog.capture`'s signature changed from named `distinct_id`/`properties`/… parameters
   to `capture(self, event: str, **kwargs: Unpack[OptionalCaptureArgs])`. `event` can still
   be passed by keyword (it is a named, not keyword-only-via-`**kwargs`, parameter), and
   `distinct_id`/`properties` are unchanged keys inside `OptionalCaptureArgs` — so the call
   shape `capture(event=..., distinct_id=..., properties=...)` this codebase uses continues
   to work, but the change is significant enough (a full signature replacement) that it
   warranted an actual real-SDK test rather than trusting the diff: see
   `tests/test_product_analytics.py::test_real_installed_posthog_sdk_accepts_our_adapter_call_shape`,
   which builds a genuine `posthog.Posthog` client (with the SDK's own `disabled=True`
   option, so it is real code with zero network reach) and calls the exact function our
   `capture()` calls internally, so a future SDK upgrade that breaks this call shape fails
   that test loudly instead of being silently swallowed by `capture()`'s own
   never-raise contract.

Re-verify the current stable version again before actually merging if meaningful time has
passed since this was written — pin drift is exactly the failure mode this section is
guarding against, and the right process is "check PyPI/GitHub releases live," not "trust
whatever number is already in this document."

Deliberately **not** enabled:

- **PostHog Feature Flags** — redundant with #51 (`services/feature_flags.py`), which
  already owns rollout/targeting and must not be duplicated.
- **PostHog Error Tracking** — redundant with #18 (Sentry).
- **PostHog Experiments** — that is #52's territory; this issue explicitly does not build an
  experimentation framework.
- **Autocapture and Session Replay** — not enabled, and this document deliberately
  **recommends against** enabling them later without a separate privacy review: autocapture
  would defeat the entire "curated, typed events only" design, and session replay would
  capture arbitrary UI content (including career-path images, which are the game's answer)
  by construction. If a future need arises, treat it as a new decision, not a flag flip.

## 3. Architecture

```
handler / API endpoint / service function (authoritative point)
        │
        ▼
services/product_analytics.capture(Event.X, user_id=..., properties={...})
        │  - validates Event is a known taxonomy member
        │  - keeps only properties THIS event allows, whose VALUE also passes its
        │    type/enum/catalogue validator (never forwards a raw dict, never a
        │    fabricated Shop item id - see §7)
        │  - pseudonymizes user_id -> distinct_id (HMAC-SHA256, dedicated salt)
        │  - enriches: environment, app_version, app_revision, $process_person_profile=False
        │  - never raises; a no-op if disabled/misconfigured/unavailable
        ▼
posthog-python client (background thread, batches, retries its own transport)
        │
        ▼
PostHog (EU or configured region)
```

One module, `services/product_analytics.py`, owns the provider. No call site anywhere in
the codebase calls `posthog.capture(...)` directly — every call goes through
`product_analytics.capture(...)`, so the provider could be swapped or the whole system
disabled without touching a single handler.

## 4. Configuration

Following the same self-contained-module convention `services/observability.py` (#18) and
`services/feature_flags.py` (#51) already use — each subsystem reads its own environment
variables via a `Settings.from_env()` dataclass rather than centralizing everything in
`config.py`:

| Variable | Meaning | Default |
| --- | --- | --- |
| `POSTHOG_API_KEY` | PostHog project API key. **Required** for any traffic. | unset → analytics fully disabled |
| `POSTHOG_HOST` | PostHog ingestion host. | `https://eu.i.posthog.com` |
| `PRODUCT_ANALYTICS_ENABLED` | `true`/`false` to force the on/off decision. | unset → on outside `local`/`test`/`development`, off inside them |
| `PRODUCT_ANALYTICS_ENVIRONMENT` | Environment label sent with every event. | `SENTRY_ENVIRONMENT`, else auto-detected (`test` under pytest, `production` on Cloud Run, else `development`) |
| `PRODUCT_ANALYTICS_SALT` | Dedicated secret (≥ 32 chars recommended) for the pseudonymous `distinct_id` HMAC. | unset → `capture()` is a safe no-op (no identity is ever invented) |

Guarantees, all covered by `tests/test_product_analytics.py`:

- **No API key → analytics disabled**, full stop; the app behaves identically either way.
- **Local/test default off** even if a key happens to be present in a developer's shell —
  pytest sets `PYTEST_CURRENT_TEST` automatically, which this module uses as one of its
  environment signals, so the ordinary test suite never needs to mock HTTP to stay silent.
- **Provider outage never breaks gameplay, payments, or referrals** — every public function
  in `product_analytics.py` is wrapped so a bad key, host, or a client that raises cannot
  propagate into a Telegram handler or a FastAPI endpoint.
- **No network call during tests unless explicitly mocked** — `_build_client` (which is the
  only place that imports and constructs `posthog.Posthog`) is called exactly once, from
  `init()`, only when a key is present and analytics is enabled; tests either never reach it
  (the default) or monkeypatch it to a fake client (see
  `tests/test_product_analytics.py::enable`). The one exception is a deliberate one: a real
  `posthog.Posthog` client built with the SDK's own `disabled=True` option, which is a
  genuinely real client that cannot reach the network by construction (see §2 and
  `test_real_installed_posthog_sdk_accepts_our_adapter_call_shape`) — used once, specifically
  to prove the adapter still matches the installed SDK's actual signature.
- **Invalid config → a bounded operational warning through `observability.log_event`, never
  a crash.** A bad host/key that fails when building the client is caught in `init()`;
  analytics is then a no-op for the rest of the process.
- **Secrets are never logged.** The API key and salt never appear in any log line; the
  observability warnings this module emits carry only event names, property key names and
  error types.

`.env.example` documents all five variables (commented out, no real value committed).

## 5. The analytics service

`services/product_analytics.py` exposes:

- `capture(event, *, user_id=None, anonymous_id=None, properties=None)` — the only entry
  point call sites use. Internally delegates the actual SDK call to `_call_capture`, split
  out on purpose so the real-SDK smoke test (§2) can exercise it directly, bypassing
  `capture()`'s own blanket exception handling.
- `flush()` / `shutdown()` — best-effort, called once from the FastAPI lifespan (`apps/api/app.py`)
  teardown; never required for correctness (posthog-python flushes on its own).
- `distinct_id_for_user(user_id)` / `distinct_id_for_anonymous(session_id)` — identity
  helpers (§7).
- `is_enabled()`, `settings()` — introspection, used by tests and available to an operator
  script.

No `identify()` is implemented: nothing in this codebase currently needs PostHog Person
profiles beyond the `distinct_id` attached to every event (see §12, "person profiles off").
If a genuine need for `identify()` appears later (e.g. a stable display trait worth
attaching to the person), add it deliberately with its own privacy review — do not assume
it is needed by default.

## 6. Event taxonomy

One flat registry (`product_analytics.Event`, a `str` Enum), one naming convention:
snake_case, verb-object, product-shaped (`daily_completed`, not `daily-complete` or
`completeDaily`). `capture()` refuses anything that is not a member of this enum — a typo'd
or ad-hoc event name never reaches PostHog.

Only events with a **real, currently-existing** trigger in the bot or Mini App are defined.
In particular: there is **no multi-step onboarding concept** in the current product (`/start`
is a single message, not a funnel with distinct steps), so no `onboarding_started` /
`onboarding_completed` events exist. If a real onboarding flow is built later, add events for
it then — do not track a funnel that does not exist.

For every event: **trigger**, **source** (server = authoritative call site; client = would
require frontend tracking, see §10), **idempotency**, **allowed properties actually sent**,
and **intent vs. completion**.

### Lifecycle

| Event | Trigger | Source | Idempotency | Properties | Intent/completion |
| --- | --- | --- | --- | --- | --- |
| `bot_started` | `/start` (any argument), `handlers/start_handler.py` | server | none needed — one event per `/start`, `is_new_user` distinguishes first contact | `language`, `is_new_user`, `acquisition_channel` | completion (the interaction happened) |
| `miniapp_opened` | First non-lightweight call to `POST /app/api/me` (`services/webapp_api.build_profile`, `include_social=True`) | server | none needed — fires on every full bootstrap call, not on the lightweight polling variant used to refresh in-game state | `language` | completion |

`miniapp_opened` is server-side rather than a client `posthog-js` call because `/app/api/me`
is already the authoritative, authenticated signal that the Mini App loaded its data; a
client-side "page loaded" event would either duplicate it or race it. See §10 for why no
frontend tracking was added in this iteration.

`acquisition_channel` ([#137](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/137))
says which link brought someone to `/start`, so a marketing channel can be compared with
another. It is derived from the `/start` argument by
`handlers/start_handler.py::acquisition_channel`, from a closed list
(`services/product_analytics.py::ACQUISITION_CHANNELS`):

| `/start` argument | `acquisition_channel` |
| --- | --- |
| none (bot opened directly) | `direct` |
| `ref_…` | `referral` |
| `duel_…` | `duel` |
| `lega_…` | `league` |
| `src_<source>` with `<source>` in `CAMPAIGN_SOURCES` (`tiktok`, `instagram`, `youtube`, `reddit`, `x`, `threads`, `facebook`, `telegram_group`, `creator`, `producthunt`, `directory`, `qr`; case-insensitive) | `<source>` |
| anything else, including an unknown `src_` value | `other` |

Campaign links are `https://t.me/<BOT_USERNAME>?start=src_<source>`: they show the normal
welcome and change nothing else. The raw argument is never sent, so a link cannot smuggle
free text or personal data into analytics; a new source needs a code change to
`CAMPAIGN_SOURCES`, until then it reads as `other`.

### Daily

| Event | Trigger | Source | Idempotency | Properties | Intent/completion |
| --- | --- | --- | --- | --- | --- |
| `daily_viewed` | Same call as `miniapp_opened` (the Daily card is part of the same bundle) | server | same as above | `surface`, `language` | intent (viewing) |
| `daily_guess_submitted` | Every accepted or refused attempt, `services/game.py::play_daily` (shared by chat and Mini App — the single authoritative implementation) | server | one event per attempt, by construction (`begin_guess_attempt` is itself transactional) | `surface`, `status` (`correct`/`wrong`/`refused`), `reason` (on refusal), `attempts_used`, `attempts_left`, `hints_used`, `typo` | intent per attempt |
| `daily_guess_correct` | The attempt in `play_daily` that matches | server | fires once, at the same transaction outcome that awards points | `surface`, `attempts_used`, `hints_used`, `streak`, `bonus_awarded` | completion signal for this sub-metric |
| `daily_completed` | Terminal outcome of `play_daily` — either the correct guess, or the wrong guess that exhausts attempts (`attempts_left == 0`) | server | fires **exactly once per user per day**: `begin_guess_attempt` refuses any further attempt once the day is closed for that user, so the terminal branch cannot re-run | `surface`, `status` (`correct`/`wrong`), `attempts_used`, `hints_used`, `difficulty_band` (`easy`/`medium`/`hard`/`impossible`, the band the Daily was played at) | completion |
| `daily_archive_viewed` | `services/webapp_api.build_archive_challenge` (Mini App opens a specific past day) | server | not idempotency-sensitive (a view, not a completion) | `surface` | intent |
| `daily_abandoned` | **Not implemented.** There is no reliable signal in the current code for "opened the Daily and never attempted it" versus "never opened it" — adding one would mean inventing a new tracked action, which the issue explicitly says not to do. | — | — | — | — |

`daily_guess_submitted`/`daily_guess_correct`/`daily_completed` are emitted from
`services/game.py` itself (not from `handlers/guess_handler.py` or
`services/webapp_api.py`) specifically so chat and Mini App — which both call
`game.play_daily` — cannot diverge or double-count; a `surface` property
(`"telegram_chat"` | `"miniapp"`) distinguishes them without a second implementation of
"when is the Daily finished."

### Hints

| Event | Trigger | Source | Idempotency | Properties | Intent/completion |
| --- | --- | --- | --- | --- | --- |
| `hint_requested` | `services/game.py::take_hint`, before the Firestore write | server | one per request; a refused request (no attempts, already guessed) still counts as a request | `surface` | intent |
| `hint_used` | Same function, after `take_daily_hint` succeeds | server | fires once per successful hint (the underlying `take_daily_hint` call is itself the authoritative consumption) | `surface`, `hint_index`, `hints_used` | completion — this is the paid-hint event; there is no separate purchase event because hints cost in-game points, not Stars (see §9 for the Shop's Stars purchases, which are a different mechanism entirely) |

### Training

| Event | Trigger | Source | Idempotency | Properties | Intent/completion |
| --- | --- | --- | --- | --- | --- |
| `training_started` | `handlers/training_handler.py::_serve_new_challenge`, after `set_training_key` | server (chat only — Training has no Mini App surface today) | one per new challenge served | `surface` | intent |
| `training_guess_submitted` | `process_training_answer`, every attempt | server | one per attempt | `surface`, `status`, `attempt_index` | intent |
| `training_completed` | Same handler, on a correct guess (`register_training_solved`) or on exhausting attempts | server | fires once per session — a solved session cannot be re-attempted, and an exhausted one clears its key | `surface`, `status` (`correct`/`failed`), `attempts_used` | completion |

### Arena / duels

| Event | Trigger | Source | Idempotency | Properties | Intent/completion |
| --- | --- | --- | --- | --- | --- |
| `arena_viewed` | **Not wired.** The Mini App's `/app/api/arena` `action=get`/`list` is polled to refresh state, so an event per call would explode; a genuine "opened the Arena tab" signal would need frontend tracking (§10). | — | — | — | — |
| `duel_created` | `POST /app/api/arena` `mode=duel action=create` | server | one event per successful creation | `surface` | completion (the duel document is created) |
| `duel_joined` | Same endpoint, `action=join` | server | fires when the joining seat is actually added; a second `join` by the same user cannot happen (the seat already exists) | `surface` | completion |
| `duel_started` | **Not a distinct event.** Joining *is* what starts a duel in the current code (both seats exist, the puzzles are already loaded) — there is no separate "ready" step to track. `duel_joined` doubles as this signal; adding a synthetic `duel_started` would track a state transition that does not exist. | — | — | — | — |
| `duel_completed` | Same endpoint, any `action` that leaves both seats finished (`result["complete"]` becomes true) | server | fires exactly once per player: a finished seat rejects any further `guess`/`reveal` (`ArenaError("finished")`), so the completion branch in `apps/api/miniapp.py::webapp_arena` cannot be reached twice for the same player, and polling with `action=get` never triggers it | `surface` | completion; no opponent identifier of any kind is sent (see §7) |

### Events (thematic challenges)

| Event | Trigger | Source | Idempotency | Properties | Intent/completion |
| --- | --- | --- | --- | --- | --- |
| `event_viewed` | `handlers/events_handler.py::events` (the `/events` home screen) | server | one per command invocation (not per tab switch inside the same message — see below) | `surface`, `event_code`, `event_type` | intent |
| `event_started` | `handle_event_navigation`, opening the "Player" tab, which opens the answer session (`set_event_key`) | server | fires once per session opened; re-opening the same tab without a new day does not reopen a session | `surface`, `event_code`, `event_type` | intent (a session, not yet a guess) |
| `event_completed` | `_process_guess`, on a correct answer | server | fires once per event/day per user: `begin_event_attempt` refuses a repeat once solved (`already_guessed`) | `surface`, `event_code`, `event_type`, `attempts_used`, `bonus_awarded` | completion |

`event_code` is the event's own stable, non-personal identifier (e.g. `"weekend_transfer"`),
never a player name or dataset content. Switching between the Home/Leaderboard tabs of an
already-open event does **not** fire additional events — only the two meaningful actions
(opening the home screen, opening the answer session) do, to avoid an event per tab click.

### Leaderboard

| Event | Trigger | Source | Idempotency | Properties | Intent/completion |
| --- | --- | --- | --- | --- | --- |
| `leaderboard_viewed` | `/top` and the `show_global`/`show_monthly` callback, `handlers/top_users_handler.py` | server | one per view/toggle | `surface`, `scope` (`global`/`monthly`) | intent |

The Mini App's own leaderboard (part of the `/app/api/me` bundle) is **not** separately
instrumented as `leaderboard_viewed`: it is embedded in the same response as
`daily_viewed`/`miniapp_opened`, and adding a second event for the same page load would
double-count "the leaderboard was on screen" against "the Mini App was opened." If a
distinct Mini App leaderboard interaction is added later (e.g. a dedicated leaderboard
screen with its own scope toggle), instrument that specific interaction then.

### Referral

| Event | Trigger | Source | Idempotency | Properties | Intent/completion |
| --- | --- | --- | --- | --- | --- |
| `referral_link_viewed` | **Not wired.** Viewing your own referral link/dashboard (`POST /app/api/referrals`) is a read of your own data, not evidence anyone acted on it, and the endpoint is already rate-limited/expensive (`cost=10`); it was judged not worth an event with no product decision behind it yet. | — | — | — | — |
| `referral_invite_created` | **Not wired**, for the same reason: the link (`code_for(user_id)`) is deterministic and always available once `BOT_USERNAME`/`BOT_TOKEN` are configured — there is no discrete "created" moment to hook, it is not a stored, mutable resource. | — | — | — | — |
| `referral_opened` | `/start ref_XXXX`, `handlers/start_handler.py` | server | fires once per `/start` call that carries a `ref_` argument; a friend re-clicking the same link fires it again by design (that is the actual product question — "how many times was this link opened" — separate from whether it *attached*, in `referral_attached`) | `referral_attached` | intent — the deep link was opened; `referral_attached` says whether the server actually recorded the attribution (it can fail, e.g. self-referral, already-attributed account) |
| `referral_converted` | `domains/referrals/service.py::credit_day`, the exact commit where the ledger's `days` count reaches `REQUIRED_DAYS` and its `status` flips `pending → qualified` | server | **fires exactly once per referral, ever.** `credit_day`'s own top-of-function guard (`entry.get("status") != "pending"`) makes every subsequent call for an already-qualified ledger a no-op before it reaches the write path — a Cloud Tasks retry, `reconcile()` replaying the same day, or a duplicate `record_completion` call cannot re-fire it. Covered by `tests/test_product_analytics.py::test_a_replayed_referral_credit_fires_the_conversion_event_only_once`. | `qualified_days` | completion — server-authoritative by construction (credit is tied to the same durable Daily-history record the game itself uses to decide the day counted) |
| `referral_reward_granted` | Same commit as `referral_converted` (the cosmetic reward is granted in the same transaction) | server | same guarantee as above | `reward_item_count` | completion |

**Identity, precisely — this is the part an earlier draft of this document got wrong, and
it matters for funnel correctness:**

- `referral_opened`, `bot_started` and the invitee's own Daily events (`daily_completed`
  etc.) are all captured under the **invitee's** `user_id` — the person who opened the
  referral link and is now playing.
- `referral_converted` is *also* captured under the **invitee's** `user_id`
  (`domains/referrals/service.py::credit_day(user_id, day)` — `user_id` there already *is* the
  invitee; the function's own parameter, not a separate lookup). "This referred user
  fulfilled the referral qualification conditions" is a fact about the invitee, and a
  PostHog funnel is walked by ONE `distinct_id` through a sequence of steps — if
  `referral_converted` resolved to a different identity than `referral_opened`/
  `bot_started`, no funnel tool could connect them and the referral funnel below would
  silently show zero conversions no matter how many referrals actually qualified.
- `referral_reward_granted` is the **one deliberate exception**: it is captured under the
  **inviter's** `user_id`, because "this inviter received their reward" is a fact about the
  inviter, not the invitee — a different subject for a genuinely different product
  question ("how many of this person's invites converted and paid off for them").
  `referral_converted` and `referral_reward_granted` fire from the same Firestore commit but
  are deliberately captured under two different identities.

`tests/test_product_analytics.py::test_referral_funnel_stays_on_one_identity_end_to_end`
is the regression test for exactly this: it drives `referral_opened` → `bot_started` → a
Daily completion → `credit_day` for one simulated invitee, and asserts all four resolve to
the same `distinct_id`, while `referral_reward_granted` resolves to a different one (the
inviter's).

### Shop / payments

| Event | Trigger | Source | Idempotency | Properties | Intent/completion |
| --- | --- | --- | --- | --- | --- |
| `shop_viewed` | `/shop` (chat) and `POST /app/api/shop` (Mini App) | server | one per view | `surface` | intent |
| `shop_item_previewed` | Opening an item card, `shop_callback` `item_*` (chat only — the Mini App renders item detail client-side from the catalogue payload without a further server round trip) | server | one per card opened | `surface`, `item_id`, `item_kind` | intent |
| `shop_purchase_started` | Invoice actually offered: `_send_invoice` (chat) / `create_invoice_link` success (`POST /app/api/shop/buy`) | server | one per invoice created (not per button tap that gets refused — see `shop_purchase_refused`) | `surface`, `item_id`, `item_kind`, `price_stars` | **intent only** — Telegram has not charged anything yet |
| `shop_purchase_refused` | A purchase attempt refused before an invoice is issued (feature disabled, already owned, price/ownership mismatch at pre-checkout) | server | one per refusal | `reason` (bounded enum matching the existing `shop.error_*` reasons), `item_id`, `success=false` | failed intent |
| `shop_purchase_completed` | `handlers/shop_handler.py::successful_payment_callback`, **only** on the branch where `shop.deliver(...)` returns `True` | server | **fires exactly once per Telegram charge.** Telegram redelivers `successful_payment` if the webhook does not answer within its window; `shop.deliver()` is keyed on the Telegram charge id and returns `False` on a replay, and the analytics call sits strictly after that check and returns early otherwise — same guard the existing `test_a_repeated_payment_delivers_only_once` test proves for delivery itself. Covered here by `tests/test_product_analytics.py::test_a_duplicate_shop_payment_fires_the_completed_event_only_once`. | `item_id`, `item_kind`, `price_stars`, `success=true` | **completion** — this means successfully delivered and recorded, never "payment authorized." A purchase started from the Mini App and one started from chat both complete through this single handler (Telegram always delivers `successful_payment` to the bot, regardless of where the invoice was opened), so there is intentionally no separate `surface` on this event — recording it twice per surface was rejected as the double-counting risk the issue calls out explicitly for Shop/Stars. | 
| `shop_item_equipped` | `shop_callback` `equip_*` (chat) / `POST /app/api/shop/equip` (Mini App) | server | one per successful equip | `surface`, `item_id`, `item_kind` | completion (of the equip action, not a purchase) |

`price_stars` is the Stars amount (an integer, matching what Telegram itself charges — not
a real-world currency conversion); no Telegram invoice payload, charge id, or provider token
is ever sent (see §7).

## 7. Identity and privacy review

**What PostHog receives, exactly:** a pseudonymous `distinct_id`, the event name, the
properties listed per-event above, plus `environment`, `app_version`, `app_revision` on
every event. Nothing else.

**What PostHog never receives**, enforced in code (not just by convention):

- Telegram username, first/last name, raw Telegram user id, chat id or group name.
- `initData` or any field decoded from it (`services/webapp_auth.py`'s HMAC-verified
  payload is treated exactly like any other credential — it authenticates the request and is
  discarded, never forwarded).
- Message text, free-form guesses, career paths, dataset content, or any other "what the
  player actually typed/saw."
- Telegram invoice payloads, payment charge ids, provider tokens.
- Email, IP addresses (`services/product_analytics.py` sets `disable_geoip=True` on the
  PostHog client, and the codebase never computes an IP itself), auth tokens, credentials.
- Full user/profile objects, raw exception data, arbitrary runtime dicts.

**Enforcement mechanism**, not just documentation. `_clean_properties(event, raw)`
(`services/product_analytics.py`) applies every layer below to every property on every
`capture()` call, in order:

1. `capture()` refuses any `event` that is not a member of the `Event` enum.
2. **Per-event key allow-list** (`EVENT_PROPERTIES[event]`): a property must be on the
   specific allowed-key set for *that* event, not just "known to the module somewhere." A
   global allow-list (an earlier design) could not express that `item_id` is legitimate for
   `shop_item_previewed` but meaningless — and therefore refused — on `bot_started`; the
   per-event set is what `test_bot_started_cannot_carry_item_id` and
   `test_daily_events_cannot_carry_shop_only_properties` exercise.
3. **Per-property value validator** (`PROPERTY_VALIDATORS[key]`): a key being allowed for
   the event is not enough — its *value* must also pass a validator bound to a concrete
   shape: a fixed string enum (`surface`, `language`, `status`, `reason`, `scope`,
   `event_type`), a real `bool` (not `1`/`"true"`/anything merely truthy — Python's `bool`
   is an `int` subclass, and the validator explicitly rejects a bare `int` where a `bool` is
   expected), a bounded `int` range, or — for `item_id`/`item_kind` — a **live lookup
   against the real Shop catalogue** (`domains/shop/service.py::get_item`/`KINDS`), not a
   shape/regex check. This is the fix for a user-controlled request (e.g. the Mini App's
   `POST /app/api/shop/buy` body) turning an arbitrary string into an analytics dimension
   merely because the key name `item_id` is allowed: the value must be a catalogue id that
   actually exists right now. `event_code`/`duel_code` (server-generated content ids, not
   user input) are bounded by a fixed-shape regex instead, since there is no equivalent
   catalogue to check them against — a deliberate, narrower defense-in-depth choice,
   documented here rather than silently assumed.
4. Every property key is additionally checked with
   `observability.is_sensitive_key` (the same denylist `token`/`secret`/`password`/
   `cookie`/`authorization`/`initdata`/… used throughout the codebase) as defense in depth,
   in case a key is ever added to a schema by mistake — proven even when both of the above
   layers are deliberately (and wrongly) made to allow it, by
   `test_sensitive_looking_keys_are_never_forwarded_even_if_allow_listed`.
5. Property *values* pass through `observability.sanitize()` before being sent — the same
   scrubbing used for Sentry events (secret-value redaction, string length/size bounds,
   depth bounds), a final layer beneath the schema above.
6. `tests/test_product_analytics.py::test_privacy_regression_scan_of_a_representative_payload`
   is the automated regression test: it calls `capture()` with a deliberately
   attacker-shaped payload (`invoice_payload`, `charge_id`, `raw_user_id`, a raw Telegram id)
   and asserts none of it appears anywhere in the resulting call — key or value. It is
   complemented by `test_malformed_numeric_values_are_dropped`,
   `test_malformed_boolean_values_are_dropped`, `test_malformed_enum_values_are_dropped` and
   `test_an_arbitrary_user_supplied_item_id_is_not_forwarded`, each proving one specific way
   a well-named-but-malformed property is still refused.

**Pseudonymous identity.** `distinct_id_for_user(user_id)` computes
`"u_" + HMAC-SHA256(PRODUCT_ANALYTICS_SALT, str(user_id)).hexdigest()[:24]` — a keyed HMAC
with a **dedicated** secret, distinct from `OBSERVABILITY_USER_SALT` (§18's salt is a
different purpose with a different blast radius; reusing it would mean a leak of one system
compromises the other). This is deliberately **not** `observability.user_ref()` reused
as-is, even though the algorithm is the same shape: a different secret means the two
pseudonymous references cannot be correlated with each other without access to both salts.
Without `PRODUCT_ANALYTICS_SALT` configured, `capture()` refuses to send anything rather
than falling back to a raw or weakly-hashed id — proven by
`test_no_salt_means_no_identity_and_no_capture`.

**Group-level data.** PostHog Groups/organizations are not used — the product has no
concept that maps naturally to a PostHog Group today, and using it "because it exists"
would be scope creep. Arena opponents are never identified even pseudonymously in analytics
(`duel_created`/`duel_joined`/`duel_completed` carry no opponent reference at all — the
product question these events answer is about *this* player's Arena usage, not
person-to-person graphs).

**Person-profile behavior, verified against the installed SDK (not assumed from older
posthog-python versions).** We deliberately never call `identify()` and only ever send a
pseudonymous `distinct_id` — but simply supplying *any* `distinct_id` to `Posthog.capture()`
is, by itself, enough for the SDK to treat the event as belonging to a real Person and build
a profile for it server-side (inspected directly in the installed `posthog/client.py`:
`get_identity_state()` only marks an event "personless" automatically when **no**
`distinct_id` was supplied at all — not our case, since we always supply one). To keep
person-profile creation minimal despite always supplying our own id,
`services/product_analytics.py::capture()` sets the property
**`$process_person_profile: False`** on every single outgoing event. This is not a
made-up flag: it is a recognised sentinel property the SDK itself looks for
(`posthog/capture_v1.py`'s `_OPTION_SENTINELS`, which lifts it into the batch payload's
`process_person_profile` field regardless of how `distinct_id` was resolved) — verified by
reading that source directly, not by assuming 3.x behaviour still applies in 7.x. Proven by
`test_every_capture_marks_the_event_personless`.

This client-side setting reduces what PostHog *tries* to build a profile from, but the
final word on Person-profile handling is still a **PostHog project setting** (see §15,
"Person profiles") — an operator must still confirm the project itself is configured for
pseudonymous/anonymous-only person handling, because a client-side property is a request to
the ingestion pipeline, not a guarantee that overrides project-level configuration.

**Anonymous/unauthenticated surfaces.** `distinct_id_for_anonymous(session_id)` exists as a
documented extension point but is **not wired to any call site**: every event defined in §6
comes from a request already authenticated by `initData` (Mini App) or a Telegram `Update`
(bot), so there is currently no genuinely unauthenticated flow that would need an anonymous
session id. If one is added later (e.g. a public, pre-`/start` landing page), use this
helper rather than inventing a new identity scheme.

## 8. Version, revision, environment

Every event automatically carries (never passed manually at a call site):

- `app_version` — `services/version.get_version()`, the same formal release (`VERSION` file)
  #49 established and #18 already reports as Sentry's `release`.
- `app_revision` — `services/version.get_build_revision()` (`K_REVISION` on Cloud Run, absent
  elsewhere) — the same exact-build identity #18 reports as Sentry's `revision` tag.
- `environment` — `local`/`test`/`development`/`staging`/`production`-shaped string
  (§4); analytics is off by default for `local`/`test`/`development` regardless of whether a
  key is configured, so accidental traffic from a laptop is structurally unlikely, not just
  discouraged by convention.

## 9. Reliability

- Every `product_analytics` public function (`capture`, `flush`, `flush_pending`, `shutdown`, `init`) is
  wrapped in `try/except Exception` and never re-raises. A PostHog outage cannot affect
  gameplay, hint delivery, Shop purchases, or referral rewards.
- `posthog-python`'s default client batches and flushes on its own background thread
  (`Posthog(...)` without `sync_mode`); this module does not build a second thread pool or a
  custom retry loop around it, per the issue's explicit guidance not to over-engineer a
  durable queue.
- No indefinite retries are added on top of the client's own bounded retry behavior.
- A bounded, deduplicated warning (`_State.warn_once`, keyed by problem signature) is logged
  through `observability.log_event` for: client init failure, an unknown event passed to
  `capture()`, dropped properties, a missing identity, and a capture-time exception — never
  more than once per distinct problem per process, so a misconfiguration cannot spam logs.
- Completion events for payments (`shop_purchase_completed`) and referrals
  (`referral_converted`/`referral_reward_granted`) are captured **after** the authoritative,
  idempotent operation has already committed — never before, and never inside a Firestore
  transaction body whose side effects could replay on contention (see the referral code
  comment in `domains/referrals/service.py::credit_day` for exactly how that is avoided: the
  transactional closure records its outcome in a local variable, and the capture call
  happens once, after `commit(...)` returns, using that outcome).
- **Delivery on Cloud Run** ([#138](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/138)).
  The service is deployed with request-based CPU: once a response leaves, the SDK's
  background thread (5-second flush interval) can be frozen until the next request, and
  events still queued when the instance scales to zero are lost. `apps/api/observe.py`
  therefore calls `product_analytics.flush_pending()` at the end of every HTTP request,
  before the response: a no-op unless that process captured something since the last
  flush, bounded by a 2-second timeout, never raising.
- **Startup status line** (#138). `init()` logs one `product_analytics.status` record:
  `sending` (true/false), `environment`, `host` and `reasons`, a list of
  `missing_api_key`, `disabled_for_environment`, `missing_salt`, `client_init_failed`.
  It never carries the key or the salt. It is a `WARNING` whenever a key is set but
  events would still be dropped.

### Troubleshooting: the PostHog dashboard is empty

Check in this order, stopping at the first failure:

1. Cloud Run logs after a deploy: find `product_analytics.status`. `sending=false` names
   the cause in `reasons`.
2. `missing_api_key` → set `POSTHOG_API_KEY` (the project key, `phc_…`) with
   `gcloud run services update guess-the-player --update-env-vars …`; `deploy.yml` never
   sets variables.
3. `missing_salt` → set `PRODUCT_ANALYTICS_SALT` (a random secret of 32+ characters).
   Without it every event is dropped because no pseudonymous id can be built.
4. `disabled_for_environment` → the environment resolved to `local`/`development`/`test`,
   usually through `SENTRY_ENVIRONMENT`. Set `PRODUCT_ANALYTICS_ENVIRONMENT=production`.
5. `sending=true` but nothing arrives → `POSTHOG_HOST` must match the project's region:
   `https://eu.i.posthog.com` (default) or `https://us.i.posthog.com`.
6. Events visible under Activity but the dashboard is empty → the dashboard in §15 is
   built by hand in PostHog; this repository does not create it. The admin page (§15a)
   also needs `POSTHOG_PERSONAL_API_KEY` and `POSTHOG_PROJECT_ID`.

## 10. Server vs. client, and the frontend-tracking scope decision

**Every event implemented in this iteration is server-side.** This was a deliberate scope
decision, not an oversight:

- The issue's own guidance is to prefer server-side for authoritative actions and treat
  client-side as optional/secondary, "if time allows."
- Server-side coverage alone already reaches both surfaces (chat and Mini App legacy `/app`)
  for every game mode, because the authoritative game logic (`services/game.py`,
  `services/arena.py`, `domains/referrals/service.py`, `domains/shop/service.py`) is shared between them —
  instrumenting it once covers both, with a `surface` property distinguishing them.
- Adding a `posthog-js` adapter to the V2 frontend (`webapp/src/`) would only add coverage
  for genuinely UI-only moments (a Shop item preview animation starting, a tab becoming
  visible) that are not currently worth a dedicated event, and V2 is **not** the production
  default (`/app` legacy remains default; the V2 switch is gated behind #81, out of scope
  here per the task boundaries).

**If frontend tracking is added later**, follow this contract (not implemented, documented
for whoever picks it up):

- One adapter module under `webapp/src/` (e.g. `analytics/`), no direct `posthog.init()`/
  `posthog.capture()` calls from individual page components.
- Initialize the client only when a public, non-secret PostHog project token is intentionally
  present in the V2 build config — never embed `POSTHOG_API_KEY` (the server-side key) in
  frontend code.
- Disable automatic person/profile collection (`person_profiles: 'identified_only'` or
  equivalent) and do not enable autocapture or session replay (same reasoning as §2).
- Never send `initData` or anything derived from it; never send a full URL with query
  parameters that could carry sensitive state (day, item ids as path segments are fine;
  tokens are not).
- **Privacy-relevant implementation detail an operator must know before this is enabled:**
  `posthog-js` writes to `localStorage`/cookies in the browser for session/device
  continuity. That is a real, user-visible storage footprint this repository's current
  server-side-only implementation does not have. Enabling it would likely require either a
  cookie-consent affordance or a `posthog-js` configuration that disables persistence
  (trading off cross-session continuity) — evaluate deliberately, do not enable by default.

## 11. Funnels

### Onboarding funnel

There is **no multi-step onboarding** in the current product to define a funnel over — see
§6. `/start` is a single message. What can be measured today with the events that exist:

- **Activation, not onboarding**: `bot_started` (`is_new_user=true`) → first
  `daily_guess_submitted` (any `surface`) for that pseudonymous id. Time window: 24 hours
  from `bot_started` is a reasonable default (matches the Daily's own cadence), but is a
  PostHog insight configuration choice, not something enforced by code.
- Exclusions: events where `is_new_user=false` are returning-user activity, not onboarding,
  and must be excluded from this funnel.
- If a real onboarding sequence (e.g. a guided first-Daily tutorial) is built later, define
  its funnel then, over its real steps.

### Referral funnel

`referral_opened` → `bot_started` (`is_new_user=true`, same request) → `daily_completed` ×
`REQUIRED_DAYS` (currently 5, `services/referrals.REQUIRED_DAYS`) → `referral_converted`.
**All four steps share one funnel subject: the invitee's pseudonymous `distinct_id`** — see
§6 for exactly why (and why `referral_reward_granted`, which follows the inviter's identity
instead, is one step *past* the end of this funnel, not part of it — it belongs to a
separate "did this inviter's referrals pay off" question, not the invitee's own journey).

**Avoiding double-counting repeated link opens:** `referral_opened` intentionally fires on
*every* `/start ref_XXXX`, including a friend re-clicking the same link twice. That is the
correct behavior for measuring "how many times was this link opened" as a distinct metric
from "how many people it actually brought in" — do not treat `referral_opened` as a unique-
visitor count; use `referral_attached=true` (a property on that same event) to count actual
new attributions, and `referral_converted` (§6, provably fires once per referral ever) for
the conversion count itself.

### Shop funnel

`shop_viewed` → `shop_item_previewed` → `shop_purchase_started` (invoice offered — **intent,
not payment**) → *(Telegram pre-checkout, not separately instrumented — it is a 10-second
internal validation step, not a product funnel stage)* → `shop_purchase_completed`
(**delivery confirmed**, not just payment authorization) → `shop_item_equipped` (a separate,
optional stage — many purchases are never equipped in the same session, e.g. bundles).

**Payment authorization vs. delivery, explicitly:** `shop_purchase_started` means an invoice
was shown to the user — Telegram has not charged anything. `shop_purchase_completed` means
`shop.deliver()` returned `True` — Stars were charged **and** the item was durably recorded
as owned. A `shop_purchase_refused` between them means the purchase was rejected before any
charge (already owned, feature disabled, price mismatch at pre-checkout) and is a distinct,
non-fatal branch, not a step toward completion.

## 12. Core metrics (how to calculate; not all built as dashboards)

| Metric | Definition |
| --- | --- |
| Daily completion rate | `daily_completed` (any `status`) ÷ distinct users with a `daily_guess_submitted` that day |
| Guesses per completed Daily | mean `attempts_used` on `daily_completed` events |
| Hint usage rate | distinct users with ≥ 1 `hint_used` ÷ distinct users with `daily_guess_submitted`, per day |
| Training starts/completions | count `training_started` vs. `training_completed` (status=`correct`) |
| Arena participation/completion | count `duel_created` + `duel_joined` vs. `duel_completed` |
| Events participation/completion | count `event_started` vs. `event_completed`, grouped by `event_code` |
| Leaderboard usage | count `leaderboard_viewed`, grouped by `scope` |
| Referral conversion rate | `referral_converted` ÷ `referral_opened` where `referral_attached=true` |
| Shop view→checkout-start rate | `shop_purchase_started` ÷ `shop_viewed` (session-scoped). **Intent only** — an invoice was shown, Telegram has not charged anything yet. Do not call this "purchase conversion"; that name belongs to the row below. |
| Shop view→purchase-completion conversion | `shop_purchase_completed` ÷ `shop_viewed` (session-scoped). **This is the real purchase-conversion KPI** — the numerator is `shop.deliver()` having actually returned `True` (Stars charged and item durably owned), not merely an invoice having been shown. An earlier draft of this document defined "purchase conversion" using `shop_purchase_started` as the numerator, which measures checkout-start rate, not completed purchases — that definition was wrong and has been replaced by this row. |
| Purchase→equip conversion | `shop_item_equipped` ÷ `shop_purchase_completed`, matched on `item_id` |
| Mini App activation | distinct users with `miniapp_opened` ÷ distinct users with `bot_started` |
| Daily returning-user behavior | **Not claimed as implemented.** This needs a cohort/retention analysis in PostHog itself (grouping `daily_completed` by pseudonymous `distinct_id` over calendar weeks) — the event data supports it, but no dashboard or saved insight is shipped with this change. Do not describe DAU/retention cohorts as "implemented" until such an insight actually exists in the PostHog project. |

## 13. Validating locally without sending production traffic

- Leave `POSTHOG_API_KEY` unset. `product_analytics.is_enabled()` is `False`, `capture()`
  is a no-op, and `tests/test_product_analytics.py::test_no_real_network_client_is_built_in_tests`
  is the standing proof that this is true even if some other env var is set.
- To exercise the code path without any network traffic, monkeypatch
  `services.product_analytics._build_client` to return a `unittest.mock.MagicMock()` (see
  `tests/test_product_analytics.py::enable` for the pattern) and call `analytics.init(...)`
  with an explicit `Settings(enabled=True, ...)` — this is exactly what the test suite does.
- To see real events land in a PostHog project during manual testing only, set
  `POSTHOG_API_KEY`/`POSTHOG_HOST` and `PRODUCT_ANALYTICS_ENABLED=true` in a local `.env`
  pointed at a **test** PostHog project, never the production one, and never commit that
  `.env`.

## 14. How to disable analytics immediately

Unset `POSTHOG_API_KEY` (or set `PRODUCT_ANALYTICS_ENABLED=false`) and redeploy — no code
change required. `product_analytics.init()` reads this at process start; there is no
runtime toggle (unlike #51's feature flags, which are intentionally live-reloadable — this
is not one, on purpose: analytics on/off is an operator/deploy-time decision, not a
targeted rollout).

## 15. Provider-dashboard-side settings — NOT enforced by repository code

The following must be configured **manually in the PostHog project itself** by an operator
with access. Nothing in this repository enforces them, and no credential for doing so is
committed:

- **Data retention** — set according to the organization's actual policy; PostHog's default
  retention is not necessarily what this product needs.
- **Person profiles** — set to identify pseudonymous-only usage (avoid PostHog's broader
  "identified" person-profile behavior if it is not needed) to keep person-level data
  minimal in the PostHog project itself, matching this document's data-minimization intent.
- **Session Replay** — must stay **off** (§2). Confirm it is off in the project settings;
  this repository's client does not request it, but a project-level toggle could enable it
  independently.
- **Autocapture** — must stay **off** for the same reason; confirm at the project level.
- **Team access** — restrict the PostHog project to people who need it, the same way
  Firestore/Cloud Run access is restricted.
- **Region/project selection** — `POSTHOG_HOST` defaults to the EU ingestion region
  (`https://eu.i.posthog.com`), matching Firestore's `europe-west1` region and this
  project's existing EU-only data residency (see [security.md](security.md) /
  [firestore.md](firestore.md)); an operator changing `POSTHOG_HOST` to the US region is a
  deliberate data-residency decision, not a default.
- **Dashboards/insights** — no dashboard is created automatically by this repository, and no
  personal PostHog API token is stored in it (nothing here requires remote credentials to
  build or test). What follows is the precise, reproducible specification for a named
  dashboard an operator (with their own, never-committed PostHog personal API key) can
  recreate by hand in the PostHog UI, or script against the PostHog API outside this
  repository — intentionally not part of the CI/deploy pipeline.

### Dashboard: "Guess the Player — Product Overview"

One insight per row below. "Breakdown" is the PostHog property to split the insight by, when
one is specified. "Window" is the funnel conversion window where applicable — a PostHog
insight setting, not something enforced by code. Every insight excludes `environment` values
other than `production` (this product/analytics is off outside it by default — §4 — but an
operator who has explicitly turned it on for `staging` for testing should filter it out of
this dashboard).

| # | Insight | Type | Event(s) / filter | Breakdown | Window / aggregation |
| --- | --- | --- | --- | --- | --- |
| 1 | Activation funnel | Funnel | `bot_started` (`is_new_user=true`) → `daily_guess_submitted` | `acquisition_channel` | 24h |
| 2 | Daily completion rate | Trend (ratio) | `daily_completed` ÷ unique users on `daily_guess_submitted` | `status` | Daily |
| 3 | Guesses per completed Daily | Trend (average) | `attempts_used` on `daily_completed` | `status` | Daily, mean |
| 4 | Hint usage rate | Trend (ratio) | unique users on `hint_used` ÷ unique users on `daily_guess_submitted` | — | Daily |
| 5 | Training starts vs. completions | Trend (two series) | `training_started`; `training_completed` (`status=correct`) | `surface` | Daily, count |
| 6 | Arena participation vs. completion | Trend (two series) | `duel_created` + `duel_joined`; `duel_completed` | `surface` | Daily, count |
| 7 | Events participation vs. completion | Trend (two series) | `event_started`; `event_completed` | `event_code` | Daily, count |
| 8 | Leaderboard views | Trend | `leaderboard_viewed` | `scope` | Daily, count |
| 9 | Referral funnel | Funnel | `referral_opened` (`referral_attached=true`) → `bot_started` (`is_new_user=true`) → `daily_completed` (×`REQUIRED_DAYS`, currently 5 — repeat the `daily_completed` step 5 times in the funnel builder, or use a single step with a minimum-occurrence-count setting if the tool supports it) → `referral_converted` | — | No fixed window (referral qualification has no deadline in the product itself; leave the insight's window generous, e.g. 90 days) |
| 10 | Shop view → checkout-start rate | Trend (ratio) | `shop_purchase_started` ÷ `shop_viewed` | `surface` | Session-scoped |
| 11 | Shop view → purchase-completion conversion | Trend (ratio) | `shop_purchase_completed` ÷ `shop_viewed` | `item_kind` | Session-scoped |
| 12 | Purchase → equip conversion | Trend (ratio) | `shop_item_equipped` ÷ `shop_purchase_completed` | `item_kind`, matched on `item_id` | Session-scoped |

Rows 10-12 deliberately do **not** collapse into one funnel: `shop_viewed` happens once per
visit to the Shop but a person can preview/start several different items in the same visit,
so a strict PostHog funnel (which counts a person once per step) would undercount per-item
detail that the ratio-of-independent-trends approach above preserves. If a future need
specifically wants a single-item purchase funnel, build `shop_item_previewed` →
`shop_purchase_started` → `shop_purchase_completed` as its own funnel, filtered to one
`item_id` at a time.

Not included as a saved insight, and not claimed as implemented (§12): Daily returning-user
/ retention cohorts. PostHog's own retention insight type, applied to `daily_completed`, is
the natural tool for this once there is a real product question driving it — no cohort
definition is prescribed here ahead of that need.

## 15a. Reading metrics back (admin dashboard, #39)

`services/product_analytics.py` is capture-only by design (§1); reading events back needs a
different credential class entirely — PostHog's **Personal** API Key (query-scoped), never
the **Project** key `POSTHOG_API_KEY` above (write-only, used only for `capture()`).
`services/product_analytics_query.py` reads its own pair,
`POSTHOG_PERSONAL_API_KEY`/`POSTHOG_PROJECT_ID`, and never falls back to the capture
settings — pasting one key into the other's variable fails loudly (`QueryError`), not
silently.

It runs one read-only HogQL `SELECT` per row of the core-metrics table (§12) that a single
query can answer (completion rate, hint usage, referral conversion, shop conversion, Mini
App activation, guesses per completed Daily) via PostHog's Query API
(`POST /api/projects/{id}/query/`). The multi-step, session-scoped funnels in §11
(onboarding, referral, shop) are **not** reimplemented here — they need PostHog's own
funnel insight to correlate ordered events within one person's session, which a bare HogQL
`SELECT` cannot express as a simple ratio. The admin page (`admin_pages/analytics.py`)
shows the core metrics and links to PostHog for those funnels instead.

Unconfigured (either variable missing) means the admin page shows a configuration notice
and makes no network call — same fail-closed posture as `product_analytics.py` itself.

## 16. Relationship with other issues

- **#18 Observability** — strictly separate concern (§1); reuses only `services/version.py`
  and `observability`'s redaction helpers, never its Sentry transport or log formatters.
- **#39 Admin Analytics** — implemented (§15a): `services/product_analytics_query.py`
  reads the single-query core metrics (§12) back from PostHog via a read-only Personal API
  Key, shown on `admin_pages/analytics.py`. The multi-step funnels (§11) still need
  PostHog's own funnel insight and are linked from that page, not reimplemented.
- **#52 Experimentation** — blocked by this issue, still open, not implemented. No variant
  assignment, no A/B testing UI, no statistical significance tooling exists in this change.
- **#51 Feature flags** — a `FEATURE_DISABLED` refusal (`services.feature_flags.FeatureDisabled`)
  is **not** counted as any successful usage event (e.g. a Shop purchase refused because the
  `shop` flag is off fires `shop_purchase_refused` with `reason="feature_disabled"`, never
  `shop_purchase_started`/`completed`). No generic "feature blocked" event was added beyond
  that — the per-area refusal events (`shop_purchase_refused`,
  `daily_guess_submitted{status=refused}`) already carry this information with real product
  context, so a separate bounded event would be redundant.
- **#21 Difficulty** — #21 defines the stable band concept (`DIFFICULTY_ORDER` in
  `services/difficulty.py`, [difficolta.md §6](difficolta.md)). `difficulty_band` is
  validated against those bands and allowed only on `daily_completed`, the one terminal
  event per user per day, carrying the band the Daily was played at
  (`challenge["difficulty"]`). No other taxonomy change. The predicted-vs-observed
  comparison itself reads the Firestore counters on `daily_path`, not PostHog.
