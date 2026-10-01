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
  /** Today's Daily after a wrong answer (#259): spares a follow-up `/app/api/me`. */
  today?: ApiTodaySummary;
}

export interface DailyCardResponse {
  image: string;
}

/** A message the bot prepared for WebApp.shareMessage (#185). */
export interface PreparedShareResponse {
  id: string;
  /** Unix seconds; null when Telegram did not say. */
  expires_at: number | null;
}

export interface DailyState {
  status: DailyStatus;
  errorMessage?: string;
  challenge?: ApiTodaySummary | null;
  user?: ApiUserSummary | null;
  feedback?: DailyGuessResult | null;
  cardImage?: string | null;
  cardLoading?: boolean;
  /** Outcome of the last "copy the result" tap (#150), shown under the buttons. */
  copyNotice?: string | null;
  squaresSymbols: SquareSymbols;
  inputValue: string;
  introVisible?: boolean;
  /** True from the final answer until the reveal animation has been drawn once. */
  revealPending?: boolean;
  /** A hint request is in flight: the button shows a spinner and ignores taps. */
  hintLoading?: boolean;
}

export const DAILY_FEATURE_METADATA = {
  id: "daily",
  name: "Daily Challenge",
  owningIssue: 40,
  migrated: true,
} as const;
