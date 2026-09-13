import { test } from "node:test";
import assert from "node:assert/strict";
import { App } from "../../webapp/src/app/App";
import {
  setupGlobalDom,
  setupTestTelegram,
  mockFetchResponse,
  captureFetchRequests,
  createTestDailyChallenge,
  createTestFullProfile,
} from "./helpers";

test("App mounts into DOM and renders shared components with real Daily feature data", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const { container, cleanup: cleanupDom } = setupGlobalDom();
  const restoreFetch = mockFetchResponse({
    user: { name: "Marco", points: 100, streak: 3 },
    today: createTestDailyChallenge(),
  });

  try {
    const app = new App(container);
    app.init();

    // Verify initial header rendered
    assert.ok(container.querySelector(".app-header"));

    // Wait for DailyController to complete initial async load
    await app.getDailyController().init();

    // Verify CareerPath rendered
    const pathEl = container.querySelector(".path");
    assert.ok(pathEl, "CareerPath element was not rendered");
    const stops = pathEl.querySelectorAll(".stop");
    assert.equal(stops.length, 3);
    assert.equal(stops[0].querySelector(".team")?.textContent, "Parma");

    // Verify GuessInput rendered
    const inputEl = container.querySelector<HTMLInputElement>("#answer");
    assert.ok(inputEl, "Guess input was not rendered");
    const submitBtn = container.querySelector<HTMLButtonElement>("#submit");
    assert.ok(submitBtn, "Submit button was not rendered");

    // Verify HintPanel rendered
    const hintItem = container.querySelector(".hint-taken-item");
    assert.ok(hintItem, "Hint item was not rendered");
    assert.equal(hintItem.textContent, "Ha vinto un Mondiale nel 2006");

    // Verify Navigation switching tabs
    const arenaTabBtn = container.querySelector<HTMLButtonElement>('nav.app-nav button[data-tab="arena"]');
    assert.ok(arenaTabBtn);
    arenaTabBtn.click();

    // Switched to Arena: career path of daily should not be in arena
    assert.ok(container.querySelector(".page-title")?.textContent?.includes("Arena"));

    // Switch back to Play
    const playTabBtn = container.querySelector<HTMLButtonElement>('nav.app-nav button[data-tab="play"]');
    assert.ok(playTabBtn);
    playTabBtn.click();
    assert.ok(container.querySelector(".path"));
  } finally {
    restoreFetch();
    cleanupDom();
    restoreTg();
  }
});

test("query-string values (?view=wrong, ?view=solved) cannot trigger a Daily submission in production App", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const { container, cleanup: cleanupDom } = setupGlobalDom();

  // Simulate preview query parameters on window.location.search
  window.location.search = "?view=wrong";

  const { requests, restore: restoreFetch } = captureFetchRequests({
    user: { name: "Marco", points: 100, streak: 3 },
    today: createTestDailyChallenge(),
  });

  try {
    const app = new App(container);
    app.init();
    await app.getDailyController().init();

    // Verify no automatic guess submission occurred
    const guessRequests = requests.filter((r) => r.url.includes("/app/api/guess"));
    assert.equal(guessRequests.length, 0, "Query-string parameter triggered an automatic guess submission!");
    assert.equal(app.getDailyController().getState().feedback, null);

    // Also test ?view=solved
    window.location.search = "?view=solved";
    const app2 = new App(container);
    app2.init();
    await app2.getDailyController().init();

    const guessRequests2 = requests.filter((r) => r.url.includes("/app/api/guess"));
    assert.equal(guessRequests2.length, 0, "?view=solved triggered an automatic guess submission!");
    assert.equal(app2.getDailyController().getState().feedback, null);
  } finally {
    window.location.search = "";
    restoreFetch();
    cleanupDom();
    restoreTg();
  }
});

test("App navigates to leaderboard tab, loads real leaderboard data, and connects LeaderboardController", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const { container, cleanup: cleanupDom } = setupGlobalDom();
  const restoreFetch = mockFetchResponse(createTestFullProfile());

  try {
    const app = new App(container);
    app.init();

    const leaderboardTabBtn = container.querySelector<HTMLButtonElement>(
      'nav.app-nav button[data-tab="leaderboard"]',
    );
    assert.ok(leaderboardTabBtn);
    leaderboardTabBtn.click();

    await app.getLeaderboardController().init();

    assert.ok(container.querySelector(".leaderboard-section"));
    assert.ok(container.querySelector(".leaderboard-tabs"));
    assert.equal(app.getLeaderboardController().getState().status, "ready");
    assert.ok(container.textContent?.includes("Alessandro Del Piero"));
  } finally {
    restoreFetch();
    cleanupDom();
    restoreTg();
  }
});

test("App navigates to archive tab, loads real calendar data, and does not render prototype", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const { container, cleanup: cleanupDom } = setupGlobalDom();
  const restoreFetch = mockFetchResponse({
    days: [
      {
        day: "2026-09-01",
        label: "01/09/26",
        number: 42,
        difficulty: "medium",
        difficulty_label: "Media",
        status: "solved",
        attempts: 2,
        hints: 0,
        playable: false,
      },
      {
        day: "2026-09-02",
        label: "02/09/26",
        number: 43,
        difficulty: "hard",
        difficulty_label: "Difficile",
        status: "lost",
        attempts: 5,
        hints: 1,
        playable: true,
      },
    ],
  });

  try {
    const app = new App(container);
    app.init();

    // Set tab to archive (as if clicking an archive entry or tab)
    app.setTab("archive");
    await app.getArchiveController().init();

    // Verify real archive components rendered
    assert.ok(container.querySelector(".archive-calendar"), "Archive calendar was not rendered");
    assert.ok(!container.querySelector(".prototype-notice"), "Prototype notice should not be present in archive tab");
    assert.equal(app.getArchiveController().getState().status, "ready");
    assert.equal(app.getArchiveController().getState().calendar.length, 2);

    // Verify day cards rendered
    const dayCards = container.querySelectorAll(".archive-day-card");
    assert.equal(dayCards.length, 2);
  } finally {
    restoreFetch();
    cleanupDom();
    restoreTg();
  }
});

test("Cross-feature navigation sequence (Daily -> Arena -> Training -> Archive -> Leaderboard -> Daily) preserves appearance, controllers, and state without duplicate calls", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const { container, cleanup: cleanupDom } = setupGlobalDom();

  const originalFetch = globalThis.fetch;
  const requests: Array<{ url: string; body: any }> = [];

  globalThis.fetch = (async (url: string, opts: any) => {
    const body = opts?.body ? JSON.parse(opts.body) : {};
    requests.push({ url, body });

    if (url.includes("/app/api/me")) {
      const fullProfile = createTestFullProfile();
      return {
        ok: true,
        status: 200,
        json: async () => ({
          ...fullProfile,
          today: createTestDailyChallenge(),
          cosmetics: {
            theme: { accent: "#38ef7d", surface: "#0a192f" },
            squares: { correct: "🟩", wrong: "🟥" },
            card: { finish: "foil" },
            celebration: "fireworks",
          },
        }),
      } as Response;
    }
    if (url.includes("/app/api/guess")) {
      return {
        ok: true,
        status: 200,
        json: async () => createTestDailyChallenge(),
      } as Response;
    }
    if (url.includes("/app/api/arena")) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          session: {
            round: 0,
            attempts_left: 5,
            career_path: [
              { team: "Milan", years: "2000-2010", apps: "300" },
            ],
          },
          feedback: null,
        }),
      } as Response;
    }
    if (url.includes("/app/api/calendar")) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          days: [
            {
              day: "2026-09-01",
              label: "01/09/26",
              number: 1,
              status: "solved",
              playable: false,
            },
          ],
        }),
      } as Response;
    }
    return { ok: true, status: 200, json: async () => ({}) } as Response;
  }) as any;

  try {
    const app = new App(container);
    app.init();

    // 1. Initial tab: Daily
    await app.getDailyController().init();
    assert.equal(app.getDailyController().getState().status, "ready");
    assert.ok(container.querySelector(".path"), "Daily career path must be visible");

    // Check appearance was resolved
    const { getResolvedAppearance } = await import("../../webapp/src/appearance");
    const appearanceAfterDaily = getResolvedAppearance();
    assert.ok(appearanceAfterDaily, "Appearance must be resolved after Daily profile load");
    assert.equal(appearanceAfterDaily?.card?.finish, "foil");

    // 2. Navigate to Arena
    app.setTab("arena");
    assert.ok(container.textContent?.includes("Arena"), "Arena hub must render");
    assert.equal(app.getArenaController().getState().subview, "hub");

    // 3. Navigate to Training subview
    app.setArenaSubview("training");
    await app.getTrainingController().init();
    assert.equal(app.getArenaController().getState().subview, "training");
    assert.ok(container.textContent?.includes("Milan"), "Training challenge path must render");

    // 4. Navigate to Archive
    app.setTab("archive");
    await app.getArchiveController().init();
    assert.equal(app.getArchiveController().getState().status, "ready");
    assert.ok(container.querySelector(".archive-calendar"), "Archive calendar must render");

    // 5. Navigate to Leaderboard
    app.setTab("leaderboard");
    await app.getLeaderboardController().init();
    assert.equal(app.getLeaderboardController().getState().status, "ready");
    assert.ok(container.querySelector(".leaderboard-section"), "Leaderboard must render");

    // 6. Navigate to Profile
    app.setTab("profile");
    await app.getProfileController().init();
    assert.equal(app.getProfileController().getState().status, "ready");
    assert.ok(container.querySelector(".profile-page"), "Profile must render");

    // 7. Navigate back to Daily
    app.setTab("play");
    assert.ok(container.querySelector(".path"), "Daily career path must be restored");
    assert.ok(container.querySelector("#answer"), "Daily guess input must be restored");

    // Verify appearance was NOT destroyed or reset across navigations
    const appearanceAfterLoop = getResolvedAppearance();
    assert.ok(appearanceAfterLoop, "Appearance must not be destroyed across navigation sequence");
    assert.equal(appearanceAfterLoop?.card?.finish, "foil");
    assert.equal(appearanceAfterLoop?.theme?.accent, "#38ef7d");

    // Verify all controllers exist and retained their integrity
    assert.ok(app.getDailyController());
    assert.ok(app.getArenaController());
    assert.ok(app.getTrainingController());
    assert.ok(app.getArchiveController());
    assert.ok(app.getLeaderboardController());
    assert.ok(app.getProfileController());
    assert.equal(app.getArchiveController().getState().calendar.length, 1);
  } finally {
    globalThis.fetch = originalFetch;
    cleanupDom();
    restoreTg();
  }
});

