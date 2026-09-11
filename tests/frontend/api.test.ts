import { test } from "node:test";
import assert from "node:assert/strict";
import { ApiClient, ApiError } from "../../webapp/src/api";

test("ApiClient formats URLs and attaches initData headers", async () => {
  let capturedUrl = "";
  let capturedHeaders: Headers | undefined;

  const mockFetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    capturedUrl = String(input);
    capturedHeaders = new Headers(init?.headers);
    return new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };

  const client = new ApiClient({
    baseUrl: "https://example.com/app/api",
    getAuthToken: () => "test_token_123",
  });

  // Temporarily stub global fetch
  const originalFetch = globalThis.fetch;
  globalThis.fetch = mockFetch as any;

  try {
    const res = await client.request<{ ok: boolean }>("/profile");
    assert.deepEqual(res, { ok: true });
    assert.equal(capturedUrl, "https://example.com/app/api/profile");
    assert.equal(capturedHeaders?.get("X-Telegram-Init-Data"), "test_token_123");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("ApiClient throws ApiError on non-200 responses", async () => {
  const mockFetch = async (): Promise<Response> => {
    return new Response(JSON.stringify({ detail: "Unauthorized" }), {
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
        await client.request("/profile");
      },
      (err: any) => {
        assert.ok(err instanceof ApiError);
        assert.equal(err.status, 401);
        return true;
      }
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});
