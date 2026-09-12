import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { setupGlobalDom, mockFetchResponse, createTestDailyChallenge } from "./helpers";
import { applyResolvedAppearance, clearResolvedAppearance, getResolvedAppearance, parseResolvedAppearance, identityAppearance, resultAppearance, SKIN_TOKENS } from "../../webapp/src/appearance";
import { renderAppearanceIdentity, resultCardAttributes } from "../../webapp/src/appearance/surfaces";
import { appearanceFixtures as fixtures } from "../../webapp/src/prototypes/appearance-fixtures";
import { applyTelegramTheme } from "../../webapp/src/telegram/theme";
import { createMockTelegramWebApp } from "../../webapp/src/telegram/mock";
import { DailyController } from "../../webapp/src/features/daily/controller";
import { ApiClient } from "../../webapp/src/api/client";
import { celebrate } from "../../webapp/src/features/daily/celebrate";
import { renderDailyPage } from "../../webapp/src/pages/DailyPage";
import { dailyFixture } from "../../webapp/src/prototypes/daily-fixtures";

const css = readFileSync("webapp/src/styles/vars.css", "utf8").replace(/@import[^;]+;|@source[^;]+;|@theme inline \{[^}]+\}/g, "");
function dom() {
  const env = setupGlobalDom();
  const style = document.createElement("style"); style.textContent = css; document.head.appendChild(style);
  clearResolvedAppearance();
  return env;
}
for (const host of ["light", "dark", "system-light"] as const) test(`${host} renders fixed dark surfaces`, () => {
  const { cleanup } = dom();
  try {
    const tg = createMockTelegramWebApp(); tg.colorScheme = host === "dark" ? "dark" : "light";
    tg.themeParams = { bg_color: "#ffffff", text_color: "#000000" };
    window.matchMedia = (() => ({ matches: false })) as unknown as typeof window.matchMedia;
    applyTelegramTheme(host === "system-light" ? null : tg);
    const style = window.getComputedStyle(document.documentElement);
    assert.equal(document.documentElement.dataset.theme, "dark");
    assert.equal(style.getPropertyValue("--bg"), "#101820");
    assert.equal(style.getPropertyValue("--text"), "#f5f8fc");
    assert.equal(style.colorScheme, "dark");
  } finally { cleanup(); }
});
test("safe areas and viewport survive, malformed insets are ignored", () => {
  const { cleanup } = dom();
  try {
    const tg = createMockTelegramWebApp();
    tg.safeAreaInset = { top: 24, bottom: 12, left: -5, right: Infinity };
    tg.contentSafeAreaInset = { top: 32, bottom: 8, left: 4, right: 0 };
    tg.viewportHeight = 700; tg.viewportStableHeight = 740; applyTelegramTheme(tg);
    const s = document.documentElement.style;
    for (const [edge, value] of Object.entries({ top: 56, bottom: 20, left: 4, right: 0 })) assert.equal(s.getPropertyValue(`--tg-safe-${edge}`), `${value}px`);
    assert.equal(s.getPropertyValue("--tg-viewport-height"), "700px");
    assert.equal(s.getPropertyValue("--tg-viewport-stable-height"), "740px");
  } finally { cleanup(); }
});
test("default payload and missing appearance use safe product fallbacks", () => {
  const { cleanup } = dom();
  try {
    assert.equal(applyResolvedAppearance(fixtures.default).card?.finish, "plain");
    assert.deepEqual(resultAppearance(undefined).squares, { correct: "🟩", wrong: "🟥", unused: "⬜" });
    applyResolvedAppearance(undefined);
    for (const token of SKIN_TOKENS) assert.equal(document.documentElement.style.getPropertyValue(token), "");
  } finally { cleanup(); }
});
test("cosmetic accent is decorative; forbidden/semantic/focus/disabled tokens stay product-owned", () => {
  const { cleanup } = dom();
  try {
    const names = ["--bg", "--bg-secondary", "--card", "--text", "--muted", "--accent", "--accent-text", "--danger", "--danger-bg", "--warn", "--warn-bg", "--success", "--success-bg", "--focus", "--disabled-opacity"];
    const before = names.map(n => window.getComputedStyle(document.documentElement).getPropertyValue(n));
    applyResolvedAppearance({ theme: { ...fixtures.theme.theme, accent: "#ff3ea5", bg: "#ffffff", text: "#111111", error: "#abcdef", success: "#abcdef", focus: "#abcdef", "--focus": "red", position: "fixed" } });
    assert.equal(document.documentElement.style.getPropertyValue("--skin-accent"), "#ff3ea5");
    assert.deepEqual(names.map(n => window.getComputedStyle(document.documentElement).getPropertyValue(n)), before);
    assert.equal(document.documentElement.style.getPropertyValue("position"), "");
    assert.match(document.documentElement.style.getPropertyValue("--skin-profile-surface"), /12%, #1a2734/);
  } finally { cleanup(); }
});
test("frame, title, badge and number map only to escaped identity surfaces", () => {
  const { container, cleanup } = dom();
  try {
    const identity = identityAppearance(fixtures.identity);
    assert.match(identity.frame.ring!, /repeating-linear-gradient/);
    assert.equal(identity.title.label, "Talent scout"); assert.equal(identity.badge, "⚽");
    container.innerHTML = renderAppearanceIdentity("<name>", { ...fixtures.identity, title: { label: "<script>bad</script>", color: "#ffffff" }, number: "01" });
    assert.equal(container.querySelector("script"), null);
    assert.equal(container.querySelector(".cosmetic-number")?.textContent, "Nº 01");
    assert.ok(container.querySelector(".ring"));
    assert.equal(identityAppearance(fixtures.number).number, "7");
  } finally { cleanup(); }
});
test("custom squares reach Daily and share/result projection", () => {
  const { container, cleanup } = dom();
  try {
    const a = resultAppearance(fixtures.squares); assert.equal(a.squares.correct, "⚽");
    const state = dailyFixture("completed"); state.squaresSymbols = a.squares;
    container.innerHTML = renderDailyPage(state);
    assert.match(container.querySelector(".attempts")!.textContent!, /⚽/);
  } finally { cleanup(); }
});
test("celebration is success-only and disabled by reduced motion; card finishes remain local", () => {
  const { container, cleanup } = dom();
  try {
    window.matchMedia = (() => ({ matches: false })) as unknown as typeof window.matchMedia;
    assert.equal(resultAppearance(fixtures.celebration).celebration, "confetti");
    window.matchMedia = (() => ({ matches: true })) as unknown as typeof window.matchMedia;
    assert.equal(resultAppearance(fixtures.celebration).celebration, "");
    celebrate("confetti"); assert.equal(document.querySelector("canvas"), null);
    container.innerHTML = `<div ${resultCardAttributes(fixtures.card)}></div>`;
    assert.equal(container.firstElementChild?.getAttribute("data-card-finish"), "foil");
    assert.equal(resultAppearance(fixtures.card).card.glow, "#ff9ce3");
    assert.equal(resultAppearance(undefined).celebration, "");
  } finally { cleanup(); }
});
test("partial, malformed and unknown styles cannot inject CSS or crash", () => {
  const { cleanup } = dom();
  try {
    for (const payload of [null, undefined, 9, "bad", [], { theme: [], squares: 7, frame: true, title: null }]) assert.doesNotThrow(() => applyResolvedAppearance(payload));
    assert.equal(applyResolvedAppearance({ title: { label: "Scout" } }).title?.label, "Scout");
    applyResolvedAppearance({ theme: { accent: "red; --bg: white", pattern: "url(https://bad.example)", future: "red" }, frame: { ring: "url(https://bad.example)" }, card: { glow: "var(--danger)", finish: "<img>" } });
    assert.equal(document.documentElement.style.getPropertyValue("--skin-accent"), "");
    assert.equal(document.documentElement.style.getPropertyValue("--skin-pattern"), "");
    assert.equal(getResolvedAppearance().frame?.ring, "");
    assert.equal(getResolvedAppearance().card?.glow, "");
    assert.equal(parseResolvedAppearance({ unknown: true }).badge, "");
  } finally { cleanup(); }
});
test("every representative outfit is idempotent and replacing users removes stale fields", () => {
  const { cleanup } = dom();
  try {
    for (const fixture of Object.values(fixtures)) {
      const first = applyResolvedAppearance(fixture); const css = document.documentElement.style.cssText;
      assert.deepEqual(applyResolvedAppearance(first), first); assert.equal(document.documentElement.style.cssText, css);
    }
    applyResolvedAppearance(fixtures.collection); applyResolvedAppearance({ badge: "⚽" });
    assert.equal(getResolvedAppearance().frame?.ring, "");
    assert.equal(document.documentElement.style.getPropertyValue("--skin-pattern"), "");
    clearResolvedAppearance(); assert.equal(getResolvedAppearance().badge, "");
  } finally { cleanup(); }
});
test("Daily load consumes shared appearance and reset invalidates an in-flight previous user", async () => {
  const { cleanup } = dom();
  const restore = mockFetchResponse({ user: { name: "A" }, today: createTestDailyChallenge(), cosmetics: fixtures.collection });
  try {
    const controller = new DailyController(); await controller.init();
    assert.equal(controller.getState().squaresSymbols.correct, "❄️");
    const pending = controller.loadDailyData();
    assert.equal(getResolvedAppearance().badge, "");
    controller.reset(); await pending;
    assert.equal(getResolvedAppearance().badge, ""); assert.equal(controller.getState().user, null);
  } finally { restore(); cleanup(); }
});
test("API auth change clears previous user skin and rejects old-session responses", async () => {
  const { cleanup } = dom(); const previous = globalThis.fetch;
  let token = "A";
  try {
    const client = new ApiClient({ getAuthToken: () => token });
    globalThis.fetch = (async () => new Response("{}")) as typeof fetch;
    await client.getMe(); applyResolvedAppearance(fixtures.collection);
    token = "B"; await client.getMe(); assert.equal(getResolvedAppearance().badge, "");
    globalThis.fetch = (async () => { token = "C"; return new Response("{}"); }) as typeof fetch;
    await assert.rejects(client.getMe(), /Session changed/);
  } finally { globalThis.fetch = previous; cleanup(); }
});


test("failed reload clears skin and prior result symbols", async () => {
  const { cleanup } = dom(); const original = globalThis.fetch;
  const restore = mockFetchResponse({ user: { name: "A" }, today: createTestDailyChallenge(), cosmetics: fixtures.collection });
  try {
    const controller = new DailyController(); await controller.init(); restore();
    globalThis.fetch = async () => { throw new Error("offline"); };
    await controller.loadDailyData({ lightweight: true });
    assert.equal(controller.getState().status, "error"); assert.equal(getResolvedAppearance().badge, "");
    assert.deepEqual(controller.getState().squaresSymbols, resultAppearance(undefined).squares);
  } finally { globalThis.fetch = original; cleanup(); }
});
test("every catalog gradient is mapped locally without URL output", () => {
  const catalog = JSON.parse(readFileSync("data/shop.json", "utf8"));
  for (const item of catalog.items) {
    if (item.kind === "theme" && item.style.pattern) {
      const result = parseResolvedAppearance({ theme: item.style });
      assert.ok(result.theme?.pattern, item.id); assert.doesNotMatch(result.theme!.pattern!, /url\(/i);
    }
    if (item.kind === "frame" && item.style.ring) assert.ok(identityAppearance({ frame: item.style }).frame.ring, item.id);
  }
});
