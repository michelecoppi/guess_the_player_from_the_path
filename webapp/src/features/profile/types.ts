import type { ResolvedAppearance } from "@/appearance/types";

/**
 * User Profile Feature Module
 * Ownership: Issue #42 (Mini App: migrare feature Profilo)
 */

export interface ProfileUserSummary {
  name: string;
  points: number;
  monthly_points: number;
  players_guessed: number;
  bonus_first_guessed: number;
  streak: number;
  best_streak: number;
  archive_solved: number;
  trophies: number;
}

export interface ProfileDistributionEntry {
  attempts: number;
  count: number;
}

export interface TrophyPlate {
  code: string;
  kind: "monthly" | "event" | string;
  position: number;
  medal: string;
  color: string;
  label: string;
  detail: string;
  year: string;
}

export interface ProfileTrophies {
  pinned: TrophyPlate[];
  all: TrophyPlate[];
  max: number;
}

export interface ProfileData {
  language: string;
  user: ProfileUserSummary;
  cosmetics: ResolvedAppearance;
  trophies: ProfileTrophies;
  distribution: ProfileDistributionEntry[];
  today?: Record<string, unknown>;
}

export interface TrophyPinResult {
  status: "ok" | "too_many" | "invalid_choice" | "not_owned" | string;
  pinned?: TrophyPlate[];
}

export type CabinetFilter = "all" | "1" | "2" | "3" | "event" | "monthly";

export type ProfileViewMode = "profile" | "cabinet";

export interface ProfileState {
  view: ProfileViewMode;
  status: "idle" | "loading" | "ready" | "error";
  error: string | null;
  profile: ProfileData | null;
  cabinetFilter: CabinetFilter;
  pendingPinCodes: string[] | null;
  isPinning: boolean;
  pinError: string | null;
  pinSuccess: boolean;
}

export const PROFILE_FEATURE_METADATA = {
  id: "profile",
  name: "User Profile",
  owningIssue: 42,
  migrated: true,
} as const;
