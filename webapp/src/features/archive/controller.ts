/**
 * ArchiveController — Issue #44
 *
 * Manages the state of the Archive feature: calendar loading, challenge
 * selection, and guess submission. Follows the same patterns as
 * DailyController (requestSeq stale-response guard) and LeaderboardController
 * (load idempotency, separate in-flight deduplication).
 *
 * The backend is always authoritative. The controller never derives status
 * (solved/lost/recovered/missed) or attempt counts client-side.
 */

import { api, ApiClient } from "@/api/client";
import { getTelegramWebApp } from "@/telegram/webapp";
import { fetchCalendar, fetchArchiveChallenge, submitArchiveGuess } from "./api";
import type { ArchiveState, ArchiveGuessResult } from "./types";

export class ArchiveController {
  private client: ApiClient;
  private state: ArchiveState;
  private listeners: Set<(state: ArchiveState) => void> = new Set();

  /** Stale-response guard for calendar loads. */
  private calendarSeq = 0;
  /** Stale-response guard for challenge loads. */
  private challengeSeq = 0;
  /** Stale-response guard for guess submissions. */
  private guessSeq = 0;

  /** Prevents concurrent calendar loads when one is already in flight. */
  private calendarInFlight: Promise<void> | null = null;

  constructor(client: ApiClient = api) {
    this.client = client;
    this.state = {
      view: "calendar",
      status: "idle",
      error: null,
      calendar: [],
      selectedDay: null,
      challenge: null,
      feedback: null,
      draftAnswer: "",
      challengeFinished: false,
    };
  }

  public getState(): ArchiveState {
    return this.state;
  }

  public subscribe(listener: (state: ArchiveState) => void): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  private notify(): void {
    this.listeners.forEach((l) => l(this.state));
  }

  private updateState(partial: Partial<ArchiveState>): void {
    this.state = { ...this.state, ...partial };
    this.notify();
  }

  // ---------------------------------------------------------------------------
  // Calendar
  // ---------------------------------------------------------------------------

  /**
   * Loads the calendar. Idempotent: if the calendar is already loaded and
   * not in an error state, this is a no-op. Call `refresh()` to force-reload.
   */
  public async init(): Promise<void> {
    if (this.state.status === "ready" || this.state.status === "loading") {
      return this.calendarInFlight ?? undefined;
    }
    return this._loadCalendar();
  }

  /**
   * Force-reloads the calendar (e.g. after finishing an archive challenge).
   */
  public async refresh(): Promise<void> {
    return this._loadCalendar(true);
  }

  public async refreshCalendar(force = true): Promise<void> {
    return this._loadCalendar(force);
  }

  private async _loadCalendar(force = false): Promise<void> {
    if (!force && this.calendarInFlight) {
      return this.calendarInFlight;
    }

    const currentSeq = ++this.calendarSeq;
    this.updateState({ status: "loading", error: null });

    this.calendarInFlight = (async () => {
      try {
        const days = await fetchCalendar(this.client);
        if (currentSeq !== this.calendarSeq) return;
        this.updateState({ status: "ready", calendar: days });
      } catch (err: any) {
        if (currentSeq !== this.calendarSeq) return;
        this.updateState({
          status: "error",
          error: err?.detail || err?.message || "loadError",
        });
      } finally {
        this.calendarInFlight = null;
      }
    })();

    return this.calendarInFlight;
  }

  /** Retry the calendar load after an error. */
  public async retry(): Promise<void> {
    return this._loadCalendar(true);
  }

  // ---------------------------------------------------------------------------
  // Challenge
  // ---------------------------------------------------------------------------

  /**
   * Opens a specific day for gameplay. Only callable for days the server
   * marked as playable; a 404 from the server (day deleted / unavailable)
   * results in a challenge_error state.
   */
  public async openDay(day: string): Promise<void> {
    const currentSeq = ++this.challengeSeq;
    this.updateState({
      view: "challenge",
      status: "challenge_loading",
      selectedDay: day,
      challenge: null,
      feedback: null,
      draftAnswer: "",
      challengeFinished: false,
      error: null,
    });

    try {
      const challenge = await fetchArchiveChallenge(day, this.client);
      if (currentSeq !== this.challengeSeq) return;
      this.updateState({ status: "challenge_ready", challenge });
    } catch (err: any) {
      if (currentSeq !== this.challengeSeq) return;
      this.updateState({
        status: "challenge_error",
        error: err?.detail || err?.message || "loadError",
      });
    }
  }

  /** Retry the challenge load after a challenge_error. */
  public async retryChallenge(): Promise<void> {
    const day = this.state.selectedDay;
    if (!day) return;
    return this.openDay(day);
  }

  /**
   * Navigate back to the calendar view.
   * Triggers a calendar refresh if the challenge was finished (so the
   * recovered/solved status reflects in the calendar immediately).
   */
  public async backToCalendar(): Promise<void> {
    ++this.challengeSeq; // Cancel any in-flight challenge load
    const needsRefresh = this.state.challengeFinished;

    this.updateState({
      view: "calendar",
      status: needsRefresh ? "loading" : this.state.status === "ready" ? "ready" : "ready",
      selectedDay: null,
      challenge: null,
      feedback: null,
      draftAnswer: "",
      challengeFinished: false,
      error: null,
    });

    if (needsRefresh) {
      return this._loadCalendar(true);
    }
  }

  // ---------------------------------------------------------------------------
  // Guessing
  // ---------------------------------------------------------------------------

  /**
   * Submits a guess for the currently open archive day.
   * Blocks double-submission (status === "submitting").
   * Uses guessSeq to discard stale responses from rapid re-submissions.
   */
  public async submitGuess(rawAnswer: string): Promise<ArchiveGuessResult | null> {
    const answer = rawAnswer.trim();
    const { selectedDay } = this.state;

    if (!answer || !selectedDay || this.state.status === "submitting") {
      return null;
    }

    const currentSeq = ++this.guessSeq;
    this.updateState({ status: "submitting", error: null });

    try {
      const result = await submitArchiveGuess(answer, selectedDay, this.client);

      if (currentSeq !== this.guessSeq) return null;

      const tg = getTelegramWebApp();
      try {
        tg?.HapticFeedback?.notificationOccurred(
          result.status === "correct" ? "success" : "error",
        );
      } catch {
        // Haptic feedback is non-critical
      }

      const isFinished =
        result.status === "correct" ||
        (result.status === "wrong" && result.attempts_left === 0) ||
        result.status === "refused" || result.status === "no_challenge";

      const updatedChallenge = this.state.challenge && (result.status === "correct" || result.status === "wrong")
        ? { ...this.state.challenge, attempts_used: result.attempts_used, attempts_left: result.attempts_left, solved: result.status === "correct" || this.state.challenge.solved }
        : this.state.challenge;

      this.updateState({
        status: "challenge_ready",
        feedback: result,
        draftAnswer: "",
        challengeFinished: isFinished,
        // Keep challenge in sync with server's attempt counts
        challenge: updatedChallenge,
      });

      return result;
    } catch (err: any) {
      if (currentSeq !== this.guessSeq) return null;
      this.updateState({
        status: "challenge_ready",
        error: err?.detail || err?.message || "loadError",
      });
      return null;
    }
  }

  // ---------------------------------------------------------------------------
  // Misc
  // ---------------------------------------------------------------------------

  public setDraftAnswer(val: string): void {
    this.state.draftAnswer = val;
  }

  public openShareUrl(url: string): void {
    if (!url) return;
    const tg = getTelegramWebApp();
    if (tg?.openTelegramLink) {
      tg.openTelegramLink(url);
    } else if (typeof window !== "undefined") {
      window.open(url, "_blank", "noopener");
    }
  }
}
