import type { CareerStop } from "@/components/CareerPath";

export type { CareerStop };

export type StoryAction = "list" | "get" | "guess" | "reveal";

/** Which screen of the feature is on: the episode menu, its level map, or a level in play. */
export type StoryMode = "chapters" | "levels" | "play";

export interface StoryHistoryEntry {
  solved: boolean;
  attempts: number;
}

export type StoryLevelState = "locked" | "current" | "cleared";

export interface StoryLevelEntry {
  id: number;
  theme: string;
  state: StoryLevelState;
  starred: boolean;
}

export interface StoryChapterSummary {
  chapter_id: string;
  title: string;
  total_levels: number;
  levels_cleared: number;
  stars_earned: number;
  finished: boolean;
  locked: boolean;
}

export interface StoryChapterView {
  chapter_id: string;
  title: string;
  total_levels: number;
  level: number;
  step: number;
  steps_per_level: number;
  attempts: number;
  max_attempts: number;
  revision: number;
  finished: boolean;
  stars: boolean[];
  history: StoryHistoryEntry[];
  levels: StoryLevelEntry[];
  theme?: string;
  level_number?: number;
  career_path?: CareerStop[];
  difficulty_label?: string;
}

export interface StoryComparisonClue {
  key: string;
  args?: Record<string, any>;
}

export interface StoryComparison {
  name?: string;
  clues?: StoryComparisonClue[];
}

export interface StoryFeedback {
  status: "correct" | "wrong" | "revealed";
  level_failed: boolean;
  level_cleared?: boolean;
  starred?: boolean;
  chapter_cleared?: boolean;
  answer?: string;
  comparison?: StoryComparison;
}

export interface StoryData {
  chapter: StoryChapterView;
  feedback?: StoryFeedback | null;
}

export interface StoryChaptersData {
  chapters: StoryChapterSummary[];
}

export type StoryStatus = "idle" | "loading" | "submitting" | "revealing" | "error";

export interface StoryState {
  mode: StoryMode;
  status: StoryStatus;
  busy: boolean;
  error: string | null;
  confirming: string | null;
  chapters: StoryChapterSummary[] | null;
  data: StoryData | null;
  draftAnswer: string;
  /** Last feedback kept on screen even after the state moves to the next step. */
  lastFeedback: StoryFeedback | null;
}

export const STORY_FEATURE_METADATA = {
  id: "story",
  name: "Story Mode / Modalita' Storia",
  migrated: true,
} as const;
