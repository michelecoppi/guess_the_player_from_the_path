import type { CareerStop } from "@/components/CareerPath";
import type { ApiTodaySummary, ApiUserSummary } from "@/api/types";
import type { SquareSymbols } from "@/utils/game";

export type { CareerStop };

export type DailyStatus =
  | "loading"
  | "ready"
  | "submitting"
  | "incorrect"
  | "correct"
  | "completed"
  | "unavailable"
  | "error";

export interface DailyComparisonClue {
  key: string;
  args?: Record<string, any>;
}

export interface DailyComparison {
  name: string;
  clues: DailyComparisonClue[];
}

export interface DailyGuessResult {
  status: "correct" | "wrong" | "refused" | "no_challenge";
  attempts_used?: number;
  attempts_left?: number;
  hints_used?: number;
  comparison?: DailyComparison;
  points_awarded?: number;
  bonus?: number;
  streak?: number;
  streak_bonus?: number;
  typo?: boolean;
  answer?: string;
  reason?: string;
  share?: {
    text: string;
    url: string;
  };
}

export interface DailyCardPayload {
  attempts: number;
  max_attempts: number;
  solved: boolean;
  hints: number;
  streak: number;
  day?: string;
}

export interface DailyCardResponse {
  image: string;
}

export interface DailyState {
  status: DailyStatus;
  errorMessage?: string;
  challenge?: ApiTodaySummary | null;
  user?: ApiUserSummary | null;
  feedback?: DailyGuessResult | null;
  cardImage?: string | null;
  cardLoading?: boolean;
  squaresSymbols: SquareSymbols;
  inputValue: string;
}

export const DAILY_FEATURE_METADATA = {
  id: "daily",
  name: "Daily Challenge",
  owningIssue: 40,
  migrated: true,
} as const;
