import { api, ApiClient } from "@/api/client";
import type { ApiProfileResponse } from "@/api/types";
import type {
  DailyCardPayload,
  DailyCardResponse,
  DailyGuessResult,
} from "./types";

/**
 * Fetches the user profile and today's challenge from POST /app/api/me.
 */
export async function fetchDailyProfile(
  client: ApiClient = api,
  options: { lightweight?: boolean } = {}
): Promise<ApiProfileResponse> {
  return client.getMe(options);
}

/**
 * Submits a player name guess to POST /app/api/guess.
 */
export async function submitDailyGuess(
  answer: string,
  client: ApiClient = api
): Promise<DailyGuessResult> {
  return client.post<DailyGuessResult>("/guess", { answer: answer.trim() });
}

/**
 * Requests an additional hint for today's challenge from POST /app/api/hint.
 */
export async function requestDailyHint(
  client: ApiClient = api
): Promise<{ status: string }> {
  return client.post<{ status: string }>("/hint", {});
}

/**
 * Generates and fetches the collectible result card image from POST /app/api/card.
 */
export async function fetchDailyCard(
  payload: DailyCardPayload,
  client: ApiClient = api
): Promise<DailyCardResponse> {
  return client.post<DailyCardResponse>("/card", payload as unknown as Record<string, unknown>);
}
