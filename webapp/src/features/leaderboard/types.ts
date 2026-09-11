/**
 * Leaderboard & Leagues Feature Module
 * Ownership: Issue #43 (Mini App: migrare feature Leaderboard)
 */

export interface LeaderboardRank {
  rank: number;
  user_id: number;
  name: string;
  points: number;
  best_streak: number;
}

export interface League {
  code: string;
  name: string;
  members_count: number;
  rankings: LeaderboardRank[];
}

export const LEADERBOARD_FEATURE_METADATA = {
  id: "leaderboard",
  name: "Leaderboard & Leagues",
  owningIssue: 43,
  migrated: false,
} as const;
