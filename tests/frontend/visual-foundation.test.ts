import { test } from "node:test";
import assert from "node:assert/strict";
import { setupGlobalDom } from "./helpers";
import { renderDailyPage } from "../../webapp/src/pages/DailyPage";
import { dailyFixture } from "../../webapp/src/prototypes/daily-fixtures";
import { startReview } from "../../webapp/src/prototypes/review";
import {
  applyTelegramTheme,
  connectTheme,
} from "../../webapp/src/telegram/theme";
import { createMockTelegramWebApp } from "../../webapp/src/telegram/mock";
import { renderCareerPath } from "../../webapp/src/components/CareerPath";

test("submission errors remain visible and a submitting Daily disables guess and hint", () => {
  const { container, cleanup } = setupGlobalDom();
  try {
    const state = dailyFixture("ready");
    state.errorMessage = "Connection failed <retry>";
    container.innerHTML = renderDailyPage(state);
    assert.equal(
      container.querySelector('[role="alert"]')?.textContent,
      "Connection failed <retry>",
    );
    assert.equal(container.querySelector("retry"), null);
    container.innerHTML = renderDailyPage(dailyFixture("submitting"));
    for (const id of ["answer", "submit", "hint"])
      assert.equal(
        container.querySelector<HTMLInputElement>(`#${id}`)?.disabled,
        true,
      );
  } finally {
    cleanup();
  }
});
test("career preserves long names, loan status, zero appearances and unknown dates", () => {
  const { container, cleanup } = setupGlobalDom();
  try {
    container.innerHTML = renderCareerPath({
      stops: [
        {
          team: "A very long football club <name>",
          country: "Country",
          loan: true,
          apps: 0,
          goals: 0,
        },
      ],
    });
    assert.equal(
      container.querySelector(".team")?.textContent,
      "A very long football club <name>",
    );
    assert.equal(container.querySelector(".apps")?.textContent, "0 (0)");
    assert.ok(container.querySelector(".loan-label"));
    assert.equal(container.querySelector("name"), null);
  } finally {
    cleanup();
  }
});
test("review navigation and fixture interactions never call an API", () => {
  const { container, cleanup } = setupGlobalDom();
  const previous = globalThis.fetch;
  let requests = 0;
  globalThis.fetch = (() => {
    requests++;
    throw Error("Unexpected request");
  }) as typeof fetch;
  try {
    startReview(container);
    container.querySelector<HTMLButtonElement>("#hint")!.click();
    assert.ok(container.querySelector(".hint-taken-item"));
    const go = (tab: string) =>
      container
        .querySelector<HTMLButtonElement>(`[data-tab="${tab}"]`)!
        .click();
    assert.deepEqual(
      Array.from(
        container.querySelectorAll(".app-nav [data-tab]"),
        (b) => (b as HTMLElement).dataset.tab,
      ),
      ["play", "arena", "leaderboard", "shop", "profile"],
    );
    go("arena");
    for (const tab of ["challenge", "duels", "archive", "events"]) {
      go(tab);
      assert.ok(container.querySelector(`[data-prototype="${tab}"]`));
      assert.equal(
        container
          .querySelector('.app-nav [aria-current="page"]')
          ?.getAttribute("data-tab"),
        "arena",
      );
      container
        .querySelectorAll<HTMLButtonElement>(
          ".prototype button:not([data-tab])",
        )
        .forEach((button) => assert.equal(button.disabled, true));
      go("arena");
    }
    for (const tab of ["leaderboard", "shop", "profile"]) {
      go(tab);
      assert.ok(container.querySelector(`[data-prototype="${tab}"]`));
    }
    go("referral");
    assert.equal(
      container
        .querySelector('.app-nav [aria-current="page"]')
        ?.getAttribute("data-tab"),
      "profile",
    );
    go("profile");
    for (const tab of ["reports", "refunds", "privacy"]) {
      go(tab);
      assert.ok(container.querySelector(`[data-support="${tab}"]`));
      assert.equal(container.querySelector("form"), null);
    }
    assert.equal(requests, 0);
  } finally {
    globalThis.fetch = previous;
    cleanup();
  }
});
test("Telegram theme changes preserve dark identity and combine safe areas", () => {
  const { cleanup } = setupGlobalDom();
  try {
    const tg = createMockTelegramWebApp();
    tg.platform = "android";
    tg.colorScheme = "light";
    tg.themeParams = { bg_color: "#ffffff", text_color: "#222222" };
    tg.safeAreaInset = { top: 24, bottom: 16, left: 0, right: 0 };
    tg.contentSafeAreaInset = { top: 32, bottom: 0, left: 0, right: 0 };
    const listeners = new Map<string, () => void>();
    tg.onEvent = (event, callback) => {
      listeners.set(event, callback);
    };
    tg.offEvent = (event) => {
      listeners.delete(event);
    };
    const dispose = connectTheme(tg);
    assert.equal(document.documentElement.dataset.theme, "dark");
    assert.equal(
      document.documentElement.style.getPropertyValue("--tg-safe-top"),
      "56px",
    );
    assert.equal(
      document.documentElement.style.getPropertyValue("--tg-theme-bg-color"),
      "",
    );
    tg.colorScheme = "dark";
    tg.themeParams = { bg_color: "#222222", text_color: "#ffffff" };
    listeners.get("themeChanged")!();
    assert.equal(document.documentElement.dataset.theme, "dark");
    assert.equal(
      document.documentElement.style.getPropertyValue("--tg-theme-text-color"),
      "",
    );
    dispose();
    assert.equal(listeners.size, 0);
    tg.themeParams = {};
    applyTelegramTheme(tg);
    assert.equal(
      document.documentElement.style.getPropertyValue("--tg-theme-text-color"),
      "",
    );
  } finally {
    cleanup();
  }
});
