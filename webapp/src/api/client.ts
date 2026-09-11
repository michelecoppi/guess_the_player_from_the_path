import type { ApiProfileResponse } from "./types";
import { getInitData } from "@/telegram/webapp";

export class ApiError extends Error {
  status: number;
  data?: unknown;

  constructor(message: string, status: number, data?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
  }
}

export interface ApiClientConfig {
  baseUrl?: string;
  getAuthToken?: () => string;
}

export class ApiClient {
  private baseUrl: string;
  private getAuthToken: () => string;

  constructor(config: ApiClientConfig = {}) {
    this.baseUrl = config.baseUrl || "/app/api";
    this.getAuthToken = config.getAuthToken || getInitData;
  }

  async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const url = `${this.baseUrl}${endpoint.startsWith("/") ? endpoint : `/${endpoint}`}`;
    const headers = new Headers(options.headers || {});

    // In Telegram Mini Apps, initData is sent either via X-Telegram-Init-Data or Authorization
    const token = this.getAuthToken();
    if (token && !headers.has("X-Telegram-Init-Data")) {
      headers.set("X-Telegram-Init-Data", token);
    }
    if (!headers.has("Content-Type") && options.method && options.method !== "GET") {
      headers.set("Content-Type", "application/json");
    }

    const response = await fetch(url, {
      ...options,
      headers,
    });

    if (!response.ok) {
      let errorData: unknown;
      try {
        errorData = await response.json();
      } catch {
        errorData = await response.text();
      }
      throw new ApiError(
        `API error ${response.status}: ${response.statusText}`,
        response.status,
        errorData
      );
    }

    return (await response.json()) as T;
  }

  /**
   * Fetches user profile data from /app/api/profile
   */
  async getProfile(): Promise<ApiProfileResponse> {
    return this.request<ApiProfileResponse>("/profile");
  }
}

export const api = new ApiClient();
