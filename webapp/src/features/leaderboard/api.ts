import { api, ApiClient } from "@/api/client";
import type { LeaderboardEntry, League, PublicProfileData } from "./types";

export interface SocialData {
  leaderboard: LeaderboardEntry[];
  leagues: League[];
}

/**
 * Fetches the user profile including full social payload (leaderboard and leagues)
 * from POST /app/api/me without lightweight mode.
 */
export async function fetchSocialData(
  client: ApiClient = api,
): Promise<SocialData> {
  const profile = await client.getMe({ lightweight: false });
  return {
    leaderboard: profile.leaderboard || [],
    leagues: profile.leagues || [],
  };
}

/**
 * Fetches public player profile from POST /app/api/profile/public.
 */
export async function fetchPublicProfile(
  profileId: number,
  client: ApiClient = api,
): Promise<PublicProfileData> {
  return client.getPublicProfile(profileId);
}
