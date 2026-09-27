/**
 * Archive Feature API Wrappers — Issue #44
 *
 * All calls use POST with Telegram initData injected automatically by ApiClient.
 * These wrappers are the single point of truth for the archive's network interface.
 */

import { api, ApiClient } from "@/api/client";
import type { ArchiveCalendarDay, ArchiveChallenge, ArchiveGuessResult } from "./types";

/** Response shape from POST /app/api/calendar (without `day`). */
interface CalendarResponse {
  days: ArchiveCalendarDay[];
}

/**
 * Fetches the calendar of past daily challenges for the authenticated user.
 * POST /app/api/calendar (no extra body fields).
 */
export async function fetchCalendar(client: ApiClient = api): Promise<ArchiveCalendarDay[]> {
  const res = await client.post<CalendarResponse>("/calendar", {});
  return res.days ?? [];
}

/**
 * Fetches the challenge data for a specific past day.
 * POST /app/api/calendar { day }.
 * Returns the ArchiveChallenge without correct_answers or player_id (stripped by backend).
 */
export async function fetchArchiveChallenge(
  day: string,
  client: ApiClient = api,
): Promise<ArchiveChallenge> {
  return client.post<ArchiveChallenge>("/calendar", { day });
}

/**
 * Submits an archive guess.
 * POST /app/api/guess { answer, day }.
 * The backend routes to play_archive() when day is present and is a past date.
 */
export async function submitArchiveGuess(
  answer: string,
  day: string,
  client: ApiClient = api,
): Promise<ArchiveGuessResult> {
  return client.post<ArchiveGuessResult>("/guess", { answer: answer.trim(), day });
}
