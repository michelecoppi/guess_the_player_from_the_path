import { test } from "node:test";
import assert from "node:assert/strict";
import { App } from "../../webapp/src/app/App";
import { setupGlobalDom, setupTestTelegram } from "./helpers";

test("App mounts into DOM and renders shared components in Daily demonstration tab", () => {
  const { restore: restoreTg } = setupTestTelegram();
  const { container, cleanup: cleanupDom } = setupGlobalDom();

  try {
    const app = new App(container);
    app.init();

    // Verify header rendered
    assert.ok(container.querySelector(".app-header"));

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
    assert.ok(hintItem, "Hint panel taken items missing");
    assert.equal(hintItem.textContent, "Ha vinto un Mondiale nel 2006");

    // Verify Navigation switching tabs
    const arenaTabBtn = container.querySelector<HTMLButtonElement>('nav.app-nav button[data-tab="arena"]');
    assert.ok(arenaTabBtn);
    arenaTabBtn.click();

    // Switched to Arena: career path of daily should not be in arena
    assert.ok(container.querySelector(".card-title")?.textContent?.includes("Arena"));

    // Switch back to Play
    const playTabBtn = container.querySelector<HTMLButtonElement>('nav.app-nav button[data-tab="play"]');
    assert.ok(playTabBtn);
    playTabBtn.click();
    assert.ok(container.querySelector(".path"));
  } finally {
    cleanupDom();
    restoreTg();
  }
});
