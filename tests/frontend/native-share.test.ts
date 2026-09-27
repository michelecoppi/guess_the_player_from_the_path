import { test } from "node:test";
import assert from "node:assert/strict";
import { DailyController } from "../../webapp/src/features/daily/controller";
import type { ResolvedAppearance } from "../../webapp/src/appearance";
import { setupTestTelegram, createTestDailyChallenge } from "./helpers";

const DAY = "2026-09-27";
const SHARE_URL = "https://t.me/share/url?text=foo";
const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

interface Scenario {
  prepareStatus?: number;
  expiresAt?: number | null;
}

/** A fetch that finishes the Daily on the first guess and answers /share/*. */
function mockServer({ prepareStatus = 200, expiresAt = Math.floor(Date.now() / 1000) + 3600 }: Scenario = {}) {
  const calls: { url: string; body: any }[] = [];
  let prepared = 0;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input: string, init?: RequestInit) => {
    const url = String(input);
    const body = init?.body ? JSON.parse(String(init.body)) : null;
    calls.push({ url, body });
    const json = (data: unknown, status = 200) =>
      new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
    if (url.endsWith("/me")) {
      return json({ user: { name: "Marco" }, today: createTestDailyChallenge({ day: DAY, solved: calls.length > 1, attempts_used: 2 }) });
    }
    if (url.endsWith("/guess")) {
      return json({ status: "correct", attempts_used: 2, attempts_left: 3, share: { text: "#42 2/5", url: SHARE_URL } });
    }
    if (url.endsWith("/share/prepare")) {
      if (prepareStatus !== 200) return json({ detail: "share_unavailable" }, prepareStatus);
      prepared++;
      return json({ id: `prep-${prepared}`, expires_at: expiresAt });
    }
    return json({ status: "ok" });
  }) as typeof fetch;
  return {
    calls,
    count: (suffix: string) => calls.filter((c) => c.url.endsWith(suffix)).length,
    restore: () => { globalThis.fetch = originalFetch; },
  };
}

function telegram(overrides: Record<string, unknown> = {}) {
  const shared: string[] = [];
  const opened: string[] = [];
  let sentCallback: ((sent: boolean) => void) | undefined;
  const { restore } = setupTestTelegram({
    isVersionAtLeast: (v: string) => Number(v) <= 8.0,
    shareMessage: (id: string, cb?: (sent: boolean) => void) => { shared.push(id); sentCallback = cb; },
    openTelegramLink: (url: string) => { opened.push(url); },
    ...overrides,
  } as any);
  return { shared, opened, confirm: (sent: boolean) => sentCallback?.(sent), restore };
}

async function finishedGame() {
  const controller = new DailyController();
  await controller.init();
  await controller.submitGuess("Buffon");
  await tick();
  return controller;
}

test("the finished result is prepared in advance and shared natively on tap (#185)", async () => {
  const server = mockServer();
  const tg = telegram();
  try {
    const controller = await finishedGame();
    const [prepare] = server.calls.filter((c) => c.url.endsWith("/share/prepare"));
    assert.equal(prepare.body.day, DAY);

    controller.shareResult();
    assert.deepEqual(tg.shared, ["prep-1"], "shareMessage runs synchronously in the tap");
    assert.deepEqual(tg.opened, []);

    tg.confirm(false);
    await tick();
    assert.equal(server.count("/share/sent"), 0, "a dismissed share is not counted");
    tg.confirm(true);
    await tick();
    assert.equal(server.count("/share/sent"), 1);
  } finally {
    tg.restore();
    server.restore();
  }
});

test("without a prepared message the classic share link is used (#185)", async () => {
  const server = mockServer({ prepareStatus: 503 });
  const tg = telegram();
  try {
    const controller = await finishedGame();
    controller.shareResult();
    assert.deepEqual(tg.shared, []);
    assert.deepEqual(tg.opened, [SHARE_URL]);
  } finally {
    tg.restore();
    server.restore();
  }
});

test("clients before Bot API 8.0 never prepare and keep the classic share (#185)", async () => {
  const server = mockServer();
  const tg = telegram({ isVersionAtLeast: (v: string) => Number(v) <= 7.10 });
  try {
    const controller = await finishedGame();
    assert.equal(server.count("/share/prepare"), 0);
    controller.shareResult();
    assert.deepEqual(tg.opened, [SHARE_URL]);
  } finally {
    tg.restore();
    server.restore();
  }
});

test("an expired prepared message falls back and is prepared again (#185)", async () => {
  const server = mockServer({ expiresAt: Math.floor(Date.now() / 1000) + 5 });
  const tg = telegram();
  try {
    const controller = await finishedGame();
    controller.shareResult();
    assert.deepEqual(tg.shared, [], "a message about to expire is not used");
    assert.deepEqual(tg.opened, [SHARE_URL]);
    await tick();
    assert.equal(server.count("/share/prepare"), 2);
  } finally {
    tg.restore();
    server.restore();
  }
});

test("a new look invalidates the prepared card and prepares it again (#185)", async () => {
  const server = mockServer();
  const tg = telegram();
  try {
    const controller = await finishedGame();
    controller.syncAppearance({} as ResolvedAppearance);
    controller.shareResult();
    assert.deepEqual(tg.shared, [], "the old card is never shared");
    assert.deepEqual(tg.opened, [SHARE_URL]);
    await tick();
    controller.shareResult();
    assert.deepEqual(tg.shared, ["prep-2"]);
  } finally {
    tg.restore();
    server.restore();
  }
});
