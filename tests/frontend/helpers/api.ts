export interface CapturedRequest {
  url: string;
  method: string;
  body: any;
  headers: Headers;
}

/**
 * Mocks globalThis.fetch to return a fixed JSON response.
 * Returns a restore function to safely tear down the mock.
 */
export function mockFetchResponse<T>(
  data: T | ((input: RequestInfo | URL, init?: RequestInit) => any),
  status = 200,
  headers: Record<string, string> = {},
): () => void {
  const originalFetch = globalThis.fetch;

  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const payload = typeof data === "function" ? await (data as any)(input, init) : data;
    if (payload instanceof Response) return payload;
    return new Response(JSON.stringify(payload), {
      status,
      headers: {
        "Content-Type": "application/json",
        ...headers,
      },
    });
  }) as any;

  return () => {
    globalThis.fetch = originalFetch;
  };
}

/**
 * Mocks globalThis.fetch to return a structured error response.
 */
export function mockFetchError(status: number, detail = "Errore mock"): () => void {
  return mockFetchResponse({ detail }, status);
}

/**
 * Captures all calls made to fetch while active.
 */
export function captureFetchRequests(
  responsePayload: any = { ok: true },
  status = 200,
): {
  requests: CapturedRequest[];
  restore: () => void;
} {
  const originalFetch = globalThis.fetch;
  const requests: CapturedRequest[] = [];

  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    let parsedBody: any = null;
    if (init?.body) {
      try {
        parsedBody = JSON.parse(String(init.body));
      } catch {
        parsedBody = String(init.body);
      }
    }

    requests.push({
      url: String(input),
      method: init?.method || "GET",
      body: parsedBody,
      headers: new Headers(init?.headers),
    });

    const payload =
      typeof responsePayload === "function"
        ? await responsePayload(input, init)
        : responsePayload;
    if (payload instanceof Response) return payload;

    return new Response(JSON.stringify(payload), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  }) as any;

  return {
    requests,
    restore: () => {
      globalThis.fetch = originalFetch;
    },
  };
}
