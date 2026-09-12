/**
 * Archive Feature Types — Issue #44 (Mini App: migrare feature Archivio)
 *
 * All state is authoritative from the backend. The client never calculates
 * status (solved/lost/recovered/missed) or attempt counts independently.
 */

import type { CareerStop } from "@/components/CareerPath";
import type { DailyComparison } from "@/features/daily/types";

// ---------------------------------------------------------------------------
// Calendar
// ---------------------------------------------------------------------------

/** The four mutually-exclusive outcomes a past day can have. */
export type ArchiveDayStatus = "solved" | "lost" | "recovered" | "missed";

/**
 * A single row in the calendar returned by POST /app/api/calendar (no `day`).
 * Matches the shape built by `build_calendar()` in services/webapp_api.py.
 */
export interface ArchiveCalendarDay {
  day: string;           // ISO-8601 date, e.g. "2026-09-01"
  label: string;         // Human-readable, e.g. "01/09/26"
  number: number;        // Challenge sequence number
  difficulty: string | null;
  difficulty_label: string;
  status: ArchiveDayStatus;
  attempts: number | null; // null for "missed" days
  hints: number;
  /** Server-authoritative: true only for "lost" and "missed" days. */
  playable: boolean;
}

// ---------------------------------------------------------------------------
// Challenge (single day loaded for gameplay)
// ---------------------------------------------------------------------------

/**
 * The challenge returned by POST /app/api/calendar { day }.
 * Matches the shape built by `build_archive_challenge()` in services/webapp_api.py.
 * `correct_answers` and `player_id` are NEVER present — the backend strips them.
 */
export interface ArchiveChallenge {
  day: string;
  label: string;
  number: number;
  difficulty: string | null;
  difficulty_label: string;
  solved: boolean;
  attempts_used: number;
  attempts_left: number;
  max_attempts: number;   // Always MAX_ARCHIVE_ATTEMPTS = 3; read from server
  career_path: CareerStop[];
}

// ---------------------------------------------------------------------------
// Guess result
// ---------------------------------------------------------------------------

/**
 * The guess result returned by POST /app/api/guess { answer, day }.
 * Matches `play_archive()` wrapped by `with_share_card()` in services/webapp_api.py.
 */
export interface ArchiveGuessResult {
  status: "correct" | "wrong" | "refused" | "no_challenge";
  attempts_used: number;
  attempts_left: number;
  /** Present on wrong guesses — same comparison as the daily game. */
  comparison?: DailyComparison;
  /** Present on the final wrong attempt (attempts_left === 0); the display name of the player. */
  answer?: string;
  /** Present when the game is over (correct or 0 attempts left). Added by with_share_card(). */
  share?: { text: string; url: string };
  /** Present on refused: "already_solved" | "no_attempts_left" | ... */
  reason?: string;
}

// ---------------------------------------------------------------------------
// Controller state
// ---------------------------------------------------------------------------

export type ArchiveView = "calendar" | "challenge";

export type ArchiveStatus =
  | "idle"
  | "loading"       // Calendar loading
  | "ready"         // Calendar loaded
  | "challenge_loading"
  | "challenge_ready"
  | "submitting"
  | "error"
  | "challenge_error";

export interface ArchiveState {
  view: ArchiveView;
  status: ArchiveStatus;
  error: string | null;
  /** The full list of past days from the calendar. */
  calendar: ArchiveCalendarDay[];
  /** The day currently open for gameplay. */
  selectedDay: string | null;
  /** The challenge data for the open day. */
  challenge: ArchiveChallenge | null;
  /** The latest guess result (persists until next guess or navigation). */
  feedback: ArchiveGuessResult | null;
  /** Input controlled by the user in the challenge view. */
  draftAnswer: string;
  /** True when the current challenge has been finished (to trigger calendar refresh on back). */
  challengeFinished: boolean;
}
