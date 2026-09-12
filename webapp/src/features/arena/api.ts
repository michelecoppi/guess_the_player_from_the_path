import { api, ApiClient } from "@/api/client";
import type { DuelAction, DuelData, OpponentProfile } from "./types";

export interface ArenaRequestOptions {
  action: DuelAction;
  code?: string;
  answer?: string;
  revision?: number;
  lang?: string;
}

/**
 * Sends a duel action request to POST /app/api/arena with mode="duel".
 */
export async function requestArena(
  options: ArenaRequestOptions,
  client: ApiClient = api,
): Promise<DuelData> {
  const payload: Record<string, unknown> = {
    mode: "duel",
    action: options.action,
  };
  if (options.code) payload.code = options.code;
  if (options.answer !== undefined) payload.answer = options.answer;
  if (options.revision !== undefined) payload.revision = options.revision;
  if (options.lang) payload.lang = options.lang;

  return client.post<DuelData>("/arena", payload);
}

/**
 * Searches for public player profiles by name prefix via POST /app/api/profile/search.
 */
export async function searchProfiles(
  query: string,
  client: ApiClient = api,
): Promise<{ profiles: OpponentProfile[] }> {
  return client.post<{ profiles: OpponentProfile[] }>("/profile/search", {
    query: query.trim(),
  });
}

export async function fetchDuelList(client: ApiClient = api): Promise<DuelData> {
  return requestArena({ action: "list" }, client);
}

export async function fetchDuel(
  code: string,
  client: ApiClient = api,
): Promise<DuelData> {
  return requestArena({ action: "get", code }, client);
}

export async function createDuel(client: ApiClient = api): Promise<DuelData> {
  return requestArena({ action: "create" }, client);
}

export async function joinDuel(
  code: string,
  client: ApiClient = api,
): Promise<DuelData> {
  return requestArena({ action: "join", code }, client);
}

export async function guessDuel(
  code: string,
  answer: string,
  revision: number,
  client: ApiClient = api,
): Promise<DuelData> {
  return requestArena(
    {
      action: "guess",
      code,
      answer: answer.trim(),
      revision,
    },
    client,
  );
}

export async function revealDuel(
  code: string,
  revision: number,
  client: ApiClient = api,
): Promise<DuelData> {
  return requestArena({ action: "reveal", code, revision }, client);
}

export async function deleteDuel(
  code: string,
  client: ApiClient = api,
): Promise<{ deleted: string }> {
  return requestArena({ action: "delete", code }, client) as Promise<{
    deleted: string;
  }>;
}
