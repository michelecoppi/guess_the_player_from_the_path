/**
 * Leaderboard & Leagues Feature Module
 * Ownership: Issue #43 (Mini App: migrare feature Leaderboard)
 */

import type {
  ApiLeaderboardEntry,
  ApiLeague,
  ApiLeagueStanding,
  ApiPublicProfileResponse,
} from "@/api/types";

export type LeaderboardEntry = ApiLeaderboardEntry;
export type League = ApiLeague;
export type LeagueStanding = ApiLeagueStanding;
export type PublicProfileData = ApiPublicProfileResponse;

/**
 * Prototype fixture type preserved for backwards compatibility with unmigrated screens.
 */
export interface LeaderboardRank {
  rank: number;
  user_id: number;
  name: string;
  points: number;
  best_streak: number;
}

export type LeaderboardTab = "global" | "leagues";

export interface PublicProfileState {
  profileId: number;
  status: "loading" | "ready" | "error";
  data: PublicProfileData | null;
  error?: string | null;
}

export interface LeaderboardState {
  status: "idle" | "loading" | "ready" | "error";
  error: string | null;
  activeTab: LeaderboardTab;
  selectedLeagueCode: string | null;
  globalLeaderboard: LeaderboardEntry[];
  leagues: League[];
  publicProfile: PublicProfileState | null;
}

export const LEADERBOARD_FEATURE_METADATA = {
  id: "leaderboard",
  name: "Leaderboard & Leagues",
  owningIssue: 43,
  migrated: true,
} as const;
