import { test } from "node:test";
import assert from "node:assert/strict";
import { App } from "../../webapp/src/app/App";
import { lazyModule } from "../../webapp/src/app/lazy";
import {
  setupGlobalDom,
  setupTestTelegram,
  mockFetchResponse,
  createTestDailyChallenge,
  createTestFullProfile,
} from "./helpers";

const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

test("lazyModule loads once, caches, and retries after a failure (#187)", async () => {
  let calls = 0;
  let fail = true;
  const view = lazyModule(async () => {
    calls++;
    if (fail) throw new Error("chunk failed");
    return { name: "shop" };
  });
  assert.equal(view.module, null);
  await assert.rejects(view.load());
  assert.equal(view.failed, true);

  fail = false;
  const [a, b] = await Promise.all([view.load(), view.load()]);
  assert.equal(calls, 2, "concurrent loads share one import");
  assert.equal(a, b);
  assert.equal(view.failed, false);
  assert.deepEqual(view.module, { name: "shop" });
  await view.load();
  assert.equal(calls, 2, "a loaded module is cached");
});

// These run first in their own process, so the Shop/Events chunks are not loaded yet.
test("Story (an Arena sub-screen) shows a loading state until its chunk is in (#187)", async () => {
  const { container, cleanup } = setupGlobalDom();
  const { restore: restoreTg } = setupTestTelegram();
  const restoreFetch = mockFetchResponse({ ...createTestFullProfile(), today: createTestDailyChallenge(), chapters: [] });
  try {
    const app = new App(container);
    app.init();
    await app.whenFirstLoaded();
    app.setTab("arena");
    app.setArenaSubview("story");
    assert.ok(container.querySelector("#app-content .loading-state"), "spinner while the chunk loads");
    for (let i = 0; i < 50 && !container.querySelector("#app-content .story-view"); i++) await tick();
    assert.ok(container.querySelector("#app-content .story-view"), "Story renders once its chunk is in");
    assert.equal(app.getActiveTab(), "arena");
  } finally {
    restoreFetch();
    restoreTg();
    cleanup();
  }
});

test("Shop shows a loading state, then renders once its chunk is in (#187)", async () => {
  const { container, cleanup } = setupGlobalDom();
  const { restore: restoreTg } = setupTestTelegram();
  const restoreFetch = mockFetchResponse({ ...createTestFullProfile(), today: createTestDailyChallenge() });
  try {
    const app = new App(container);
    app.init();
    await app.whenFirstLoaded();
    app.setTab("shop");
    assert.ok(container.querySelector("#app-content .loading-state"), "spinner while the chunk loads");
    await app.prefetchLazyViews();
    await tick();
    assert.equal(container.querySelector("#app-content .loading-state"), null);
    assert.ok(container.querySelector("#app-content .shop-shell"));
  } finally {
    restoreFetch();
    restoreTg();
    cleanup();
  }
});

test("a lazy view loading in the background never re-renders another tab (#187)", async () => {
  const { container, cleanup } = setupGlobalDom();
  const { restore: restoreTg } = setupTestTelegram();
  const restoreFetch = mockFetchResponse({ ...createTestFullProfile(), today: createTestDailyChallenge(), events: [] });
  try {
    const app = new App(container);
    app.init();
    await app.whenFirstLoaded();
    app.setTab("events");
    app.setTab("play");
    const daily = container.querySelector("#app-content");
    const marker = document.createElement("span");
    marker.id = "still-here";
    daily?.appendChild(marker);
    await app.prefetchLazyViews();
    await tick();
    assert.ok(container.querySelector("#still-here"), "the Daily was not re-rendered");
  } finally {
    restoreFetch();
    restoreTg();
    cleanup();
  }
});
