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
(`posthog==3.7.4`, pinned in `requirements.txt`), using the documented
`Posthog(api_key=..., host=...).capture(distinct_id=..., event=..., properties=...)`
pattern. The client batches events and flushes them on its own background thread; this
codebase does not build a second queue or thread pool around it.

**Version currency note for the reviewer:** `posthog-python` was pinned to the newest stable
release available on PyPI (3.7.4) at the time this was written, verified live against
`pip install` and the `Posthog.__init__`/`Posthog.capture` signatures. Re-verify the current
stable version before merging if meaningful time has passed, the same way any other pinned
dependency is checked.

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
        │  - drops any property key not on the allow-list (never forwards a raw dict)
        │  - pseudonymizes user_id -> distinct_id (HMAC-SHA256, dedicated salt)
        │  - enriches: environment, app_version, app_revision
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
  `tests/test_product_analytics.py::enable`).
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
  point call sites use.
- `flush()` / `shutdown()` — best-effort, called once from `bot.py`'s FastAPI lifespan
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
| `bot_started` | `/start` (any argument), `handlers/start_handler.py` | server | none needed — one event per `/start`, `is_new_user` distinguishes first contact | `language`, `is_new_user` | completion (the interaction happened) |
| `miniapp_opened` | First non-lightweight call to `POST /app/api/me` (`services/webapp_api.build_profile`, `include_social=True`) | server | none needed — fires on every full bootstrap call, not on the lightweight polling variant used to refresh in-game state | `language` | completion |

`miniapp_opened` is server-side rather than a client `posthog-js` call because `/app/api/me`
is already the authoritative, authenticated signal that the Mini App loaded its data; a
client-side "page loaded" event would either duplicate it or race it. See §10 for why no
frontend tracking was added in this iteration.

### Daily

| Event | Trigger | Source | Idempotency | Properties | Intent/completion |
| --- | --- | --- | --- | --- | --- |
| `daily_viewed` | Same call as `miniapp_opened` (the Daily card is part of the same bundle) | server | same as above | `surface`, `language` | intent (viewing) |
| `daily_guess_submitted` | Every accepted or refused attempt, `services/game.py::play_daily` (shared by chat and Mini App — the single authoritative implementation) | server | one event per attempt, by construction (`begin_guess_attempt` is itself transactional) | `surface`, `status` (`correct`/`wrong`/`refused`), `reason` (on refusal), `attempts_used`, `attempts_left`, `hints_used`, `typo` | intent per attempt |
| `daily_guess_correct` | The attempt in `play_daily` that matches | server | fires once, at the same transaction outcome that awards points | `surface`, `attempts_used`, `hints_used`, `streak`, `bonus_awarded` | completion signal for this sub-metric |
| `daily_completed` | Terminal outcome of `play_daily` — either the correct guess, or the wrong guess that exhausts attempts (`attempts_left == 0`) | server | fires **exactly once per user per day**: `begin_guess_attempt` refuses any further attempt once the day is closed for that user, so the terminal branch cannot re-run | `surface`, `status` (`correct`/`wrong`), `attempts_used`, `hints_used` | completion |
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
| `duel_completed` | Same endpoint, any `action` that leaves both seats finished (`result["complete"]` becomes true) | server | fires exactly once per player: a finished seat rejects any further `guess`/`reveal` (`ArenaError("finished")`), so the completion branch in `bot.py::webapp_arena` cannot be reached twice for the same player, and polling with `action=get` never triggers it | `surface` | completion; no opponent identifier of any kind is sent (see §7) |

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
| `referral_converted` | `services/referrals.py::credit_day`, the exact commit where the ledger's `days` count reaches `REQUIRED_DAYS` and its `status` flips `pending → qualified` | server | **fires exactly once per referral, ever.** `credit_day`'s own top-of-function guard (`entry.get("status") != "pending"`) makes every subsequent call for an already-qualified ledger a no-op before it reaches the write path — a Cloud Tasks retry, `reconcile()` replaying the same day, or a duplicate `record_completion` call cannot re-fire it. Covered by `tests/test_product_analytics.py::test_a_replayed_referral_credit_fires_the_conversion_event_only_once`. | `qualified_days` | completion — server-authoritative by construction (credit is tied to the same durable Daily-history record the game itself uses to decide the day counted) |
| `referral_reward_granted` | Same commit as `referral_converted` (the cosmetic reward is granted in the same transaction) | server | same guarantee as above | `reward_item_count` | completion |

The subject of `referral_converted`/`referral_reward_granted` is the **inviter** (the person
whose referral qualified), not the invitee — the product question is "how many of this
person's invites converted," and the invitee's own gameplay is already fully covered by the
Daily events above.

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

**Enforcement mechanism**, not just documentation:

1. `capture()` refuses any `event` that is not a member of the `Event` enum.
2. Every property is checked against `ALLOWED_PROPERTIES`, a fixed, hand-written allow-list
   (§6 lists exactly what each event actually sends, which is a subset of this). A property
   key not on the list is dropped, not forwarded — call sites cannot leak an arbitrary dict
   by construction.
3. Every property key is additionally checked with
   `observability.is_sensitive_key` (the same denylist `token`/`secret`/`password`/
   `cookie`/`authorization`/`initdata`/… used throughout the codebase) as defense in depth,
   in case a key is ever added to the allow-list by mistake.
4. Property *values* pass through `observability.sanitize()` before being sent — the same
   scrubbing used for Sentry events (secret-value redaction, string length/size bounds,
   depth bounds), a second layer beneath the key allow-list.
5. `tests/test_product_analytics.py::test_privacy_regression_scan_of_a_representative_payload`
   is the automated regression test: it calls `capture()` with a deliberately
   attacker-shaped payload (`invoice_payload`, `charge_id`, `raw_user_id`, a raw Telegram id)
   and asserts none of it appears anywhere in the resulting call — key or value.

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

- Every `product_analytics` public function (`capture`, `flush`, `shutdown`, `init`) is
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
  comment in `services/referrals.py::credit_day` for exactly how that is avoided: the
  transactional closure records its outcome in a local variable, and the capture call
  happens once, after `commit(...)` returns, using that outcome).

## 10. Server vs. client, and the frontend-tracking scope decision

**Every event implemented in this iteration is server-side.** This was a deliberate scope
decision, not an oversight:

- The issue's own guidance is to prefer server-side for authoritative actions and treat
  client-side as optional/secondary, "if time allows."
- Server-side coverage alone already reaches both surfaces (chat and Mini App legacy `/app`)
  for every game mode, because the authoritative game logic (`services/game.py`,
  `services/arena.py`, `services/referrals.py`, `services/shop.py`) is shared between them —
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

`referral_opened` (subject: whichever account opens the link — not tracked as a funnel
subject today, since the invitee's own identity isn't yet linked to prior opens) →
`bot_started` (`is_new_user=true`, same request) → `daily_completed` × `REQUIRED_DAYS`
(currently 5, `services/referrals.REQUIRED_DAYS`) → `referral_converted` (subject: the
**inviter**) → `referral_reward_granted`.

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
| Shop view→purchase conversion | `shop_purchase_started` ÷ `shop_viewed` (session-scoped) |
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
- **Dashboards/insights** — this document (§6, §11, §12) is the reproducible specification
  (event names, funnel steps, property breakdowns); no dashboard is created automatically,
  and no personal PostHog API token is stored in this repository. An operator with a
  personally-scoped PostHog API key can build the dashboards described here manually, or
  script it outside this repository — that is intentionally not part of the CI/deploy
  pipeline.

## 16. Relationship with other issues

- **#18 Observability** — strictly separate concern (§1); reuses only `services/version.py`
  and `observability`'s redaction helpers, never its Sentry transport or log formatters.
- **#39 Admin Analytics** — not built here. The event taxonomy (§6) and metric definitions
  (§12) are the schema #39 is expected to read from PostHog (via its API/export, or a future
  internal aggregation) — this issue deliberately stops at "the data exists and is
  well-defined," not "there is an Admin page showing it."
- **#52 Experimentation** — blocked by this issue, still open, not implemented. No variant
  assignment, no A/B testing UI, no statistical significance tooling exists in this change.
- **#51 Feature flags** — a `FEATURE_DISABLED` refusal (`services.feature_flags.FeatureDisabled`)
  is **not** counted as any successful usage event (e.g. a Shop purchase refused because the
  `shop` flag is off fires `shop_purchase_refused` with `reason="feature_disabled"`, never
  `shop_purchase_started`/`completed`). No generic "feature blocked" event was added beyond
  that — the per-area refusal events (`shop_purchase_refused`,
  `daily_guess_submitted{status=refused}`) already carry this information with real product
  context, so a separate bounded event would be redundant.
- **#21 Difficulty** — `services/difficulty.py` has a difficulty *value* per challenge
  (`challenge["difficulty"]`) but no stable, named "difficulty band" concept yet in the
  codebase today. No `difficulty_band` property is invented; `ALLOWED_PROPERTIES` reserves
  the name for when #21 actually defines one, and it can be added to the relevant events at
  that point without any other taxonomy change.
