/**
 * Special Events Feature Module
 * Ownership: Issue #47 (Mini App: migrare feature Eventi)
 */

import type { CareerStop } from "@/components/CareerPath";
import type { DailyComparison } from "@/features/daily/types";

/**
 * Fallback daily attempts limit for events served before #31. The authoritative value is
 * `EventCard.max_attempts`, copied from the event template (`rules.attempts`) and enforced
 * by the backend in services/app_events.py.
 */
export const EVENT_MAX_ATTEMPTS = 3;

export type KnownEventType = "path" | "blind_path" | "career" | "father_son" | "transfer_guess";

/** @deprecated Preview-only shape retained until the prototype fixture is removed. */
export interface EventChallenge {
  event_id: string;
  title: string;
  theme: string;
  starts_at: string;
  ends_at: string;
  active: boolean;
}

export type EventType = KnownEventType | (string & {});

export interface EventProgress {
  attempts: number;
  revealed?: number;
  revision?: number;
  finished: boolean;
  solved: boolean;
  points: number;
}

export interface EventLeaderboardRow {
  name: string;
  points: number;
}

/**
 * Public projection only: no player_id, correct_answers, or first_correct_user.
 */
export interface EventCard {
  code: string;
  day: string;
  type: EventType;
  name: string;
  description: string;
  dates: string[];
  available: boolean;
  rules: string;
  player_name: string;
  min_correct: number;
  career_path: CareerStop[];
  total_stops?: number | null;
  image_url: string | null;
  points: number;
  bonus_available: boolean;
  /** Attempts per day for this event (`rules.attempts` of its template). */
  max_attempts?: number;
  progress: EventProgress;
  leaderboard: EventLeaderboardRow[];
}

export interface EventFeedback {
  status: "correct" | "wrong";
  points: number;
  /**
   * For career events, the authoritative count of matched clubs returned by the backend
   * evaluator (services/event_rules.py). Null or undefined for other event types.
   */
  matched?: number | null;
  comparison?: DailyComparison | null;
}

export interface EventsResponse {
  events: EventCard[];
  feedback?: EventFeedback | null;
}

export interface EventsState {
  status: "idle" | "loading" | "ready" | "submitting" | "error";
  events: EventCard[];
  selectedCode: string | null;
  feedback: EventFeedback | null;
  draftAnswer: string;
  error: string | null;
}

export const EVENTS_FEATURE_METADATA = {
  id: "events",
  name: "Events",
  owningIssue: 47,
  migrated: true,
} as const;
