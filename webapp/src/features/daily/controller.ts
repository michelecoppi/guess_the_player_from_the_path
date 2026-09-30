import { ApiClient, ApiError, api } from "@/api/client";
import { getTelegramUser, getTelegramWebApp } from "@/telegram/webapp";
import { setLanguage, t } from "@/i18n";
import {
  fetchDailyProfile,
  submitDailyGuess,
  requestDailyHint,
  fetchDailyCard,
  prepareDailyShare,
  reportDailyShared,
} from "./api";
import { celebrate } from "./celebrate";
import type { DailyState, DailyGuessResult } from "./types";
import type { TelegramWebApp } from "@/telegram/types";
import { applyResolvedAppearance, clearResolvedAppearance, getResolvedAppearance, appearanceSquares, appearanceGeneration, resultAppearance, DEFAULT_SQUARE_SYMBOLS, type ResolvedAppearance } from "@/appearance";
export { DEFAULT_SQUARE_SYMBOLS } from "@/appearance";

/** Length of the sticker flip that reveals the name (keep in sync with `.reveal-card`). */
export const REVEAL_FLIP_MS = 900;

export class DailyController {
  private state: DailyState;
  private subscribers: Array<(state: DailyState) => void> = [];
  private apiClient: ApiClient;
  private requestSeq = 0;
  private loadSeq = 0;
  private appearanceSeq = 0;
  private introDismissed = false;
  /** The message prepared for WebApp.shareMessage (#185); null until ready or when stale. */
  private preparedShare: { id: string; expiresAt: number | null; appearanceSeq: number } | null = null;
  private preparingShare = false;

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
      introVisible: false,
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
    await this.loadDailyData({ lightweight: true });
  }

  public async loadDailyData(options: { lightweight?: boolean } = {}): Promise<void> {
    const loadSeq = ++this.loadSeq;
    const isLightweight = Boolean(options.lightweight);
    const previousState = this.state;
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
      const dayChanged = Boolean(previousState.challenge?.day && today?.day &&
        previousState.challenge.day !== today.day);
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

      if (dayChanged) this.preparedShare = null;
      this.updateState({
        user: profile.user || null,
        challenge: today,
        status: nextStatus,
        errorMessage: undefined,
        introVisible: this.shouldShowIntro(profile.user?.players_guessed, today?.attempts_used),
        ...(dayChanged ? { feedback: null, cardImage: null, copyNotice: null, inputValue: "" } : {}),
      });
    } catch (err: any) {
      if (loadSeq !== this.loadSeq) return;
      // A Shop mutation may have synchronized a newer appearance while this
      // same-user request was in flight.  Its failure must not undo that
      // authoritative appearance or discard an already usable challenge.
      if (sessionGen !== appearanceGeneration()) { this.reset(); return; }
      if (this.appearanceSeq !== loadAppearanceSeq) {
        this.updateState({
          status: previousState.status,
          user: previousState.user,
          challenge: previousState.challenge,
          feedback: previousState.feedback,
          cardImage: null,
          cardLoading: false,
          errorMessage: err?.detail || err?.message || "Impossibile caricare la sfida quotidiana.",
        });
        return;
      }
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
    this.dismissIntro();

    const currentSeq = ++this.requestSeq;
    this.updateState({ status: "submitting", errorMessage: undefined });

    try {
      const result = await submitDailyGuess(answer, this.state.challenge?.day, this.apiClient);

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

      const revealing = Boolean(result.answer) &&
        (result.status === "correct" || (result.status === "wrong" && (result.attempts_left ?? 0) <= 0));
      if (result.status === "correct") {
        const effect = resultAppearance(getResolvedAppearance()).celebration;
        // With the sticker flip the celebration waits for the name to be on show.
        if (effect) setTimeout(() => celebrate(effect), revealing ? REVEAL_FLIP_MS : 0);
      }

      if (result.status === "wrong" && result.today && result.today.day === this.state.challenge?.day) {
        // After a wrong answer only attempts and hints change, and the server already sent
        // them (#259): no second round trip for the same Daily.
        this.updateState({ challenge: result.today });
      } else {
        // Reload fresh profile data
        await this.loadDailyData({ lightweight: result.status === "wrong" });
      }
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
        copyNotice: null,
        inputValue: "",
        status: nextStatus,
        revealPending: revealing,
      });
      // A new result: whatever was prepared before shows something else.
      this.preparedShare = null;
      if (result.share) {
        void this.prepareNativeShare();
        // The final report previews the card (#254): only right after the game, so reopening
        // the app later does not render a PNG every time.
        void this.loadResultCard();
      }

      return result;
    } catch (err: any) {
      if (currentSeq === this.requestSeq) {
        if (err instanceof ApiError && err.status === 409 && err.detail === "daily_changed") {
          await this.loadDailyData({ lightweight: true });
          this.updateState({ errorMessage: t("daily.dayChanged") });
          return null;
        }
        this.updateState({
          status: "ready",
          errorMessage: err instanceof ApiError && err.isFeatureDisabled
            ? t("common.featureDisabled")
            : err?.detail || err?.message || "Errore durante l'invio della risposta.",
        });
      }
      return null;
    }
  }

  public async takeHint(): Promise<void> {
    if (this.state.status === "submitting") return;
    const generation = appearanceGeneration();

    try {
      const result = await requestDailyHint(this.state.challenge?.day, this.apiClient);
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
      if (err instanceof ApiError && err.status === 409 && err.detail === "daily_changed") {
        await this.loadDailyData({ lightweight: true });
        this.updateState({ errorMessage: t("daily.dayChanged") });
        return;
      }
      if (err instanceof ApiError && err.isFeatureDisabled) {
        this.updateState({ errorMessage: t("common.featureDisabled") });
        return;
      }
      console.warn("Hint error:", err);
    }
  }

  public async loadResultCard(): Promise<void> {
    if (this.state.cardLoading || this.state.cardImage) return;

    const sessionGen = appearanceGeneration();
    const cardAppearanceSeq = this.appearanceSeq;
    this.updateState({ cardLoading: true });

    try {
      const res = await fetchDailyCard(this.apiClient);
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

  /**
   * Prepares today's result for Telegram's native share (#185) as soon as the game ends, so
   * the tap on "Share" opens it immediately, still inside the user's gesture. Silent on
   * failure: without a prepared message the classic share link is used.
   */
  public async prepareNativeShare(): Promise<void> {
    if (this.preparingShare || !supportsShareMessage(getTelegramWebApp())) return;
    const seq = this.appearanceSeq;
    this.preparingShare = true;
    try {
      const prepared = await prepareDailyShare(this.state.challenge?.day, this.apiClient);
      if (seq === this.appearanceSeq) {
        this.preparedShare = { id: prepared.id, expiresAt: prepared.expires_at, appearanceSeq: seq };
      }
    } catch {
      // 503 (no storage chat, Telegram throttling) or network: keep the classic share.
    } finally {
      this.preparingShare = false;
    }
  }

  /**
   * The "Share" button: Telegram's native share of the prepared card when it is ready and
   * still valid, otherwise the classic share link (and a fresh preparation for next time).
   */
  public shareResult(): void {
    if (!this.state.feedback?.share) return;
    const tg = getTelegramWebApp();
    const prepared = this.preparedShare;
    const fresh =
      prepared !== null &&
      prepared.appearanceSeq === this.appearanceSeq &&
      (prepared.expiresAt === null || prepared.expiresAt * 1000 > Date.now() + 10_000);
    if (tg && fresh && supportsShareMessage(tg)) {
      try {
        tg.shareMessage!(prepared.id, (sent) => {
          if (sent) void reportDailyShared(this.apiClient).catch(() => undefined);
        });
        return;
      } catch {
        this.preparedShare = null;
      }
    }
    this.openShareUrl();
    if (!fresh) void this.prepareNativeShare();
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

  /**
   * Copies the shared text to the clipboard (#150): the Telegram share sheet only reaches
   * Telegram chats, this is how the result gets to WhatsApp, Instagram or X.
   */
  public async copyShareText(): Promise<boolean> {
    const text = this.state.feedback?.share?.text;
    if (!text) return false;
    try {
      if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
        this.updateState({ copyNotice: t("daily.copied") });
        return true;
      }
      throw new Error("Clipboard API unavailable");
    } catch {
      this.updateState({ copyNotice: t("daily.copyError") });
      return false;
    }
  }

  /**
   * The page drew the reveal: later renders (card, copy notice) show the name already
   * turned instead of flipping it again. Haptics land when the sticker shows its face.
   */
  public consumeReveal(): void {
    if (!this.state.revealPending) return;
    this.state.revealPending = false;
    setTimeout(() => {
      try {
        getTelegramWebApp()?.HapticFeedback?.impactOccurred("heavy");
      } catch {
        // Haptic feedback is non-critical
      }
    }, REVEAL_FLIP_MS / 2);
  }

  public setInputValue(val: string): void {
    this.state.inputValue = val;
  }

  private introStorageKey(): string | null {
    const id = getTelegramUser()?.id;
    return typeof id === "number" ? `gtp-daily-intro-v1:${id}` : null;
  }

  private shouldShowIntro(playersGuessed?: number, attemptsUsed?: number): boolean {
    if (playersGuessed !== 0 || (attemptsUsed ?? 0) > 0 || this.introDismissed) return false;
    const key = this.introStorageKey();
    if (!key) return false;
    try {
      return window.localStorage.getItem(key) !== "seen";
    } catch {
      return true;
    }
  }

  public dismissIntro(): void {
    if (!this.state.introVisible) return;
    this.introDismissed = true;
    const key = this.introStorageKey();
    try {
      if (key) window.localStorage.setItem(key, "seen");
    } catch {
      // The guide can still be dismissed when browser storage is unavailable.
    }
    this.updateState({ introVisible: false });
  }

  public retry(): void {
    this.loadDailyData();
  }

  public syncAppearance(appearance: ResolvedAppearance): void {
    this.appearanceSeq++;
    this.state.squaresSymbols = appearanceSquares(appearance);
    this.state.cardImage = null;
    // The prepared card shows the old look: prepare it again.
    this.preparedShare = null;
    this.notify();
    if (this.state.feedback?.share) void this.prepareNativeShare();
  }

  /** Call before logout/user replacement; also invalidates pending responses. */
  public reset(): void {
    this.requestSeq++;
    this.loadSeq++;
    this.appearanceSeq++;
    this.preparedShare = null;
    clearResolvedAppearance();
    this.introDismissed = false;
    this.updateState({ status: "loading", user: null, challenge: null, feedback: null,
      cardImage: null, cardLoading: false, errorMessage: undefined, inputValue: "",
      introVisible: false, squaresSymbols: { ...DEFAULT_SQUARE_SYMBOLS } });
  }
}

/** Bot API 8.0+ clients expose shareMessage; older ones keep the classic share link. */
function supportsShareMessage(tg: TelegramWebApp | null): tg is TelegramWebApp {
  if (!tg || typeof tg.shareMessage !== "function") return false;
  return typeof tg.isVersionAtLeast !== "function" || tg.isVersionAtLeast("8.0");
}
