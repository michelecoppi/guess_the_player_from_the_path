import { test } from "node:test";
import assert from "node:assert/strict";
import { App } from "../../webapp/src/app/App";
import type { EventCard } from "../../webapp/src/features/events/types";
import { createTestDuelData, createTestDuelSession, setupGlobalDom, setupTestTelegram } from "./helpers";

test("closing confirmation follows an active duel and clears on completion or navigation", () => {
  const { container, cleanup } = setupGlobalDom();
  const { mock, restore } = setupTestTelegram();
  let enables = 0;
  let disables = 0;
  mock.enableClosingConfirmation = () => { enables++; mock.isClosingConfirmationEnabled = true; };
  mock.disableClosingConfirmation = () => { disables++; mock.isClosingConfirmationEnabled = false; };
  try {
    const app = new App(container);
    const arena = app.getArenaController();
    app.setTab("duels");
    assert.equal(enables, 0);

    const data = createTestDuelData();
    arena["updateState"]({ activeDuelCode: data.code, data });
    assert.equal(mock.isClosingConfirmationEnabled, true);
    arena["updateState"]({ data: createTestDuelData({ session: createTestDuelSession({ finished: true }), complete: true }) });
    assert.equal(mock.isClosingConfirmationEnabled, false);

    arena["updateState"]({ data });
    app.setTab("play");
    assert.equal(mock.isClosingConfirmationEnabled, false);
    assert.equal(enables, 2);
    assert.equal(disables, 2);
  } finally {
    restore();
    cleanup();
  }
});

test("closing confirmation follows playable event detail and clears on exit", () => {
  const { container, cleanup } = setupGlobalDom();
  const { mock, restore } = setupTestTelegram();
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (() => new Promise(() => {})) as typeof fetch;
  try {
    const app = new App(container);
    const events = app.getEventsController();
    app.setTab("events");
    assert.equal(mock.isClosingConfirmationEnabled, false);
    const card = {
      code: "event-1", available: true, progress: { attempts: 0, finished: false, solved: false, points: 0 },
    } as EventCard;
    events["setState"]({ events: [card], status: "ready" });
    events.select(card.code);
    assert.equal(mock.isClosingConfirmationEnabled, true);
    events["setState"]({ events: [{ ...card, progress: { ...card.progress, finished: true } }] });
    assert.equal(mock.isClosingConfirmationEnabled, false);
    events["setState"]({ events: [card] });
    events.back();
    assert.equal(mock.isClosingConfirmationEnabled, false);
  } finally {
    globalThis.fetch = originalFetch;
    restore();
    cleanup();
  }
});

test("closing confirmation gracefully skips clients without Bot API 6.2", () => {
  const { container, cleanup } = setupGlobalDom();
  const { mock, restore } = setupTestTelegram({ isVersionAtLeast: () => false });
  try {
    const app = new App(container);
    app.setTab("duels");
    const data = createTestDuelData();
    app.getArenaController()["updateState"]({ activeDuelCode: data.code, data });
    assert.equal(mock.isClosingConfirmationEnabled, false);
  } finally {
    restore();
    cleanup();
  }
});
