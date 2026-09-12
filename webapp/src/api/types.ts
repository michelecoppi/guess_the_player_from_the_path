import type { ResolvedAppearance } from "@/appearance/types";
/**
 * API request and response data models.
 * Compatible with FastAPI backend endpoints defined in bot.py & services/webapp_api.py.
 */

export interface ApiUserSummary {
  name: string;
  points: number;
  monthly_points?: number;
  players_guessed?: number;
  bonus_first_guessed?: number;
  streak: number;
  best_streak: number;
  archive_solved?: number;
  trophies?: number;
}

export interface CareerStop {
  team: string;
  league?: string | null;
  country?: string | null;
  start_year?: number | string | null;
  end_year?: number | string | null;
  apps?: number | null;
  goals?: number | null;
  loan?: boolean;
}


export interface ApiTodaySummary {
  day?: string;
  number?: number;
  available?: boolean;
  solved: boolean;
  attempts_used?: number;
  attempts_left?: number;
  max_attempts?: number;
  difficulty?: string;
  difficulty_label?: string;
  points?: number;
  bonus_available?: boolean;
  career_path?: CareerStop[];
  hints?: {
    used: number;
    total: number;
    taken: string[];
  };
}

export interface ApiLeaderboardEntry {
  position: number;
  profile_id?: number;
  name: string;
  badge?: string;
  points: number;
  me?: boolean;
}

export interface ApiDistributionEntry {
  attempts: number;
  count: number;
}

export type ApiCosmetics = ResolvedAppearance;

export interface ApiTrophies {
  pinned?: unknown[];
  all?: unknown[];
  max?: number;
  [key: string]: unknown;
}

export interface ApiProfileResponse {
  language?: string;
  user: ApiUserSummary;
  cosmetics?: ApiCosmetics;
  trophies?: ApiTrophies;
  today?: ApiTodaySummary;
  distribution?: ApiDistributionEntry[];
  leaderboard?: ApiLeaderboardEntry[];
  leagues?: unknown[];
  [key: string]: unknown;
}

export interface ApiErrorResponse {
  detail: string;
  code?: string;
}

export interface ApiRequestPayload {
  initData?: string;
  [key: string]: unknown;
}
