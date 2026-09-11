/**
 * API request and response data models.
 * Compatible with FastAPI backend endpoints defined in bot.py & services/webapp_api.py.
 */

export interface ApiUserProfile {
  id: number;
  name: string;
  points: number;
  current_streak: number;
  best_streak: number;
  language: string;
  referral_code?: string;
  referral_qualified?: number;
}

export interface ApiDailyChallenge {
  date: string;
  path: Array<{
    team: string;
    years?: string;
    apps?: number;
    goals?: number;
  }>;
  total_teams: number;
  max_attempts: number;
  solved?: boolean;
}

export interface ApiProfileResponse {
  user: ApiUserProfile;
  today?: {
    solved: boolean;
    attempts?: number;
    used_hints?: number;
  };
  leaderboard?: Array<{
    rank: number;
    name: string;
    points: number;
  }>;
  stats?: {
    played: number;
    wins: number;
    win_rate: number;
    distribution: Array<{ attempts: number; count: number }>;
  };
}

export interface ApiErrorResponse {
  detail: string;
  code?: string;
}
