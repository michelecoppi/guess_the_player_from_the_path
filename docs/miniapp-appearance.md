# Mini App appearance

Primary cosmetic contract (#66, #115, #122). The Vite Mini App is served at `/app`. Project #2 remains the source of work status.

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
navigation and tabs. `styles/cosmetic-effects.css` (loaded last) extends that to every
tab: inside `[data-cosmetic-shell]` the structural `--bg`, `--bg-secondary`, `--card`,
`--edge` and `--track` are derived from the scoped skin (darkened or lightly lifted
`--skin-profile-surface`, never the theme's own `bg`/`bg2`), and the decorative
brand-green highlights (active nav pill, own leaderboard row, mode icons, featured Arena
card via `--sport-*`, referral hero) use `--skin-soft`. Accent-as-text on those surfaces
(own row, back links, Daily status) uses `--skin-ink`, a lift of the accent toward
`--text`, so deep accents stay readable. Real results keep `--success`/`--success-bg`. Product text, success/error/warning colors, focus, typography,
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
| frame | Reviewed avatar ring. General ring spinning stays off. Referral `tactics` accepts only 3 or 11 nodes, with one three-second ball movement. Optional `motion` (`shine`, `pulse`, `orbit`) plays three times when the avatar appears, as `data-motion` on the ring. |
| title | Localized backend label near the name, escaped as text. |
| badge | Profile, public profile and supported identity/list surfaces. |
| squares | Daily attempts and results; backend owns shared text. |
| number | Identity string, including leading zero when supplied. |
| celebration | Correct-answer feedback and explicit Shop try-on use the same two-second canvas effect. |
| card | Backend shared image. Finishes: plain, night, foil, grain, tactics, eleven, ticket, aurora, pixel, halftone. The last three decorate only the edges; the attempts/score band is pixel-identical to plain. Profiles and Shop show a labelled sample. |

The Ultimo minuto collection (#143) adds a reviewed coral scoreboard texture and
segmented avatar ring, with five purchasable core slots. Number 90 and the Stadium
wave celebration are separate purchases. The wave travels across the canvas for two
seconds after a correct answer or explicit Shop try-on; reduced motion suppresses it.
The Mini App keeps structural backgrounds dark, so the plum colour tints scoped
surfaces while coral marks the accent. Bundle ownership uses the existing prorated
quote and all appearance styles pass through the reviewed parser.

### Animated collections

Seven collections add ambient theme motion: Aurora boreale, Coreografia, Sala giochi,
Hanami, Beach soccer, Pallone cosmico and Derby sotto il diluvio. Each fills the five
core slots, some add a card finish (aurora, halftone, pixel) and/or a celebration
(petals, pixels, comets, bubbles, flares, lightning), and single numbers, titles,
badges and the bouncing-ball celebration are sold separately. Theme `motion` is a
reviewed id (`float`, `twinkle`, `breathe`) mapped by `THEME_MOTIONS` to the
`--skin-motion` animation shorthand. It only moves (vertically, within a 24px
oversize) or fades the decorative pattern layer of the shell, profiles, event
boards and Shop stages. Surfaces clip vertical overflow, so motion never adds
scroll. Unknown motion values are dropped by the parser.

Formation entrance and ball movement are finite. `prefers-reduced-motion` disables
these, theme motion, frame flourishes and canvas celebrations while keeping static
decorations visible. Referral
cards show a tactical pitch and passing routes; their samples and shared PNGs are static.

### Shop navigation (#153)

The Mini App Shop opens on a short Discover page with a small set of featured
collections and weekly picks. Catalogue is a separate searchable list with visible
category chips, price and ownership filters, and 24 items per page. Each card opens
a product detail that names the surface the cosmetic changes, shows the existing
faithful preview and, for bundles, lists included pieces and their ownership.
The displayed price is the server-calculated `price`, including bundle proration;
no frontend price calculation or payment rule changes. My items holds the current
outfit, saved looks and owned items. Achievements and purchase history remain
available from secondary Shop navigation. Preview remains temporary and leaving
Shop restores the authoritative appearance.

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
