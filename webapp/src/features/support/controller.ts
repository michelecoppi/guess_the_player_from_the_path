import { api, type ApiClient } from "@/api/client";
import { sendReport } from "./api";
import type { SupportReportState } from "./types";

/**
 * The "Segnalazioni" screen in the header menu: one message, sent to the admins.
 * No list to load, so no `init()` - state starts idle and only ever reacts to a submit.
 */
export class SupportController {
  private state: SupportReportState = { status: "idle", draft: "" };
  private listeners: Array<(state: SupportReportState) => void> = [];

  constructor(private client: ApiClient = api) {}

  public getState(): SupportReportState {
    return this.state;
  }

  public subscribe(listener: (state: SupportReportState) => void): () => void {
    this.listeners.push(listener);
    return () => {
      this.listeners = this.listeners.filter((l) => l !== listener);
    };
  }

  private setState(patch: Partial<SupportReportState>): void {
    this.state = { ...this.state, ...patch };
    for (const listener of this.listeners) listener(this.state);
  }

  public async submitReport(message: string): Promise<void> {
    const trimmed = message.trim();
    if (!trimmed || this.state.status === "sending") return;
    this.setState({ status: "sending", draft: trimmed });
    try {
      await sendReport(trimmed, this.client);
      this.setState({ status: "sent", draft: "" });
    } catch {
      // The draft from setState above stays: a failed send should not cost the retyping.
      this.setState({ status: "error" });
    }
  }

  /** Back to a blank form - leaving the screen, or dismissing the sent/error notice. */
  public reset(): void {
    if (this.state.status !== "idle") this.setState({ status: "idle", draft: "" });
  }
}
