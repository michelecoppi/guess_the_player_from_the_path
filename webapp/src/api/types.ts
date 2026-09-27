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

export interface ApiLeagueStanding {
  position: number;
  profile_id?: number;
  name: string;
  points: number;
  me?: boolean;
}

export interface ApiLeague {
  code: string;
  name: string;
  members: number;
  position: number | null;
  points: number;
  standings: ApiLeagueStanding[];
}

export interface ApiPublicProfileItem {
  id?: string;
  kind: string;
  name: string;
  free?: boolean;
}

export interface ApiPublicProfileResponse {
  user: ApiUserSummary;
  cosmetics: ApiCosmetics;
  trophies: unknown[];
  wearing: ApiPublicProfileItem[];
  wardrobe?: ApiPublicProfileItem[];
  [key: string]: unknown;
}

/**
 * Feature flags (#51) resolved by the server for the authenticated user. Only booleans:
 * rules, rollout percentages and target lists never reach the client. Hiding a control
 * based on these is cosmetic; the API still refuses with `FEATURE_DISABLED`.
 */
export type FeatureFlagKey =
  | "arena"
  | "shop"
  | "daily_ui"
  | "hints"
  | "player_pipeline"
  | "events_v2"
  | "leaderboard";

export type ApiResolvedFeatures = Partial<Record<FeatureFlagKey, boolean>>;

export const FEATURE_DISABLED = "FEATURE_DISABLED";

export interface ApiProfileResponse {
  language?: string;
  features?: ApiResolvedFeatures;
  user: ApiUserSummary;
  cosmetics?: ApiCosmetics;
  trophies?: ApiTrophies;
  today?: ApiTodaySummary;
  distribution?: ApiDistributionEntry[];
  leaderboard?: ApiLeaderboardEntry[];
  leagues?: ApiLeague[];
  [key: string]: unknown;
}

export interface ApiErrorResponse {
  detail: string;
  code?: string;
  feature?: FeatureFlagKey;
}

/**
 * Whether a feature is on for this profile. A missing block or key (an older server) means
 * enabled: the flags default to the behaviour that existed before them.
 */
export function isFeatureEnabled(
  profile: Pick<ApiProfileResponse, "features"> | null | undefined,
  key: FeatureFlagKey,
): boolean {
  return profile?.features?.[key] !== false;
}

export interface ApiRequestPayload {
  initData?: string;
  [key: string]: unknown;
}
