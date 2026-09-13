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
import { applyResolvedAppearance, clearResolvedAppearance, getResolvedAppearance, appearanceSquares, appearanceGeneration, resultAppearance, DEFAULT_SQUARE_SYMBOLS, type ResolvedAppearance } from "@/appearance";
export { DEFAULT_SQUARE_SYMBOLS } from "@/appearance";

export class DailyController {
  private state: DailyState;
  private subscribers: Array<(state: DailyState) => void> = [];
  private apiClient: ApiClient;
  private requestSeq = 0;
  private loadSeq = 0;
  private appearanceSeq = 0;

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
    const loadSeq = ++this.loadSeq;
    const isLightweight = Boolean(options.lightweight && this.state.challenge);
    if (!isLightweight) {
      clearResolvedAppearance();
      this.updateState({ status: "loading", errorMessage: undefined, user: null, challenge: null, feedback: null, cardImage: null, cardLoading: false, squaresSymbols: { ...DEFAULT_SQUARE_SYMBOLS } });
    }

    const pending = fetchDailyProfile(this.apiClient, { lightweight: isLightweight });
    const sessionGen = appearanceGeneration();
    const loadAppearanceSeq = this.appearanceSeq;
    try {
      const profile = await pending;

      if (loadSeq !== this.loadSeq) return;
      if (sessionGen !== appearanceGeneration()) { this.reset(); return; }
      if (profile.language) {
        setLanguage(profile.language as any);
      }

      const hasNewerAppearance = this.appearanceSeq !== loadAppearanceSeq;
      if (!hasNewerAppearance) {
        const appearance = applyResolvedAppearance(profile.cosmetics);
        this.state.squaresSymbols = appearanceSquares(appearance);
      }

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
      if (loadSeq !== this.loadSeq) return;
      clearResolvedAppearance();
      this.state.squaresSymbols = { ...DEFAULT_SQUARE_SYMBOLS };
      this.state.user = null;
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
        const effect = resultAppearance(getResolvedAppearance()).celebration;
        if (effect) celebrate(effect);
      }

      // Reload fresh profile data
      await this.loadDailyData({ lightweight: result.status === "wrong" });
      if (currentSeq !== this.requestSeq) return null;

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
    const generation = appearanceGeneration();

    try {
      const result = await requestDailyHint(this.apiClient);
      if (generation !== appearanceGeneration()) return;
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

    const sessionGen = appearanceGeneration();
    const cardAppearanceSeq = this.appearanceSeq;
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
      if (sessionGen !== appearanceGeneration() || cardAppearanceSeq !== this.appearanceSeq) return;
      this.updateState({
        cardImage: res.image,
        cardLoading: false,
      });
    } catch {
      if (sessionGen !== appearanceGeneration() || cardAppearanceSeq !== this.appearanceSeq) return;
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

  public syncAppearance(appearance: ResolvedAppearance): void {
    this.appearanceSeq++;
    this.state.squaresSymbols = appearanceSquares(appearance);
    this.state.cardImage = null;
    this.notify();
  }

  /** Call before logout/user replacement; also invalidates pending responses. */
  public reset(): void {
    this.requestSeq++;
    this.loadSeq++;
    this.appearanceSeq++;
    clearResolvedAppearance();
    this.updateState({ status: "loading", user: null, challenge: null, feedback: null,
      cardImage: null, cardLoading: false, errorMessage: undefined, inputValue: "",
      squaresSymbols: { ...DEFAULT_SQUARE_SYMBOLS } });
  }
}
