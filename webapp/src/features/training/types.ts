import type { CareerStop } from "@/components/CareerPath";

export type { CareerStop };

export type TrainingAction = "get" | "next" | "guess" | "reveal";

export interface TrainingSession {
  round: number;
  attempts: number;
  solved: number;
  spent: number;
  revision: number;
  finished: boolean;
  history: Array<{ solved: boolean; attempts: number }>;
  total: number;
  max_attempts: number;
  career_path?: CareerStop[];
  difficulty_label?: string;
}

export interface TrainingComparisonClue {
  key: string;
  args?: Record<string, any>;
}

export interface TrainingComparison {
  name?: string;
  clues?: TrainingComparisonClue[];
}

export interface TrainingFeedback {
  status: "correct" | "wrong" | "refused";
  done: boolean;
  answer?: string;
  comparison?: TrainingComparison;
  matched?: number;
  points?: number;
}

export interface TrainingData {
  session: TrainingSession | null;
  feedback?: TrainingFeedback | null;
}

export type TrainingStatus =
  | "idle"
  | "loading"
  | "submitting"
  | "revealing"
  | "error";

export interface TrainingState {
  status: TrainingStatus;
  busy: boolean;
  error: string | null;
  notice: string | null;
  confirming: string | null;
  data: TrainingData | null;
  draftAnswer: string;
}

export const TRAINING_FEATURE_METADATA = {
  id: "training",
  name: "Training / Allenamento",
  owningIssue: 68,
  migrated: true,
} as const;
