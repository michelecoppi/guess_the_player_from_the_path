import { test } from "node:test";
import assert from "node:assert/strict";
import {
  createTestDom,
  setupGlobalDom,
  createTestTelegramUser,
  createTestInitData,
  setupTestTelegram,
  mockFetchResponse,
  mockFetchError,
  captureFetchRequests,
  createTestCareerPath,
  createTestDailyChallenge,
  createTestLeaderboard,
} from "./helpers";

test("createTestDom creates isolated DOM environment and cleanly destroys it", () => {
  const dom = createTestDom('<p id="my-para">Hello DOM</p>');
  const p = dom.document.getElementById("my-para");
  assert.ok(p);
  assert.equal(p.textContent, "Hello DOM");

  dom.cleanup();
  // Document body should no longer contain container
  assert.equal(dom.document.body.children.length, 0);
});

test("setupGlobalDom mounts and cleans up global window and document without leaking", () => {
  assert.equal((globalThis as any).window, undefined);

  const { container, cleanup } = setupGlobalDom('<span id="glob-span">Global</span>');
  assert.ok((globalThis as any).window);
  assert.ok((globalThis as any).document);
  assert.equal(document.getElementById("glob-span")?.textContent, "Global");
  assert.equal(container.id, "app-root");

  cleanup();
  assert.equal((globalThis as any).window, undefined);
  assert.equal((globalThis as any).document, undefined);
});

test("createTestTelegramUser and createTestInitData generate valid structures", () => {
  const user = createTestTelegramUser({ first_name: "Giorgio", id: 999 });
  assert.equal(user.first_name, "Giorgio");
  assert.equal(user.id, 999);

  const initData = createTestInitData({ first_name: "Giorgio", id: 999 });
  assert.ok(initData.includes("Giorgio"));
  assert.ok(initData.includes("hash="));
  assert.ok(initData.includes("query_id="));
});

test("setupTestTelegram sets and cleanly restores window.Telegram.WebApp", () => {
  assert.equal((globalThis as any).Telegram, undefined);

  const { mock, restore } = setupTestTelegram({
    colorScheme: "light",
  });

  assert.ok(mock);
  assert.ok((globalThis as any).Telegram?.WebApp);
  assert.equal((globalThis as any).Telegram.WebApp.colorScheme, "light");

  restore();
  assert.equal((globalThis as any).Telegram, undefined);
});

test("mockFetchResponse and mockFetchError stub fetch cleanly and restore original", async () => {
  const original = globalThis.fetch;

  const restore1 = mockFetchResponse({ data: [1, 2, 3] });
  const res1 = await fetch("/api/test");
  const json1 = await res1.json();
  assert.deepEqual(json1, { data: [1, 2, 3] });
  restore1();
  assert.equal(globalThis.fetch, original);

  const restore2 = mockFetchError(404, "Risorsa non trovata");
  const res2 = await fetch("/api/missing");
  assert.equal(res2.status, 404);
  const json2 = await res2.json();
  assert.equal(json2.detail, "Risorsa non trovata");
  restore2();
  assert.equal(globalThis.fetch, original);
});

test("captureFetchRequests records all outgoing fetch requests with parsed JSON body", async () => {
  const { requests, restore } = captureFetchRequests({ result: "ok" });

  await fetch("https://api.example.com/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: "player1" }),
  });

  assert.equal(requests.length, 1);
  assert.equal(requests[0].url, "https://api.example.com/login");
  assert.equal(requests[0].method, "POST");
  assert.equal(requests[0].body.username, "player1");

  restore();
});

test("test fixtures provide valid and rich data models", () => {
  const career = createTestCareerPath();
  assert.equal(career.length, 3);
  assert.equal(career[0].team, "Parma");

  const daily = createTestDailyChallenge();
  assert.equal(daily.number, 42);
  assert.equal(daily.solved, false);
  assert.equal(daily.hints.total, 3);

  const leaderboard = createTestLeaderboard();
  assert.equal(leaderboard.length, 4);
  assert.equal(leaderboard[0].position, 1);
});
