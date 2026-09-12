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
