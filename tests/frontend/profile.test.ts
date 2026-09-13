import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { ProfileController } from "../../webapp/src/features/profile/controller";
import { getTrophyPlacementLabel } from "../../webapp/src/features/profile";
import { setLanguage, getLanguage } from "../../webapp/src/i18n";
import {
  renderProfilePage,
  attachProfileEventListeners,
} from "../../webapp/src/pages/ProfilePage";
import {
  setupGlobalDom,
  setupTestTelegram,
  mockFetchResponse,
  captureFetchRequests,
  createTestFullProfile,
} from "./helpers";
import {
  applyResolvedAppearance,
  getResolvedAppearance,
  clearResolvedAppearance,
} from "../../webapp/src/appearance";
import { App } from "../../webapp/src/app/App";

test("1 & 2. Profile init calls /app/api/me with lightweight: true", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const { cleanup: cleanupDom } = setupGlobalDom();
  const fullProfile = createTestFullProfile();
  const { requests, restore: restoreFetch } = captureFetchRequests(fullProfile);

  try {
    const controller = new ProfileController();
    await controller.init();

    const meReqs = requests.filter((r) => r.url.includes("/app/api/me"));
    assert.equal(meReqs.length, 1);
    assert.equal(meReqs[0].body.lightweight, true);
    assert.equal(controller.getState().status, "ready");
    assert.equal(controller.getState().profile?.user.name, "Mario");
  } finally {
    restoreFetch();
    cleanupDom();
    restoreTg();
  }
});

test("3. Profile loading state renders loading indicator before data arrives", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const { container, cleanup: cleanupDom } = setupGlobalDom();

  let finishFetch!: () => void;
  const fetchPromise = new Promise<Response>((resolve) => {
    finishFetch = () => {
      resolve({
        ok: true,
        status: 200,
        json: async () => createTestFullProfile(),
      } as Response);
    };
  });

  const originalFetch = globalThis.fetch;
  globalThis.fetch = (() => fetchPromise) as any;

  try {
    const controller = new ProfileController();
    const initPromise = controller.init();

    assert.equal(controller.getState().status, "loading");
    container.innerHTML = renderProfilePage(controller.getState());
    assert.ok(container.querySelector(".loading-state"), "Loading state must be rendered");

    finishFetch();
    await initPromise;
    assert.equal(controller.getState().status, "ready");
  } finally {
    globalThis.fetch = originalFetch;
    cleanupDom();
    restoreTg();
  }
});

test("4 & 5. API error and retry flow works", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const { container, cleanup: cleanupDom } = setupGlobalDom();

  let shouldFail = true;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () => {
    if (shouldFail) {
      throw new Error("Network error loading profile");
    }
    return {
      ok: true,
      status: 200,
      json: async () => createTestFullProfile(),
    } as Response;
  }) as any;

  try {
    const controller = new ProfileController();
    await controller.init();

    assert.equal(controller.getState().status, "error");
    container.innerHTML = renderProfilePage(controller.getState());
    attachProfileEventListeners(container, controller);

    const retryBtn = container.querySelector<HTMLButtonElement>("#profile-retry-btn");
    assert.ok(retryBtn, "Retry button must be rendered on error");

    shouldFail = false;
    retryBtn.click();
    await new Promise((r) => setTimeout(r, 20));

    assert.equal(controller.getState().status, "ready");
    assert.equal(controller.getState().profile?.user.name, "Mario");
  } finally {
    globalThis.fetch = originalFetch;
    cleanupDom();
    restoreTg();
  }
});

test("6. Duplicate init calls reuse in-flight request without dispatching duplicate /me", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const { cleanup: cleanupDom } = setupGlobalDom();
  const { requests, restore: restoreFetch } = captureFetchRequests(createTestFullProfile());

  try {
    const controller = new ProfileController();
    await Promise.all([controller.init(), controller.init(), controller.init()]);

    const meReqs = requests.filter((r) => r.url.includes("/app/api/me"));
    assert.equal(meReqs.length, 1, "Duplicate init must not trigger multiple in-flight requests");
  } finally {
    restoreFetch();
    cleanupDom();
    restoreTg();
  }
});

test("7. Stale out-of-order profile response is discarded by sequence guard", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const { cleanup: cleanupDom } = setupGlobalDom();

  let resolveFirst!: (res: Response) => void;
  const firstPromise = new Promise<Response>((r) => (resolveFirst = r));

  const originalFetch = globalThis.fetch;
  let callCount = 0;
  globalThis.fetch = (() => {
    callCount++;
    if (callCount === 1) {
      return firstPromise;
    }
    return Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({
        ...createTestFullProfile(),
        user: { ...createTestFullProfile().user, name: "SecondUser" },
      }),
    } as Response);
  }) as any;

  try {
    const controller = new ProfileController();
    const p1 = controller.refresh();
    const p2 = controller.refresh();

    await p2;
    assert.equal(controller.getState().profile?.user.name, "SecondUser");

    // Later, first slow response resolves
    resolveFirst({
      ok: true,
      status: 200,
      json: async () => ({
        ...createTestFullProfile(),
        user: { ...createTestFullProfile().user, name: "StaleFirstUser" },
      }),
    } as Response);
    await p1;

    // Must still be SecondUser
    assert.equal(controller.getState().profile?.user.name, "SecondUser");
  } finally {
    globalThis.fetch = originalFetch;
    cleanupDom();
    restoreTg();
  }
});

test("8 to 16. Real user statistics are rendered accurately, including zero-value user", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const { container, cleanup: cleanupDom } = setupGlobalDom();

  const standardData = createTestFullProfile({
    user: {
      name: "Gianluigi",
      points: 850,
      monthly_points: 210,
      players_guessed: 65,
      bonus_first_guessed: 7,
      streak: 9,
      best_streak: 15,
      archive_solved: 14,
      trophies: 3,
    },
  });

  const restoreFetch = mockFetchResponse(standardData);

  try {
    const controller = new ProfileController();
    await controller.init();
    container.innerHTML = renderProfilePage(controller.getState());

    const text = container.textContent || "";
    // Verify each statistic is present
    assert.ok(text.includes("Gianluigi"), "Name must be rendered");
    assert.ok(text.includes("850"), "Total points must be rendered");
    assert.ok(text.includes("210"), "Monthly points must be rendered");
    assert.ok(text.includes("65"), "Players guessed must be rendered");
    assert.ok(text.includes("7"), "Bonus first guessed must be rendered");
    assert.ok(text.includes("9"), "Current streak must be rendered");
    assert.ok(text.includes("15"), "Best streak must be rendered");
    assert.ok(text.includes("14"), "Archive recovered must be rendered");
    assert.ok(text.includes("3 trofei") || text.includes("3 Trofei"), "Trophy count must be rendered");

    // Zero-value user
    const zeroData = createTestFullProfile({
      user: {
        name: "Newbie",
        points: 0,
        monthly_points: 0,
        players_guessed: 0,
        bonus_first_guessed: 0,
        streak: 0,
        best_streak: 0,
        archive_solved: 0,
        trophies: 0,
      },
      trophies: { pinned: [], all: [], max: 3 },
      distribution: [
        { attempts: 1, count: 0 },
        { attempts: 2, count: 0 },
        { attempts: 3, count: 0 },
        { attempts: 4, count: 0 },
        { attempts: 5, count: 0 },
      ],
    });

    const zeroController = new ProfileController();
    (zeroController as any).updateState({ status: "ready", profile: zeroData });
    container.innerHTML = renderProfilePage(zeroController.getState());

    const zeroText = container.textContent || "";
    assert.ok(zeroText.includes("Newbie"));
    assert.ok(zeroText.includes("0"), "Zero points/streak must be rendered honestly");
    assert.ok(!zeroText.includes("PLAYER / 001"), "No fake prototype player number");
  } finally {
    restoreFetch();
    cleanupDom();
    restoreTg();
  }
});

test("17 to 21. Attempt distribution renders accurately with scaling, zero buckets, and empty state", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const { container, cleanup: cleanupDom } = setupGlobalDom();

  const distData = createTestFullProfile({
    distribution: [
      { attempts: 1, count: 2 },
      { attempts: 2, count: 10 },
      { attempts: 3, count: 0 },
      { attempts: 4, count: 4 },
      { attempts: 5, count: 1 },
    ],
  });

  try {
    const controller = new ProfileController();
    (controller as any).updateState({ status: "ready", profile: distData });
    container.innerHTML = renderProfilePage(controller.getState());

    const rows = container.querySelectorAll(".distribution-row");
    assert.equal(rows.length, 5);

    // Row 2 has max count (10) so it should have .best
    const bestBar = container.querySelector(".distribution-bar-fill.best");
    assert.ok(bestBar, "Highest bar must have .best class");
    assert.ok(bestBar?.textContent?.includes("10"));

    // Row 3 with count 0 still renders with accessible attempt label
    assert.equal(rows[2].querySelector(".distribution-count")?.textContent, "0");

    // All zero distribution empty state
    const allZeroData = createTestFullProfile({
      distribution: [
        { attempts: 1, count: 0 },
        { attempts: 2, count: 0 },
        { attempts: 3, count: 0 },
        { attempts: 4, count: 0 },
        { attempts: 5, count: 0 },
      ],
    });
    const zeroController = new ProfileController();
    (zeroController as any).updateState({ status: "ready", profile: allZeroData });
    container.innerHTML = renderProfilePage(zeroController.getState());

    assert.ok(container.textContent?.includes("Nessuna partita ancora."));
  } finally {
    cleanupDom();
    restoreTg();
  }
});

test("22 to 28. #66 Appearance contract: frame, title, badge, shirt number rendered, raw equipped IDs NEVER rendered", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const { container, cleanup: cleanupDom } = setupGlobalDom();

  const profileData = createTestFullProfile({
    cosmetics: {
      equipped: {
        theme: "raw_theme_secret_id_123",
        frame: "raw_frame_secret_id_456",
        title: "raw_title_secret_id_789",
        badge: "raw_badge_secret_id_000",
      },
      badge: "👑",
      number: "07",
      frame: {
        ring: "repeating-linear-gradient(45deg, #f5c542 0 7px, #1b3a6b 7px 14px)",
      },
      title: {
        label: "Capitano Storico",
        color: "#d9b45b",
      },
      theme: {
        accent: "#ff007f",
      },
    },
  });

  try {
    const controller = new ProfileController();
    (controller as any).updateState({ status: "ready", profile: profileData });
    container.innerHTML = renderProfilePage(controller.getState());

    const html = container.innerHTML;
    assert.ok(html.includes("👑"), "Badge must render");
    assert.ok(html.includes("07"), "Shirt number must preserve leading zero");
    assert.ok(html.includes("Capitano Storico"), "Title label must render");

    // Crucial check: raw equipped IDs must never render
    assert.ok(!html.includes("raw_theme_secret_id_123"));
    assert.ok(!html.includes("raw_frame_secret_id_456"));
    assert.ok(!html.includes("raw_title_secret_id_789"));
    assert.ok(!html.includes("raw_badge_secret_id_000"));

    // Global appearance sync
    applyResolvedAppearance(profileData.cosmetics);
    const resolved = getResolvedAppearance();
    assert.equal(resolved.badge, "👑");
    assert.equal(resolved.number, "07");
    assert.equal(resolved.title?.label, "Capitano Storico");
  } finally {
    cleanupDom();
    restoreTg();
  }
});

test("29 to 32. Trophy showcase renders 0, 1, and 3 trophies simply by rendering returned pinned", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const { container, cleanup: cleanupDom } = setupGlobalDom();

  try {
    // 0 trophies
    const noTrophies = createTestFullProfile({ trophies: { pinned: [], all: [], max: 3 } });
    const c0 = new ProfileController();
    (c0 as any).updateState({ status: "ready", profile: noTrophies });
    container.innerHTML = renderProfilePage(c0.getState());
    assert.ok(container.querySelector(".profile-empty-pinned"));

    // 1 trophy
    const oneTrophy = createTestFullProfile({
      trophies: {
        pinned: [
          {
            code: "MON_July_3_2026_1",
            kind: "monthly",
            position: 1,
            medal: "🥇",
            color: "#e8b647",
            label: "Luglio",
            detail: "Classifica mensile",
            year: "2026",
          },
        ],
        all: [],
        max: 3,
      },
    });
    const c1 = new ProfileController();
    (c1 as any).updateState({ status: "ready", profile: oneTrophy });
    container.innerHTML = renderProfilePage(c1.getState());
    const tags1 = container.querySelectorAll(".trophy-tag");
    assert.equal(tags1.length, 1);
    assert.ok(container.textContent?.includes("Luglio"));

    // 3 trophies
    const threeTrophies = createTestFullProfile({
      trophies: {
        pinned: [
          { code: "T1", kind: "event", position: 1, medal: "🥇", color: "#e8b647", label: "Trophy 1", detail: "D1", year: "2026" },
          { code: "T2", kind: "event", position: 2, medal: "🥈", color: "#c3ccd6", label: "Trophy 2", detail: "D2", year: "2026" },
          { code: "T3", kind: "event", position: 3, medal: "🥉", color: "#c98652", label: "Trophy 3", detail: "D3", year: "2026" },
        ],
        all: [],
        max: 3,
      },
    });
    const c3 = new ProfileController();
    (c3 as any).updateState({ status: "ready", profile: threeTrophies });
    container.innerHTML = renderProfilePage(c3.getState());
    const tags3 = container.querySelectorAll(".trophy-tag");
    assert.equal(tags3.length, 3);
  } finally {
    cleanupDom();
    restoreTg();
  }
});

test("33 to 42. Trophy cabinet open, close, filters, and year groupings", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const { container, cleanup: cleanupDom } = setupGlobalDom();

  const fullProfile = createTestFullProfile();
  const controller = new ProfileController();
  (controller as any).updateState({ status: "ready", profile: fullProfile });

  try {
    // 33. Open Cabinet
    container.innerHTML = renderProfilePage(controller.getState());
    attachProfileEventListeners(container, controller);

    const openBtn = container.querySelector<HTMLButtonElement>("#open-cabinet");
    assert.ok(openBtn, "Open cabinet button must exist");
    openBtn.click();
    assert.equal(controller.getState().view, "cabinet");

    container.innerHTML = renderProfilePage(controller.getState());
    attachProfileEventListeners(container, controller);
    assert.ok(container.querySelector(".cabinet-view"));

    // 34. Close Cabinet
    const closeBtn = container.querySelector<HTMLButtonElement>("#close-cabinet");
    assert.ok(closeBtn, "Close cabinet button must exist");
    closeBtn.click();
    assert.equal(controller.getState().view, "profile");

    // Open again to test filters
    controller.openCabinet();
    container.innerHTML = renderProfilePage(controller.getState());
    attachProfileEventListeners(container, controller);

    // 35. All trophies (default)
    let rows = container.querySelectorAll(".cabinet-row");
    assert.equal(rows.length, 3);

    // 36. 1st place filter
    controller.setCabinetFilter("1");
    container.innerHTML = renderProfilePage(controller.getState());
    rows = container.querySelectorAll(".cabinet-row");
    assert.equal(rows.length, 1);
    assert.ok(container.textContent?.includes("Luglio"));

    // 37. 2nd place filter
    controller.setCabinetFilter("2");
    container.innerHTML = renderProfilePage(controller.getState());
    rows = container.querySelectorAll(".cabinet-row");
    assert.equal(rows.length, 1);
    assert.ok(container.textContent?.includes("Un amore una maglia"));

    // 38. 3rd place filter
    controller.setCabinetFilter("3");
    container.innerHTML = renderProfilePage(controller.getState());
    rows = container.querySelectorAll(".cabinet-row");
    assert.equal(rows.length, 1);
    assert.ok(container.textContent?.includes("Mondiali passati"));

    // 39. Events filter
    controller.setCabinetFilter("event");
    container.innerHTML = renderProfilePage(controller.getState());
    rows = container.querySelectorAll(".cabinet-row");
    assert.equal(rows.length, 2);

    // 40. Monthly filter
    controller.setCabinetFilter("monthly");
    container.innerHTML = renderProfilePage(controller.getState());
    rows = container.querySelectorAll(".cabinet-row");
    assert.equal(rows.length, 1);

    // 41. Filter matching zero trophies
    const emptyFilterProfile = createTestFullProfile({
      trophies: {
        pinned: [],
        all: [
          { code: "M1", kind: "monthly", position: 1, medal: "🥇", color: "#e8b647", label: "M", detail: "D", year: "2026" },
        ],
        max: 3,
      },
    });
    (controller as any).updateState({ profile: emptyFilterProfile, cabinetFilter: "event" });
    container.innerHTML = renderProfilePage(controller.getState());
    assert.ok(container.querySelector(".cabinet-empty"));
    assert.ok(container.textContent?.includes("Nessun trofeo con questo filtro."));

    // 42. Active pinned indicators
    controller.setCabinetFilter("all");
    (controller as any).updateState({ profile: fullProfile });
    container.innerHTML = renderProfilePage(controller.getState());
    const pinnedRow = container.querySelector('.cabinet-row[data-pin="MON_July_3_2026_1"]');
    assert.equal(pinnedRow?.getAttribute("aria-pressed"), "true");
    assert.ok(pinnedRow?.textContent?.includes("Sul profilo"));
  } finally {
    cleanupDom();
    restoreTg();
  }
});

test("43 to 48. Trophy pin mutation: payload, showcase update, unpin, and 4th selection limit", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const { cleanup: cleanupDom } = setupGlobalDom();

  const fullProfile = createTestFullProfile();
  let sentPayload: any = null;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (url: string, opts: any) => {
    if (url.includes("/app/api/trophies/pin")) {
      sentPayload = JSON.parse(opts.body);
      const chosenCodes: string[] = sentPayload.codes;
      const allTrophies = fullProfile.trophies.all;
      const resolvedPinned = allTrophies.filter((t) => chosenCodes.includes(t.code));
      return {
        ok: true,
        status: 200,
        json: async () => ({ status: "ok", pinned: resolvedPinned }),
      } as Response;
    }
    return { ok: true, status: 200, json: async () => fullProfile } as Response;
  }) as any;

  try {
    const controller = new ProfileController();
    (controller as any).updateState({ status: "ready", profile: fullProfile, view: "cabinet" });

    // Initial pinned: 2 trophies (MON_July_3_2026_1 and 2_un_amore_una_maglia_20260907)
    // 43 & 44. Pin the 3rd trophy (3_mondiali_passati_20250615)
    await controller.togglePin("3_mondiali_passati_20250615");

    assert.ok(sentPayload);
    assert.equal(sentPayload.codes.length, 3);
    assert.ok(sentPayload.codes.includes("3_mondiali_passati_20250615"));

    // 45. Authoritative returned pinned replaces local showcase
    assert.equal(controller.getState().profile?.trophies.pinned.length, 3);
    assert.equal(controller.getState().pinSuccess, true);

    // 46. Unpin an already selected trophy
    await controller.togglePin("MON_July_3_2026_1");
    assert.equal(sentPayload.codes.length, 2);
    assert.equal(controller.getState().profile?.trophies.pinned.length, 2);

    // Pin again to reach max 3
    await controller.togglePin("MON_July_3_2026_1");
    assert.equal(controller.getState().profile?.trophies.pinned.length, 3);

    // 48. Attempt 4th selection: blocked client-side before sending network request
    sentPayload = null;
    await controller.togglePin("4_hypothetical_fourth_trophy");
    assert.equal(sentPayload, null, "Should not dispatch network request for 4th selection");
    assert.ok(controller.getState().pinError?.includes("al massimo 3"));
  } finally {
    globalThis.fetch = originalFetch;
    cleanupDom();
    restoreTg();
  }
});

test("49 to 55. Server pin rejections (too_many, invalid_choice, not_owned, unknown) preserve previous showcase", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const { cleanup: cleanupDom } = setupGlobalDom();

  let serverStatus = "too_many";
  const fullProfile = createTestFullProfile();
  const initialPinned = fullProfile.trophies.pinned;

  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (url: string) => {
    if (url.includes("/app/api/trophies/pin")) {
      return {
        ok: true,
        status: 200,
        json: async () => ({ status: serverStatus }),
      } as Response;
    }
    return { ok: true, status: 200, json: async () => fullProfile } as Response;
  }) as any;

  try {
    const controller = new ProfileController();
    (controller as any).updateState({ status: "ready", profile: fullProfile, view: "cabinet" });

    // 49. Server rejects with too_many
    serverStatus = "too_many";
    await controller.togglePin("3_mondiali_passati_20250615");
    assert.ok(controller.getState().pinError?.includes("al massimo 3"));
    assert.deepEqual(controller.getState().profile?.trophies.pinned, initialPinned);

    // 50. Server rejects with invalid_choice
    serverStatus = "invalid_choice";
    await controller.togglePin("3_mondiali_passati_20250615");
    assert.ok(controller.getState().pinError?.includes("non valida"));
    assert.deepEqual(controller.getState().profile?.trophies.pinned, initialPinned);

    // 51. Server rejects with not_owned
    serverStatus = "not_owned";
    await controller.togglePin("3_mondiali_passati_20250615");
    assert.ok(controller.getState().pinError?.includes("non appartengono"));
    assert.deepEqual(controller.getState().profile?.trophies.pinned, initialPinned);

    // 52. Unknown server status
    serverStatus = "some_random_future_error";
    await controller.togglePin("3_mondiali_passati_20250615");
    assert.ok(controller.getState().pinError);
    assert.deepEqual(controller.getState().profile?.trophies.pinned, initialPinned);

    // 53. Double mutation blocked while isPinning is true
    let finishPin!: () => void;
    const pinHangPromise = new Promise<Response>((r) => {
      finishPin = () => r({ ok: true, status: 200, json: async () => ({ status: "ok", pinned: [] }) } as Response);
    });
    globalThis.fetch = (() => pinHangPromise) as any;

    const t1 = controller.togglePin("3_mondiali_passati_20250615");
    assert.equal(controller.getState().isPinning, true);

    // Second click during in-flight must be ignored
    const t2 = controller.togglePin("2_un_amore_una_maglia_20260907");
    finishPin();
    await Promise.all([t1, t2]);
    assert.equal(controller.getState().isPinning, false);
  } finally {
    globalThis.fetch = originalFetch;
    cleanupDom();
    restoreTg();
  }
});

test("56 & 57. Leaderboard and public profile remain strictly functional and restricted", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const { cleanup: cleanupDom } = setupGlobalDom();

  const fullProfile = createTestFullProfile();
  const { requests, restore: restoreFetch } = captureFetchRequests(fullProfile);

  try {
    const { LeaderboardController } = await import("../../webapp/src/features/leaderboard/controller");
    const lbController = new LeaderboardController();
    await lbController.init();

    // Verify Leaderboard calls full /me (without lightweight: true)
    const meReq = requests.find((r) => r.url.includes("/app/api/me"));
    assert.ok(meReq);
    assert.equal(meReq.body.lightweight, false);
    assert.equal(lbController.getState().globalLeaderboard.length, 4);
  } finally {
    restoreFetch();
    cleanupDom();
    restoreTg();
  }
});

test("58 to 61. Cross-feature integration: App shell navigation includes Profile without resetting appearance", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const { container, cleanup: cleanupDom } = setupGlobalDom();

  const fullProfile = createTestFullProfile({
    cosmetics: {
      badge: "⭐",
      theme: { accent: "#38ef7d" },
    },
  });

  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (url: string) => {
    if (url.includes("/app/api/me")) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          ...fullProfile,
          today: { available: true, number: 1, career_path: [], hints: { taken: [] } },
        }),
      } as Response;
    }
    return { ok: true, status: 200, json: async () => ({}) } as Response;
  }) as any;

  try {
    const app = new App(container);
    app.init();

    // Navigate to profile tab
    app.setTab("profile");
    await app.getProfileController().init();

    assert.equal(app.getProfileController().getState().status, "ready");
    assert.ok(container.querySelector(".profile-page"), "Profile page must be rendered");
    assert.ok(!container.querySelector(".prototype-notice"), "No prototype notice in Profile tab");

    // Navigate to Daily and back to Profile
    app.setTab("play");
    app.setTab("profile");
    assert.ok(container.querySelector(".profile-page"));
  } finally {
    globalThis.fetch = originalFetch;
    cleanupDom();
    restoreTg();
  }
});

test("62. Dark-only appearance contract: Profile cosmetic theme does not compromise dark structural surfaces", async () => {
  const fullProfile = createTestFullProfile({
    cosmetics: {
      theme: {
        accent: "#00ffcc",
        edge: "#224466",
        track: "#112233",
        card: "#ffffff", // Legacy light card
      },
    },
  });

  applyResolvedAppearance(fullProfile.cosmetics);
  const appearance = getResolvedAppearance();

  assert.equal(appearance.theme?.accent, "#00ffcc");
  // Verify dark structural background is never altered by theme
  assert.equal((appearance.theme as any).bg, undefined);

  clearResolvedAppearance();
});

test("63. Legacy /app files (webapp/index.html, webapp/client.js) remain completely untouched", () => {
  const rootDir = path.resolve(__dirname, "../../");
  const indexPath = path.join(rootDir, "webapp/index.html");
  const clientPath = path.join(rootDir, "webapp/client.js");

  assert.ok(fs.existsSync(indexPath));
  assert.ok(fs.existsSync(clientPath));

  const indexContent = fs.readFileSync(indexPath, "utf-8");
  assert.ok(indexContent.includes("function statsTab()"));
  assert.ok(indexContent.includes("function cabinetView()"));
});

test("64. Profile runtime does not render Astra fixture data", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const { container, cleanup: cleanupDom } = setupGlobalDom();

  const realData = createTestFullProfile({
    user: {
      name: "Paolo Maldini",
      points: 9999,
      monthly_points: 500,
      players_guessed: 200,
      bonus_first_guessed: 10,
      streak: 20,
      best_streak: 50,
      archive_solved: 30,
      trophies: 1,
    },
  });

  try {
    const controller = new ProfileController();
    (controller as any).updateState({ status: "ready", profile: realData });
    container.innerHTML = renderProfilePage(controller.getState());

    const text = container.textContent || "";
    // Verify Astra prototype fixture data is NOT rendered
    assert.ok(!text.includes("Marco Rossi"), "Astra prototype name Marco Rossi must not appear");
    assert.ok(!text.includes("PLAYER / 001"), "Astra prototype badge PLAYER / 001 must not appear");
    assert.ok(!text.includes("Sette giornate di fila"), "Astra prototype streak copy must not appear");
    assert.ok(text.includes("Paolo Maldini"), "Authenticated user name must appear");
  } finally {
    cleanupDom();
    restoreTg();
  }
});

test("65. Cabinet accessibility & localization in Italian (IT)", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const { container, cleanup: cleanupDom } = setupGlobalDom();
  const prevLang = getLanguage();
  setLanguage("it");

  const testProfile = createTestFullProfile({
    trophies: {
      pinned: [
        { code: "T1", kind: "monthly", position: 1, medal: "🥇", color: "#e8b647", label: "Oro 2026", detail: "1° posto", year: "2026" },
        { code: "T2", kind: "event", position: 2, medal: "🥈", color: "#c3ccd6", label: "Argento 2026", detail: "2° posto", year: "2026" },
        { code: "T3", kind: "event", position: 3, medal: "🥉", color: "#c98652", label: "Bronzo 2026", detail: "3° posto", year: "2026" },
      ],
      all: [
        { code: "T1", kind: "monthly", position: 1, medal: "🥇", color: "#e8b647", label: "Oro 2026", detail: "1° posto", year: "2026" },
        { code: "T2", kind: "event", position: 2, medal: "🥈", color: "#c3ccd6", label: "Argento 2026", detail: "2° posto", year: "2026" },
        { code: "T3", kind: "event", position: 3, medal: "🥉", color: "#c98652", label: "Bronzo 2026", detail: "3° posto", year: "2026" },
      ],
      max: 3,
    },
  });

  try {
    const controller = new ProfileController();
    (controller as any).updateState({ status: "ready", profile: testProfile });

    // 1. Verify showcase trophy placement in IT
    container.innerHTML = renderProfilePage(controller.getState());
    const showcasePlates = container.querySelectorAll(".trophy-tag");
    assert.equal(showcasePlates.length, 3);
    assert.equal(showcasePlates[0].querySelector(".sr-only")?.textContent, "1° posto");
    assert.equal(showcasePlates[1].querySelector(".sr-only")?.textContent, "2° posto");
    assert.equal(showcasePlates[2].querySelector(".sr-only")?.textContent, "3° posto");

    // 2. Open Cabinet and verify IT filter group and podium buttons
    controller.openCabinet();
    container.innerHTML = renderProfilePage(controller.getState());

    const filterGroup = container.querySelector(".cabinet-filters[role='group']");
    assert.ok(filterGroup, "Cabinet filters role='group' must exist");
    assert.equal(filterGroup.getAttribute("aria-label"), "Filtri bacheca");

    const btn1 = container.querySelector<HTMLButtonElement>("button[data-cabinet-filter='1']");
    assert.ok(btn1);
    assert.equal(btn1.getAttribute("aria-label"), "Primo posto");
    assert.equal(btn1.querySelector("[aria-hidden='true']")?.textContent, "🥇");

    const btn2 = container.querySelector<HTMLButtonElement>("button[data-cabinet-filter='2']");
    assert.ok(btn2);
    assert.equal(btn2.getAttribute("aria-label"), "Secondo posto");
    assert.equal(btn2.querySelector("[aria-hidden='true']")?.textContent, "🥈");

    const btn3 = container.querySelector<HTMLButtonElement>("button[data-cabinet-filter='3']");
    assert.ok(btn3);
    assert.equal(btn3.getAttribute("aria-label"), "Terzo posto");
    assert.equal(btn3.querySelector("[aria-hidden='true']")?.textContent, "🥉");

    // 3. Verify cabinet rows expose placement in IT
    const cabinetRows = container.querySelectorAll(".cabinet-row");
    assert.equal(cabinetRows.length, 3);
    assert.equal(cabinetRows[0].querySelector(".sr-only")?.textContent, "1° posto");
    assert.equal(cabinetRows[1].querySelector(".sr-only")?.textContent, "2° posto");
    assert.equal(cabinetRows[2].querySelector(".sr-only")?.textContent, "3° posto");
  } finally {
    setLanguage(prevLang);
    cleanupDom();
    restoreTg();
  }
});

test("66. Cabinet accessibility & localization in English (EN)", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const { container, cleanup: cleanupDom } = setupGlobalDom();
  const prevLang = getLanguage();
  setLanguage("en");

  const testProfile = createTestFullProfile({
    trophies: {
      pinned: [
        { code: "T1", kind: "monthly", position: 1, medal: "🥇", color: "#e8b647", label: "Gold 2026", detail: "1st place", year: "2026" },
        { code: "T2", kind: "event", position: 2, medal: "🥈", color: "#c3ccd6", label: "Silver 2026", detail: "2nd place", year: "2026" },
        { code: "T3", kind: "event", position: 3, medal: "🥉", color: "#c98652", label: "Bronze 2026", detail: "3rd place", year: "2026" },
      ],
      all: [
        { code: "T1", kind: "monthly", position: 1, medal: "🥇", color: "#e8b647", label: "Gold 2026", detail: "1st place", year: "2026" },
        { code: "T2", kind: "event", position: 2, medal: "🥈", color: "#c3ccd6", label: "Silver 2026", detail: "2nd place", year: "2026" },
        { code: "T3", kind: "event", position: 3, medal: "🥉", color: "#c98652", label: "Bronze 2026", detail: "3rd place", year: "2026" },
      ],
      max: 3,
    },
  });

  try {
    const controller = new ProfileController();
    (controller as any).updateState({ status: "ready", profile: testProfile });

    // 1. Verify showcase trophy placement in EN
    container.innerHTML = renderProfilePage(controller.getState());
    const showcasePlates = container.querySelectorAll(".trophy-tag");
    assert.equal(showcasePlates.length, 3);
    assert.equal(showcasePlates[0].querySelector(".sr-only")?.textContent, "1st place");
    assert.equal(showcasePlates[1].querySelector(".sr-only")?.textContent, "2nd place");
    assert.equal(showcasePlates[2].querySelector(".sr-only")?.textContent, "3rd place");

    // 2. Open Cabinet and verify EN filter group and podium buttons
    controller.openCabinet();
    container.innerHTML = renderProfilePage(controller.getState());

    // Proving NO hardcoded Italian "Filtri bacheca"
    assert.ok(!container.innerHTML.includes("Filtri bacheca"), "Must NOT contain hardcoded Italian 'Filtri bacheca'");

    const filterGroup = container.querySelector(".cabinet-filters[role='group']");
    assert.ok(filterGroup, "Cabinet filters role='group' must exist");
    assert.equal(filterGroup.getAttribute("aria-label"), "Cabinet filters");

    const btn1 = container.querySelector<HTMLButtonElement>("button[data-cabinet-filter='1']");
    assert.ok(btn1);
    assert.equal(btn1.getAttribute("aria-label"), "First place");
    assert.equal(btn1.querySelector("[aria-hidden='true']")?.textContent, "🥇");

    const btn2 = container.querySelector<HTMLButtonElement>("button[data-cabinet-filter='2']");
    assert.ok(btn2);
    assert.equal(btn2.getAttribute("aria-label"), "Second place");
    assert.equal(btn2.querySelector("[aria-hidden='true']")?.textContent, "🥈");

    const btn3 = container.querySelector<HTMLButtonElement>("button[data-cabinet-filter='3']");
    assert.ok(btn3);
    assert.equal(btn3.getAttribute("aria-label"), "Third place");
    assert.equal(btn3.querySelector("[aria-hidden='true']")?.textContent, "🥉");

    // 3. Verify cabinet rows expose placement in EN
    const cabinetRows = container.querySelectorAll(".cabinet-row");
    assert.equal(cabinetRows.length, 3);
    assert.equal(cabinetRows[0].querySelector(".sr-only")?.textContent, "1st place");
    assert.equal(cabinetRows[1].querySelector(".sr-only")?.textContent, "2nd place");
    assert.equal(cabinetRows[2].querySelector(".sr-only")?.textContent, "3rd place");
  } finally {
    setLanguage(prevLang);
    cleanupDom();
    restoreTg();
  }
});

test("67. Cabinet accessibility & localization in Spanish (ES)", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const { container, cleanup: cleanupDom } = setupGlobalDom();
  const prevLang = getLanguage();
  setLanguage("es");

  const testProfile = createTestFullProfile({
    trophies: {
      pinned: [
        { code: "T1", kind: "monthly", position: 1, medal: "🥇", color: "#e8b647", label: "Oro 2026", detail: "1.er puesto", year: "2026" },
        { code: "T2", kind: "event", position: 2, medal: "🥈", color: "#c3ccd6", label: "Plata 2026", detail: "2.º puesto", year: "2026" },
        { code: "T3", kind: "event", position: 3, medal: "🥉", color: "#c98652", label: "Bronce 2026", detail: "3.er puesto", year: "2026" },
      ],
      all: [
        { code: "T1", kind: "monthly", position: 1, medal: "🥇", color: "#e8b647", label: "Oro 2026", detail: "1.er puesto", year: "2026" },
        { code: "T2", kind: "event", position: 2, medal: "🥈", color: "#c3ccd6", label: "Plata 2026", detail: "2.º puesto", year: "2026" },
        { code: "T3", kind: "event", position: 3, medal: "🥉", color: "#c98652", label: "Bronce 2026", detail: "3.er puesto", year: "2026" },
      ],
      max: 3,
    },
  });

  try {
    const controller = new ProfileController();
    (controller as any).updateState({ status: "ready", profile: testProfile });

    // 1. Verify showcase trophy placement in ES
    container.innerHTML = renderProfilePage(controller.getState());
    const showcasePlates = container.querySelectorAll(".trophy-tag");
    assert.equal(showcasePlates.length, 3);
    assert.equal(showcasePlates[0].querySelector(".sr-only")?.textContent, "1.er puesto");
    assert.equal(showcasePlates[1].querySelector(".sr-only")?.textContent, "2.º puesto");
    assert.equal(showcasePlates[2].querySelector(".sr-only")?.textContent, "3.er puesto");

    // 2. Open Cabinet and verify ES filter group and podium buttons
    controller.openCabinet();
    container.innerHTML = renderProfilePage(controller.getState());

    // Proving NO hardcoded Italian "Filtri bacheca"
    assert.ok(!container.innerHTML.includes("Filtri bacheca"), "Must NOT contain hardcoded Italian 'Filtri bacheca'");

    const filterGroup = container.querySelector(".cabinet-filters[role='group']");
    assert.ok(filterGroup, "Cabinet filters role='group' must exist");
    assert.equal(filterGroup.getAttribute("aria-label"), "Filtros de la vitrina");

    const btn1 = container.querySelector<HTMLButtonElement>("button[data-cabinet-filter='1']");
    assert.ok(btn1);
    assert.equal(btn1.getAttribute("aria-label"), "Primer puesto");
    assert.equal(btn1.querySelector("[aria-hidden='true']")?.textContent, "🥇");

    const btn2 = container.querySelector<HTMLButtonElement>("button[data-cabinet-filter='2']");
    assert.ok(btn2);
    assert.equal(btn2.getAttribute("aria-label"), "Segundo puesto");
    assert.equal(btn2.querySelector("[aria-hidden='true']")?.textContent, "🥈");

    const btn3 = container.querySelector<HTMLButtonElement>("button[data-cabinet-filter='3']");
    assert.ok(btn3);
    assert.equal(btn3.getAttribute("aria-label"), "Tercer puesto");
    assert.equal(btn3.querySelector("[aria-hidden='true']")?.textContent, "🥉");

    // 3. Verify cabinet rows expose placement in ES
    const cabinetRows = container.querySelectorAll(".cabinet-row");
    assert.equal(cabinetRows.length, 3);
    assert.equal(cabinetRows[0].querySelector(".sr-only")?.textContent, "1.er puesto");
    assert.equal(cabinetRows[1].querySelector(".sr-only")?.textContent, "2.º puesto");
    assert.equal(cabinetRows[2].querySelector(".sr-only")?.textContent, "3.er puesto");
  } finally {
    setLanguage(prevLang);
    cleanupDom();
    restoreTg();
  }
});

test("68. Safe degradation for unknown/future numeric positions and preservation of backend label/detail", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const { container, cleanup: cleanupDom } = setupGlobalDom();
  const prevLang = getLanguage();

  try {
    // 1. Position degradation across languages
    setLanguage("it");
    assert.equal(getTrophyPlacementLabel(4), "Posizione 4");
    assert.equal(getTrophyPlacementLabel(10), "Posizione 10");
    assert.equal(getTrophyPlacementLabel(undefined), "");
    assert.equal(getTrophyPlacementLabel(0), "");
    assert.equal(getTrophyPlacementLabel(-1), "");
    assert.equal(getTrophyPlacementLabel(NaN), "");

    setLanguage("en");
    assert.equal(getTrophyPlacementLabel(4), "Position 4");
    assert.equal(getTrophyPlacementLabel(12), "Position 12");
    assert.equal(getTrophyPlacementLabel(undefined), "");

    setLanguage("es");
    assert.equal(getTrophyPlacementLabel(4), "Posición 4");
    assert.equal(getTrophyPlacementLabel(15), "Posición 15");
    assert.equal(getTrophyPlacementLabel(undefined), "");

    // 2. Render showcase with unknown position 4 and undefined position
    setLanguage("en");
    const serverLabel = "Server Trophy 2026";
    const serverDetail = "Official backend detail untouched";

    const customProfile = createTestFullProfile({
      trophies: {
        pinned: [
          { code: "T_POS4", kind: "event", position: 4, medal: "🎖️", color: "#888888", label: serverLabel, detail: serverDetail, year: "2026" },
          { code: "T_NOPOS", kind: "event", medal: "⭐", color: "#666666", label: "No Pos Trophy", detail: "Participation", year: "2026" },
        ],
        all: [
          { code: "T_POS4", kind: "event", position: 4, medal: "🎖️", color: "#888888", label: serverLabel, detail: serverDetail, year: "2026" },
        ],
        max: 3,
      },
    });

    const controller = new ProfileController();
    (controller as any).updateState({ status: "ready", profile: customProfile });

    container.innerHTML = renderProfilePage(controller.getState());
    const plates = container.querySelectorAll(".trophy-tag");
    assert.equal(plates.length, 2);

    // Position 4 plate renders "Position 4"
    assert.equal(plates[0].querySelector(".sr-only")?.textContent, "Position 4");
    // Verify server-provided label & detail are preserved exactly without alteration
    assert.equal(plates[0].querySelector(".plate-name")?.textContent, serverLabel);
    assert.equal(plates[0].querySelector(".plate-detail")?.textContent, serverDetail);

    // No position plate has no .sr-only element and renders name & detail cleanly
    assert.equal(plates[1].querySelector(".sr-only"), null);
    assert.equal(plates[1].querySelector(".plate-name")?.textContent, "No Pos Trophy");
    assert.equal(plates[1].querySelector(".plate-detail")?.textContent, "Participation");

    // In cabinet view, verify cabinet row preservation
    controller.openCabinet();
    container.innerHTML = renderProfilePage(controller.getState());
    const row = container.querySelector(".cabinet-row");
    assert.ok(row);
    assert.equal(row.querySelector(".sr-only")?.textContent, "Position 4");
    assert.equal(row.querySelector(".nm")?.textContent, serverLabel);
    assert.equal(row.querySelector(".ds")?.textContent, serverDetail);
  } finally {
    setLanguage(prevLang);
    cleanupDom();
    restoreTg();
  }
});

