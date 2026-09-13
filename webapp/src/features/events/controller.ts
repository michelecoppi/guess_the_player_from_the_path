import { api, type ApiClient } from "@/api/client";
import { fetchEvents, guessEvent } from "./api";
import type { EventCard, EventsState } from "./types";

/**
 * Controller for Special Events in Mini App V2.
 * Manages state, concurrency guards, resynchronization, and server-authoritative progress.
 */
export class EventsController {
  private state: EventsState = {
    status: "idle",
    events: [],
    selectedCode: null,
    feedback: null,
    draftAnswer: "",
    error: null,
  };

  private listeners: Array<(state: EventsState) => void> = [];
  private loadSeq = 0;
  private submitSeq = 0;

  constructor(private client: ApiClient = api) {}

  public getState(): EventsState {
    return this.state;
  }

  public subscribe(listener: (state: EventsState) => void): () => void {
    this.listeners.push(listener);
    return () => {
      this.listeners = this.listeners.filter((l) => l !== listener);
    };
  }

  private setState(patch: Partial<EventsState>): void {
    this.state = { ...this.state, ...patch };
    for (const listener of this.listeners) {
      listener(this.state);
    }
  }

  /**
   * Load active events from the server.
   * If an event is currently selected, preserves selection if it remains in the updated list,
   * otherwise clears the selection.
   */
  public async load(): Promise<void> {
    if (this.state.status === "submitting") {
      return;
    }

    const currentSeq = ++this.loadSeq;
    const initialSelection = this.state.selectedCode;
    this.setState({ status: "loading", error: null });

    try {
      const response = await fetchEvents(this.client);
      if (currentSeq !== this.loadSeq) {
        return;
      }

      const events = Array.isArray(response?.events) ? response.events : [];
      const activeCode = this.state.selectedCode ?? initialSelection;
      const nextSelection =
        activeCode && events.some((e) => e.code === activeCode)
          ? activeCode
          : null;

      this.setState({
        status: "ready",
        events,
        selectedCode: nextSelection,
        feedback: null,
        error: null,
      });
    } catch (err: any) {
      if (currentSeq !== this.loadSeq) {
        return;
      }
      this.setState({
        status: "error",
        error: err?.detail || "loadError",
      });
    }
  }

  /**
   * Select an event card to view details or play.
   */
  public select(code: string): void {
    if (this.state.events.some((e) => e.code === code)) {
      this.setState({
        selectedCode: code,
        feedback: null,
        draftAnswer: "",
        error: null,
      });
    }
  }

  /**
   * Return from event detail back to the events list.
   */
  public back(): void {
    this.setState({
      selectedCode: null,
      feedback: null,
      draftAnswer: "",
      error: null,
    });
  }

  public setDraftAnswer(draftAnswer: string): void {
    this.setState({ draftAnswer });
  }

  public selected(): EventCard | undefined {
    return this.state.events.find((e) => e.code === this.state.selectedCode);
  }

  /**
   * Submit an answer to the currently selected event.
   * Enforces sequence guards, prevents double-submission, and auto-resyncs on divergence.
   */
  public async submit(answer: string): Promise<void> {
    const event = this.selected();
    const trimmed = answer.trim();

    if (
      !event ||
      this.state.status === "submitting" ||
      !event.available ||
      event.progress.finished ||
      !trimmed
    ) {
      return;
    }

    const targetCode = event.code;
    const currentSeq = ++this.submitSeq;
    this.setState({
      status: "submitting",
      error: null,
      feedback: null,
    });

    try {
      const response = await guessEvent(
        targetCode,
        event.day,
        trimmed,
        event.progress.attempts,
        this.client,
      );

      if (currentSeq !== this.submitSeq) {
        return;
      }

      // If user navigated away from targetCode while submission was in-flight,
      // update events in background without polluting the active screen.
      if (this.state.selectedCode !== targetCode) {
        this.setState({
          status: "ready",
          events: response.events,
        });
        return;
      }

      this.setState({
        status: "ready",
        events: response.events,
        feedback: response.feedback || null,
        draftAnswer: "",
        error: null,
      });
    } catch (err: any) {
      if (currentSeq !== this.submitSeq) {
        return;
      }

      if (this.state.selectedCode !== targetCode) {
        return;
      }

      const error = err?.detail || "unknown";
      this.setState({
        status: "error",
        error,
      });

      // Stale, expired, or finished mean client state diverged from backend.
      // Resynchronize from server without replaying the guess.
      if (["stale", "expired", "finished"].includes(error)) {
        await this.load();
        // Preserve the error notice so the user sees the explanation.
        this.setState({ error });
      }
    }
  }
}
