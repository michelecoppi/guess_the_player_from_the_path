import { api, ApiClient } from "@/api/client";
import { getTelegramWebApp } from "@/telegram/webapp";
import {
  fetchTrainingSession,
  nextTrainingChallenge,
  guessTraining,
  revealTraining,
} from "./api";
import type {
  TrainingData,
  TrainingState,
} from "./types";

const RESYNC_ERRORS = ["stale", "finished"];

export class TrainingController {
  private client: ApiClient;
  private state: TrainingState;
  private listeners: Set<() => void> = new Set();
  private activeRequestId = 0;

  constructor(client: ApiClient = api) {
    this.client = client;
    this.state = {
      status: "idle",
      busy: false,
      error: null,
      notice: null,
      confirming: null,
      data: null,
      draftAnswer: "",
    };
  }

  public getState(): TrainingState {
    return this.state;
  }

  public subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  private notify(): void {
    this.listeners.forEach((listener) => listener());
  }

  private triggerHaptic(type: "success" | "error"): void {
    try {
      const tg = getTelegramWebApp();
      tg?.HapticFeedback?.notificationOccurred(type);
    } catch {
      // Ignored outside Telegram or in headless environments
    }
  }

  /**
   * Initializes or refreshes the Training mode state from the server.
   */
  public async init(): Promise<void> {
    const requestId = ++this.activeRequestId;
    this.state.status = "loading";
    this.state.busy = true;
    this.state.error = null;
    this.state.notice = null;
    this.state.confirming = null;
    this.notify();

    try {
      const result = await fetchTrainingSession(this.client);
      if (requestId !== this.activeRequestId) return;

      this.state.data = result;
      this.state.status = "idle";
      this.state.error = null;
    } catch (err: any) {
      if (requestId !== this.activeRequestId) return;
      this.state.status = "error";
      this.state.error = err?.detail || "loadError";
    } finally {
      if (requestId === this.activeRequestId) {
        this.state.busy = false;
        this.notify();
      }
    }
  }

  /**
   * Starts a new Training challenge via action: "next".
   */
  public async startNext(): Promise<TrainingData | null> {
    if (this.state.busy) return null;

    const requestId = ++this.activeRequestId;
    this.state.status = "loading";
    this.state.busy = true;
    this.state.error = null;
    this.state.notice = null;
    this.state.confirming = null;
    this.state.draftAnswer = "";
    this.notify();

    try {
      const result = await nextTrainingChallenge(this.client);
      if (requestId !== this.activeRequestId) return null;

      this.state.data = result;
      this.state.status = "idle";
      this.state.error = null;
      return result;
    } catch (err: any) {
      if (requestId !== this.activeRequestId) return null;
      this.state.status = "error";
      this.state.error = err?.detail || "loadError";
      return null;
    } finally {
      if (requestId === this.activeRequestId) {
        this.state.busy = false;
        this.notify();
      }
    }
  }

  /**
   * Submits a player guess for the current Training session.
   */
  public async submitGuess(rawAnswer?: string): Promise<TrainingData | null> {
    if (this.state.busy) return null;

    const answer = (rawAnswer ?? this.state.draftAnswer).trim();
    if (!answer) {
      this.state.error = "invalid_answer";
      this.notify();
      return null;
    }

    const session = this.state.data?.session;
    if (!session || session.finished) {
      return null;
    }

    const requestId = ++this.activeRequestId;
    this.state.status = "submitting";
    this.state.busy = true;
    this.state.error = null;
    this.state.notice = null;
    this.state.confirming = null;
    this.notify();

    try {
      const result = await guessTraining(answer, session.revision, this.client);
      if (requestId !== this.activeRequestId) return null;

      this.state.data = result;
      this.state.draftAnswer = "";
      this.state.status = "idle";
      this.state.error = null;

      if (result.feedback?.status === "correct") {
        this.triggerHaptic("success");
      } else {
        this.triggerHaptic("error");
      }

      return result;
    } catch (err: any) {
      if (requestId !== this.activeRequestId) return null;

      const detail = err?.detail || "loadError";
      this.state.error = detail;
      this.state.status = "idle";

      // If error indicates stale revision or finished game, auto-resync state
      if (RESYNC_ERRORS.includes(detail)) {
        await this.resyncSession();
      }

      return null;
    } finally {
      if (requestId === this.activeRequestId) {
        this.state.busy = false;
        this.notify();
      }
    }
  }

  /**
   * Reveals the current Training puzzle solution.
   * Requires 2-step confirmation to prevent accidental reveal.
   */
  public async reveal(): Promise<TrainingData | null> {
    if (this.state.busy) return null;

    if (this.state.confirming !== "reveal") {
      this.state.confirming = "reveal";
      this.notify();
      return null;
    }

    const session = this.state.data?.session;
    if (!session || session.finished) {
      this.state.confirming = null;
      return null;
    }

    const requestId = ++this.activeRequestId;
    this.state.status = "revealing";
    this.state.busy = true;
    this.state.error = null;
    this.state.notice = null;
    this.state.confirming = null;
    this.notify();

    try {
      const result = await revealTraining(session.revision, this.client);
      if (requestId !== this.activeRequestId) return null;

      this.state.data = result;
      this.state.draftAnswer = "";
      this.state.status = "idle";
      this.state.error = null;
      return result;
    } catch (err: any) {
      if (requestId !== this.activeRequestId) return null;

      const detail = err?.detail || "loadError";
      this.state.error = detail;
      this.state.status = "idle";

      if (RESYNC_ERRORS.includes(detail)) {
        await this.resyncSession();
      }

      return null;
    } finally {
      if (requestId === this.activeRequestId) {
        this.state.busy = false;
        this.notify();
      }
    }
  }

  /**
   * Automatically re-fetches the authoritative session state after a 409 stale/finished error.
   */
  private async resyncSession(): Promise<void> {
    try {
      const resynced = await fetchTrainingSession(this.client);
      this.state.data = resynced;
      this.state.error = null;
      this.state.notice = "synced";
    } catch {
      // Retain the error if re-fetch also failed
    }
  }

  public cancelConfirm(): void {
    if (this.state.confirming) {
      this.state.confirming = null;
      this.notify();
    }
  }

  public setDraftAnswer(answer: string): void {
    this.state.draftAnswer = answer;
  }

  public clearError(): void {
    this.state.error = null;
    this.notify();
  }
}
