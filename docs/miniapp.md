# Mini App architecture

Authoritative description of the Telegram Mini App: the frontend, how it talks to the
backend and how it is served. The appearance contract is owned by
[miniapp-appearance.md](miniapp-appearance.md); API performance behavior by
[performance.md](performance.md); local commands by
[local-development.md](local-development.md).

## One frontend, served on `/app`

| | |
| --- | --- |
| Route | `GET /app` (ETag + revalidation), assets at `/app/assets/*` (hashed names, immutable cache, path containment; source maps hidden and never served, #181) |
| Source | [`webapp/src/`](../webapp/src/), entry [`index.html`](../index.html) → `webapp/src/main.ts` |
| Build | Vite + TypeScript (`npm run build` → `webapp/dist/`, built in the Docker frontend stage; `/app` returns 503 if the bundle is missing) |
| Tests | `npm run test:frontend` (`tests/frontend/*.test.ts`, happy-dom), `npm run typecheck` |
| Entry points | `config.WEBAPP_URL` is `<PUBLIC_BASE_URL>/app`; the bot's menu button and in-chat buttons open it |
| Theme | structurally dark-only (`color-scheme: dark`), see below |

The frontend calls the `POST /app/api/*` endpoints implemented in
[`apps/api/miniapp.py`](../apps/api/miniapp.py) on top of `services/`.

**History.** Until the rollout of #81/#115 the production app was a plain HTML/JS page
(`webapp/index.html`, `client.js`, …) on `/app` and this frontend lived on `/app/v2`. The
old page is gone, `/app` serves the Vite build, and the `/app/v2` path was removed (#146).
"V2" in older issues, PRs and review documents means this frontend.

## Backend contract and authentication

The successful Daily `guess` response also includes optional `answer`, the display
name resolved on the server after a confirmed correct result (#126). It is not
included in the active challenge or unsuccessful in-progress guesses. Shared text
and cards remain spoiler-free. Points continue to come from `points_awarded`.

A wrong Daily `guess` response also carries `today` (#259): the same projection as the `today`
block of `/app/api/me`, with the attempts and hints just recorded. The client draws it
directly instead of requesting `/app/api/me` again; without the field (older servers) it
falls back to a lightweight refresh.

**Native share (#185).** On Bot API 8.0+ clients the Daily "Share" button uses
`WebApp.shareMessage`, which only takes the id of a message the bot prepared:

1. when the game ends, the page calls `POST /app/api/share/prepare` (rate cost 10);
2. the server rebuilds the result from the saved history (`webapp_api.todays_result`,
   never from the page; the range checks live in `services/daily_result.py` and are shared
   with the bot's "📸 card" button, whose payload carries only the day - #222), renders the figurina and the chat card text with the sharer's
   invite link, uploads the image once to the private storage chat
   `SHARE_STORAGE_CHAT_ID` (`file_id` cached per process by image hash) and calls
   `savePreparedInlineMessage` (photo + caption + "Play too" link button; user, group and
   channel chats) - see [`apps/api/share_message.py`](../apps/api/share_message.py);
3. the tap calls `shareMessage(id)` synchronously; when Telegram confirms the send the page
   reports `POST /app/api/share/sent` (analytics `result_shared`).

Without a prepared, unexpired message (no storage chat configured → 503
`share_unavailable`, Telegram throttling, older client, new look equipped) the button
keeps the classic `t.me/share/url` link; the copy button is unchanged. A public URL of
the card is deliberately never created: the card shows the player's name.

**Current state.**

- Every Mini App API call is a `POST` with a JSON body containing `initData` from
  `Telegram.WebApp`. `apps/api/miniapp.py::_webapp_user` verifies it with
  [`services/webapp_auth.py`](../services/webapp_auth.py) (HMAC-SHA256 keyed from the
  bot token, max age 24 h), applies the per-user token bucket
  ([`services/rate_limit.py`](../services/rate_limit.py)), and loads the user document
  (404 if the user never ran `/start`). The client never sends a user id.
- Malformed field types and oversized client strings return 422 before a game move,
  payment link or support message. `initData` must be a string of at most 4096
  characters; missing or empty authentication still returns 401. Daily and Archive
  `guess.answer` must be nonblank text of at most 220 characters. Optional `day`
  and `expected_day` values use ISO dates; the absent `expected_day` remains
  accepted for older clients. Support reports accept at most 3500 characters.
- A rejected `initData` (expired after 24 h or invalid) returns 401. Telegram keeps a
  minimised Mini App alive, so this is what a session resumed the next day gets: the
  `ApiClient` notifies `onSessionExpired` listeners and `App` replaces the whole shell
  with a "Sessione scaduta" screen whose button calls `Telegram.WebApp.close()`;
  reopening from the bot chat signs a fresh `initData` (#179).
- Telegram's native back arrow (and the Android back gesture) is driven by `App` (#182): it
  taps the page's own back control (a modal's `[data-telegram-back]` button first, then the
  page's `.back-link`), otherwise returns to the Daily; on the Daily it is hidden, so back
  closes the Mini App. A new sub-screen or modal only needs one of those markers on its
  back/close button.
- Responses are explicit projections built in services (`services/webapp_api.py`,
  `services/arena.py`, `services/app_events.py`, `domains/shop/service.py`,
  `domains/referrals/service.py`, `services/trophies.py`). Answers, accepted aliases and
  unpaid hints are never serialized; prices come from the server catalogue.
- Endpoints: `me`, `profile/public`, `profile/search`, `referrals`, `guess`, `hint`,
  `arena` (`mode`: `training` | `duel` | `events`), `calendar`, `league`, `shop`,
  `shop/buy`, `shop/equip`, `shop/look`, `shop/history`, `card`, `trophies/pin`, and
  `perf` (startup timing beacon: signature and rate limit only, no user document read, see
  [performance.md](performance.md)). The route list in `apps/api/miniapp.py` is authoritative.
- Mutating moves in Training, duels and events carry a `revision`; the server answers
  409 when the state changed and the client reloads.
  Blind Career events use the same `/app/api/arena` route with `mode: "events"` and
  `action: "reveal"` to uncover one career stop. For this type, guesses and reveals
  use `progress.revision`; other event types continue to use attempts as their revision.
  `career_path` in the response contains only the stops already shown to that user.
- A feature switched off by a flag answers 403
  `{"detail": "feature_disabled", "code": "FEATURE_DISABLED", "feature": "<key>"}`, and
  `me` carries `features` (resolved booleans only). See [feature-flags.md](feature-flags.md).
- Daily `guess` and `hint` carry the day shown by the client as `expected_day`.
  A page left open across midnight receives 409 `{"detail":"daily_changed"}` before
  consuming a guess or hint; the client reloads the new Daily. Older clients without
  `expected_day` remain accepted during rollout.
- `card` renders only a finished current Daily from the user's saved history. It does not
  trust the browser's attempts, result, hints or streak. Legacy card fields are accepted
  with type validation but ignored so an already open Mini App can still load its card.

## Frontend structure

**Current state** (after [#16](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/16),
epic [#17](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/17)
with #40–#48 and #68, visual work #64/#66 and redesign
[#61](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/61), all merged):

| Folder | Responsibility |
| --- | --- |
| `app/` | `Router.ts` tracks destinations, `PageRenderer.ts` selects the active page and `ShellRenderer.ts` keeps the shell mounted while updating the active screen; `App.ts` wires controllers and listeners. The Shop, Story and Events **views** are separate chunks (`lazy.ts`, dynamic `import()`, #187): a loading state until the chunk arrives, an error with retry if it fails, and `bootstrap.ts` prefetches them ~1 s after the Daily is on screen. Their controllers stay in the main bundle (they hold state the shell syncs across features). A new heavy page can be split the same way |
| `features/<name>/` | Per feature `api.ts` (typed calls), `controller.ts` (state, loading/error, stale-response guards), `types.ts`, `views.ts`. Features: daily, arena, training, events, archive, leaderboard, profile, shop, referral |
| `pages/` | Page composition and event wiring per destination |
| `components/` | Shared UI (CareerPath, GuessInput, NavBar, Header, Modal, states…) |
| `api/` | `ApiClient`: base `/app/api`, injects `initData`, maps errors, clears appearance when the auth token changes |
| `telegram/` | `initTelegram` (`ready`, `expand`, `disableVerticalSwipes` on Bot API 7.7+ so scrolling lists cannot swipe the app closed), theme/viewport/safe-area subscriptions, typed WebApp API (including the optional `BackButton`); a mock WebApp is used outside Telegram, which the backend rejects because its `initData` is not signed |
| `appearance/` | Sanitized cosmetic token mapping (see below) |
| `i18n/` | IT/EN/ES strings |
| `prototypes/` | Dev-only `?design-review` harness and fixtures (backend-generated appearance/theme fixtures are contract-tested by `tests/test_appearance_contract.py`); excluded from the production bundle |

Navigation: Daily, Arena (hub for duels, events, archive and training), Classifica,
Shop, Profilo; referral lives under Profile.

The Profile shows "Your recent days" (#273), the last 30 Daily challenges as a calendar,
Monday first. The data is the existing `calendar` endpoint (the archive's list: `solved`,
`lost`, `recovered`, `missed` and the attempts), fetched in parallel with `me`; a failed
calendar leaves the card out and never blocks the Profile. The card is a `<details>` closed
by default, with the played/solved summary visible; its open state is kept across re-renders
(recorded on the summary click, because the async `toggle` event is lost when a refresh
replaces the element). Every state has a shape as well as a colour (dot = first attempt,
full = solved, ring = recovered, slash = lost, dashed = skipped) and "lost" is neutral grey,
so the calendar stays readable on every cosmetic theme, red and pink accents included.
Tapping a day shows its detail, with a link to the archive while it can still be played.
The layout follows the card width (container query): full width on phones, calendar on the
left and detail and legend beside it on wider cards.

Classifica has three tabs, in this order: **Del mese** (top 10 by `monthly_points`,
open by default because everyone restarts from zero on the 1st), **Generale** (top 10
by all-time points) and **Le tue leghe**. Both rankings come from the full `me` payload
(`monthly_leaderboard` and `leaderboard`, same row shape; `points` is the monthly score
in the first) and are empty lists when the `leaderboard` flag is off (#256).

On Telegram clients with Bot API 6.2+, the close confirmation is enabled while an
unfinished Arena duel or playable event detail is visible. It is disabled when the
match finishes, the user leaves that view, or the session expires. Daily and other
screens do not request confirmation.

The initial Daily uses `me` with `lightweight: true`; once it is on screen the running
events are loaded for the announcement below. Arena's duel list loads only
when Arena is opened (unless a duel invite deep link is present). Returning to a visible
Daily refreshes its state. New players see a dismissible three-step guide before their
first attempt. Its seen marker is stored locally under a key scoped to the Telegram user;
no guide state is sent to the server.

Once the Daily is over (#254) the result comes first: the answer desk with the final report
moves above the career, which folds into a "Show the career" row (`<details>`). The report
keeps its share actions in one row (Telegram share, then copy and card as icon buttons with
accessible names) and previews the result card as a small thumbnail that enlarges in place
on tap. The card is fetched automatically only right after a game (`submitGuess` →
`loadResultCard`); reopening a finished Daily asks for it on demand, so no PNG is rendered
on every app open.

On narrow screens, an active Daily keeps a small answer shortcut above the fixed
navigation while the career path is in view. It focuses the existing guess field and
disappears when that field is visible or the challenge is complete. Standard path
events use the same career-sheet and answer-desk presentation as Daily; every event's
answer box has the Daily's shape (attempt squares, the shared `renderGuessInput` field and
button, bonus note) (#250). Answer fields keep what is typed in the controller without
re-rendering the page: a re-render per keystroke rebuilt the input and moved the caret to
the start, reversing the text (Events and duels, #250). Arena mode
entries are compact on mobile; leaderboard search expands on request so the Top 10
appears first. Shop keeps the Discover introduction and uses a shorter header and
filters on mobile, especially in Catalogue. These are presentation changes; gameplay,
event attempts, purchases and API contracts are unchanged.

## Running event announcement

**Current state** ([#248](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/248)).
A running event is announced outside its own page, from `webapp/src/features/events/spotlight.ts`:

- **Arena hub card** on top of the Arena modes: event name, time left (days, or hours to
  the Italian midnight on the last day), today's points, first-solver bonus while available,
  podium trophies, and the player's state for today. The whole card is one button that opens
  that event directly.
- **"Up next" in the Daily's final report** (#252): once the Daily is over (won or lost), the
  final report carries a compact invitation (name, time left, today's points, arrow button),
  only while the event is still to play today. This is the only place the Daily mentions the
  event: a Daily still to play shows nothing about it (#266; the top banner of #248 was
  removed so that the event never comes before the game the app opens on).
- **Dot on the Arena tab** of the nav bar while an event is available and not yet finished
  today (`progress.finished`); its accessible name says so. It clears as soon as the guess
  response updates the events state.

An event still to play is preferred. Once today's round is played (solved or out of
attempts) the Daily invitation and the dot disappear; the Arena card stays as a quiet recap
("Solved today · +N pts" or "No attempts left"). The events are loaded once, in the
background, after the first Daily load (`App.init` → `whenFirstLoaded`), with the existing
`/app/api/arena` `mode: "events"` call; no new endpoint or field. No event, a loading or a
failed request shows nothing. Opening the Events page sends `entry` (`daily_result`,
`arena_card`, `arena_list`; `daily_banner` is still accepted from clients on the old page) so
the server records `event_viewed`; the background load
sends none and is never counted ([product-analytics.md](product-analytics.md)).

## Monthly recap ("Wrapped")

**Current state** ([#245](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/245)).
An animated, story-style summary of a closed month, in `webapp/src/features/recap/`:

- **Where.** A banner at the top of the Daily tab from the 1st to the 7th of the month, until the
  recap is watched on that device (`localStorage` key `gtp.recap.seen`), and a permanent
  "Your recaps" entry in the Profile. The banner calls the API only in that week; `?recap` in
  the URL forces it for local demos.
- **What.** `POST /app/api/recap` (`services/monthly_recap.py`) returns, for one of the last three
  closed months: days played on a calendar, players guessed and the attempts distribution, the
  longest streak, the "gem" (the solved Daily with the lowest solve rate, with its career), the
  lucky club (most frequent club among the guessed careers), a play-style title, "better than
  X%" of the month's players and the first-to-answer count. Parts without data are omitted and
  their slide is skipped.
- **Threshold.** Fewer than `MIN_PLAYED` (8) days played: no recap, the entry explains why.
- **Cost.** Computed on first open from the Daily history and the solved `daily_path` documents,
  then cached on the user (`recaps.{month}`) once the month's closure exists.
- **Share.** `POST /app/api/recap/share` prepares the server-drawn card
  (`monthly_recap.recap_card_png`) for `WebApp.shareMessage`, like the Daily card; without a
  storage chat the page falls back to the classic share link.
- **Cosmetics.** The story wears the equipped theme: the overlay maps the same `--skin-*`
  tokens as the app shell (`.recap-overlay` in `styles/recap.css`), with success/warning/danger
  colours still product-owned. The final card, in the story and in the shared image
  (`path_image.render_recap_card`), wears the equipped card cosmetic (paper, ink, glow and
  finish), title and shirt number, like the Daily result card (`webapp_api.recap_look`).
- **Motion.** Tap right/left or arrow keys to move, hold (or Space) to pause, Escape to close;
  `prefers-reduced-motion` turns the animations off.

## Appearance (summary)

The Mini App is structurally dark-only: product-owned tokens define structure, readability and
interaction states, and Telegram light/system preferences cannot change them.
Cosmetics are resolved by the backend (`domains/shop/service.py::appearance`) and applied
only through an allowlist of sanitized decorative tokens. There are eight cosmetic
slots — `theme`, `frame`, `title`, `badge`, `squares`, `number`, `celebration`, `card` —
and ownership, pricing and equip rules stay in Python. The full contract, token
ownership and surface mapping are in [miniapp-appearance.md](miniapp-appearance.md).

## Local development

- Real API from the Vite dev server: `npm run dev` (port 5173, proxies `/app/api` to
  `localhost:8000`) plus the API (`python -m tools.dev api`); gameplay needs valid
  Telegram `initData`.
- Isolated previews without Telegram or Firestore: `python -m tools.dev webapp`
  (`scripts/preview_webapp.py`, serves the built `/app` with an in-memory user) and
  the dev-only `?design-review` harness.
- Required checks for frontend changes: `npm run typecheck`, `npm test`,
  `npm run build`, `npm audit --audit-level=high`, and
  `python -m pytest -q tests/test_webapp_serving.py tests/test_webapp_api.py tests/test_webapp_auth.py`.
