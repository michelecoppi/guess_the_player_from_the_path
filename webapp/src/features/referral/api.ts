import { api, type ApiClient } from "@/api/client";
import type { EquipResponse } from "@/features/shop/types";
import type { ReferralDashboardResponse } from "./types";

/**
 * Fetches the authoritative referral dashboard from POST /app/api/referrals.
 * Supports cursor-based pagination. Never sends unauthenticated or raw user IDs.
 */
export async function fetchReferrals(
  cursor?: string | null,
  client: ApiClient = api,
): Promise<ReferralDashboardResponse> {
  const payload = cursor ? { cursor } : {};
  return client.post<ReferralDashboardResponse>("/app/api/referrals", payload);
}

/**
 * Equips an earned referral cosmetic via the authoritative POST /app/api/shop/equip endpoint.
 */
export async function equipReferralItem(
  itemId: string,
  client: ApiClient = api,
): Promise<EquipResponse> {
  return client.post<EquipResponse>("/app/api/shop/equip", { item: itemId });
}
