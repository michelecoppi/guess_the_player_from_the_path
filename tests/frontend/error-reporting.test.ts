import { test } from "node:test";
import assert from "node:assert/strict";
import { ApiClient, ApiError } from "../../webapp/src/api";
import {
  installErrorReporting,
  reportFromErrorEvent,
  reportFromRejection,
  MAX_REPORTS_PER_PAGE,
} from "../../webapp/src/telemetry/errors";

const ORIGIN = "https://app.example";

function fakeTarget() {
  const listeners = new Map<string, (event: Event) => void>();
  return {
    target: {
      addEventListener: (type: string, fn: (event: Event) => void) => listeners.set(type, fn),
      removeEventListener: (type: string) => listeners.delete(type),
    } as unknown as Pick<Window, "addEventListener" | "removeEventListener">,
    fire: (type: string, event: object) => listeners.get(type)?.(event as Event),
    listeners,
  };
}

function capture() {
  const bodies: Record<string, unknown>[] = [];
  const urls: string[] = [];
  const client = new ApiClient({ getAuthToken: () => "signed" });
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (url: string, init?: RequestInit) => {
    urls.push(String(url));
    bodies.push(JSON.parse(String(init?.body)));
    return new Response(JSON.stringify({ status: "ok" }), { status: 200 });
  }) as typeof fetch;
  return { client, bodies, urls, restore: () => { globalThis.fetch = originalFetch; } };
}

const errorEvent = (message: string, line = 10) => ({
  message,
  filename: `${ORIGIN}/app/assets/index-abc.js?v=2`,
  lineno: line,
  colno: 4,
  error: new TypeError(message),
});

test("reports our unhandled errors with a bounded payload and the current screen (#180)", async () => {
  const { target, fire } = fakeTarget();
  const { client, bodies, urls, restore } = capture();
  try {
    installErrorReporting({ client, target, origin: ORIGIN, random: () => 0, screen: () => "shop" });
    fire("error", errorEvent("x is undefined " + "a".repeat(500)));
    await new Promise((resolve) => setTimeout(resolve, 0));
    assert.deepEqual(urls, ["/app/api/client-error"]);
    const [body] = bodies;
    assert.equal(body.initData, "signed");
    assert.equal(body.kind, "error");
    assert.equal(body.screen, "shop");
    assert.equal(body.source, `${ORIGIN}/app/assets/index-abc.js`, "query string stripped");
    assert.equal(body.line, 10);
    assert.ok(String(body.message).startsWith("TypeError: x is undefined"));
    assert.ok(String(body.message).length <= 300);
  } finally {
    restore();
  }
});

test("deduplicates, caps per page and skips unsampled sessions (#180)", async () => {
  const { target, fire } = fakeTarget();
  const { client, bodies, restore } = capture();
  try {
    installErrorReporting({ client, target, origin: ORIGIN, random: () => 0 });
    fire("error", errorEvent("same"));
    fire("error", errorEvent("same"));
    for (let i = 0; i < 10; i++) fire("error", errorEvent(`crash ${i}`, i + 1));
    await new Promise((resolve) => setTimeout(resolve, 0));
    assert.equal(bodies.length, MAX_REPORTS_PER_PAGE);
    assert.equal(bodies.filter((b) => String(b.message).includes("same")).length, 1);

    const other = fakeTarget();
    installErrorReporting({ client, target: other.target, origin: ORIGIN, random: () => 0.99 });
    assert.equal(other.listeners.size, 0, "an unsampled session installs nothing");
  } finally {
    restore();
  }
});

test("ignores foreign scripts, opaque errors and API failures (#180)", () => {
  assert.equal(reportFromErrorEvent({ ...errorEvent("x"), filename: "https://telegram.org/js/telegram-web-app.js" } as unknown as ErrorEvent, ORIGIN), null);
  assert.equal(reportFromErrorEvent({ message: "Script error.", filename: "", lineno: 0, colno: 0, error: null } as unknown as ErrorEvent, ORIGIN), null);
  assert.equal(reportFromRejection(new ApiError("API error 500", 500)), null);
  assert.equal(reportFromRejection({ not: "an error" }), null);
  assert.deepEqual(reportFromRejection("plain reason"), { kind: "unhandledrejection", message: "plain reason" });
  const report = reportFromRejection(new RangeError("bad"));
  assert.equal(report?.message, "RangeError: bad");
  assert.ok(report?.stack);
});

test("reporting failures are swallowed and never re-reported (#180)", async () => {
  const { target, fire } = fakeTarget();
  const client = new ApiClient({ getAuthToken: () => "signed" });
  const originalFetch = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = (async () => { calls++; throw new Error("offline"); }) as typeof fetch;
  try {
    const uninstall = installErrorReporting({ client, target, origin: ORIGIN, random: () => 0 });
    fire("unhandledrejection", { reason: new Error("boom") });
    await new Promise((resolve) => setTimeout(resolve, 0));
    assert.equal(calls, 1);
    uninstall();
    fire("unhandledrejection", { reason: new Error("after uninstall") });
    assert.equal(calls, 1);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
