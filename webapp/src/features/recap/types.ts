/** The monthly recap served by POST /app/api/recap (#245), see services/monthly_recap.py. */
export type RecapStyleKey = "professor" | "sniper" | "purist" | "last_minute" | "marathon" | "playmaker";

export interface RecapGem {
  day: string;
  rate: number;
  attempts?: number;
  name: string;
  path: { team: string; start_year?: number; end_year?: number | null }[];
}

export interface MonthlyRecap {
  month: string;
  available: boolean;
  played: number;
  min_played?: number;
  days?: number;
  solved?: number;
  calendar?: ("won" | "lost" | "skip")[];
  attempts?: [number, number, number];
  best_streak?: number;
  hints?: number;
  style?: { key: RecapStyleKey; value: number };
  gem?: RecapGem;
  lucky_club?: { team: string; count: number; players: string[] };
  better_than?: number;
  firsts?: number;
}

export interface RecapResponse {
  recap: MonthlyRecap | null;
  months: string[];
  name: string;
}
