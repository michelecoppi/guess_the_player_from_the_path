# Mini App V2 — match programme

Issue #64. Frontend foundation; #41–#47 remain functional migrations.

## Audit and direction

Legacy uses five compact destinations but repeats rounded cards inside cards;
club and competition names truncate, and emoji compete with years and attempts.
V2 repeats that structure, adds developer copy above the game, exposes inert
feature buttons, and limits desktop to a 520px column. Its existing controller,
API contracts, localization and behavioral tests are useful foundations.

Use the compact hierarchy of a football results app: clear scores, restrained green
interaction accents, grouped career rows and a thumb-friendly bottom navigation.
The career is the main visual: seasons left, clubs centre, appearances right,
continuous vertical connection, dashed loan branches, no horizontal scrolling.
Long names wrap. Never fabricate dates or badges absent from the payload.

## System

- Fixed dark navy surfaces in V2 (#66). Football green marks interaction and
  correctness; red marks mistakes; amber marks hints. No light/dark toggle.
- System sans with strong weight contrast for headings; tabular figures for
  seasons, attempts, scores and rankings.
- Spacing: 4/8/12/16/24/32/48px. Structural corners 0–2px, controls 6px,
  avatar circles only. Dividers rather than container shadows.
- One 24px outline SVG family with a custom career/pitch mark.
- Telegram theme changes do not change structural colors. Safe-area and viewport
  events still propagate. Device and Telegram safe areas protect all edges.
  Cosmetics use the shared [appearance contract](miniapp-appearance.md).
- Mobile starts at 320px; review at 390×844. At 900px, career and answer desk
  sit side by side; navigation becomes a top strip within the same sports interface.
- Motion only for feedback and hints, 150–220ms; reduced motion removes it.
  No decorative entry animations or perpetual effects.

## Navigation

- Bottom navigation: Daily, Arena, Classifica, Shop, Profilo.
- Arena is the extra-mode hub: challenge a player, current duel, archive, events.
  Child screens retain Arena as the active destination and offer a back link.
- Referral invitations live under Profile, separately from inviting a duel opponent.
- Header menu: reports, refunds, privacy/forgetme only. These are informational
  screens: reports integration is pending; refunds explain `/paysupport` and
  privacy explains `/forgetme`. No message, refund or deletion is triggered.

## Boundaries and review

Daily uses the existing controller. Other destinations show an explicit preview
notice and typed local sample data, with unavailable actions disabled. The
separate development review mode renders Daily states without API calls.
No backend, legacy assets, bot URLs or feature migration contracts change.
Review artifacts are temporary, outside Git. Human visual approval is required;
this branch must not merge automatically.

## Preview and acceptance evidence

From the dedicated worktree:

```powershell
npm ci
npm run dev -- --host 127.0.0.1 --port 5174 --strictPort
```

- Real runtime: http://127.0.0.1:5174/app/v2/ (requires API on port 8000 and
  valid Telegram authentication to play).
- Isolated visual review: http://127.0.0.1:5174/app/v2/?design-review
  (development build only). State/appearance controls appear below the page.
- Build validation: `npm run typecheck`, `npm test`, `npm run build`,
  `npm audit --audit-level=high`.
- Route regression: `python -m pytest -q tests/test_webapp_v2_serving.py tests/test_webapp_auth.py`.

Tailwind CSS and its official Vite plugin are development dependencies. There
are no new runtime dependencies, web fonts or third-party icon requests. Vite
removes the Daily review harness and its fixtures from production JS. Future
screen fixtures remain in their explicit prototype namespace and are labelled
as sample data in the UI. Their preview copy is Italian for design review;
Daily and navigation retain Italian, English and Spanish.

The original component contracts remain available for future migrations;
`Card` is retained only for compatibility, with no uses in the redesigned
screens. Button, HintPanel, FeedbackBox, Loading/Error/EmptyState, StatTile,
ListRow, Badge, Avatar and Modal share the new tokens/styles. CareerPath,
GuessInput, Header, NavBar and Daily composition are redesigned. Default
attempts use numbered score marks; explicitly equipped symbols are preserved.

### Review limitations

- Six-stop Daily has a reachable input and submit action at 390×844; longer
  careers and expanded feedback scroll vertically. Club names wrap instead of
  being truncated. Desktop shows the full six-stop career beside the answer.
- The #64 browser review covered light/dark, 320px layout, and all supplied states.
  Physical Telegram keyboard behavior still needs device review. Safe-area and
  live theme propagation have automated coverage.
- Existing hint/card API failure handling remains owned by the existing Daily
  controller. Guess request errors now surface next to the answer field.
- PRs #62/#63 are merged. This branch was rebased onto main after both landed;
  security and full CI are rerun on that combined state. No automatic rollout
  or merge; human visual approval remains outstanding.

References: [Tailwind Vite integration](https://tailwindcss.com/docs/installation/using-vite)
and [Telegram Mini Apps](https://core.telegram.org/bots/webapps).

Sports revision screenshots: local `.worktrees/issue-64-review/sports-revision/`.
