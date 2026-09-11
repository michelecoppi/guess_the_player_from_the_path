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
export function mockFetchResponse<T>(data: T, status = 200, headers: Record<string, string> = {}): () => void {
  const originalFetch = globalThis.fetch;

  globalThis.fetch = (async (_input: RequestInfo | URL, _init?: RequestInit): Promise<Response> => {
    return new Response(JSON.stringify(data), {
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
export function captureFetchRequests(responsePayload: any = { ok: true }, status = 200): {
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

    return new Response(JSON.stringify(responsePayload), {
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
