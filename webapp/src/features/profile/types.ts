/**
 * User Profile Feature Module
 * Ownership: Issue #42 (Mini App: migrare feature Profilo)
 */

export interface Trophy {
  id: string;
  name: string;
  position: 1 | 2 | 3;
  date: string;
}

export interface UserProfileData {
  id: number;
  name: string;
  points: number;
  current_streak: number;
  best_streak: number;
  trophies: Trophy[];
  cosmetics: {
    avatar_frame?: string;
    background_theme?: string;
  };
}

export const PROFILE_FEATURE_METADATA = {
  id: "profile",
  name: "User Profile",
  owningIssue: 42,
  migrated: false,
} as const;
