import { api, ApiClient } from "@/api/client";
import type { RecapResponse } from "./types";

/** POST /app/api/recap (#245): the recap of `month` (default: the last closed month). */
export async function fetchRecap(month?: string, client: ApiClient = api): Promise<RecapResponse> {
  return client.post<RecapResponse>("/recap", month ? { month } : {});
}

/** POST /app/api/recap/share: the recap card prepared for WebApp.shareMessage. */
export async function prepareRecapShare(
  month: string,
  client: ApiClient = api,
): Promise<{ id: string; expires_at: number | null }> {
  return client.post("/recap/share", { month });
}
