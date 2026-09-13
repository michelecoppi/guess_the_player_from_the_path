# Issue #61 — first visual review

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

## Follow-up requested for the next agent

This PR intentionally leaves the following items open for the next visual pass:

- Il profilo è ancora graficamente grezzo: controllare bene armadio, stili equipaggiabili e stati correlati.
- L’anteprima dello Shop è ancora buggata e può sovrapporsi: rifare il layout e la gerarchia dell’anteprima.
- Il profilo degli altri utenti è troppo vuoto: mostrare gli stili posseduti e la mini tabella degli stili equipaggiati presente in V1.
- Eliminare il quadrato verde che compare al passaggio sulla riga cliccabile della classifica; resta solo un feedback coerente con il sistema editoriale.
- Portare la classifica da Top 8 a Top 10 e aggiungere la ricerca giocatori, avviata dai primi due caratteri.

The current review harness demonstrates the intended interaction paths with local fixtures; these follow-ups require the final product data and responsive polish.
