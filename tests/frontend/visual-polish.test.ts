import { test } from "node:test";
import assert from "node:assert/strict";
import { flagEmoji, renderCareerPath } from "../../webapp/src/components/CareerPath";
import { renderHintPanel } from "../../webapp/src/components/HintPanel";
import { renderLeaderboardRow } from "../../webapp/src/features/leaderboard/views";
import { renderHubView } from "../../webapp/src/features/arena/views";
import { ProfileController } from "../../webapp/src/features/profile/controller";
import { renderProfilePage } from "../../webapp/src/pages/ProfilePage";
import { setLanguage, tCount } from "../../webapp/src/i18n";
import type { ArenaState } from "../../webapp/src/features/arena/types";
import {
  setupGlobalDom,
  setupTestTelegram,
  captureFetchRequests,
  createTestFullProfile,
} from "./helpers";

test("flags: ISO codes become emoji flags, the UK nations their own, anything else nothing", () => {
  assert.equal(flagEmoji("JP"), "🇯🇵");
  assert.equal(flagEmoji("GB-ENG"), "🏴󠁧󠁢󠁥󠁮󠁧󠁿");
  assert.equal(flagEmoji("GB-SCT"), "🏴󠁧󠁢󠁳󠁣󠁴󠁿");
  for (const bad of [undefined, null, "", "jp", "JPN", "<b>", "GB-NIR"]) assert.equal(flagEmoji(bad), "");
});

test("flags: the career shows the flag before league and country, hidden from screen readers", () => {
  const html = renderCareerPath({ stops: [
    { team: "Cerezo Osaka", league: "J1 League", country: "Giappone", country_code: "JP", start_year: 2006 },
    { team: "Stella Rossa", league: "Prva Liga", country: "Jugoslavia", start_year: 1990 },
  ] });
  assert.ok(html.includes('<span class="flag" aria-hidden="true">🇯🇵</span>J1 League · Giappone'));
  assert.ok(html.includes('<div class="meta">Prva Liga · Jugoslavia</div>'));
});

test("hints left: singular for one hint, plural otherwise, in every language", () => {
  const cases: Array<["it" | "en" | "es", string, string]> = [
    ["it", "1 indizio rimasto", "2 indizi rimasti"],
    ["en", "1 hint left", "2 hints left"],
    ["es", "1 pista restante", "2 pistas restantes"],
  ];
  try {
    for (const [lang, one, two] of cases) {
      setLanguage(lang);
      const label = (n: number) => tCount("daily.hintsLeft", n);
      assert.ok(renderHintPanel({ hintsTotal: 1, hintsUsed: 0, hintsLeftLabel: label }).includes(one));
      assert.ok(renderHintPanel({ hintsTotal: 3, hintsUsed: 1, hintsLeftLabel: label }).includes(two));
    }
  } finally {
    setLanguage("it");
  }
});

test("leaderboard: podium rows and the worn frame around the avatar", () => {
  const gold = renderLeaderboardRow({
    position: 1, profile_id: 5, name: "Giulia", points: 1180,
    frame: { ring: "conic-gradient(#b8892f, #f7e39c, #d9b45b, #fff3c4, #b8892f)" },
  });
  assert.ok(gold.includes('class="row podium podium-1"'));
  assert.ok(gold.includes("row-avatar"));
  assert.ok(gold.includes("background: conic-gradient(#b8892f"));

  const plain = renderLeaderboardRow({ position: 4, profile_id: 6, name: "Dario", points: 610 });
  assert.ok(plain.includes('class="row"'));
  assert.ok(!plain.includes('class="ring'));
});

test("leaderboard: a frame paint that is not in the reviewed list is never drawn", () => {
  const html = renderLeaderboardRow({
    position: 2, profile_id: 7, name: "Eve", points: 1,
    frame: { ring: "url(https://evil.example/x.png)" },
  });
  assert.ok(!html.includes("evil.example"));
  assert.ok(!html.includes('class="ring'));
});

test("arena: duels stay featured with the count of open ones, the other modes form a grid", () => {
  const state = {
    subview: "hub", status: "idle", busy: false, error: null, notice: null, confirming: null,
    activeDuelCode: null, invitationCode: null, searchQuery: "", searchResults: [], searchError: null, draftAnswer: "",
    data: { open: [{ code: "A", complete: false }, { code: "B", complete: false }, { code: "C", complete: true }] },
  } as unknown as ArenaState;
  setLanguage("it");
  const html = renderHubView(state);
  assert.ok(html.includes('class="mode-entry mode-feature"'));
  assert.ok(html.includes('<em class="mode-live">2 in corso</em>'));
  assert.equal((html.match(/<div class="arena-mode-grid">/g) || []).length, 1);
  for (const target of ['data-tab="events"', 'data-tab="archive"', 'data-arena-nav="training"', 'data-arena-nav="story"']) {
    assert.ok(html.includes(target));
  }

  const none = renderHubView({ ...state, data: { open: [] } } as unknown as ArenaState);
  assert.ok(!none.includes("mode-live"));
});

async function renderProfileWith(cosmetics: unknown): Promise<string> {
  const { restore: restoreTg } = setupTestTelegram();
  const { cleanup } = setupGlobalDom();
  const profile = { ...createTestFullProfile(), cosmetics };
  const { restore: restoreFetch } = captureFetchRequests(profile);
  try {
    const controller = new ProfileController();
    await controller.init();
    return renderProfilePage(controller.getState());
  } finally {
    restoreFetch();
    cleanup();
    restoreTg();
  }
}

test("profile: a player pass with nothing worn invites to the Shop; a styled one does not", async () => {
  setLanguage("it");
  const bare = await renderProfileWith({ frame: { ring: "" }, title: { label: "", color: "" } });
  assert.ok(bare.includes('class="style-cta" data-tab="shop"'));
  assert.ok(bare.includes("Dai stile alla tua tessera"));

  const styled = await renderProfileWith(createTestFullProfile().cosmetics);
  assert.ok(!styled.includes("style-cta"));
});
