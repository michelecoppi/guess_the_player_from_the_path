# Mini App appearance

Primary cosmetic contract (#66, #115, #122). The Vite Mini App is served at `/app`;
`/app/v2` redirects there. Project #2 remains the source of work status.

## Theme and token ownership

### Matchday presentation (#126)

`styles/matchday.css`, loaded after the existing layout and cosmetic rules, owns
the career sheet, final match report, player pass, primary/secondary profile
statistics, Arena match presentation and collection-first Shop layout. It uses
the existing product and scoped skin tokens; it never changes ownership, prices
or the meaning of progress. Arena fractions show completed paths out of total,
not a score against an opponent. All existing modes remain reachable.

Display typography uses locally bundled Barlow Condensed SemiBold (SIL OFL,
`webapp/src/assets/fonts/OFL.txt`) with `font-display: swap`; no third-party font
request is made. Body text retains the system stack. The result entrance obeys
reduced motion and supplements the existing equipped celebration.

The final Daily report shows server-awarded points and a revealed name only when
present in the response. Reopening an already completed Daily shows attempts and
the card action without inventing a score/name absent from `/me`. The profile's
three primary stats are total points, guessed players and current streak; a native
disclosure keeps the four secondary stats accessible by touch and keyboard.

The app starts dark before JavaScript. Telegram and system appearance cannot
change its structural colors; safe-area and viewport subscriptions remain active.
`appearance/index.ts` accepts six-digit hex colors and maps theme `accent`,
`accentText`, `edge`, `track`, `card`, `pattern` and boolean `formation`.
`bg`, `bg2`, `text` and `muted` never replace structural colors. Light surfaces become
a dark tint (30% accent with #0b121b); dark surfaces retain 70% of their card color.
Glow uses 16% accent. Descriptions must describe this result, including Ghiaccio.

The CSS shell applies decorative surface, glow, pattern and accent to the header,
navigation and tabs. Product text, success/error/warning colors, focus, typography,
layout and touch sizes remain product-owned. `skinTokens()` owns seven `--skin-*`
variables. Titles use decorative color while keeping readable product text.
Reviewed gradients belong to `appearance/decorations.ts`. Unknown gradients, CSS
keys and URLs are ignored; legacy grain maps to a local texture. Parsing is idempotent.

## Wire contract and lifecycle

`ResolvedAppearance` represents `domains/shop/service.py::appearance`, returned by
`/app/api/me` and public profiles: eight optional slots plus `equipped` IDs. Ownership,
achievements, completion, prices and equip rules remain backend-authoritative.

- `applyResolvedAppearance()` validates and replaces tokens, returning a detached snapshot.
- `clearResolvedAppearance()` resets tokens and invalidates pending loads; auth changes
  and Daily reset prevent old requests from restoring another user's appearance.
- `identityAppearance()` and `resultAppearance()` project the supplied person's look.
  Public profiles never apply their skin globally.
- No local/session storage. Missing values use presentation fallbacks, not ownership rules.
- New wire styles require parser, renderer, tests and catalogue review together.

## Slots and surfaces

| Slot | Rendering |
| --- | --- |
| theme | Decorative shell and scoped profile. Referral `formation: true` draws eleven players on own/public profiles and Shop try-on. |
| frame | Reviewed avatar ring. General ring spinning stays off. Referral `tactics` accepts only 3 or 11 nodes, with one three-second ball movement. |
| title | Localized backend label near the name, escaped as text. |
| badge | Profile, public profile and supported identity/list surfaces. |
| squares | Daily attempts and results; backend owns shared text. |
| number | Identity string, including leading zero when supplied. |
| celebration | Correct-answer feedback and explicit Shop try-on use the same two-second canvas effect. |
| card | Backend shared image. Finishes: plain, night, foil, grain, tactics, eleven, ticket. Profiles and Shop show a labelled sample. |

The Ultimo minuto collection (#143) adds a reviewed coral scoreboard texture and
segmented avatar ring, with five purchasable core slots. Number 90 and the Stadium
wave celebration are separate purchases. The wave travels across the canvas for two
seconds after a correct answer or explicit Shop try-on; reduced motion suppresses it.
The Mini App keeps structural backgrounds dark, so the plum colour tints scoped
surfaces while coral marks the accent. Bundle ownership uses the existing prorated
quote and all appearance styles pass through the reviewed parser.

Formation entrance and ball movement are finite. `prefers-reduced-motion` disables
these and canvas celebrations while keeping static decorations visible. Referral
cards show a tactical pitch and passing routes; their samples and shared PNGs are static.

## Faithful previews

`components/CosmeticArt.ts` is shared by Shop and profiles. Card samples use
`services/path_image.py::render_share_card`, resized to 400x500. Challenge #412 and
PLAYER are examples, identified by a localized caption. Real shared images keep
the actual user's name and score. Regenerate when styles or the renderer change:

```sh
python -m scripts.shop_previews
```

Commit `webapp/src/assets/card-previews/` and generated `appearance/card-previews.ts`
together. The manifest records catalogue styles and renderer hash with normalized
newlines; tests reject stale/missing samples. Only generated asset URLs are used,
never payload URLs. Images load lazily; Vite fingerprints filenames for caching.

Bundle artwork uses the applied theme's scoped skin and shows included card samples,
including exclusive pieces. Try-on contains one wearer identity; stopping or leaving
Shop restores authoritative appearance. The Away ticket set covers four slots
(theme, frame, title, card); existing full collections cover all five core slots.
Existing signed quotes prorate the missing pieces; no payment API change was needed.

## Review

`tests/test_appearance_contract.py` checks backend theme fixtures;
`tests/frontend/shop-quality.test.ts` checks every real visual style through the
parser, including referral exclusives. `tests/test_shop_quality.py` checks samples,
travel bundle pricing and the ticket's unobscured result area.
Use `scripts/preview_webapp.py` with the real build for 320/390px and desktop checks:
IT/EN/ES, own/public profiles, try-on/restore and reduced motion. This preview has
in-memory users and does not touch Firestore. Browser simulation does not replace
physical Telegram iOS/Android checks.
