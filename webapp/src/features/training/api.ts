import { api, ApiClient } from "@/api/client";
import type { TrainingAction, TrainingData } from "./types";

export interface TrainingRequestOptions {
  action: TrainingAction;
  answer?: string;
  revision?: number;
}

/**
 * Sends a training action request to POST /app/api/arena with mode="training".
 */
export async function requestTraining(
  options: TrainingRequestOptions,
  client: ApiClient = api,
): Promise<TrainingData> {
  const payload: Record<string, unknown> = {
    mode: "training",
    action: options.action,
  };
  if (options.answer !== undefined) {
    payload.answer = options.answer;
  }
  if (options.revision !== undefined) {
    payload.revision = options.revision;
  }

  return client.post<TrainingData>("/arena", payload);
}

export async function fetchTrainingSession(
  client: ApiClient = api,
): Promise<TrainingData> {
  return requestTraining({ action: "get" }, client);
}

export async function nextTrainingChallenge(
  client: ApiClient = api,
): Promise<TrainingData> {
  return requestTraining({ action: "next" }, client);
}

export async function guessTraining(
  answer: string,
  revision: number,
  client: ApiClient = api,
): Promise<TrainingData> {
  return requestTraining(
    {
      action: "guess",
      answer: answer.trim(),
      revision,
    },
    client,
  );
}

export async function revealTraining(
  revision: number,
  client: ApiClient = api,
): Promise<TrainingData> {
  return requestTraining({ action: "reveal", revision }, client);
}
