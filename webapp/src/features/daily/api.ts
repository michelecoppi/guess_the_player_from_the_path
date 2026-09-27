import { api, ApiClient } from "@/api/client";
import type { ApiProfileResponse } from "@/api/types";
import type { DailyCardResponse, DailyGuessResult, PreparedShareResponse } from "./types";

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
  expectedDay: string | undefined,
  client: ApiClient = api
): Promise<DailyGuessResult> {
  return client.post<DailyGuessResult>("/guess", { answer: answer.trim(), expected_day: expectedDay });
}

/**
 * Requests an additional hint for today's challenge from POST /app/api/hint.
 */
export async function requestDailyHint(
  expectedDay: string | undefined,
  client: ApiClient = api
): Promise<{ status: string }> {
  return client.post<{ status: string }>("/hint", { expected_day: expectedDay });
}

/**
 * Generates and fetches the collectible result card image from POST /app/api/card.
 */
export async function fetchDailyCard(
  client: ApiClient = api
): Promise<DailyCardResponse> {
  return client.post<DailyCardResponse>("/card");
}

/**
 * Asks the bot to prepare today's result as a shareable message (POST /app/api/share/prepare,
 * #185). The server builds it from the saved result; 503 means "use the classic share".
 */
export async function prepareDailyShare(
  expectedDay: string | undefined,
  client: ApiClient = api
): Promise<PreparedShareResponse> {
  return client.post<PreparedShareResponse>("/share/prepare", expectedDay ? { day: expectedDay } : {});
}

/** Telegram confirmed a shareMessage was sent: analytics only (POST /app/api/share/sent). */
export async function reportDailyShared(client: ApiClient = api): Promise<void> {
  await client.post("/share/sent");
}
