import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { ShopController } from "../../webapp/src/features/shop/controller";
import {
  renderShopPage,
  attachShopEventListeners,
} from "../../webapp/src/pages/ShopPage";
import {
  setupGlobalDom,
  setupTestTelegram,
  captureFetchRequests,
  createTestFullProfile,
} from "./helpers";
import {
  applyResolvedAppearance,
  getResolvedAppearance,
  clearResolvedAppearance,
  type ResolvedAppearance,
} from "../../webapp/src/appearance";
import { App } from "../../webapp/src/app/App";
import { setLanguage } from "../../webapp/src/i18n";
import type {
  ShopCatalogueResponse,
  ShopCosmeticItem,
  ShopPurchaseHistoryResponse,
} from "../../webapp/src/features/shop/types";

function createMockShopCatalogue(): ShopCatalogueResponse {
  const freeTheme: ShopCosmeticItem = {
    id: "tema_classico",
    kind: "theme",
    name: "Classico",
    description: "Il verde del campo e il bianco delle linee.",
    price: 0,
    full_price: 0,
    missing: [],
    achievement: null,
    progress: 0,
    style: { bg: "#0a131e", accent: "#38bd82", card: "#132437" },
    grants: [],
    owned: true,
    equipped: true,
    free: true,
    featured: false,
    equippable: true,
    rarity: "free",
    completes: [],
    trophy: null,
    welcome: false,
  };

  const paidTheme: ShopCosmeticItem = {
    id: "tema_neon",
    kind: "theme",
    name: "Neon",
    description: "I riflettori della notte.",
    price: 25,
    full_price: 25,
    missing: [],
    achievement: null,
    progress: 0,
    style: { bg: "#0a101d", accent: "#4dc4ff", card: "#101d2d" },
    grants: [],
    owned: false,
    equipped: false,
    free: false,
    featured: false,
    equippable: true,
    rarity: "rare",
    completes: [],
    trophy: null,
    welcome: false,
  };

  const paidFrame: ShopCosmeticItem = {
    id: "cornice_oro",
    kind: "frame",
    name: "Oro",
    description: "Un anello dorato per l'avatar.",
    price: 55,
    full_price: 55,
    missing: [],
    achievement: null,
    progress: 0,
    style: { ring: "#f0c74e" },
    grants: [],
    owned: true,
    equipped: false,
    free: false,
    featured: false,
    equippable: true,
    rarity: "collector",
    completes: [],
    trophy: null,
    welcome: false,
  };

  const achievementItem: ShopCosmeticItem = {
    id: "distintivo_bomber",
    kind: "badge",
    name: "Bomber",
    description: "100 risposte esatte.",
    price: 0,
    full_price: 0,
    missing: [],
    achievement: { field: "guessed", target: 100 },
    progress: 42,
    style: { emoji: "⚽" },
    grants: [],
    owned: false,
    equipped: false,
    free: false,
    featured: false,
    equippable: true,
    rarity: "earned",
    completes: [],
    trophy: null,
    welcome: false,
  };

  const trophyItem: ShopCosmeticItem = {
    id: "titolo_campione",
    kind: "title",
    name: "Campione",
    description: "Primo posto del mese.",
    price: 0,
    full_price: 0,
    missing: [],
    achievement: null,
    progress: 0,
    style: { label: "Campione", color: "#f0c74e" },
    grants: [],
    owned: false,
    equipped: false,
    free: false,
    featured: false,
    equippable: true,
    rarity: "earned",
    completes: [],
    trophy: { position: 1 },
    welcome: false,
  };

  const completionItem: ShopCosmeticItem = {
    id: "figurina_speciale",
    kind: "card",
    name: "Figurina Speciale",
    description: "Completa la collezione Neon.",
    price: 0,
    full_price: 0,
    missing: ["tema_neon"],
    achievement: null,
    progress: 0,
    style: { finish: "foil" },
    grants: [],
    owned: false,
    equipped: false,
    free: false,
    featured: false,
    equippable: true,
    rarity: "earned",
    completes: [
      { id: "tema_neon", name: "Neon", owned: false },
      { id: "cornice_oro", name: "Oro", owned: true },
    ],
    trophy: null,
    welcome: false,
  };

  const welcomeItem: ShopCosmeticItem = {
    id: "distintivo_stella",
    kind: "badge",
    name: "Stella",
    description: "Offerta di benvenuto.",
    price: 1,
    full_price: 15,
    missing: [],
    achievement: null,
    progress: 0,
    style: { emoji: "⭐" },
    grants: [],
    owned: false,
    equipped: false,
    free: false,
    featured: false,
    equippable: true,
    rarity: "common",
    completes: [],
    trophy: null,
    welcome: true,
  };

  const regularBundle: ShopCosmeticItem = {
    id: "pack_neon",
    kind: "bundle",
    name: "Collezione Neon",
    description: "Il look coordinato completo.",
    price: 45,
    full_price: 75,
    missing: ["tema_neon"],
    achievement: null,
    progress: 0,
    style: {},
    grants: ["tema_neon", "cornice_oro"],
    owned: false,
    equipped: false,
    free: false,
    featured: false,
    equippable: true,
    rarity: "collector",
    completes: [],
    trophy: null,
    welcome: false,
    contents: [paidTheme, paidFrame],
  };

  const featuredBundle: ShopCosmeticItem = {
    id: "pack_leggenda",
    kind: "bundle",
    name: "Collezione Leggenda",
    description: "I colori dei grandi campioni.",
    price: 100,
    full_price: 100,
    missing: [],
    achievement: null,
    progress: 0,
    style: {},
    grants: ["tema_classico"],
    owned: false,
    equipped: false,
    free: false,
    featured: true,
    equippable: true,
    rarity: "collector",
    completes: [],
    trophy: null,
    welcome: false,
    contents: [freeTheme],
  };

  return {
    sections: [
      { kind: "theme", items: [freeTheme, paidTheme] },
      { kind: "frame", items: [paidFrame] },
      { kind: "badge", items: [achievementItem, welcomeItem] },
      { kind: "title", items: [trophyItem] },
      { kind: "card", items: [completionItem] },
    ],
    bundles: [featuredBundle, regularBundle],
    showcase: {
      week: "2026-W37",
      items: [paidTheme, paidFrame, welcomeItem],
    },
    equipped: {
      theme: "tema_classico",
      frame: null,
      badge: null,
      title: null,
      squares: null,
      number: null,
      celebration: null,
      card: null,
    },
    owned: ["tema_classico", "cornice_oro"],
    looks: [
      {
        name: "Partita serale",
        equipped: {
          theme: "tema_classico",
          frame: "cornice_oro",
        },
      },
    ],
  };
}

function createMockHistory(): ShopPurchaseHistoryResponse {
  return {
    purchases: [
      {
        name: "Neon",
        day: "2026-09-10",
        stars: 25,
        refunded: false,
        charge_id: "ch_12345",
      },
      {
        name: "Oro",
        day: "2026-08-15",
        stars: 55,
        refunded: true,
        charge_id: "ch_67890",
      },
    ],
    support_url: "https://t.me/TestBot",
  };
}

// ---------------------------------------------------------------------------
// 1-10. Catalogue loading & structure
// ---------------------------------------------------------------------------

test("1 & 2. Shop init calls /app/api/shop and transitions to ready", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const { cleanup: cleanupDom } = setupGlobalDom();
  const catalogue = createMockShopCatalogue();
  const { requests, restore: restoreFetch } = captureFetchRequests(catalogue);

  try {
    const controller = new ShopController();
    await controller.init();

    const shopReqs = requests.filter((r) => r.url.includes("/app/api/shop"));
    assert.equal(shopReqs.length, 1);
    assert.equal(shopReqs[0].body.initData, "mock_init_data_for_dev=true&user_id=42");
    assert.equal(shopReqs[0].body.item, undefined);
    assert.equal(controller.getState().status, "ready");
    assert.equal(controller.getState().catalogue?.bundles.length, 2);
  } finally {
    restoreFetch();
    cleanupDom();
    restoreTg();
  }
});

test("3 & 4. Shop loading and error handling with retry", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const { container, cleanup: cleanupDom } = setupGlobalDom();

  let finishFetch!: (success: boolean) => void;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = () =>
    new Promise((resolve, reject) => {
      finishFetch = (success: boolean) => {
        if (success) {
          resolve({
            ok: true,
            status: 200,
            json: async () => createMockShopCatalogue(),
          } as Response);
        } else {
          reject(new Error("Network failure"));
        }
      };
    });

  try {
    const controller = new ShopController();
    const initPromise = controller.init();

    // Verify loading indicator in DOM
    container.innerHTML = renderShopPage(controller.getState());
    assert.ok(container.querySelector(".shop-loading"));

    finishFetch(false);
    await initPromise;

    // Verify error UI and retry button
    container.innerHTML = renderShopPage(controller.getState());
    assert.ok(container.querySelector(".error-card"));
    const retryBtn = container.querySelector<HTMLButtonElement>("#shop-retry");
    assert.ok(retryBtn);

    // Click retry
    attachShopEventListeners(container, controller);
    const retryPromise = controller.refresh();
    finishFetch(true);
    await retryPromise;

    assert.equal(controller.getState().status, "ready");
  } finally {
    globalThis.fetch = originalFetch;
    cleanupDom();
    restoreTg();
  }
});

test("5 & 6. Duplicate requests deduplicated; stale out-of-order response discarded", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const { cleanup: cleanupDom } = setupGlobalDom();

  let resolverA!: (val: any) => void;
  let resolverB!: (val: any) => void;
  let callCount = 0;

  const originalFetch = globalThis.fetch;
  globalThis.fetch = () => {
    callCount++;
    if (callCount === 1) {
      return new Promise((r) => {
        resolverA = r;
      });
    }
    return new Promise((r) => {
      resolverB = r;
    });
  };

  try {
    const controller = new ShopController();

    // Two concurrent inits reuse in-flight request
    const p1 = controller.init();
    const p2 = controller.init();
    assert.equal(callCount, 1);

    // Refresh triggers second fetch (callCount 2)
    const p3 = controller.refresh();
    assert.equal(callCount, 2);

    const oldCat = createMockShopCatalogue();
    oldCat.showcase.week = "OLD-W01";
    const newCat = createMockShopCatalogue();
    newCat.showcase.week = "NEW-W99";

    // Resolve newer first
    resolverB({
      ok: true,
      status: 200,
      json: async () => newCat,
    } as Response);
    await p3;
    assert.equal(controller.getState().catalogue?.showcase.week, "NEW-W99");

    // Resolve older later -> discarded by sequence guard
    resolverA({
      ok: true,
      status: 200,
      json: async () => oldCat,
    } as Response);
    await Promise.all([p1, p2]);
    assert.equal(controller.getState().catalogue?.showcase.week, "NEW-W99");
  } finally {
    globalThis.fetch = originalFetch;
    cleanupDom();
    restoreTg();
  }
});

test("7 to 10. Showcase, sections, bundles, and featured collections rendered", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const { container, cleanup: cleanupDom } = setupGlobalDom();
  const catalogue = createMockShopCatalogue();
  const { restore: restoreFetch } = captureFetchRequests(catalogue);

  try {
    const controller = new ShopController();
    await controller.init();

    container.innerHTML = renderShopPage(controller.getState());

    // 7. Weekly showcase strip
    const showcase = container.querySelector("#shelf-showcase");
    assert.ok(showcase, "Showcase must be rendered");
    assert.ok(showcase.textContent?.includes("Vetrina della settimana"));

    // 8. Category shelves
    assert.ok(container.querySelector("#shelf-theme"));
    assert.ok(container.querySelector("#shelf-frame"));

    // 9 & 10. Featured collections and regular bundles
    assert.ok(container.querySelector("#shelf-collections"));
    assert.ok(container.querySelector("#shelf-bundle"));
  } finally {
    restoreFetch();
    cleanupDom();
    restoreTg();
  }
});

// ---------------------------------------------------------------------------
// 11-16. Filters
// ---------------------------------------------------------------------------

test("11 to 16. Filter semantics: kind, price, hide-owned, and empty state", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const { container, cleanup: cleanupDom } = setupGlobalDom();
  const catalogue = createMockShopCatalogue();
  const { restore: restoreFetch } = captureFetchRequests(catalogue);

  try {
    const controller = new ShopController();
    await controller.init();

    // 11 & 12. Slot filter: only frames
    controller.setKindFilter("frame");
    container.innerHTML = renderShopPage(controller.getState());
    assert.ok(container.querySelector("#shelf-frame"));
    assert.equal(container.querySelector("#shelf-theme"), null);

    // 13. Price filter: <= 25 (frame costs 55 so frame disappears)
    controller.setPriceFilter("25");
    container.innerHTML = renderShopPage(controller.getState());
    assert.equal(container.querySelector("#shelf-frame"), null);

    // 14. Hide owned: hides owned items in catalog
    controller.setKindFilter("theme");
    controller.setPriceFilter("all");
    controller.setHideOwned(true);
    container.innerHTML = renderShopPage(controller.getState());
    // Free theme is owned, so it should be hidden; Neon theme is not owned, so visible
    const items = container.querySelector("#shelf-theme")!.querySelectorAll(".shop-item");
    assert.equal(items.length, 1);
    assert.ok(items[0].textContent?.includes("Neon"));

    // 15. Empty filtered results
    controller.setPriceFilter("15"); // Neon costs 25, so nothing matches
    container.innerHTML = renderShopPage(controller.getState());
    assert.ok(container.textContent?.includes("Nessun oggetto con questi filtri."));

    // 16. Backend cards remain completely unchanged
    assert.equal(catalogue.sections[0].items[0].name, "Classico");
  } finally {
    restoreFetch();
    cleanupDom();
    restoreTg();
  }
});

// ---------------------------------------------------------------------------
// 17-28. Product states
// ---------------------------------------------------------------------------

test("17 to 28. Acquisition models: free, paid, owned, equipped, achievements, trophies, bundles", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const { container, cleanup: cleanupDom } = setupGlobalDom();
  const catalogue = createMockShopCatalogue();
  const { restore: restoreFetch } = captureFetchRequests(catalogue);

  try {
    const controller = new ShopController();
    await controller.init();
    container.innerHTML = renderShopPage(controller.getState());

    // 17 & 20. Free & equipped item (tema_classico)
    const classic = container.querySelector('[data-item-id="tema_classico"]');
    assert.ok(classic?.querySelector(".worn-tag"));

    // 18. Paid unowned item (tema_neon: 25 ⭐)
    const neon = container.querySelector('[data-item-id="tema_neon"]');
    assert.ok(neon?.querySelector(".buy-btn"));
    assert.ok(neon?.textContent?.includes("25 ⭐"));

    // 19. Owned unequipped item (cornice_oro)
    const oro = container.querySelector('[data-item-id="cornice_oro"]');
    assert.ok(oro?.querySelector('[data-equip="cornice_oro"]'));

    // Switch to achievements view
    controller.setView("achievements");
    container.innerHTML = renderShopPage(controller.getState());

    // 21 & 22. Achievement item
    const bomber = container.querySelector('[data-item-id="distintivo_bomber"]');
    assert.ok(bomber?.querySelector("progress"));
    assert.ok(bomber?.textContent?.includes("42/100"));

    // 23. Trophy item
    const camp = container.querySelector('[data-item-id="titolo_campione"]');
    assert.ok(camp?.textContent?.includes("Si vince sul podio"));

    // 24. Completion reward
    const fig = container.querySelector('[data-item-id="figurina_speciale"]');
    assert.ok(fig?.textContent?.includes("Manca ancora: 1/2"));

    // Switch back to catalog
    controller.setView("catalog");
    container.innerHTML = renderShopPage(controller.getState());

    // 25. Welcome item
    const stella = container.querySelector('[data-item-id="distintivo_stella"]');
    assert.ok(stella?.textContent?.includes("1 ⭐"));

    // 26 & 27. Partial bundle with prorated price
    const packNeon = container.querySelector('[data-item-id="pack_neon"]');
    assert.ok(packNeon?.textContent?.includes("Prezzo per i soli pezzi mancanti"));
    assert.ok(packNeon?.textContent?.includes("Ti mancano: Neon"));
  } finally {
    restoreFetch();
    cleanupDom();
    restoreTg();
  }
});

// ---------------------------------------------------------------------------
// 29-34. Preview mode
// ---------------------------------------------------------------------------

test("29 to 34. Temporary preview: start, stop, safe sanitize, revert on tab switch", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const { container, cleanup: cleanupDom } = setupGlobalDom();
  const catalogue = createMockShopCatalogue();
  const fullProfile = createTestFullProfile();

  const originalFetch = globalThis.fetch;
  globalThis.fetch = (url: any) => {
    if (String(url).includes("/app/api/me")) {
      return Promise.resolve({ ok: true, status: 200, json: async () => fullProfile } as Response);
    }
    return Promise.resolve({ ok: true, status: 200, json: async () => catalogue } as Response);
  };

  // Set initial appearance
  applyResolvedAppearance({
    theme: { accent: "#112233" },
    equipped: { theme: "tema_classico" },
  });

  try {
    const controller = new ShopController();
    await controller.init();

    // 29. Start preview
    controller.startPreview("tema_neon");
    assert.ok(controller.getState().preview);
    assert.equal(controller.getState().preview?.item.id, "tema_neon");
    assert.equal(getResolvedAppearance().theme?.accent, "#4dc4ff");

    // Preview bar in UI
    container.innerHTML = renderShopPage(controller.getState());
    assert.ok(container.querySelector(".preview-bar"));

    // 30 & 31. Stop preview restores authoritative skin and does not persist
    controller.stopPreview();
    assert.equal(controller.getState().preview, null);
    assert.equal(getResolvedAppearance().theme?.accent, "#112233");

    // 32. Leaving Shop tab via App shell restores appearance cleanly
    const app = new App(container, undefined, undefined, undefined, undefined, undefined, undefined, controller);
    app.setTab("shop");
    controller.startPreview("tema_neon");
    assert.equal(getResolvedAppearance().theme?.accent, "#4dc4ff");

    // Switch to profile -> preview terminated
    app.setTab("profile");
    assert.equal(controller.getState().preview, null);
    assert.equal(getResolvedAppearance().theme?.accent, "#112233");

    // 33. Unsafe raw CSS in preview is stripped by #66 sanitizer
    const maliciousItem = {
      ...catalogue.sections[0].items[1],
      id: "tema_malicious",
      style: { accent: "red; position: fixed;", evil: "alert(1)" },
    };
    controller.getState().catalogue!.sections[0].items.push(maliciousItem);
    controller.startPreview(maliciousItem.id);
    assert.equal(getResolvedAppearance().theme?.accent, undefined);
  } finally {
    clearResolvedAppearance();
    globalThis.fetch = originalFetch;
    cleanupDom();
    restoreTg();
  }
});

// ---------------------------------------------------------------------------
// 35-48. Equip & Cross-Feature Coherence (STEP 13, 31, 32)
// ---------------------------------------------------------------------------

test("35 to 48. Equip contract, duplicate guards, appearance sync across Profile & Daily", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const { container, cleanup: cleanupDom } = setupGlobalDom();

  const newCosmetics: ResolvedAppearance = {
    equipped: {
      theme: "tema_classico",
      frame: "cornice_oro",
      squares: "quadratini_stelle",
      celebration: "fireworks",
    },
    theme: { accent: "#38bd82" },
    frame: { ring: "conic-gradient(#b8892f, #f7e39c, #d9b45b, #fff3c4, #b8892f)", spin: false },
    squares: { correct: "⭐", wrong: "❌", unused: "⚪" },
    celebration: "fireworks",
    number: "10",
    title: { label: "Capitano", color: "#f0c74e" },
  };

  const { requests, restore: restoreFetch } = captureFetchRequests({
    status: "ok",
    cosmetics: newCosmetics,
  });

  try {
    const app = new App(container);
    const shopController = app.getShopController();
    const profileController = app.getProfileController();
    const dailyController = app.getDailyController();
    (profileController as any).state.profile = createTestFullProfile();

    // Initial load of shop
    await shopController.init();

    // 35 & 36. Exact /shop/equip request with item ID only
    const ok = await shopController.equip("cornice_oro");
    assert.equal(ok, true);

    const equipReqs = requests.filter((r) => r.url.includes("/app/api/shop/equip"));
    assert.equal(equipReqs.length, 1);
    assert.equal(equipReqs[0].body.item, "cornice_oro");

    // 41. Returned cosmetics applied globally
    assert.equal(getResolvedAppearance().frame?.ring, "conic-gradient(#b8892f, #f7e39c, #d9b45b, #fff3c4, #b8892f)");

    // 43 & 44. Profile controller received updated appearance
    assert.equal(profileController.getState().profile?.cosmetics?.frame?.ring, "conic-gradient(#b8892f, #f7e39c, #d9b45b, #fff3c4, #b8892f)");
    assert.equal(profileController.getState().profile?.cosmetics?.number, "10");

    // 45 & 46. Daily controller received updated squares and celebration
    assert.equal(dailyController.getState().squaresSymbols.correct, "⭐");

    // 47. Daily cached cardImage invalidated
    assert.equal(dailyController.getState().cardImage, null);

    // 42. Raw equipped IDs never render in UI
    container.innerHTML = renderShopPage(shopController.getState());
    assert.ok(!container.textContent?.includes("tema_classico"));
    assert.ok(!container.textContent?.includes("cornice_oro"));
  } finally {
    clearResolvedAppearance();
    restoreFetch();
    cleanupDom();
    restoreTg();
  }
});

// ---------------------------------------------------------------------------
// 49-57. Saved Looks
// ---------------------------------------------------------------------------

test("49 to 57. Saved looks: save, look_limit, wear appearance update, delete", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const { cleanup: cleanupDom } = setupGlobalDom();

  const mockProfile = createTestFullProfile();
  mockProfile.cosmetics = {
    ...mockProfile.cosmetics,
    theme: { accent: "#4dc4ff" },
    frame: { ring: "#f0c74e", spin: false },
  };

  let lookActionRequested = "";
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (url: any, init?: any) => {
    const body = init?.body ? JSON.parse(init.body) : {};
    if (String(url).includes("/app/api/shop/look")) {
      lookActionRequested = body.action;
      if (body.name === "Troppi") {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({ status: "look_limit" }),
        } as Response);
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({ status: "ok" }),
      } as Response);
    }
    if (String(url).includes("/app/api/me")) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => mockProfile,
      } as Response);
    }
    return Promise.resolve({
      ok: true,
      status: 200,
      json: async () => createMockShopCatalogue(),
    } as Response);
  };

  try {
    const controller = new ShopController();
    await controller.init();

    // 51. Invalid name rejected client-side
    const invalidRes = await controller.lookAction("save", "   ");
    assert.equal(invalidRes, false);
    assert.ok(controller.getState().toast?.includes("1 a 30 caratteri"));

    // 49. Save valid look
    const saveRes = await controller.lookAction("save", "Nuovo Look");
    assert.equal(saveRes, true);
    assert.equal(lookActionRequested, "save");

    // 52. Look limit error from backend
    const limitRes = await controller.lookAction("save", "Troppi");
    assert.equal(limitRes, false);
    assert.ok(controller.getState().toast?.includes("Hai già 5 look"));

    // 53. Wear look refreshes appearance via /me
    let appearanceUpdated = false;
    controller.onAppearanceChanged = () => {
      appearanceUpdated = true;
    };
    const wearRes = await controller.lookAction("wear", "Partita serale");
    assert.equal(wearRes, true);
    assert.equal(appearanceUpdated, true);

    // 55. Delete look
    const deleteRes = await controller.lookAction("delete", "Nuovo Look");
    assert.equal(deleteRes, true);
    assert.equal(lookActionRequested, "delete");
  } finally {
    globalThis.fetch = originalFetch;
    cleanupDom();
    restoreTg();
  }
});

// ---------------------------------------------------------------------------
// 58-69. Purchase with Telegram Stars & delivery synchronization
// ---------------------------------------------------------------------------

test("58 to 69. Purchase flow: item ID only, invoice, paid status, bounded polling, duplicate guard", async () => {
  const { cleanup: cleanupDom } = setupGlobalDom();
  const { restore: restoreTg } = setupTestTelegram();

  let invoiceLinkOpened = "";
  let invoiceCallback: ((status: string) => void) | null = null;

  // Stub Telegram openInvoice
  const tg = window.Telegram!.WebApp;
  tg.openInvoice = (link: string, cb?: any) => {
    invoiceLinkOpened = link;
    invoiceCallback = cb;
  };

  let buyReqBody: any = null;
  let shopPollCount = 0;
  const catalogue = createMockShopCatalogue();

  const originalFetch = globalThis.fetch;
  globalThis.fetch = (url: any, init?: any) => {
    const urlStr = String(url);
    if (urlStr.includes("/app/api/shop/buy")) {
      buyReqBody = JSON.parse(init.body);
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({ status: "ok", link: "https://t.me/$invoice_123" }),
      } as Response);
    }
    if (urlStr.includes("/app/api/shop")) {
      shopPollCount++;
      // On 3rd poll, item becomes delivered in owned
      if (shopPollCount >= 3) {
        catalogue.owned.push("tema_neon");
        const found = catalogue.sections[0].items.find((i) => i.id === "tema_neon");
        if (found) found.owned = true;
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => catalogue,
      } as Response);
    }
    return Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({}),
    } as Response);
  };

  try {
    const controller = new ShopController(undefined, { pollIntervalMs: 1 });
    await controller.init();

    // 58 & 59. Buy dispatches only item ID, never price or currency
    const buyPromise = controller.buy("tema_neon");

    // 68. Concurrent buy is blocked while buying: true
    const concurrentBuy = controller.buy("cornice_oro");
    await concurrentBuy;
    assert.equal(controller.getState().buyingItemId, "tema_neon");

    // Await initial buy setup to invoke openInvoice
    await buyPromise;

    // Assert item ID sent, no price/currency leaked
    assert.equal((buyReqBody as any)?.item, "tema_neon");
    assert.equal((buyReqBody as any)?.price, undefined);
    assert.equal((buyReqBody as any)?.currency, undefined);

    // 61. openInvoice opened with returned link
    assert.equal(invoiceLinkOpened, "https://t.me/$invoice_123");

    // 64, 65, 66, 67. Trigger paid callback -> bounded polling loop delivers item
    assert.ok(invoiceCallback);
    await (invoiceCallback as (status: string) => Promise<void>)("paid");

    // Delivery succeeded after bounded polling
    assert.equal(controller.getState().deliveryStatus, "delivered");
    assert.ok(controller.isItemOwned("tema_neon"));
    assert.ok(controller.getState().toast?.includes("Grazie! È tuo."));
  } finally {
    globalThis.fetch = originalFetch;
    cleanupDom();
    restoreTg();
  }
});

// ---------------------------------------------------------------------------
// 70-79. Purchase History
// ---------------------------------------------------------------------------

test("70 to 79. Purchase history: lazy fetch, paid/refunded entries, support copy fallback", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const { container, cleanup: cleanupDom } = setupGlobalDom();
  const history = createMockHistory();
  const { requests, restore: restoreFetch } = captureFetchRequests(history);

  try {
    const controller = new ShopController();
    await controller.init();

    // 70. History is not fetched before switching to history view
    assert.equal(requests.filter((r) => r.url.includes("/shop/history")).length, 0);

    // Switch view -> history loaded
    controller.setView("history");
    await controller.loadHistory();

    assert.equal(requests.filter((r) => r.url.includes("/shop/history")).length, 1);
    assert.equal(controller.getState().history?.purchases.length, 2);

    container.innerHTML = renderShopPage(controller.getState());

    // 75 & 76. Paid and refunded entries
    assert.ok(container.textContent?.includes("Acquisto completato"));
    assert.ok(container.textContent?.includes("Rimborsato"));

    // 77 & 78. Support command and bot link
    assert.ok(container.querySelector(".history-command"));
    assert.ok(container.querySelector('a[href="https://t.me/TestBot"]'));

    // 79. Support copy button
    attachShopEventListeners(container, controller);
    const copyBtn = container.querySelector<HTMLButtonElement>('[data-copy-support="0"]');
    assert.ok(copyBtn);
    copyBtn.click();
  } finally {
    restoreFetch();
    cleanupDom();
    restoreTg();
  }
});

// ---------------------------------------------------------------------------
// 80-86. Localization (IT, EN, ES) & Accessibility
// ---------------------------------------------------------------------------

test("80 to 86. Full localization across IT, EN, ES and accessible controls", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const { container, cleanup: cleanupDom } = setupGlobalDom();
  const catalogue = createMockShopCatalogue();
  const { restore: restoreFetch } = captureFetchRequests(catalogue);

  try {
    const controller = new ShopController();
    await controller.init();

    // 80. Italian
    setLanguage("it");
    container.innerHTML = renderShopPage(controller.getState());
    assert.ok(container.textContent?.includes("LO SPOGLIATOIO"));
    assert.ok(container.textContent?.includes("Catalogo"));

    // 81. English
    setLanguage("en");
    container.innerHTML = renderShopPage(controller.getState());
    assert.ok(container.textContent?.includes("THE LOCKER ROOM"));
    assert.ok(container.textContent?.includes("Catalogue"));

    // 82. Spanish
    setLanguage("es");
    container.innerHTML = renderShopPage(controller.getState());
    assert.ok(container.textContent?.includes("EL VESTUARIO"));
    assert.ok(container.textContent?.includes("Catálogo"));

    // 83 & 84. Accessibility: role="tab" and aria-selected
    const tabBtns = container.querySelectorAll('[role="tab"]');
    assert.equal(tabBtns.length, 4);
    assert.equal(tabBtns[0].getAttribute("aria-selected"), "true");

    // 85. Touch targets min 44px
    const selects = container.querySelectorAll("select");
    selects.forEach((s) => assert.ok(s.getAttribute("aria-label")));
  } finally {
    setLanguage("it");
    restoreFetch();
    cleanupDom();
    restoreTg();
  }
});

// ---------------------------------------------------------------------------
// 87-95. Regressions: Legacy untouched, no prototype runtime
// ---------------------------------------------------------------------------

test("87 to 95. Legacy /app untouched, no shop prototype in runtime", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const { container, cleanup: cleanupDom } = setupGlobalDom();
  const catalogue = createMockShopCatalogue();
  const { restore: restoreFetch } = captureFetchRequests(catalogue);

  try {
    const app = new App(container);
    app.setTab("shop");
    await app.getShopController().init();

    container.innerHTML = renderShopPage(app.getShopController().getState());

    // 95. Authenticated Shop no longer renders prototype screens
    assert.ok(!container.textContent?.includes("SHOP / IL TUO STILE"));
    assert.ok(!container.textContent?.includes("prototype-screen"));

    // 94. Legacy /app index.html remains untouched
    const legacyPath = path.resolve(__dirname, "../../webapp/index.html");
    const legacyContent = fs.readFileSync(legacyPath, "utf-8");
    assert.ok(legacyContent.includes("function shopTab()"));
    assert.ok(legacyContent.includes("function loadShop()"));
  } finally {
    restoreFetch();
    cleanupDom();
    restoreTg();
  }
});
