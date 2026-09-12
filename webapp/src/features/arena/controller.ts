import { ApiClient, api } from "@/api/client";
import { getTelegramWebApp, getTelegramUser } from "@/telegram/webapp";
import { t } from "@/i18n";
import {
  fetchDuelList,
  fetchDuel,
  createDuel,
  joinDuel,
  guessDuel,
  revealDuel,
  deleteDuel,
  searchProfiles,
} from "./api";
import type {
  ArenaState,
  ArenaSubview,
  DuelData,
  OpponentProfile,
} from "./types";

export const DUEL_CODE_REGEX = /^[a-f0-9]{24}$/;
const RESYNC_ERRORS = ["stale", "finished"];

export class ArenaController {
  private state: ArenaState;
  private subscribers: Array<(state: ArenaState) => void> = [];
  private apiClient: ApiClient;
  private searchTimer: ReturnType<typeof setTimeout> | null = null;
  private searchSeq = 0;

  constructor(apiClient: ApiClient = api) {
    this.apiClient = apiClient;
    this.state = {
      subview: "hub",
      status: "idle",
      busy: false,
      error: null,
      notice: null,
      confirming: null,
      data: null,
      activeDuelCode: null,
      invitationCode: null,
      searchQuery: "",
      searchResults: [],
      searchError: null,
      draftAnswer: "",
    };
  }

  public getState(): ArenaState {
    return this.state;
  }

  public subscribe(subscriber: (state: ArenaState) => void): () => void {
    this.subscribers.push(subscriber);
    return () => {
      this.subscribers = this.subscribers.filter((s) => s !== subscriber);
    };
  }

  private updateState(partial: Partial<ArenaState>): void {
    this.state = { ...this.state, ...partial };
    this.notify();
  }

  private notify(): void {
    for (const subscriber of this.subscribers) {
      try {
        subscriber(this.state);
      } catch (err) {
        console.error("Error in ArenaController subscriber:", err);
      }
    }
  }

  /**
   * Initializes Arena state: inspects deep-links (?duel= or start_param: duel_)
   * or loads the open duels list.
   */
  public async init(): Promise<void> {
    const inviteCode = this.detectInvitationCode();
    if (inviteCode) {
      this.updateState({
        subview: "invitation",
        invitationCode: inviteCode,
        status: "idle",
        busy: false,
        error: null,
      });
      return;
    }

    await this.loadDuelList();
  }

  public detectInvitationCode(): string | null {
    if (typeof window !== "undefined" && window.location?.search) {
      const param = new URLSearchParams(window.location.search).get("duel");
      if (param && DUEL_CODE_REGEX.test(param)) {
        return param;
      }
    }

    const tg = getTelegramWebApp();
    const startParam = tg?.initDataUnsafe?.start_param || "";
    const cleanParam = startParam.replace(/^duel_/, "");
    if (cleanParam && DUEL_CODE_REGEX.test(cleanParam)) {
      return cleanParam;
    }

    return null;
  }

  public setSubview(subview: ArenaSubview, code?: string): void {
    this.updateState({
      subview,
      error: null,
      notice: null,
      confirming: null,
      searchQuery: "",
      searchResults: [],
      searchError: null,
      draftAnswer: "",
    });

    if (subview === "hub") {
      void this.loadDuelList();
    } else if (subview === "duel" && code) {
      void this.loadDuel(code);
    } else if (subview === "invitation" && code) {
      this.updateState({ invitationCode: code });
    }
  }

  public setDraftAnswer(value: string): void {
    this.updateState({ draftAnswer: value });
  }

  public clearNotice(): void {
    this.updateState({ notice: null });
  }

  public clearError(): void {
    this.updateState({ error: null });
  }

  public cancelConfirming(): void {
    this.updateState({ confirming: null });
  }

  /**
   * Loads open duels list and player duel ledger.
   */
  public async loadDuelList(): Promise<void> {
    this.updateState({ busy: true, status: "loading", error: null });
    try {
      const data = await fetchDuelList(this.apiClient);
      const isHub = this.state.subview === "hub";
      this.updateState({
        busy: false,
        status: "idle",
        data,
        ...(isHub ? { subview: "hub" } : {}),
      });
    } catch (err: any) {
      const errorKey = err?.detail || "loadError";
      this.updateState({
        busy: false,
        status: "error",
        error: errorKey,
      });
    }
  }

  /**
   * Loads a specific duel by code.
   */
  public async loadDuel(code: string): Promise<void> {
    if (!DUEL_CODE_REGEX.test(code)) {
      this.updateState({ error: "invalid", status: "error" });
      return;
    }

    this.updateState({
      busy: true,
      status: "loading",
      error: null,
      activeDuelCode: code,
      subview: "duel",
    });

    try {
      const data = await fetchDuel(code, this.apiClient);
      this.updateState({
        busy: false,
        status: "idle",
        data,
        activeDuelCode: code,
      });
    } catch (err: any) {
      const errorKey = err?.detail || "loadError";
      this.updateState({
        busy: false,
        status: "error",
        error: errorKey,
      });
    }
  }

  /**
   * Creates a new duel, automatically setting it active in the duel subview.
   */
  public async createNewDuel(): Promise<DuelData | null> {
    this.updateState({ busy: true, status: "loading", error: null });
    try {
      const data = await createDuel(this.apiClient);
      this.updateState({
        busy: false,
        status: "idle",
        data,
        activeDuelCode: data.code || null,
        subview: "duel",
      });
      return data;
    } catch (err: any) {
      const errorKey = err?.detail || "loadError";
      this.updateState({
        busy: false,
        status: "error",
        error: errorKey,
      });
      return null;
    }
  }

  /**
   * Accepts an invitation and joins the duel.
   */
  public async acceptInvitation(code?: string): Promise<void> {
    const duelCode = code || this.state.invitationCode;
    if (!duelCode || !DUEL_CODE_REGEX.test(duelCode)) {
      this.updateState({ error: "invalid", status: "error" });
      return;
    }

    this.updateState({ busy: true, status: "loading", error: null });
    try {
      const data = await joinDuel(duelCode, this.apiClient);
      this.updateState({
        busy: false,
        status: "idle",
        data,
        activeDuelCode: duelCode,
        invitationCode: null,
        subview: "duel",
      });
    } catch (err: any) {
      const errorKey = err?.detail || "loadError";
      this.updateState({
        busy: false,
        status: "error",
        error: errorKey,
      });
    }
  }

  /**
   * Submits a guess in the active duel.
   */
  public async submitGuess(answer: string): Promise<void> {
    const code = this.state.activeDuelCode || this.state.data?.code;
    const session = this.state.data?.session;
    const trimmed = answer.trim();

    if (this.state.busy) return;
    if (!code || !session) return;
    if (!trimmed) {
      this.updateState({ error: "invalid_answer" });
      return;
    }

    const revision = session.revision;
    this.updateState({
      busy: true,
      status: "submitting",
      error: null,
      notice: null,
      confirming: null,
    });

    try {
      const data = await guessDuel(code, trimmed, revision, this.apiClient);
      this.triggerHaptic(
        data.feedback?.status === "correct" ? "success" : "error",
      );
      this.updateState({
        busy: false,
        status: "idle",
        data,
        draftAnswer: "",
      });
    } catch (err: any) {
      const errorKey = err?.detail || "loadError";
      this.updateState({
        busy: false,
        status: "error",
        error: errorKey,
      });

      // If state is stale or game finished, automatically resync
      if (RESYNC_ERRORS.includes(errorKey)) {
        await this.resync(code);
      }
    }
  }

  /**
   * Skips the current round (2-step confirmation: costs 3 attempts).
   */
  public async skipRound(): Promise<void> {
    const code = this.state.activeDuelCode || this.state.data?.code;
    const session = this.state.data?.session;

    if (this.state.busy || !code || !session) return;

    if (this.state.confirming !== "skip") {
      this.updateState({ confirming: "skip" });
      return;
    }

    this.updateState({
      confirming: null,
      busy: true,
      status: "submitting",
      error: null,
      notice: null,
    });

    try {
      const data = await revealDuel(code, session.revision, this.apiClient);
      this.updateState({
        busy: false,
        status: "idle",
        data,
        draftAnswer: "",
      });
    } catch (err: any) {
      const errorKey = err?.detail || "loadError";
      this.updateState({
        busy: false,
        status: "error",
        error: errorKey,
      });

      if (RESYNC_ERRORS.includes(errorKey)) {
        await this.resync(code);
      }
    }
  }

  /**
   * Deletes an unjoined duel (2-step confirmation).
   */
  public async deleteDuel(code: string): Promise<void> {
    if (this.state.busy) return;

    const confirmKey = `delete:${code}`;
    if (this.state.confirming !== confirmKey) {
      this.updateState({ confirming: confirmKey });
      return;
    }

    this.updateState({
      confirming: null,
      busy: true,
      status: "loading",
      error: null,
      notice: null,
    });

    try {
      await deleteDuel(code, this.apiClient);
      // After deletion, refresh open duels list
      const listData = await fetchDuelList(this.apiClient);
      this.updateState({
        busy: false,
        status: "idle",
        data: listData,
        notice: t("arena.duelDeleted"),
      });
    } catch (err: any) {
      const errorKey = err?.detail || "loadError";
      this.updateState({
        busy: false,
        status: "error",
        error: errorKey,
      });
    }
  }

  /**
   * Debounced search for player profiles (300ms, min 2 chars).
   */
  public searchOpponents(query: string): void {
    this.updateState({ searchQuery: query });

    if (this.searchTimer) {
      clearTimeout(this.searchTimer);
      this.searchTimer = null;
    }

    const trimmed = query.trim();
    if (trimmed.length < 2) {
      this.updateState({
        searchResults: [],
        searchError: null,
        status: "idle",
      });
      return;
    }

    const seq = ++this.searchSeq;
    this.updateState({ status: "searching", searchError: null });

    this.searchTimer = setTimeout(async () => {
      try {
        const response = await searchProfiles(trimmed, this.apiClient);
        if (seq !== this.searchSeq) return;

        const currentUserId = getTelegramUser()?.id;
        const filtered = (response.profiles || []).filter(
          (p: OpponentProfile) => p.profile_id !== currentUserId,
        );

        this.updateState({
          searchResults: filtered,
          status: "idle",
          searchError: null,
        });
      } catch (err: any) {
        if (seq !== this.searchSeq) return;
        this.updateState({
          status: "idle",
          searchError: err?.detail || t("arena.loadError"),
        });
      }
    }, 300);
  }

  /**
   * Shares the duel invite link via Telegram WebApp share URL.
   */
  public shareInvite(url?: string): void {
    const inviteUrl = url || this.state.data?.invite_url;
    if (!inviteUrl) return;

    const text = t("arena.inviteText");
    const shareUrl = `https://t.me/share/url?url=${encodeURIComponent(inviteUrl)}&text=${encodeURIComponent(text)}`;

    const tg = getTelegramWebApp();
    if (tg && typeof tg.openTelegramLink === "function") {
      tg.openTelegramLink(shareUrl);
    } else if (typeof window !== "undefined" && typeof window.open === "function") {
      window.open(shareUrl, "_blank", "noopener");
    }
  }

  /**
   * Copies the duel invite link to the clipboard.
   */
  public async copyInvite(url?: string): Promise<boolean> {
    const inviteUrl = url || this.state.data?.invite_url;
    if (!inviteUrl) return false;

    try {
      if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(inviteUrl);
        this.updateState({ notice: t("arena.copied") });
        return true;
      }
      throw new Error("Clipboard API unavailable");
    } catch {
      this.updateState({ notice: t("arena.copyError") });
      return false;
    }
  }

  /**
   * Triggers haptic feedback via Telegram WebApp if available.
   */
  private triggerHaptic(type: "success" | "error"): void {
    try {
      const tg = getTelegramWebApp();
      tg?.HapticFeedback?.notificationOccurred(type);
    } catch {
      // Ignored outside native Telegram
    }
  }

  /**
   * Internal resync on stale/finished server states.
   */
  private async resync(code: string): Promise<void> {
    try {
      const fresh = await fetchDuel(code, this.apiClient);
      this.updateState({
        data: fresh,
        error: null,
        notice: t("arena.synced"),
      });
    } catch {
      // Keep original error state
    }
  }
}
