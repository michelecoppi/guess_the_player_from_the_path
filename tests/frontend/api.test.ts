import { test } from "node:test";
import assert from "node:assert/strict";
import { ApiClient, ApiError } from "../../webapp/src/api";

test("ApiClient sends POST with JSON body containing initData and no X-Telegram-Init-Data header", async () => {
  let capturedUrl = "";
  let capturedMethod = "";
  let capturedHeaders: Headers | undefined;
  let capturedBody = "";

  const mockFetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    capturedUrl = String(input);
    capturedMethod = String(init?.method);
    capturedHeaders = new Headers(init?.headers);
    capturedBody = String(init?.body);
    return new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };

  const client = new ApiClient({
    baseUrl: "https://example.com/app/api",
    getAuthToken: () => "test_token_123",
  });

  const originalFetch = globalThis.fetch;
  globalThis.fetch = mockFetch as any;

  try {
    const res = await client.request<{ ok: boolean }>("/me");
    assert.deepEqual(res, { ok: true });
    assert.equal(capturedUrl, "https://example.com/app/api/me");
    assert.equal(capturedMethod, "POST");
    assert.equal(capturedHeaders?.get("Content-Type"), "application/json");
    // Contract requirement: no X-Telegram-Init-Data header
    assert.equal(capturedHeaders?.has("X-Telegram-Init-Data"), false);

    // Contract requirement: initData is inside JSON body
    const parsedBody = JSON.parse(capturedBody);
    assert.equal(parsedBody.initData, "test_token_123");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("ApiClient.post merges initData with custom payload into request body", async () => {
  let capturedUrl = "";
  let capturedBody = "";

  const mockFetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    capturedUrl = String(input);
    capturedBody = String(init?.body);
    return new Response(JSON.stringify({ guessed: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };

  const client = new ApiClient({
    baseUrl: "/app/api",
    getAuthToken: () => "signed_webapp_token",
  });

  const originalFetch = globalThis.fetch;
  globalThis.fetch = mockFetch as any;

  try {
    const res = await client.post<{ guessed: boolean }>("/guess", { query: "Zidane", day: "2026-09-11" });
    assert.deepEqual(res, { guessed: true });
    assert.equal(capturedUrl, "/app/api/guess");

    const parsedBody = JSON.parse(capturedBody);
    assert.equal(parsedBody.initData, "signed_webapp_token");
    assert.equal(parsedBody.query, "Zidane");
    assert.equal(parsedBody.day, "2026-09-11");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("ApiClient.getMe and getProfile call POST /app/api/me matching FastAPI route", async () => {
  const calls: Array<{ url: string; method: string; body: any }> = [];

  const mockFetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    calls.push({
      url: String(input),
      method: String(init?.method),
      body: JSON.parse(String(init?.body)),
    });
    return new Response(
      JSON.stringify({
        user: { name: "Mario", points: 100, streak: 3, best_streak: 5 },
      }),
      { status: 200, headers: { "Content-Type": "application/json" } }
    );
  };

  const client = new ApiClient({
    baseUrl: "/app/api",
    getAuthToken: () => "auth_token_xyz",
  });

  const originalFetch = globalThis.fetch;
  globalThis.fetch = mockFetch as any;

  try {
    const meRes = await client.getMe({ lightweight: true });
    assert.equal(meRes.user.name, "Mario");

    const profileRes = await client.getProfile();
    assert.equal(profileRes.user.name, "Mario");

    assert.equal(calls.length, 2);
    // Both must target /app/api/me (NOT /profile)
    assert.equal(calls[0].url, "/app/api/me");
    assert.equal(calls[0].method, "POST");
    assert.equal(calls[0].body.initData, "auth_token_xyz");
    assert.equal(calls[0].body.lightweight, true);

    assert.equal(calls[1].url, "/app/api/me");
    assert.equal(calls[1].method, "POST");
    assert.equal(calls[1].body.initData, "auth_token_xyz");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("ApiClient extracts structured detail from backend 401 error", async () => {
  const mockFetch = async (): Promise<Response> => {
    return new Response(JSON.stringify({ detail: "initData mancante" }), {
      status: 401,
      statusText: "Unauthorized",
      headers: { "Content-Type": "application/json" },
    });
  };

  const client = new ApiClient({ baseUrl: "/app/api" });
  const originalFetch = globalThis.fetch;
  globalThis.fetch = mockFetch as any;

  try {
    await assert.rejects(
      async () => {
        await client.post("/me");
      },
      (err: any) => {
        assert.ok(err instanceof ApiError);
        assert.equal(err.status, 401);
        assert.equal(err.detail, "initData mancante");
        assert.match(err.message, /initData mancante/);
        return true;
      }
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("ApiClient request shape matches backend _webapp_user payload extraction contract", async () => {
  // Verifies that what ApiClient produces can be directly consumed by backend _webapp_user(payload)
  // Backend contract in bot.py:
  //   user_id = user_id_from_init_data(payload.get("initData", ""), BOT_TOKEN)
  let sentBody: string = "";

  const mockFetch = async (_: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    sentBody = String(init?.body);
    return new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };

  const client = new ApiClient({
    baseUrl: "/app/api",
    getAuthToken: () => "query_id=1&user=%7B%22id%22%3A42%7D&hash=fakehash",
  });

  const originalFetch = globalThis.fetch;
  globalThis.fetch = mockFetch as any;

  try {
    await client.post("/me", { customField: "test" });
    const payload = JSON.parse(sentBody);

    // Emulate Python backend dict extraction: payload.get("initData", "")
    const backendExtractedInitData = payload["initData"] || "";
    assert.equal(backendExtractedInitData, "query_id=1&user=%7B%22id%22%3A42%7D&hash=fakehash");
    assert.equal(payload["customField"], "test");
  } finally {
    globalThis.fetch = originalFetch;
  }
});
