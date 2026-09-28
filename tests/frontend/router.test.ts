import { test } from "node:test";
import assert from "node:assert/strict";
import { Router } from "../../webapp/src/app/Router";
import { renderActivePage } from "../../webapp/src/app/PageRenderer";

test("router records actual destinations without duplicate visits", () => {
  const router = new Router();
  assert.equal(router.activeTab, "play");
  assert.equal(router.navigate("play"), false);
  assert.equal(router.navigate("events"), true);
  assert.equal(router.navigate("arena"), true);
  assert.deepEqual(router.visitedTabs, ["play", "events"]);
  assert.equal(router.activeTab, "arena");
  assert.equal(Router.isArenaTab("challenge"), true);
  assert.equal(Router.isArenaTab("profile"), false);
});

test("page renderer invokes only the current destination", () => {
  let inactiveCalls = 0;
  const html = renderActivePage("shop", {
    play: () => { inactiveCalls++; return "daily"; },
    arena: () => { inactiveCalls++; return "arena"; },
    duels: () => { inactiveCalls++; return "duels"; },
    challenge: () => { inactiveCalls++; return "challenge"; },
    leaderboard: () => { inactiveCalls++; return "leaderboard"; },
    archive: () => { inactiveCalls++; return "archive"; },
    profile: () => { inactiveCalls++; return "profile"; },
    shop: () => "shop",
    referral: () => { inactiveCalls++; return "referral"; },
    events: () => { inactiveCalls++; return "events"; },
    fallback: () => { inactiveCalls++; return "fallback"; },
  });
  assert.equal(html, "shop");
  assert.equal(inactiveCalls, 0);
});
