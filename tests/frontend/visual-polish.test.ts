import { test } from "node:test";
import assert from "node:assert/strict";
import { flagUrl, renderCareerPath } from "../../webapp/src/components/CareerPath";
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

test("flags: a country code becomes the URL of its bundled image, anything else nothing", () => {
  assert.ok(flagUrl("JP").endsWith("/assets/flags/jp.webp"));
  assert.ok(flagUrl("GB-ENG").endsWith("/assets/flags/gb-eng.webp"));
  assert.ok(flagUrl("YU").endsWith("/assets/flags/yu.webp"));
  for (const bad of [undefined, null, "", "jp", "JPN", "<b>", "../x", "GB-ENGLAND"]) assert.equal(flagUrl(bad), "");
});

test("flags: every image the server can name exists in the bundle folder", async () => {
  const { readdirSync } = await import("node:fs");
  const files = new Set(readdirSync(new URL("../../webapp/src/assets/flags/", import.meta.url)));
  for (const code of ["JP", "DE", "GB-ENG", "GB-SCT", "GB-WLS", "GB", "YU", "US"]) {
    assert.ok(files.has(`${code.toLowerCase()}.webp`), code);
  }
});

test("flags: the career shows a decorative flag image before league and country", () => {
  const html = renderCareerPath({ stops: [
    { team: "Cerezo Osaka", league: "J1 League", country: "Giappone", country_code: "JP", start_year: 2006 },
    { team: "Atlantide FC", league: "Lega", country: "Atlantide", start_year: 1990 },
  ] });
  assert.match(html, /<img class="flag" src="[^"]*\/assets\/flags\/jp\.webp" alt="" width="18" height="14" loading="lazy" decoding="async">J1 League · Giappone/);
  assert.ok(html.includes('<div class="meta">Lega · Atlantide</div>'));
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

test("leaderboard: the frame keeps its effects (reviewed motion, tactics dots) like on the profile", () => {
  const ring = "conic-gradient(#b8892f, #f7e39c, #d9b45b, #fff3c4, #b8892f)";
  const shine = renderLeaderboardRow({ position: 5, profile_id: 8, name: "Elisa", points: 1, frame: { ring, motion: "shine" } });
  assert.ok(shine.includes('data-motion="shine"'));
  const tactics = renderLeaderboardRow({ position: 6, profile_id: 9, name: "Luca", points: 1, frame: { ring, tactics: 3 } });
  assert.equal((tactics.match(/<circle /g) || []).length, 4); // three players and the ball
  const odd = renderLeaderboardRow({ position: 7, profile_id: 10, name: "Eve", points: 1, frame: { ring, motion: "explode", tactics: 99 } });
  assert.ok(!odd.includes("data-motion") && !odd.includes("avatar-tactics"));
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

test("profile: a player pass with nothing worn has a quiet link to the Shop; a styled one does not", async () => {
  setLanguage("it");
  const bare = await renderProfileWith({ frame: { ring: "" }, title: { label: "", color: "" } });
  assert.ok(bare.includes('class="style-link" data-tab="shop"'));
  assert.ok(bare.includes("Personalizza la tessera"));

  const styled = await renderProfileWith(createTestFullProfile().cosmetics);
  assert.ok(!styled.includes("style-link"));
});
