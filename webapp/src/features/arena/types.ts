/**
 * Arena Duel Feature Module
 * Ownership: Issue #41 (Mini App: migrare feature Arena)
 */

export interface DuelOpponent {
  id: number;
  name: string;
  avatar?: string;
  score?: number;
}

export interface ArenaDuel {
  duel_id: string;
  status: "waiting" | "active" | "completed";
  opponent?: DuelOpponent;
  current_round: number;
  total_rounds: number;
  user_score: number;
  opponent_score: number;
}

export const ARENA_FEATURE_METADATA = {
  id: "arena",
  name: "Arena Duels",
  owningIssue: 41,
  migrated: false,
} as const;
