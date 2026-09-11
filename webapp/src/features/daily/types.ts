/**
 * Daily Challenge Feature Module
 * Ownership: Issue #40 (Mini App: migrare feature Daily)
 */

export interface CareerStep {
  team: string;
  years?: string;
  apps?: number;
  goals?: number;
}

export interface GuessAttempt {
  player_id: number;
  name: string;
  is_correct: boolean;
  timestamp: number;
}

export interface DailyState {
  date: string;
  path: CareerStep[];
  attempts: GuessAttempt[];
  max_attempts: number;
  hints: string[];
  solved: boolean;
}

export const DAILY_FEATURE_METADATA = {
  id: "daily",
  name: "Daily Challenge",
  owningIssue: 40,
  migrated: false,
} as const;
