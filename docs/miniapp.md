# Mini App architecture

Authoritative description of the Telegram Mini App: the two frontends, how they talk to
the backend and how the V2 rollout is gated. The V2 appearance contract is owned by
[miniapp-appearance.md](miniapp-appearance.md); API performance behavior by
[performance.md](performance.md); local commands by
[local-development.md](local-development.md).

## Two frontends, one backend

| | Legacy Mini App | Mini App V2 |
| --- | --- | --- |
| Route | `GET /app` | `GET /app/v2`, assets at `/app/v2/assets/*` |
| Source | `webapp/index.html`, `webapp/client.js`, `webapp/strings.js`, `webapp/arena.js`, `webapp/arena.css`, `webapp/referrals.js`, `webapp/referrals.css` | [`webapp/src/`](../webapp/src/), entry [`index.html`](../index.html) → `webapp/src/main.ts` |
| Build | none (files served as-is, ETag + revalidation) | Vite + TypeScript (`npm run build` → `webapp/dist/`, built in the Docker frontend stage; `/app/v2` returns 503 if the bundle is missing) |
| Tests | `node --test tests/client.test.cjs` (pure functions and i18n parity) | `npm run test:frontend` (`tests/frontend/*.test.ts`, happy-dom), `npm run typecheck` |
| Status | **Production default.** `config.WEBAPP_URL` is `<PUBLIC_BASE_URL>/app`; the bot's menu button and in-chat buttons open it | Deployed and reachable, **not** the default. No bot button points to it |
| Theme | follows Telegram theme variables | structurally dark-only (`color-scheme: dark`), see below |

Both frontends call the same `POST /app/api/*` endpoints implemented in
[`apps/api/miniapp.py`](../apps/api/miniapp.py) on top of `services/`. There is no V2-specific backend.

## Backend contract and authentication

**Current state.**

- Every Mini App API call is a `POST` with a JSON body containing `initData` from
  `Telegram.WebApp`. `apps/api/miniapp.py::_webapp_user` verifies it with
  [`services/webapp_auth.py`](../services/webapp_auth.py) (HMAC-SHA256 keyed from the
  bot token, max age 24 h), applies the per-user token bucket
  ([`services/rate_limit.py`](../services/rate_limit.py)), and loads the user document
  (404 if the user never ran `/start`). The client never sends a user id.
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
- A feature switched off by a flag answers 403
  `{"detail": "feature_disabled", "code": "FEATURE_DISABLED", "feature": "<key>"}`, and
  `me` carries `features` (resolved booleans only). See [feature-flags.md](feature-flags.md).

## V2 structure

**Current state** (after [#16](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/16),
epic [#17](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/17)
with #40–#48 and #68, visual work #64/#66 and redesign
[#61](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/61), all merged):

| Folder | Responsibility |
| --- | --- |
| `app/` | `App.ts` shell: navigation state, creates one controller per feature, mounts pages |
| `features/<name>/` | Per feature `api.ts` (typed calls), `controller.ts` (state, loading/error, stale-response guards), `types.ts`, `views.ts`. Features: daily, arena, training, events, archive, leaderboard, profile, shop, referral |
| `pages/` | Page composition and event wiring per destination |
| `components/` | Shared UI (CareerPath, GuessInput, NavBar, Header, Modal, states…) |
| `api/` | `ApiClient`: base `/app/api`, injects `initData`, maps errors, clears appearance when the auth token changes |
| `telegram/` | `initTelegram` (`ready`, `expand`), theme/viewport/safe-area subscriptions, typed WebApp API; a mock WebApp is used outside Telegram, which the backend rejects because its `initData` is not signed |
| `appearance/` | Sanitized cosmetic token mapping (see below) |
| `i18n/` | IT/EN/ES strings |
| `utils/legacy-bridge.ts` | Exposes pure helpers under the legacy `window.PlayerClient` names |
| `prototypes/` | Dev-only `?design-review` harness and fixtures (backend-generated appearance/theme fixtures are contract-tested by `tests/test_appearance_contract.py`); excluded from the production bundle |

Navigation: Daily, Arena (hub for duels, events, archive and training), Classifica,
Shop, Profilo; referral lives under Profile.

## Appearance (summary)

V2 is structurally dark-only: product-owned tokens define structure, readability and
interaction states, and Telegram light/system preferences cannot change them.
Cosmetics are resolved by the backend (`domains/shop/service.py::appearance`) and applied
only through an allowlist of sanitized decorative tokens. There are eight cosmetic
slots — `theme`, `frame`, `title`, `badge`, `squares`, `number`, `celebration`, `card` —
and ownership, pricing and equip rules stay in Python. The full contract, token
ownership and surface mapping are in [miniapp-appearance.md](miniapp-appearance.md).

## Rollout gate

**Current state.** Production users use `/app`. Legacy files remain in place and must
not be removed or redirected as part of feature work.

**Planned evolution.**

1. [#81](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/81) —
   final V2 review of every real cosmetic on every surface, isolation/state checks and
   bug hunt. It is intended as the last V2 issue, after other open work, with human
   approval.
2. A **separate rollout issue**, opened only after #81 is closed, will switch the
   public entry point from `/app` to `/app/v2`. No other issue or PR should perform the
   switch.

## Local development

- Real API from the Vite dev server: `npm run dev` (port 5173, proxies `/app/api` to
  `localhost:8000`) plus the API (`python -m tools.dev api`); gameplay needs valid
  Telegram `initData`.
- Isolated previews without Telegram or Firestore: `python -m tools.dev webapp`
  (`scripts/preview_webapp.py`, serves `/app` and `/app/v2` with an in-memory user) and
  the dev-only `?design-review` harness.
- Required checks for frontend changes: `npm run typecheck`, `npm test`,
  `npm run build`, `npm audit --audit-level=high`, and
  `python -m pytest -q tests/test_webapp_v2_serving.py tests/test_webapp_api.py tests/test_webapp_auth.py`.
