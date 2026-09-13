import { api, type ApiClient } from "@/api/client";
import type { ProfileData, TrophyPinResult } from "./types";

/**
 * Fetches the authenticated user's own profile via /app/api/me.
 * Uses `lightweight: true` to skip costly social additions (global leaderboard, private leagues),
 * while fetching user summary, resolved cosmetics, full trophy cabinet, and attempt distribution.
 */
export async function fetchOwnProfile(client: ApiClient = api): Promise<ProfileData> {
  return client.post<ProfileData>("/app/api/me", { lightweight: true });
}

/**
 * Pins selected trophies to the user's profile showcase via /app/api/trophies/pin.
 * Ownership and max constraints are enforced authoritatively by the backend.
 */
export async function pinTrophies(
  codes: string[],
  client: ApiClient = api,
): Promise<TrophyPinResult> {
  return client.post<TrophyPinResult>("/app/api/trophies/pin", { codes });
}
