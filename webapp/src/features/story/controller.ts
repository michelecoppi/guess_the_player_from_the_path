import { api, ApiClient } from "@/api/client";
import { getTelegramWebApp } from "@/telegram/webapp";
import { fetchStoryChapter, fetchStoryChapters, guessStory, revealStory } from "./api";
import type { StoryData, StoryFeedback, StoryState } from "./types";

const RESYNC_ERRORS = ["stale", "finished"];

export class StoryController {
  private client: ApiClient;
  private state: StoryState;
  private listeners: Set<() => void> = new Set();
  private activeRequestId = 0;

  constructor(client: ApiClient = api) {
    this.client = client;
    this.state = {
      mode: "chapters",
      status: "idle",
      busy: false,
      error: null,
      confirming: null,
      chapters: null,
      data: null,
      draftAnswer: "",
      lastFeedback: null,
    };
  }

  public getState(): StoryState {
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

  private triggerHaptic(type: "success" | "error" | "warning"): void {
    try {
      const tg = getTelegramWebApp();
      tg?.HapticFeedback?.notificationOccurred(type);
    } catch {
      // Ignored outside Telegram or in headless environments
    }
  }

  private applyResult(result: StoryData): void {
    this.state.data = result;
    if (result.feedback) {
      this.state.lastFeedback = result.feedback;
    }
  }

  /** Loads the episode menu. Entry point when Story Mode opens from the Arena hub. */
  public async init(): Promise<void> {
    const requestId = ++this.activeRequestId;
    this.state.mode = "chapters";
    this.state.status = "loading";
    this.state.busy = true;
    this.state.error = null;
    this.state.confirming = null;
    this.notify();

    try {
      const result = await fetchStoryChapters(this.client);
      if (requestId !== this.activeRequestId) return;
      this.state.chapters = result.chapters;
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

  /** Opens a chapter's level map. Its response also carries the current-level play data. */
  public async openChapter(chapterId: string): Promise<void> {
    if (this.state.busy) return;
    const requestId = ++this.activeRequestId;
    this.state.mode = "levels";
    this.state.status = "loading";
    this.state.busy = true;
    this.state.error = null;
    this.state.confirming = null;
    this.state.lastFeedback = null;
    this.notify();

    try {
      const result = await fetchStoryChapter(chapterId, this.client);
      if (requestId !== this.activeRequestId) return;
      this.applyResult(result);
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

  /** Enters play for the chapter's current (unlocked) level - no fetch, the data is already there. */
  public enterPlay(): void {
    if (!this.state.data?.chapter) return;
    this.state.mode = "play";
    this.state.draftAnswer = "";
    this.notify();
  }

  public backToLevels(): void {
    this.state.mode = "levels";
    this.state.confirming = null;
    this.notify();
  }

  public async backToChapters(): Promise<void> {
    this.state.mode = "chapters";
    this.state.confirming = null;
    this.notify();
    await this.init();
  }

  public async submitGuess(rawAnswer?: string): Promise<StoryData | null> {
    if (this.state.busy) return null;

    const answer = (rawAnswer ?? this.state.draftAnswer).trim();
    if (!answer) {
      this.state.error = "invalid_answer";
      this.notify();
      return null;
    }

    const chapter = this.state.data?.chapter;
    if (!chapter || chapter.finished) return null;

    const requestId = ++this.activeRequestId;
    this.state.status = "submitting";
    this.state.busy = true;
    this.state.error = null;
    this.state.confirming = null;
    this.notify();

    try {
      const result = await guessStory(answer, chapter.revision, chapter.chapter_id, this.client);
      if (requestId !== this.activeRequestId) return null;

      this.applyResult(result);
      this.state.draftAnswer = "";
      this.state.status = "idle";
      this.state.error = null;
      this.triggerHaptic(this.hapticFor(result.feedback));
      return result;
    } catch (err: any) {
      if (requestId !== this.activeRequestId) return null;
      const detail = err?.detail || "loadError";
      this.state.error = detail;
      this.state.status = "idle";
      if (RESYNC_ERRORS.includes(detail)) {
        await this.resync();
      }
      return null;
    } finally {
      if (requestId === this.activeRequestId) {
        this.state.busy = false;
        this.notify();
      }
    }
  }

  private hapticFor(feedback?: StoryFeedback | null): "success" | "error" | "warning" {
    if (!feedback) return "error";
    if (feedback.chapter_cleared || feedback.level_cleared) return "success";
    if (feedback.level_failed) return "warning";
    return feedback.status === "correct" ? "success" : "error";
  }

  public async reveal(): Promise<StoryData | null> {
    if (this.state.busy) return null;

    if (this.state.confirming !== "reveal") {
      this.state.confirming = "reveal";
      this.notify();
      return null;
    }

    const chapter = this.state.data?.chapter;
    if (!chapter || chapter.finished) {
      this.state.confirming = null;
      return null;
    }

    const requestId = ++this.activeRequestId;
    this.state.status = "revealing";
    this.state.busy = true;
    this.state.error = null;
    this.state.confirming = null;
    this.notify();

    try {
      const result = await revealStory(chapter.revision, chapter.chapter_id, this.client);
      if (requestId !== this.activeRequestId) return null;
      this.applyResult(result);
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
        await this.resync();
      }
      return null;
    } finally {
      if (requestId === this.activeRequestId) {
        this.state.busy = false;
        this.notify();
      }
    }
  }

  private async resync(): Promise<void> {
    const chapterId = this.state.data?.chapter.chapter_id;
    if (!chapterId) return;
    try {
      const resynced = await fetchStoryChapter(chapterId, this.client);
      this.applyResult(resynced);
      this.state.error = null;
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
