# V2 appearance policy (#66)

V2 is structurally dark before JavaScript loads. Telegram light/dark and system
preferences cannot choose its colors. `connectTheme` retains theme, viewport and
both safe-area event subscriptions; CSS still combines device and Telegram insets.
No theme toggle, backend changes, catalog products, or legacy `/app` changes.

## Token ownership

Product-owned: `--bg`, `--bg-secondary`, `--card`, `--text`, `--muted`, `--edge`,
`--track`, `--accent`, `--accent-text`, `--danger`, `--danger-bg`, `--warn`,
`--warn-bg`, `--success`, `--success-bg`, `--focus`, `--disabled-opacity`,
`--sport-surface`, `--sport-text`, `--sport-highlight`, all font, radius, touch,
transition, spacing, layout and safe-area tokens. Interaction green is deliberately
independent of decorative accent. Focus and success no longer depend on cosmetics.

Cosmetic theme allowlist (wire key -> V2 token):

| Wire key | Decorative token | Use |
| --- | --- | --- |
| accent | --skin-accent | Daily edition edge, identity decoration |
| edge | --skin-accent-secondary | Non-semantic identity border |
| track | --skin-pitch | Decorative pitch/career mark |
| card | --skin-profile-surface | 12% tint mixed with fixed dark #1a2734 |
| pattern | --skin-pattern | Reviewed identity texture |

The mapper never writes arbitrary property names. Colors require six-digit hex;
gradients require exact membership in `appearance/decorations.ts`, a reviewed
visual vocabulary without item IDs or business rules. The legacy grain SVG maps
to a local CSS texture. Unknown gradients, URLs and unknown keys are ignored.
Theme bg/bg2/text/muted/accentText cannot alter V2 structure or readability.
Decorative tokens must not be used for readable text or interactive states.
Title color decorates a border, while the label retains readable product text.

## Contract and lifecycle

`appearance/types.ts::ResolvedAppearance` represents `services/shop.py::appearance`,
returned under `/app/api/me.cosmetics` and public-profile `cosmetics`:
`equipped?`, `theme?`, `frame?`, `title?`, `badge?` (string), `squares?`,
`number?` (string, preserves leading zero), `celebration?` (effect string), `card?`.
Style objects retain wire names. All eight slots share one `CosmeticSlot` type.
Shop products use backend `kind` (including bundle), `price`, `owned`, `free`,
`equipped`, `rarity`, etc.; these are server results, never recomputed in TypeScript.
Ownership, default item IDs, earned/collection completion, pricing/refunds and equip
validation remain solely in Python. No additive API change was needed.

- `applyResolvedAppearance(unknown)` validates, replaces every supported token and
  returns a detached sanitized value. Reapplying is idempotent.
- `getResolvedAppearance()` exposes a detached snapshot to current-user consumers.
- `clearResolvedAppearance()` resets all skin/data and invalidates pending loads.
- `identityAppearance(payload)` and `resultAppearance(payload)` are pure surface
  projections; pass the target user's payload for public/list contexts, never apply
  somebody else's skin globally. Renderers in `appearance/surfaces.ts` escape text.
- Daily consumes `/me.cosmetics`, resets before full reload, clears on load failure,
  and ignores old responses after reset/newer load. `DailyController.reset()` is the
  integration hook before a future logout/user replacement. App initialization calls
  it. API auth-token changes clear skin; old-session responses are rejected.
- No local/session storage. A fresh page always starts with the dark product base.

Missing/partial/malformed payloads never trigger catalog resolution: available safe
fields are retained, other fields are omitted/empty. Missing attempt symbols use
product presentation fallbacks, not item ownership defaults. Unknown future slots,
style keys, effects and finishes are ignored until explicitly supported.

## Surface mapping

| Slot | Surface and limits |
| --- | --- |
| theme | Controlled global decorative skin; never structure/semantics |
| frame | Avatar/identity only; reviewed ring paint, static in V2 even if spin=true |
| title | Near username; localized label from backend, escaped as text |
| badge | Profile/public/leaderboard identity, where the consuming surface supports it |
| squares | Daily attempts and result/share projection; server owns shared text |
| number | Player/profile identity only; string, including 01 |
| celebration | Correct-answer feedback only; empty means none; reduced motion disables |
| card | Result-image frame: plain/night/foil/grain; --result-finish-accent from safe glow |

Share-card pixels (including ink/paper) remain rendered by the backend `/card`.
No client reconstruction or recoloring of the image. Card appearance is exposed for
future previews. Frame spinning stays off to avoid perpetual decoration.

## Fixtures and review

`prototypes/appearance-fixtures.json` contains backend-generated snapshots checked
by `tests/test_appearance_contract.py`: default, captain frame + scout title + football
badge, full Neve collection plus number 10/night card/earned snow celebration,
football squares, Ghiaccio theme, number 7, confetti, and foil card. Fixtures have no
ownership logic. The dev-only `?design-review` appearance selector demonstrates them
with an identity sample and Daily symbols. This does not implement Profile or Shop.

Deferred: #42/#45 functional identity/catalog/equip/purchase flows, other migration
consumers, #61 final visual polish and human device review. Legacy `/app` remains
untouched and no production route rollout is part of this work.
