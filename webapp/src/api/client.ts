import { clearResolvedAppearance } from "@/appearance";
import type { ApiProfileResponse, ApiRequestPayload } from "./types";
import { getInitData } from "@/telegram/webapp";

export class ApiError extends Error {
  status: number;
  data?: unknown;
  detail?: string;

  constructor(message: string, status: number, data?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
    if (
      data &&
      typeof data === "object" &&
      "detail" in data &&
      typeof (data as { detail: unknown }).detail === "string"
    ) {
      this.detail = (data as { detail: string }).detail;
    }
  }
}

export interface ApiClientConfig {
  baseUrl?: string;
  getAuthToken?: () => string;
}

export interface ApiRequestOptions extends Omit<RequestInit, "body"> {
  body?: Record<string, unknown> | string;
  skipAuth?: boolean;
}

export class ApiClient {
  private baseUrl: string;
  private getAuthToken: () => string;
  private lastAuthToken: string | undefined;

  constructor(config: ApiClientConfig = {}) {
    this.baseUrl = (config.baseUrl || "/app/api").replace(/\/+$/, "");
    this.getAuthToken = config.getAuthToken || getInitData;
  }

  resolveUrl(endpoint: string): string {
    if (endpoint.startsWith("http://") || endpoint.startsWith("https://")) {
      return endpoint;
    }
    const clean = endpoint.startsWith("/") ? endpoint : `/${endpoint}`;
    if (clean === this.baseUrl || clean.startsWith(`${this.baseUrl}/`)) {
      return clean;
    }
    return `${this.baseUrl}${clean}`;
  }

  /**
   * Performs an API request matching the production FastAPI contract.
   * By default, Mini App endpoints use POST with a JSON body containing { initData, ...payload }.
   */
  async request<T>(endpoint: string, options: ApiRequestOptions = {}): Promise<T> {
    const authToken = options.skipAuth ? undefined : this.getAuthToken();
    if (this.lastAuthToken !== undefined && authToken !== undefined && authToken !== this.lastAuthToken) clearResolvedAppearance();
    if (authToken !== undefined) this.lastAuthToken = authToken;
    const url = this.resolveUrl(endpoint);
    const method = (options.method || "POST").toUpperCase();
    const headers = new Headers(options.headers || {});

    let body: BodyInit | undefined;

    if (method !== "GET" && method !== "HEAD") {
      if (!headers.has("Content-Type")) {
        headers.set("Content-Type", "application/json");
      }

      if (typeof options.body === "string") {
        body = options.body;
      } else {
        const token = authToken;
        const payload: ApiRequestPayload = {
          ...(token !== undefined ? { initData: token } : {}),
          ...(options.body || {}),
        };
        body = JSON.stringify(payload);
      }
    }

    const response = await fetch(url, {
      ...options,
      method,
      headers,
      body,
    });

    const checkSession = () => {
    if (authToken !== undefined && this.getAuthToken() !== authToken) {
      if (this.lastAuthToken === authToken) {
        clearResolvedAppearance();
        this.lastAuthToken = this.getAuthToken();
      }
      throw new ApiError("Session changed", 409);
    }
    };
    checkSession();
    if (!response.ok) {
      let errorData: unknown;
      try {
        errorData = await response.json();
      } catch {
        errorData = await response.text();
      }
      const detail =
        errorData && typeof errorData === "object" && "detail" in errorData
          ? String((errorData as { detail: unknown }).detail)
          : response.statusText;
      throw new ApiError(
        `API error ${response.status}: ${detail}`,
        response.status,
        errorData
      );
    }

    const data = (await response.json()) as T;
    checkSession();
    return data;
  }

  /**
   * Convenience helper to perform an authenticated POST request.
   */
  async post<T>(
    endpoint: string,
    payload: Record<string, unknown> = {},
    options: Omit<ApiRequestOptions, "body" | "method"> = {}
  ): Promise<T> {
    return this.request<T>(endpoint, {
      ...options,
      method: "POST",
      body: payload,
    });
  }

  /**
   * Fetches user profile data from POST /app/api/me.
   * Matches production backend route @app.post("/app/api/me").
   */
  async getMe(payload: { lightweight?: boolean } = {}): Promise<ApiProfileResponse> {
    return this.post<ApiProfileResponse>("/me", payload);
  }

  /**
   * Alias for getMe() matching feature requirements.
   */
  async getProfile(payload: { lightweight?: boolean } = {}): Promise<ApiProfileResponse> {
    return this.getMe(payload);
  }
}

export const api = new ApiClient();
