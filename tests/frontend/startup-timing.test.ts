import { test } from "node:test";
import assert from "node:assert/strict";
import { ApiClient } from "../../webapp/src/api";
import { collectStartupMetrics, reportStartup, resetStartupReport } from "../../webapp/src/telemetry/startup";

function timeline(entries: { navigation?: object[]; resource?: object[] }, now = 1234.56) {
  return {
    now: () => now,
    getEntriesByType: (type: string) => ((entries as Record<string, object[]>)[type] || []) as PerformanceEntryList,
  };
}

test("collectStartupMetrics reads navigation, the first /me call and its Server-Timing", () => {
  const perf = timeline({
    navigation: [{ responseStart: 180.04, domContentLoadedEventEnd: 420.2, transferSize: 2048 }],
    resource: [
      { name: "https://bot.example/app/assets/index.js", duration: 90, transferSize: 102400 },
      {
        name: "https://bot.example/app/api/me", duration: 350.44, transferSize: 1024,
        serverTiming: [{ name: "fs", duration: 80 }, { name: "app", duration: 120.25 }],
      },
    ],
  });

  assert.deepEqual(collectStartupMetrics(perf, 910.36), {
    first_data_ms: 910.4,
    ttfb_ms: 180,
    dom_ready_ms: 420.2,
    api_me_ms: 350.4,
    api_me_server_ms: 120.3,
    transfer_kb: 103,
  });
});

test("collectStartupMetrics omits what the browser does not expose", () => {
  assert.deepEqual(collectStartupMetrics(timeline({}), 500), { first_data_ms: 500 });
});

test("reportStartup posts one bounded report per page load and never throws", async () => {
  resetStartupReport();
  const bodies: unknown[] = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (_url: string, init?: RequestInit) => {
    bodies.push(JSON.parse(String(init?.body)));
    return new Response(JSON.stringify({ status: "ok" }), { status: 200 });
  }) as typeof fetch;
  const client = new ApiClient({ baseUrl: "/app/api", getAuthToken: () => "signed-init-data" });
  try {
    assert.equal(await reportStartup("ok", client, timeline({})), true);
    assert.equal(await reportStartup("ok", client, timeline({})), false, "second report in the same load");
    assert.deepEqual(bodies, [
      { initData: "signed-init-data", app: "v2", outcome: "ok", metrics: { first_data_ms: 1234.6 } },
    ]);

    resetStartupReport();
    globalThis.fetch = (async () => { throw new Error("offline"); }) as typeof fetch;
    assert.equal(await reportStartup("error", client, timeline({})), false);
  } finally {
    globalThis.fetch = originalFetch;
    resetStartupReport();
  }
});
