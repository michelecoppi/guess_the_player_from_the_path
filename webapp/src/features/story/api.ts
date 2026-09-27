import { api, ApiClient } from "@/api/client";
import type { StoryAction, StoryChaptersData, StoryData } from "./types";

export interface StoryRequestOptions {
  action: StoryAction;
  chapterId?: string;
  answer?: string;
  revision?: number;
}

/**
 * Sends a story action request to POST /app/api/arena with mode="story".
 */
export async function requestStory<T = StoryData>(
  options: StoryRequestOptions,
  client: ApiClient = api,
): Promise<T> {
  const payload: Record<string, unknown> = {
    mode: "story",
    action: options.action,
  };
  if (options.chapterId !== undefined) {
    payload.chapter_id = options.chapterId;
  }
  if (options.answer !== undefined) {
    payload.answer = options.answer;
  }
  if (options.revision !== undefined) {
    payload.revision = options.revision;
  }

  return client.post<T>("/arena", payload);
}

export async function fetchStoryChapters(client: ApiClient = api): Promise<StoryChaptersData> {
  return requestStory<StoryChaptersData>({ action: "list" }, client);
}

export async function fetchStoryChapter(chapterId: string, client: ApiClient = api): Promise<StoryData> {
  return requestStory({ action: "get", chapterId }, client);
}

export async function guessStory(
  answer: string,
  revision: number,
  chapterId: string,
  client: ApiClient = api,
): Promise<StoryData> {
  return requestStory({ action: "guess", answer: answer.trim(), revision, chapterId }, client);
}

export async function revealStory(
  revision: number,
  chapterId: string,
  client: ApiClient = api,
): Promise<StoryData> {
  return requestStory({ action: "reveal", revision, chapterId }, client);
}
