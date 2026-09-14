# Issue #61 — visual review and PR #78 follow-up

Base: `114df2227d5792ece9234246343475c8288ba9bb`.
Branch: `feat/61-final-v2-ux`, dedicated worktree `.worktrees/issue-61`.

This is a first review proposal, not completion of #61. The user requested a
visible result to approve or adjust before finalization. No merge or rollout.

Run `npm ci`, then `npm run dev -- --host 127.0.0.1 --port 5176 --strictPort`.
Open `http://127.0.0.1:5176/app/v2/?design-review`.
The review controls below the content select 17 real feature views, IT/EN/ES,
appearance fixtures, and supported example states. These are local rendering
snapshots, not a connected game: purchase, persistence, and API actions do not run.
Some interaction buttons are deliberately not wired in the visual harness;
use the view selector. Production controllers and routing are unchanged.

## Findings and proposal

- The old review harness still showed migration prototypes outside Daily.
  Replace them with production renderers and typed sample fixtures.
- Career information was enclosed in a rounded card. Use an open transfer
  sheet with square sequence nodes, strong club names and aligned seasons.
- Shared styles have grown to approximately 3,800 lines. The proposed
  editorial layer is separate; consolidation of the existing file remains.
- Profile repeated containers and had a second h1. Use section dividers,
  aligned statistics and an h3 for player identity below the page title.
- Shop's rotated decorative pitch overflowed the viewport. Contain it within
  the header; use the shared SVG family for its four navigation tabs.
- Referral passing animation restored after user review; preserve reduced-motion
  and pause off-screen through the existing observer.
- Keep all structural dark and protected semantic tokens, appearance resolution
  and all eight cosmetic slots unchanged.

## Evidence and checks

- `npm ci`, `npm run typecheck`, `npm test`: 324 tests pass.
- Production build passed; npm audit reported zero vulnerabilities.
- Real browser overflow checks: all 16 sample views pass at a 320px viewport
  (305px content with Windows scrollbar). Initial 390px check found Shop's
  decorative overflow, fixed in this proposal.
- Local `review-evidence/`: mobile screenshots of all views, desktop captures
  of seven core views, Daily wrong/correct/loading/error examples.
- Review fixtures/styles are development-only, excluded from production build.

## Still required before completing #61

Human direction review; complete state/interaction inventory and visual polish;
full responsive/language/long-content matrix; modal, focus, keyboard and real
Telegram device validation; CSS consolidation; backend/security/dev checks;
final PR and green CI on its exact head. Do not use `Closes #61` yet.

## Interaction review correction

The first harness omitted working interactions. Search now filters sample users
and opens a sample duel; leaderboard names open real public-profile rendering.
Shop try-on uses the shared sanitized appearance builder; equip persists across
page navigation for this review session. Mock acquisition changes only local
ownership and explicitly spends no Stars. Refreshing the page resets the demo.
Referral reward previews and animated passing are connected, and invite/copy
actions explicitly report that no message or real invitation is sent.
Public profiles now display resolved frames and titles as well as badge/number.
Regression tests cover search, profile open/close, cumulative equip, preview
restoration and absence of network calls.

Browser verification confirmed sample search, public-profile opening, equipped number persistence and changing ball offset-distance. Fixed the existing player entrance keyframes so they no longer override SVG formation transforms. Final production build passed.

## Profile themes, preview and mode navigation review

Decorative theme tokens now cover the full own/public profile surface and the
expanded Shop preview. Each profile scopes sanitized skin tokens, preventing a
public profile from inheriting the viewer's theme. Structural colors remain
product-owned. Preview includes large identity, selected artwork, description
and equip for owned items. Sample frame/theme/card paints now use accepted
appearance fixtures.

Arena now has four destinations: Duels (search, open games, expandable history),
Events, Archive and Training. The new duel-list subview uses the existing list
request; scoring/session rules are unchanged. Review leagues now switch between
two fixtures, with member profiles. Tests exercise the updated navigation path
and theme isolation. 324 tests pass; typecheck/build pass.
Browser checks: themed profile and Arena have no horizontal overflow at 320px.
Screenshot: review-evidence/profile-themed-mobile.png.

## Follow-up requested by the reviewer — implemented 2026-09-14

The five requested changes are implemented in PR #78 and ready for visual review:

- [x] Il profilo è ancora graficamente grezzo: controllare bene armadio, stili equipaggiabili e stati correlati.
- [x] L’anteprima dello Shop è ancora buggata e può sovrapporsi: rifare il layout e la gerarchia dell’anteprima.
- [x] Il profilo degli altri utenti è troppo vuoto: mostrare gli stili posseduti e la mini tabella degli stili equipaggiati presente in V1.
- [x] Eliminare il quadrato verde che compare al passaggio sulla riga cliccabile della classifica; resta solo un feedback coerente con il sistema editoriale.
- [x] Portare la classifica da Top 8 a Top 10 e aggiungere la ricerca giocatori, avviata dai primi due caratteri.

### Implementation and review links

- Own/public profiles and the wardrobe share an eight-slot outfit sheet. Public profiles also show the owned collection, grouped by category. The additive `wardrobe` field contains only item ID, kind and localized name, resolved from valid ownership; saved looks and payment data stay private. The existing `wearing` response stays compatible. Own inventory refreshes on the next profile visit after leaving Shop.
- Shop try-on separates player identity from product artwork, description and equip action. Its theme stays inside its bounds instead of inheriting the full-page profile bleed. Preview triggers now take their own space below artwork. Non-equippable owned items never expose an equip action; equip is disabled during an appearance mutation.
- Leaderboard names use an underline and neutral row hover, retaining a keyboard focus outline. Top 10 uses the existing ten-row backend result. Independent name-prefix search calls `/profile/search` after two characters with a 250 ms debounce, stale-response guards, loading/error/empty states, retry and caret preservation.
- The review demo supports search (including Valentina outside the Top 10), public profiles, cumulative equip and local saved-look save/wear/delete. Refresh resets the demo. Production controllers use authenticated APIs; demo actions make no network calls.

Start the local Vite server as above, then open:

- [Shop try-on](http://127.0.0.1:5176/app/v2/?design-review&view=Shop&try=review-frame)
- [Own profile](http://127.0.0.1:5176/app/v2/?design-review&view=Profilo)
- [Wardrobe](http://127.0.0.1:5176/app/v2/?design-review&view=Guardaroba)
- [Top 10 and profile search](http://127.0.0.1:5176/app/v2/?design-review&view=Classifica)

### Verification

- Typecheck, 329 frontend tests, production build and diff whitespace checks pass.
- 53 targeted backend tests pass (public profiles, webapp API, performance and V2 serving); Ruff passes for touched Python files.
- Security check passes using the repository's existing documented dependency/baseline exceptions.
- Browser: all 18 review views fit 320 px (305 px content with Windows scrollbar); the four modified views also fit in EN and ES. Shop try-on and profile/ranking checks cover mobile and desktop.
- Local screenshots: `review-evidence/followup/`, including Daily ready/wrong/correct/loading/error at 390 × 844 and 1280 × 800, plus the modified views. Dark structure under Telegram/system light is covered by the existing theme regression test; physical Telegram validation remains pending.

Human visual approval and the remaining global #61 gates above are still pending. This PR remains `Refs #61`, with no merge or production rollout.

### Second pass on the follow-up — 2026-09-14

A browser review of the first pass found the remaining gaps below; all are fixed.

- Ranking search: the input rendered without any style (transparent, borderless), so only its label was visible. It now has a field surface, placeholder and focus ring.
- Outfit sheet: customised slots carry an accent marker and strong weight; starter styles are muted. The heading counts customised slots (`3 su 8 personalizzati`) instead of repeating "Indossato".
- Owned collection: free starter styles are no longer listed (the public `wardrobe` projection adds a boolean `free`); styles are chips grouped by category, with the worn ones highlighted. The native disclosure marker is replaced by a count pill and chevron.
- Public profile: the outfit resolves from `cosmetics.equipped` + `wardrobe`, falling back to `wearing`; stat tiles and shirt number match the own profile.
- Shop try-on: product name, description, equip action, then a muted disclaimer.

Verification: typecheck, 330 frontend tests, production build, 43 public-profile/webapp API tests and Ruff pass. Browser: the four modified views have no horizontal overflow at 320 px; Shop try-on checked at 390 px and 1280 px; equip from Shop is reflected in Profile; search `Va` opens Valentina with 3/8 customised slots.

### Profile theme backgrounds — 2026-09-14

Reviewer feedback: a purchased theme was not visible behind the profile.

- Cause: the profile surface mixed only 12% of the theme card into the default navy, so Terra rossa, Neon or Oro di notte looked like the free profile; light themes (Ghiaccio, Carta ingiallita, Domenica '90) turned into flat grey. The Shop theme artwork also ignored the theme colours.
- Surface: dark themes now keep 70% of their own card colour; light themes become a deep tint (30%) of their accent, so product-owned light text stays legible. A new decorative `--skin-profile-glow` adds a soft accent glow at the top. Glow and pattern span the full viewport width (`::before`, horizontal overflow clipped on `html`).
- Inside a themed profile, divider lines, avatar disc, trophy chip, attempt bars and the Shop/Referral entries follow the surface instead of painting default navy. Primary actions and the best-attempt bar stay product green.
- Shop theme cards show the same surface the owner's profile will get.
- Contrast: muted text is ≥ 4.78:1 and body text ≥ 9:1 on every real theme, including the glow (worst case Calcio di strada / Il tuo undici).

Real-data proof: `webapp/src/prototypes/theme-fixtures.json` is generated from `services/shop.py::appearance` for all 16 themes in `data/shop.json`, and `tests/test_appearance_contract.py` fails if a theme is added or the resolver changes without refreshing it.

- [Theme gallery, all 16 real themes](http://127.0.0.1:5176/app/v2/?design-review&view=Temi%20profilo) — each tile is the real public-profile renderer; "Profilo completo" opens the own profile with that theme.
- Own profile with one theme: `&view=Profilo&theme=<id>`, e.g. [Neon](http://127.0.0.1:5176/app/v2/?design-review&view=Profilo&theme=neon). The review controls also offer a "Tema reale" selector.

Screenshots committed in `review-evidence/themes/`: `00-galleria-prima-1280.png` (previous formula reconstructed on the same page), `01-galleria-dopo-1280.png`, and full own profiles at 390 px for Terra rossa, Ghiaccio, Neon, Notti europee, Calcio di strada and Oro del podio. No horizontal overflow at 320, 390 or 1280 px. 331 frontend tests, 68 backend tests, typecheck and build pass. Review fixtures are not in the production bundle.
