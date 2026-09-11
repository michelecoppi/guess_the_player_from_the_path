import { ApiClient, api } from "@/api/client";
import { getTelegramWebApp } from "@/telegram/webapp";
import { setLanguage } from "@/i18n";
import {
  fetchDailyProfile,
  submitDailyGuess,
  requestDailyHint,
  fetchDailyCard,
} from "./api";
import { celebrate } from "./celebrate";
import type { DailyState, DailyGuessResult, DailyCardPayload } from "./types";
import type { SquareSymbols } from "@/utils/game";

export const DEFAULT_SQUARE_SYMBOLS: SquareSymbols = {
  correct: "🟩",
  wrong: "🟥",
  unused: "⬜",
};

const THEME_VARS: Record<string, string> = {
  bg: "--bg",
  bg2: "--bg-secondary",
  card: "--card",
  edge: "--edge",
  text: "--text",
  muted: "--muted",
  accent: "--accent",
  accentText: "--accent-text",
  track: "--track",
  pattern: "--theme-pattern",
};

export class DailyController {
  private state: DailyState;
  private subscribers: Array<(state: DailyState) => void> = [];
  private apiClient: ApiClient;
  private requestSeq = 0;

  constructor(apiClient: ApiClient = api) {
    this.apiClient = apiClient;
    this.state = {
      status: "loading",
      errorMessage: undefined,
      challenge: null,
      user: null,
      feedback: null,
      cardImage: null,
      cardLoading: false,
      squaresSymbols: { ...DEFAULT_SQUARE_SYMBOLS },
      inputValue: "",
    };
  }

  public getState(): DailyState {
    return this.state;
  }

  public subscribe(subscriber: (state: DailyState) => void): () => void {
    this.subscribers.push(subscriber);
    return () => {
      this.subscribers = this.subscribers.filter((s) => s !== subscriber);
    };
  }

  private updateState(partial: Partial<DailyState>): void {
    this.state = { ...this.state, ...partial };
    this.notify();
  }

  private notify(): void {
    for (const subscriber of this.subscribers) {
      try {
        subscriber(this.state);
      } catch (err) {
        console.error("Error in DailyController subscriber:", err);
      }
    }
  }

  public async init(): Promise<void> {
    await this.loadDailyData();
  }

  public async loadDailyData(options: { lightweight?: boolean } = {}): Promise<void> {
    const isLightweight = Boolean(options.lightweight && this.state.challenge);
    if (!isLightweight) {
      this.updateState({ status: "loading", errorMessage: undefined });
    }

    try {
      const profile = await fetchDailyProfile(this.apiClient, { lightweight: isLightweight });

      if (profile.language) {
        setLanguage(profile.language as any);
      }

      this.applyCosmetics(profile.cosmetics);

      const today = profile.today || null;
      let nextStatus = this.state.status;

      if (!today || !today.available) {
        nextStatus = "unavailable";
      } else if (today.solved) {
        nextStatus = "completed";
      } else if ((today.attempts_left ?? 0) <= 0 && (today.attempts_used ?? 0) > 0) {
        nextStatus = "completed";
      } else {
        nextStatus = "ready";
      }

      this.updateState({
        user: profile.user || null,
        challenge: today,
        status: nextStatus,
        errorMessage: undefined,
      });
    } catch (err: any) {
      const detail = err?.detail || err?.message || "Impossibile caricare la sfida quotidiana.";
      this.updateState({
        status: "error",
        errorMessage: detail,
        challenge: null,
      });
    }
  }

  public async submitGuess(rawAnswer: string): Promise<DailyGuessResult | null> {
    const answer = rawAnswer.trim();
    if (!answer || this.state.status === "submitting") {
      return null;
    }

    const currentSeq = ++this.requestSeq;
    this.updateState({ status: "submitting", errorMessage: undefined });

    try {
      const result = await submitDailyGuess(answer, this.apiClient);

      // Discard stale response if a newer submission was fired
      if (currentSeq !== this.requestSeq) {
        return null;
      }

      const tg = getTelegramWebApp();
      try {
        tg?.HapticFeedback?.notificationOccurred(result.status === "correct" ? "success" : "error");
      } catch {
        // Haptic feedback is non-critical
      }

      if (result.status === "correct") {
        celebrate();
      }

      // Reload fresh profile data
      await this.loadDailyData({ lightweight: result.status === "wrong" });

      let nextStatus = this.state.status;
      if (result.status === "correct") {
        nextStatus = "correct";
      } else if (result.status === "wrong") {
        nextStatus = (result.attempts_left ?? 0) <= 0 ? "completed" : "incorrect";
      } else if (result.status === "refused") {
        nextStatus = "completed";
      }

      this.updateState({
        feedback: result,
        cardImage: null,
        inputValue: "",
        status: nextStatus,
      });

      return result;
    } catch (err: any) {
      if (currentSeq === this.requestSeq) {
        this.updateState({
          status: "ready",
          errorMessage: err?.detail || err?.message || "Errore durante l'invio della risposta.",
        });
      }
      return null;
    }
  }

  public async takeHint(): Promise<void> {
    if (this.state.status === "submitting") return;

    try {
      const result = await requestDailyHint(this.apiClient);
      if (result.status === "ok") {
        const tg = getTelegramWebApp();
        try {
          tg?.HapticFeedback?.notificationOccurred("warning");
        } catch {
          // Ignore
        }
        await this.loadDailyData({ lightweight: true });
      }
    } catch (err: any) {
      console.warn("Hint error:", err);
    }
  }

  public async loadResultCard(): Promise<void> {
    const f = this.state.feedback;
    const ch = this.state.challenge;
    if (this.state.cardLoading || this.state.cardImage) return;

    this.updateState({ cardLoading: true });

    try {
      const payload: DailyCardPayload = {
        attempts: f?.attempts_used ?? ch?.attempts_used ?? 1,
        max_attempts: ch?.max_attempts ?? 5,
        solved: f?.status === "correct" || !!ch?.solved,
        hints: f?.hints_used ?? ch?.hints?.used ?? 0,
        streak: this.state.user?.streak ?? 0,
      };

      const res = await fetchDailyCard(payload, this.apiClient);
      this.updateState({
        cardImage: res.image,
        cardLoading: false,
      });
    } catch {
      this.updateState({ cardLoading: false });
    }
  }

  public openShareUrl(): void {
    const url = this.state.feedback?.share?.url;
    if (!url) return;

    const tg = getTelegramWebApp();
    if (tg?.openTelegramLink) {
      tg.openTelegramLink(url);
    } else if (typeof window !== "undefined") {
      window.open(url, "_blank", "noopener");
    }
  }

  public setInputValue(val: string): void {
    this.state.inputValue = val;
  }

  public retry(): void {
    this.loadDailyData();
  }

  private applyCosmetics(worn: any): void {
    if (typeof document === "undefined") return;
    const style = document.documentElement.style;
    const theme = worn?.theme || {};

    for (const key of Object.keys(THEME_VARS)) {
      if (theme[key]) {
        style.setProperty(THEME_VARS[key], theme[key]);
      } else {
        style.removeProperty(THEME_VARS[key]);
      }
    }

    const squares = worn?.squares || {};
    this.state.squaresSymbols = {
      correct: squares.correct || DEFAULT_SQUARE_SYMBOLS.correct,
      wrong: squares.wrong || DEFAULT_SQUARE_SYMBOLS.wrong,
      unused: squares.unused || DEFAULT_SQUARE_SYMBOLS.unused,
    };
  }
}
