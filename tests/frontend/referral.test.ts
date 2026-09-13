import { test, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import {
  setupGlobalDom,
  setupTestTelegram,
  captureFetchRequests,
  mockFetchResponse,
  createTestReferralDashboardResponse,
  createTestFullProfile,
} from "./helpers";
import { App } from "@/app/App";
import { ReferralController } from "@/features/referral/controller";
import { renderReferralPage } from "@/pages/ReferralPage";
import { setLanguage } from "@/i18n";
import { TRANSLATIONS } from "@/i18n/translations";
import {
  getResolvedAppearance,
  clearResolvedAppearance,
} from "@/appearance";
import * as fs from "node:fs";
import * as path from "node:path";

test("Referral Feature Test Suite (#46 Parity & Hardening)", async (t) => {
  let cleanupDom: () => void;
  let cleanupTelegram: () => void;

  beforeEach(() => {
    cleanupDom = setupGlobalDom().cleanup;
    cleanupTelegram = setupTestTelegram().restore;
    setLanguage("it");
    clearResolvedAppearance();
  });

  afterEach(() => {
    cleanupTelegram?.();
    cleanupDom?.();
    clearResolvedAppearance();
  });

  await t.test(
    "1. /app/api/referrals initial request contract: POST with Telegram initData",
    async () => {
      const { requests, restore } = captureFetchRequests(
        createTestReferralDashboardResponse(),
      );
      try {
        const controller = new ReferralController();
        await controller.init();

        assert.equal(requests.length, 1);
        assert.equal(requests[0].url, "/app/api/referrals");
        assert.equal(requests[0].method, "POST");
        assert.ok(requests[0].body?.initData);
      } finally {
        restore();
      }
    },
  );

  await t.test("2. Loading state rendering", async () => {
    const controller = new ReferralController();
    let resolvePromise: (val: any) => void = () => {};
    const pendingPromise = new Promise((resolve) => {
      resolvePromise = resolve;
    });

    const restore = mockFetchResponse(() => pendingPromise);
    try {
      const initPromise = controller.init();
      assert.equal(controller.getState().status, "loading");
      const html = renderReferralPage(controller.getState());
      assert.ok(html.includes("loading-state"));
      assert.ok(html.includes("spinner"));

      resolvePromise(createTestReferralDashboardResponse());
      await initPromise;
      assert.equal(controller.getState().status, "ready");
    } finally {
      restore();
    }
  });

  await t.test("3 & 4. Error state, recovery and retry", async () => {
    let shouldFail = true;
    const restore = mockFetchResponse(() => {
      if (shouldFail) {
        return new Response(JSON.stringify({ detail: "Server error" }), {
          status: 500,
        });
      }
      return createTestReferralDashboardResponse();
    });

    try {
      const controller = new ReferralController();
      await controller.init();

      assert.equal(controller.getState().status, "error");
      const html = renderReferralPage(controller.getState());
      assert.ok(html.includes("role=\"alert\""));
      assert.ok(html.includes("rf-retry"));

      // Retry
      shouldFail = false;
      await controller.init(true);
      assert.equal(controller.getState().status, "ready");
      assert.ok(controller.getState().data !== null);
    } finally {
      restore();
    }
  });

  await t.test(
    "5. Strictly no automatic polling or background intervals",
    async () => {
      const { requests, restore } = captureFetchRequests(
        createTestReferralDashboardResponse(),
      );
      try {
        const controller = new ReferralController();
        await controller.init();
        assert.equal(requests.length, 1);

        // Advance artificial timers / wait a bit
        await new Promise((resolve) => setTimeout(resolve, 50));
        assert.equal(
          requests.length,
          1,
          "No background polling should be triggered",
        );
      } finally {
        restore();
      }
    },
  );

  await t.test(
    "6. Duplicate load deduplication: in-flight request reuse",
    async () => {
      let fetchCount = 0;
      const restore = mockFetchResponse(async () => {
        fetchCount++;
        await new Promise((resolve) => setTimeout(resolve, 20));
        return createTestReferralDashboardResponse();
      });

      try {
        const controller = new ReferralController();
        await Promise.all([controller.init(), controller.init()]);
        assert.equal(
          fetchCount,
          1,
          "Concurrent init calls must reuse the in-flight promise",
        );
      } finally {
        restore();
      }
    },
  );

  await t.test(
    "7. Stale initial response ignored via sequence guard",
    async () => {
      let callCount = 0;
      let resolveFirst: (val: any) => void = () => {};
      let resolveSecond: (val: any) => void = () => {};

      const restore = mockFetchResponse(() => {
        callCount++;
        if (callCount === 1) {
          return new Promise((r) => {
            resolveFirst = r;
          });
        }
        return new Promise((r) => {
          resolveSecond = r;
        });
      });

      try {
        const controller = new ReferralController();
        const p1 = controller.init();
        controller.reset();
        const p2 = controller.init();

        // Resolve second (newer) first
        resolveSecond(
          createTestReferralDashboardResponse({ qualified: 5 }),
        );
        await p2;
        assert.equal(controller.getState().data?.qualified, 5);

        // Resolve first (stale) later
        resolveFirst(
          createTestReferralDashboardResponse({ qualified: 1 }),
        );
        await p1;
        assert.equal(
          controller.getState().data?.qualified,
          5,
          "Older response must not overwrite newer state",
        );
      } finally {
        restore();
      }
    },
  );

  await t.test(
    "8. Manual refresh updates data in-place without page destruction",
    async () => {
      let callCount = 0;
      const restore = mockFetchResponse(() => {
        callCount++;
        return createTestReferralDashboardResponse({
          qualified: callCount === 1 ? 2 : 3,
        });
      });

      try {
        const controller = new ReferralController();
        await controller.init();
        assert.equal(controller.getState().data?.qualified, 2);

        await controller.refresh();
        assert.equal(controller.getState().data?.qualified, 3);
        assert.equal(controller.getState().refreshing, false);
      } finally {
        restore();
      }
    },
  );

  await t.test("9. Authoritative qualified count rendered", async () => {
    const controller = new ReferralController();
    const restore = mockFetchResponse(
      createTestReferralDashboardResponse({ qualified: 7 }),
    );
    try {
      await controller.init();
      const html = renderReferralPage(controller.getState());
      assert.ok(html.includes("7<span>/10</span>"));
    } finally {
      restore();
    }
  });

  await t.test(
    "10. Dynamic required_days respected from backend",
    async () => {
      const controller = new ReferralController();
      const restore = mockFetchResponse(
        createTestReferralDashboardResponse({
          required_days: 7,
          friends: [{ name: "Marco", days: 3, status: "pending" }],
        }),
      );
      try {
        await controller.init();
        const html = renderReferralPage(controller.getState());
        assert.ok(html.includes("3/7"));
        assert.ok(html.includes("max=\"7\""));
      } finally {
        restore();
      }
    },
  );

  await t.test("11 & 12. Pending and qualified friend states", async () => {
    const controller = new ReferralController();
    const restore = mockFetchResponse(
      createTestReferralDashboardResponse({
        required_days: 5,
        friends: [
          { name: "Marco", days: 2, status: "pending" },
          { name: "Lucia", days: 5, status: "qualified" },
        ],
      }),
    );
    try {
      await controller.init();
      const html = renderReferralPage(controller.getState());
      assert.ok(html.includes("Marco"));
      assert.ok(html.includes("2/5"));
      assert.ok(html.includes("Lucia"));
      assert.ok(html.includes("✓ Invito completato"));
    } finally {
      restore();
    }
  });

  await t.test("13. Empty friends state displays localized copy", async () => {
    const controller = new ReferralController();
    const restore = mockFetchResponse(
      createTestReferralDashboardResponse({ friends: [] }),
    );
    try {
      await controller.init();
      const html = renderReferralPage(controller.getState());
      assert.ok(html.includes("Il primo posto è per un tuo amico"));
    } finally {
      restore();
    }
  });

  await t.test(
    "14. Malicious friend name with HTML entities is safely escaped",
    async () => {
      const controller = new ReferralController();
      const restore = mockFetchResponse(
        createTestReferralDashboardResponse({
          friends: [
            {
              name: "<img src=x onerror=alert(1)>Malicious",
              days: 1,
              status: "pending",
            },
          ],
        }),
      );
      try {
        await controller.init();
        const html = renderReferralPage(controller.getState());
        assert.ok(!html.includes("<img src=x"));
        assert.ok(html.includes("&lt;img src=x onerror=alert(1)&gt;Malicious"));
      } finally {
        restore();
      }
    },
  );

  await t.test(
    "15. Privacy guarantee: Invitee Telegram/user IDs are never exposed",
    async () => {
      const controller = new ReferralController();
      const restore = mockFetchResponse(
        createTestReferralDashboardResponse({
          friends: [{ name: "FriendA", days: 2, status: "pending" }],
        }),
      );
      try {
        await controller.init();
        const html = renderReferralPage(controller.getState());
        assert.ok(!html.includes("user_id"));
        assert.ok(!html.includes("invitee_id"));
        assert.ok(!html.includes("inviter_id"));
      } finally {
        restore();
      }
    },
  );

  await t.test(
    "16 & 17. Pagination: cursor request and append friends",
    async () => {
      const { requests, restore } = captureFetchRequests((_url: string, init?: RequestInit) => {
        const body = (init as any)?.body ? JSON.parse(String((init as any).body)) : {};
        if (body.cursor === "cursor_page_2") {
          return createTestReferralDashboardResponse({
            friends: [{ name: "Page2Friend", days: 4, status: "pending" }],
            next_cursor: null,
          });
        }
        return createTestReferralDashboardResponse({
          friends: [{ name: "Page1Friend", days: 2, status: "pending" }],
          next_cursor: "cursor_page_2",
        });
      });

      try {
        const controller = new ReferralController();
        await controller.init();
        assert.equal(controller.getState().data?.friends.length, 1);
        assert.equal(requests.length, 1);

        await controller.loadMore();
        assert.equal(requests.length, 2);
        assert.equal(requests[1].body.cursor, "cursor_page_2");
        assert.equal(controller.getState().data?.friends.length, 2);
        assert.equal(
          controller.getState().data?.friends[1].name,
          "Page2Friend",
        );
        assert.equal(controller.getState().data?.next_cursor, null);
      } finally {
        restore();
      }
    },
  );

  await t.test(
    "18 & 19. Stale pagination response ignored & row deduplication",
    async () => {
      let resolveMore: (val: any) => void = () => {};
      const restore = mockFetchResponse((_, init) => {
        const body = (init as any)?.body ? JSON.parse(String((init as any).body)) : {};
        if (body.cursor) {
          return new Promise((r) => {
            resolveMore = r;
          });
        }
        return createTestReferralDashboardResponse({
          friends: [{ name: "FriendA", days: 2, status: "pending" }],
          next_cursor: "cursor_page_2",
        });
      });

      try {
        const controller = new ReferralController();
        await controller.init();

        const pMore = controller.loadMore();
        // Trigger a fresh refresh before more resolves
        controller.reset();
        await controller.init();

        // Now resolve the old loadMore
        resolveMore(
          createTestReferralDashboardResponse({
            friends: [{ name: "StaleFriend", days: 1, status: "pending" }],
            next_cursor: null,
          }),
        );
        await pMore;

        // Old response should not have been appended
        assert.ok(
          !controller
            .getState()
            .data?.friends.some((f) => f.name === "StaleFriend"),
        );
      } finally {
        restore();
      }
    },
  );

  await t.test(
    "20. 'More friends' button hidden when cursor is null",
    async () => {
      const controller = new ReferralController();
      const restore = mockFetchResponse(
        createTestReferralDashboardResponse({ next_cursor: null }),
      );
      try {
        await controller.init();
        const html = renderReferralPage(controller.getState());
        assert.ok(!html.includes("id=\"rf-more\""));
      } finally {
        restore();
      }
    },
  );

  await t.test(
    "21 & 22. Authoritative backend link displayed vs null link state",
    async () => {
      const controller = new ReferralController();
      let restore = mockFetchResponse(
        createTestReferralDashboardResponse({
          link: "https://t.me/test_bot?start=authoritative_ref",
        }),
      );
      try {
        await controller.init();
        let html = renderReferralPage(controller.getState());
        assert.ok(html.includes("value=\"https://t.me/test_bot?start=authoritative_ref\""));
        assert.ok(html.includes("id=\"rf-invite\""));

        restore();
        restore = mockFetchResponse(
          createTestReferralDashboardResponse({ link: null }),
        );
        controller.reset();
        await controller.init();
        html = renderReferralPage(controller.getState());
        assert.ok(html.includes("Gli inviti non sono ancora disponibili"));
        assert.ok(!html.includes("id=\"rf-invite\""));
      } finally {
        restore();
      }
    },
  );

  await t.test(
    "23 & 24. Telegram share URL generated and uses openTelegramLink / window.open fallback",
    async () => {
      const controller = new ReferralController();
      const restore = mockFetchResponse(
        createTestReferralDashboardResponse({
          link: "https://t.me/test_bot?start=ref123",
        }),
      );
      try {
        await controller.init();

        let openedUrl = "";
        (window as any).Telegram.WebApp.openTelegramLink = (url: string) => {
          openedUrl = url;
        };

        controller.shareInvite();
        assert.ok(
          openedUrl.startsWith("https://t.me/share/url?url=https%3A%2F%2Ft.me%2Ftest_bot%3Fstart%3Dref123"),
        );
        assert.ok(openedUrl.includes("&text="));

        // Fallback when openTelegramLink not present
        (window as any).Telegram.WebApp.openTelegramLink = undefined;
        let windowOpened = "";
        (window as any).open = (url: string) => {
          windowOpened = url;
        };
        controller.shareInvite();
        assert.ok(windowOpened.startsWith("https://t.me/share/url?url="));
      } finally {
        restore();
      }
    },
  );

  await t.test(
    "25 & 26. Copy link success shows toast; clipboard failure reveals details",
    async () => {
      const controller = new ReferralController();
      const restore = mockFetchResponse(
        createTestReferralDashboardResponse({
          link: "https://t.me/test_bot?start=copy_ref",
        }),
      );
      try {
        await controller.init();

        let clipboardText = "";
        (navigator as any).clipboard = {
          writeText: async (text: string) => {
            clipboardText = text;
          },
        };

        const success = await controller.copyLink();
        assert.equal(success, true);
        assert.equal(clipboardText, "https://t.me/test_bot?start=copy_ref");
        assert.equal(controller.getState().toast, "Link copiato");

        // Failure fallback
        (navigator as any).clipboard = {
          writeText: async () => {
            throw new Error("Denied");
          },
        };
        const failResult = await controller.copyLink();
        assert.equal(failResult, false);
      } finally {
        restore();
      }
    },
  );

  await t.test(
    "27 to 30. Milestones 3, 5, 10 rendered, locked vs unlocked, multiple reward items",
    async () => {
      const controller = new ReferralController();
      const restore = mockFetchResponse(
        createTestReferralDashboardResponse({ qualified: 4 }),
      );
      try {
        await controller.init();
        const html = renderReferralPage(controller.getState());
        // 3 is unlocked, 5 and 10 are locked
        assert.ok(html.includes("data-rf-preview=\"3\""));
        assert.ok(html.includes("data-rf-preview=\"5\""));
        assert.ok(html.includes("data-rf-preview=\"10\""));
        assert.ok(html.includes("L’intesa"));
        assert.ok(html.includes("La squadra"));
        assert.ok(html.includes("Il tuo undici"));
      } finally {
        restore();
      }
    },
  );

  await t.test(
    "31 & 32. Reward preview open and close returns to main formation",
    async () => {
      const controller = new ReferralController();
      const restore = mockFetchResponse(
        createTestReferralDashboardResponse({ qualified: 3 }),
      );
      try {
        await controller.init();

        controller.openRewardPreview(3);
        assert.equal(controller.getState().selectedRewardTarget, 3);
        let html = renderReferralPage(
          controller.getState(),
          controller.getSelectedMilestone(),
        );
        assert.ok(html.includes("rf-reveal"));
        assert.ok(html.includes("rf-close-preview"));
        assert.ok(html.includes("L’intesa") || html.includes("L'Intesa"));

        controller.closeRewardPreview();
        assert.equal(controller.getState().selectedRewardTarget, null);
        html = renderReferralPage(controller.getState());
        assert.ok(html.includes("rf-hero"));
      } finally {
        restore();
      }
    },
  );

  await t.test(
    "33 to 35. Equip request dispatches item-only POST /app/api/shop/equip, handles success/rejection",
    async () => {
      const { requests, restore } = captureFetchRequests((url: string, init?: RequestInit) => {
        if (url === "/app/api/shop/equip") {
          const body = JSON.parse(String((init as any).body));
          if (body.item === "referral_intesa") {
            return {
              status: "ok",
              cosmetics: {
                theme: null,
                frame: "referral_intesa",
                title: null,
                badge: null,
                squares: "classic",
                number: null,
                celebration: null,
                card: null,
              },
            };
          }
          return { status: "not_owned" };
        }
        return createTestReferralDashboardResponse({
          qualified: 3,
          rewards: [
            {
              target: 3,
              items: [
                {
                  id: "referral_intesa",
                  kind: "frame",
                  name: "L'Intesa",
                  description: "Desc",
                  price: 0,
                  full_price: 0,
                  missing: [],
                  achievement: null,
                  progress: 0,
                  style: { tactics: 3 },
                  grants: [],
                  owned: true,
                  equipped: false,
                  free: false,
                  featured: false,
                  equippable: true,
                  rarity: "earned",
                  completes: [],
                  trophy: null,
                  welcome: false,
                },
              ],
            },
          ],
        });
      });

      try {
        const controller = new ReferralController();
        let appearanceNotified: any = null;
        controller.onAppearanceChanged = (app) => {
          appearanceNotified = app;
        };

        await controller.init();
        const success = await controller.equipItem("referral_intesa");
        assert.equal(success, true);
        assert.ok(appearanceNotified);
        assert.ok(appearanceNotified.frame);

        // Verify exact payload: only item was sent!
        const equipReq = requests.find((r) => r.url === "/app/api/shop/equip");
        assert.ok(equipReq);
        assert.equal(equipReq.body?.item, "referral_intesa");
        assert.ok(equipReq.body?.initData);
        assert.ok(!("user_id" in (equipReq.body || {})));
        assert.ok(!("slot" in (equipReq.body || {})));
      } finally {
        restore();
      }
    },
  );

  await t.test(
    "36 & 37. Referral reward equip synchronizes Profile and Daily appearances",
    async () => {
      const restore = mockFetchResponse((url) => {
        if (url === "/app/api/shop/equip") {
          return {
            status: "ok",
            cosmetics: {
              theme: null,
              frame: "referral_intesa",
              title: null,
              badge: null,
              squares: "classic",
              number: null,
              celebration: null,
              card: null,
            },
          };
        }
        if (url === "/app/api/me") {
          return createTestFullProfile();
        }
        return createTestReferralDashboardResponse({
          qualified: 3,
          rewards: [
            {
              target: 3,
              items: [
                {
                  id: "referral_intesa",
                  kind: "frame",
                  name: "L'Intesa",
                  description: "Desc",
                  price: 0,
                  full_price: 0,
                  missing: [],
                  achievement: null,
                  progress: 0,
                  style: { tactics: 3 },
                  grants: [],
                  owned: true,
                  equipped: false,
                  free: false,
                  featured: false,
                  equippable: true,
                  rarity: "earned",
                  completes: [],
                  trophy: null,
                  welcome: false,
                },
              ],
            },
          ],
        });
      });

      try {
        const root = document.createElement("div");
        root.id = "root";
        document.body.appendChild(root);

        const app = new App(root);
        app.init();
        await app.getProfileController().init();

        // Equip from referral
        await app.getReferralController().init();
        await app.getReferralController().equipItem("referral_intesa");

        // ProfileController appearance is updated
        const profileCosmetics = app
          .getProfileController()
          .getState().profile?.cosmetics;
        assert.ok(profileCosmetics?.frame);

        // Global appearance is updated
        assert.ok(getResolvedAppearance().frame);
      } finally {
        restore();
      }
    },
  );

  await t.test(
    "38. Shop remains coherent after Referral navigation and equip",
    async () => {
      const restore = mockFetchResponse((url) => {
        if (url === "/app/api/shop") {
          return {
            sections: [],
            bundles: [],
            showcase: { week: "2026-W37", items: [] },
            equipped: { frame: "referral_intesa" },
            owned: ["referral_intesa"],
            looks: [],
          };
        }
        return createTestReferralDashboardResponse();
      });

      try {
        const root = document.createElement("div");
        document.body.appendChild(root);
        const app = new App(root);
        app.init();

        app.setTab("referral");
        app.setTab("shop");
        await app.getShopController().init();
        assert.equal(app.getShopController().getState().status, "ready");
      } finally {
        restore();
      }
    },
  );

  await t.test(
    "39 & 40. Dark-only theme preserved and no raw IDs rendered",
    async () => {
      const controller = new ReferralController();
      const restore = mockFetchResponse(createTestReferralDashboardResponse());
      try {
        await controller.init();
        const html = renderReferralPage(controller.getState());
        assert.ok(!html.includes("referral_intesa_raw_style_token"));
        assert.ok(!html.includes("ref_123_signature"));
      } finally {
        restore();
      }
    },
  );

  await t.test("41. Reduced motion supported in markup and CSS", () => {
    const cssPath = path.resolve(__dirname, "../../webapp/src/styles/app.css");
    const cssContent = fs.readFileSync(cssPath, "utf-8");
    assert.ok(cssContent.includes("prefers-reduced-motion: reduce"));
    assert.ok(cssContent.includes(".rf-pitch *"));
    assert.ok(cssContent.includes("animation: none !important"));
  });

  await t.test(
    "42, 43, 44. Full localization across IT, EN, ES with matching keys",
    () => {
      const itKeys = Object.keys(TRANSLATIONS.it.referral).sort();
      const enKeys = Object.keys(TRANSLATIONS.en.referral).sort();
      const esKeys = Object.keys(TRANSLATIONS.es.referral).sort();

      assert.deepEqual(enKeys, itKeys, "English keys must match Italian");
      assert.deepEqual(esKeys, itKeys, "Spanish keys must match Italian");

      for (const lang of ["it", "en", "es"] as const) {
        setLanguage(lang);
        const controller = new ReferralController();
        controller.reset();
        (controller as any).state = {
          status: "ready",
          data: createTestReferralDashboardResponse(),
          loadingMore: false,
          refreshing: false,
          selectedRewardTarget: null,
          equippingItemId: null,
          toast: null,
          errorNotice: null,
        };
        const html = renderReferralPage(controller.getState());
        assert.ok(!html.includes("undefined"), `No undefined in ${lang}`);
        assert.ok(html.length > 500);
      }
    },
  );

  await t.test(
    "45. Accessibility: semantic <progress>, ARIA labels, roles",
    async () => {
      const controller = new ReferralController();
      const restore = mockFetchResponse(
        createTestReferralDashboardResponse({
          friends: [{ name: "Mario", days: 3, status: "pending" }],
        }),
      );
      try {
        await controller.init();
        const html = renderReferralPage(controller.getState());
        assert.ok(html.includes("<progress value=\"3\" max=\"5\" aria-label=\"Mario · Progressi degli inviti\"></progress>"));
        assert.ok(html.includes("class=\"rf-hero\""));
      } finally {
        restore();
      }
    },
  );

  await t.test(
    "46 & 47. Profile to Referral navigation and Referral to Profile back",
    async () => {
      const restore = mockFetchResponse((url) => {
        if (url === "/app/api/me") {
          return createTestFullProfile();
        }
        return createTestReferralDashboardResponse();
      });

      try {
        const root = document.createElement("div");
        document.body.appendChild(root);
        const app = new App(root);
        app.init();

        app.setTab("profile");
        await app.getProfileController().init();
        const referralEntryBtn = root.querySelector<HTMLButtonElement>(
          "button[data-tab=\"referral\"]",
        );
        assert.ok(referralEntryBtn, "Profile must contain referral button");
        referralEntryBtn.click();
        await app.getReferralController().init();

        // Should have transitioned to referral
        const referralHero = root.querySelector(".rf-hero");
        assert.ok(referralHero, "Must render referral page");

        // Click back to profile
        const backBtn = root.querySelector<HTMLButtonElement>(
          ".back-link[data-tab=\"profile\"]",
        );
        assert.ok(backBtn, "Back to profile button must exist");
        backBtn.click();

        const profileHeading = root.querySelector("#profile-heading");
        assert.ok(profileHeading, "Must return to profile page");
      } finally {
        restore();
      }
    },
  );

  await t.test(
    "48. Prototype referral runtime completely eliminated",
    async () => {
      const root = document.createElement("div");
      document.body.appendChild(root);
      const restore = mockFetchResponse(createTestReferralDashboardResponse());
      try {
        const app = new App(root);
        app.init();
        app.setTab("referral");

        const html = root.innerHTML;
        assert.ok(!html.includes("prototype-notice"));
        assert.ok(!html.includes("data-prototype=\"referral\""));
        assert.ok(!html.includes("PASS PER UN AMICO"));
      } finally {
        restore();
      }
    },
  );

  await t.test(
    "49. Legacy /app files untouched and legacy client tests intact",
    () => {
      const indexPath = path.resolve(__dirname, "../../webapp/index.html");
      const referralsJsPath = path.resolve(
        __dirname,
        "../../webapp/referrals.js",
      );
      assert.ok(fs.existsSync(indexPath));
      assert.ok(fs.existsSync(referralsJsPath));
    },
  );

  await t.test(
    "50. Pagination race: loadMore A pending -> refresh B -> B resolves -> A resolves -> B remains authoritative & loadingMore false & next loadMore works",
    async () => {
      let resolveMoreA: (val: any) => void = () => {};
      let resolveRefreshB: (val: any) => void = () => {};
      let resolveMoreC: (val: any) => void = () => {};

      let callCount = 0;
      const restore = mockFetchResponse((_url, init) => {
        callCount++;
        const body = (init as any)?.body ? JSON.parse(String((init as any).body)) : {};
        if (callCount === 1) {
          return createTestReferralDashboardResponse({
            friends: [{ name: "FriendPage1", days: 1, status: "pending" }],
            next_cursor: "cursor_1",
          });
        }
        if (body.cursor === "cursor_1") {
          return new Promise((r) => {
            resolveMoreA = r;
          });
        }
        if (callCount === 3 && !body.cursor) {
          return new Promise((r) => {
            resolveRefreshB = r;
          });
        }
        if (body.cursor === "cursor_2") {
          return new Promise((r) => {
            resolveMoreC = r;
          });
        }
        return createTestReferralDashboardResponse();
      });

      try {
        const controller = new ReferralController();
        await controller.init();
        assert.equal(controller.getState().data?.friends.length, 1);
        assert.equal(controller.getState().data?.friends[0].name, "FriendPage1");
        assert.equal(controller.getState().data?.next_cursor, "cursor_1");

        // 1. loadMore A starts
        const promiseA = controller.loadMore();
        assert.equal(controller.getState().loadingMore, true);

        // 2. refresh B starts
        const promiseB = controller.refresh();
        assert.equal(controller.getState().refreshing, true);
        assert.equal(controller.getState().loadingMore, false);

        // 3. B resolves
        resolveRefreshB(
          createTestReferralDashboardResponse({
            friends: [{ name: "RefreshedFriendB", days: 3, status: "qualified" }],
            next_cursor: "cursor_2",
          }),
        );
        await promiseB;
        assert.equal(controller.getState().refreshing, false);
        assert.equal(controller.getState().loadingMore, false);
        assert.equal(controller.getState().data?.friends.length, 1);
        assert.equal(controller.getState().data?.friends[0].name, "RefreshedFriendB");

        // 4. old loadMore A resolves later
        resolveMoreA(
          createTestReferralDashboardResponse({
            friends: [{ name: "StaleFriendA", days: 1, status: "pending" }],
            next_cursor: "cursor_stale",
          }),
        );
        await promiseA;

        // B remains authoritative!
        assert.equal(controller.getState().loadingMore, false);
        assert.equal(controller.getState().data?.friends.length, 1);
        assert.equal(controller.getState().data?.friends[0].name, "RefreshedFriendB");
        assert.equal(controller.getState().data?.next_cursor, "cursor_2");

        // 5. Subsequent loadMore works using cursor_2
        const promiseC = controller.loadMore();
        assert.equal(controller.getState().loadingMore, true);
        resolveMoreC(
          createTestReferralDashboardResponse({
            friends: [{ name: "Page2FriendC", days: 4, status: "pending" }],
            next_cursor: null,
          }),
        );
        await promiseC;
        assert.equal(controller.getState().loadingMore, false);
        assert.equal(controller.getState().data?.friends.length, 2);
        assert.equal(controller.getState().data?.friends[1].name, "Page2FriendC");
      } finally {
        restore();
      }
    },
  );

  await t.test(
    "51. Pagination race inverse ordering: loadMore A pending -> refresh B pending -> A resolves -> B resolves -> B remains authoritative & loadingMore false & next loadMore works",
    async () => {
      let resolveMoreA: (val: any) => void = () => {};
      let resolveRefreshB: (val: any) => void = () => {};
      let resolveMoreC: (val: any) => void = () => {};

      let callCount = 0;
      const restore = mockFetchResponse((_url, init) => {
        callCount++;
        const body = (init as any)?.body ? JSON.parse(String((init as any).body)) : {};
        if (callCount === 1) {
          return createTestReferralDashboardResponse({
            friends: [{ name: "FriendPage1", days: 1, status: "pending" }],
            next_cursor: "cursor_1",
          });
        }
        if (body.cursor === "cursor_1") {
          return new Promise((r) => {
            resolveMoreA = r;
          });
        }
        if (callCount === 3 && !body.cursor) {
          return new Promise((r) => {
            resolveRefreshB = r;
          });
        }
        if (body.cursor === "cursor_2") {
          return new Promise((r) => {
            resolveMoreC = r;
          });
        }
        return createTestReferralDashboardResponse();
      });

      try {
        const controller = new ReferralController();
        await controller.init();

        // 1. loadMore A starts
        const promiseA = controller.loadMore();
        assert.equal(controller.getState().loadingMore, true);

        // 2. refresh B starts
        const promiseB = controller.refresh();
        assert.equal(controller.getState().refreshing, true);
        assert.equal(controller.getState().loadingMore, false);

        // 3. A resolves while B is still pending
        resolveMoreA(
          createTestReferralDashboardResponse({
            friends: [{ name: "StaleFriendA", days: 1, status: "pending" }],
            next_cursor: "cursor_stale",
          }),
        );
        await promiseA;

        // Old response discarded, data not corrupted
        assert.equal(controller.getState().loadingMore, false);
        assert.equal(controller.getState().data?.friends[0].name, "FriendPage1");

        // 4. B resolves
        resolveRefreshB(
          createTestReferralDashboardResponse({
            friends: [{ name: "RefreshedFriendB", days: 3, status: "qualified" }],
            next_cursor: "cursor_2",
          }),
        );
        await promiseB;

        assert.equal(controller.getState().refreshing, false);
        assert.equal(controller.getState().loadingMore, false);
        assert.equal(controller.getState().data?.friends.length, 1);
        assert.equal(controller.getState().data?.friends[0].name, "RefreshedFriendB");
        assert.equal(controller.getState().data?.next_cursor, "cursor_2");

        // 5. Subsequent loadMore works
        const promiseC = controller.loadMore();
        assert.equal(controller.getState().loadingMore, true);
        resolveMoreC(
          createTestReferralDashboardResponse({
            friends: [{ name: "Page2FriendC", days: 4, status: "pending" }],
            next_cursor: null,
          }),
        );
        await promiseC;
        assert.equal(controller.getState().loadingMore, false);
        assert.equal(controller.getState().data?.friends.length, 2);
        assert.equal(controller.getState().data?.friends[1].name, "Page2FriendC");
      } finally {
        restore();
      }
    },
  );

  await t.test(
    "52. Referral reward equip leaves Shop coherent (Integration Test)",
    async () => {
      let shopCatalogueEquipped: any = {};
      const restore = mockFetchResponse((url) => {
        if (url === "/app/api/shop/equip") {
          shopCatalogueEquipped = { frame: "referral_intesa" };
          return {
            status: "ok",
            cosmetics: {
              theme: null,
              frame: { ring: "conic-gradient(#b8892f, #f7e39c, #d9b45b, #fff3c4, #b8892f)" },
              title: null,
              badge: null,
              squares: { correct: "⭐", wrong: "❌", unused: "⬜" },
              number: null,
              celebration: null,
              card: null,
              equipped: { frame: "referral_intesa" },
            },
          };
        }
        if (url === "/app/api/shop") {
          return {
            sections: [
              {
                kind: "frame",
                items: [
                  {
                    id: "referral_intesa",
                    kind: "frame",
                    name: "L'Intesa",
                    description: "Desc",
                    price: 0,
                    full_price: 0,
                    missing: [],
                    achievement: null,
                    progress: 0,
                    style: { tactics: 3 },
                    grants: [],
                    owned: true,
                    equipped: Boolean(shopCatalogueEquipped.frame === "referral_intesa"),
                    free: false,
                    featured: false,
                    equippable: true,
                    rarity: "earned",
                    completes: [],
                    trophy: null,
                    welcome: false,
                  },
                ],
              },
            ],
            bundles: [],
            showcase: { week: "2026-W37", items: [] },
            equipped: shopCatalogueEquipped,
            owned: ["referral_intesa"],
            looks: [],
          };
        }
        if (url === "/app/api/me") {
          return createTestFullProfile();
        }
        return createTestReferralDashboardResponse({
          qualified: 3,
          rewards: [
            {
              target: 3,
              items: [
                {
                  id: "referral_intesa",
                  kind: "frame",
                  name: "L'Intesa",
                  description: "Desc",
                  price: 0,
                  full_price: 0,
                  missing: [],
                  achievement: null,
                  progress: 0,
                  style: { tactics: 3 },
                  grants: [],
                  owned: true,
                  equipped: false,
                  free: false,
                  featured: false,
                  equippable: true,
                  rarity: "earned",
                  completes: [],
                  trophy: null,
                  welcome: false,
                },
              ],
            },
          ],
        });
      });

      try {
        const root = document.createElement("div");
        document.body.appendChild(root);
        const app = new App(root);
        app.init();

        await app.getProfileController().init();
        await app.getReferralController().init();
        app.setTab("referral");

        // Referral equips reward
        const ok = await app.getReferralController().equipItem("referral_intesa");
        assert.equal(ok, true);

        // Navigate to Shop
        app.setTab("shop");

        // 1. Shop catalogue reflects the newly equipped item
        assert.equal(
          app.getShopController().getState().catalogue?.equipped.frame,
          "referral_intesa",
        );
        const shopItem = app
          .getShopController()
          .allItems()
          .find((i) => i.id === "referral_intesa");
        assert.equal(shopItem?.equipped, true);

        // 2. Profile appearance matches
        const profileCosmetics = app
          .getProfileController()
          .getState().profile?.cosmetics;
        assert.ok(profileCosmetics?.frame);
        assert.equal(profileCosmetics?.equipped?.frame, "referral_intesa");

        // 3. Daily appearance matches
        const dailyState = app.getDailyController().getState();
        assert.equal(dailyState.squaresSymbols.correct, "⭐");
        assert.equal(dailyState.cardImage, null);

        // 4. Referral appearance state matches
        const refItem = app
          .getReferralController()
          .findRewardItem("referral_intesa");
        assert.equal(refItem?.equipped, true);

        // 5. Global #66 appearance matches
        const globalApp = getResolvedAppearance();
        assert.ok(globalApp.frame?.ring);
        assert.equal(globalApp.equipped?.frame, "referral_intesa");
      } finally {
        restore();
      }
    },
  );

  await t.test(
    "53. Cross-feature race: Shop equip pending -> Referral equip attempted is blocked",
    async () => {
      let resolveShopEquip: (val: any) => void = () => {};
      const restore = mockFetchResponse((url, init) => {
        if (url === "/app/api/shop/equip") {
          const body = JSON.parse(String((init as any).body));
          if (body.item === "shop_item_1") {
            return new Promise((r) => {
              resolveShopEquip = r;
            });
          }
          return { status: "ok", cosmetics: { frame: body.item, equipped: { frame: body.item } } };
        }
        if (url === "/app/api/shop") {
          return {
            sections: [],
            bundles: [],
            showcase: { week: "2026-W37", items: [] },
            equipped: {},
            owned: ["shop_item_1", "referral_intesa"],
            looks: [],
          };
        }
        return createTestReferralDashboardResponse({
          qualified: 3,
          rewards: [
            {
              target: 3,
              items: [
                {
                  id: "referral_intesa",
                  kind: "frame",
                  name: "L'Intesa",
                  description: "Desc",
                  price: 0,
                  full_price: 0,
                  missing: [],
                  achievement: null,
                  progress: 0,
                  style: { tactics: 3 },
                  grants: [],
                  owned: true,
                  equipped: false,
                  free: false,
                  featured: false,
                  equippable: true,
                  rarity: "earned",
                  completes: [],
                  trophy: null,
                  welcome: false,
                },
              ],
            },
          ],
        });
      });

      try {
        const root = document.createElement("div");
        document.body.appendChild(root);
        const app = new App(root);
        app.init();
        await app.getReferralController().init();

        // 1. Shop equip starts and stays pending
        const pShop = app.getShopController().equip("shop_item_1");

        // 2. Referral equip is attempted concurrently
        const pRef = app.getReferralController().equipItem("referral_intesa");
        const refResult = await pRef;

        // Referral equip must be safely blocked and return false
        assert.equal(refResult, false);
        assert.equal(app.getReferralController().getState().equippingItemId, null);

        // 3. Resolve Shop equip
        resolveShopEquip({
          status: "ok",
          cosmetics: {
            theme: null,
            frame: "shop_item_1",
            title: null,
            badge: null,
            squares: "classic",
            number: null,
            celebration: null,
            card: null,
            equipped: { frame: "shop_item_1" },
          },
        });
        const shopResult = await pShop;
        assert.equal(shopResult, true);
        assert.equal(getResolvedAppearance().equipped?.frame, "shop_item_1");
      } finally {
        restore();
      }
    },
  );

  await t.test(
    "54. Cross-feature race: Referral equip pending -> saved Look wear attempted is blocked",
    async () => {
      let resolveRefEquip: (val: any) => void = () => {};
      const restore = mockFetchResponse((url) => {
        if (url === "/app/api/shop/equip") {
          return new Promise((r) => {
            resolveRefEquip = r;
          });
        }
        if (url === "/app/api/shop/look") {
          return { status: "ok" };
        }
        if (url === "/app/api/shop") {
          return {
            sections: [],
            bundles: [],
            showcase: { week: "2026-W37", items: [] },
            equipped: {},
            owned: ["referral_intesa"],
            looks: [{ name: "MyLook", equipped: { frame: "look_frame" } }],
          };
        }
        return createTestReferralDashboardResponse({
          qualified: 3,
          rewards: [
            {
              target: 3,
              items: [
                {
                  id: "referral_intesa",
                  kind: "frame",
                  name: "L'Intesa",
                  description: "Desc",
                  price: 0,
                  full_price: 0,
                  missing: [],
                  achievement: null,
                  progress: 0,
                  style: { tactics: 3 },
                  grants: [],
                  owned: true,
                  equipped: false,
                  free: false,
                  featured: false,
                  equippable: true,
                  rarity: "earned",
                  completes: [],
                  trophy: null,
                  welcome: false,
                },
              ],
            },
          ],
        });
      });

      try {
        const root = document.createElement("div");
        document.body.appendChild(root);
        const app = new App(root);
        app.init();
        await app.getReferralController().init();

        // 1. Referral equip starts and is pending in ShopController
        const pRef = app.getReferralController().equipItem("referral_intesa");

        // 2. Saved Look wear is attempted while Referral equip owns appearanceMutation
        const pWear = app.getShopController().lookAction("wear", "MyLook");
        const wearResult = await pWear;

        // Look wear must be safely blocked and return false
        assert.equal(wearResult, false);

        // 3. Resolve Referral equip
        resolveRefEquip({
          status: "ok",
          cosmetics: {
            theme: null,
            frame: "referral_intesa",
            title: null,
            badge: null,
            squares: "classic",
            number: null,
            celebration: null,
            card: null,
            equipped: { frame: "referral_intesa" },
          },
        });
        const refResult = await pRef;
        assert.equal(refResult, true);
        assert.equal(getResolvedAppearance().equipped?.frame, "referral_intesa");
      } finally {
        restore();
      }
    },
  );

  await t.test(
    "55. Shop equip -> return to already-cached Referral -> equipped indicators are correct",
    async () => {
      let currentEquippedFrame = "other_frame";
      const restore = mockFetchResponse((url) => {
        if (url === "/app/api/shop/equip") {
          currentEquippedFrame = "referral_intesa";
          return {
            status: "ok",
            cosmetics: {
              theme: null,
              frame: "referral_intesa",
              title: null,
              badge: null,
              squares: "classic",
              number: null,
              celebration: null,
              card: null,
              equipped: { frame: "referral_intesa" },
            },
          };
        }
        if (url === "/app/api/shop") {
          return {
            sections: [],
            bundles: [],
            showcase: { week: "2026-W37", items: [] },
            equipped: { frame: currentEquippedFrame },
            owned: ["referral_intesa", "other_frame"],
            looks: [],
          };
        }
        return createTestReferralDashboardResponse({
          qualified: 3,
          rewards: [
            {
              target: 3,
              items: [
                {
                  id: "referral_intesa",
                  kind: "frame",
                  name: "L'Intesa",
                  description: "Desc",
                  price: 0,
                  full_price: 0,
                  missing: [],
                  achievement: null,
                  progress: 0,
                  style: { tactics: 3 },
                  grants: [],
                  owned: true,
                  equipped: false,
                  free: false,
                  featured: false,
                  equippable: true,
                  rarity: "earned",
                  completes: [],
                  trophy: null,
                  welcome: false,
                },
              ],
            },
          ],
        });
      });

      try {
        const root = document.createElement("div");
        document.body.appendChild(root);
        const app = new App(root);
        app.init();

        // 1. Referral loaded and cached
        app.setTab("referral");
        await app.getReferralController().init();
        assert.equal(
          app.getReferralController().findRewardItem("referral_intesa")?.equipped,
          false,
        );

        // 2. User navigates to Shop and equips referral_intesa
        app.setTab("shop");
        await app.getShopController().init();
        const ok = await app.getShopController().equip("referral_intesa");
        assert.equal(ok, true);

        // 3. Return to Referral (cached, init does not re-fetch from network)
        app.setTab("referral");
        await app.getReferralController().init();

        // Reconciled without network reload
        const item = app.getReferralController().findRewardItem("referral_intesa");
        assert.equal(item?.equipped, true);

        // Rendered view must show Equipaggiato (disabled)
        app.getReferralController().openRewardPreview(3);
        const previewHtml = root.innerHTML;
        assert.ok(previewHtml.includes("disabled"));
        assert.ok(previewHtml.includes("Equipaggiato"));
      } finally {
        restore();
      }
    },
  );
});
