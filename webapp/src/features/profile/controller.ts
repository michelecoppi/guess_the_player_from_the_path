import { api, type ApiClient } from "@/api/client";
import { getTelegramWebApp } from "@/telegram/webapp";
import { applyResolvedAppearance } from "@/appearance";
import { t } from "@/i18n";
import { fetchOwnProfile, pinTrophies } from "./api";
import type {
  CabinetFilter,
  ProfileState,
  ProfileViewMode,
} from "./types";

export class ProfileController {
  private client: ApiClient;
  private state: ProfileState;
  private listeners: Set<(state: ProfileState) => void> = new Set();

  /** Stale-response guard for profile loads */
  private loadSeq = 0;
  /** Stale-response guard for trophy pin mutations */
  private pinSeq = 0;

  /** Prevents duplicate concurrent loads when one is already in flight */
  private loadInFlight: Promise<void> | null = null;

  constructor(client: ApiClient = api) {
    this.client = client;
    this.state = {
      view: "profile",
      status: "idle",
      error: null,
      profile: null,
      cabinetFilter: "all",
      pendingPinCodes: null,
      isPinning: false,
      pinError: null,
      pinSuccess: false,
    };
  }

  public getState(): ProfileState {
    return this.state;
  }

  public subscribe(listener: (state: ProfileState) => void): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  private notify(): void {
    this.listeners.forEach((l) => l(this.state));
  }

  private updateState(partial: Partial<ProfileState>): void {
    this.state = { ...this.state, ...partial };
    this.notify();
  }

  // ---------------------------------------------------------------------------
  // Profile loading
  // ---------------------------------------------------------------------------

  /**
   * Loads the authenticated user's profile.
   * Idempotent: if already ready or loading, returns existing in-flight promise.
   */
  public async init(): Promise<void> {
    if (this.state.status === "ready" || this.state.status === "loading") {
      return this.loadInFlight ?? undefined;
    }
    return this._loadProfile();
  }

  /**
   * Forces a reload of the profile.
   */
  public async refresh(): Promise<void> {
    return this._loadProfile(true);
  }

  private async _loadProfile(force = false): Promise<void> {
    if (!force && this.loadInFlight) {
      return this.loadInFlight;
    }

    const currentSeq = ++this.loadSeq;
    this.updateState({ status: "loading", error: null });

    const loadPromise = (async () => {
      try {
        const data = await fetchOwnProfile(this.client);

        if (currentSeq !== this.loadSeq) {
          return;
        }

        // Apply appearance tokens to document while respecting dark-only constraints
        if (data.cosmetics) {
          applyResolvedAppearance(data.cosmetics);
        }

        this.updateState({
          status: "ready",
          error: null,
          profile: data,
        });
      } catch (err) {
        if (currentSeq !== this.loadSeq) {
          return;
        }

        this.updateState({
          status: "error",
          error: err instanceof Error ? err.message : t("common.error"),
        });
      } finally {
        this.loadInFlight = null;
      }
    })();

    this.loadInFlight = loadPromise;
    return loadPromise;
  }

  // ---------------------------------------------------------------------------
  // Cabinet view navigation
  // ---------------------------------------------------------------------------

  public openCabinet(): void {
    this.updateState({
      view: "cabinet",
      pinError: null,
      pinSuccess: false,
    });
  }

  public closeCabinet(): void {
    this.updateState({
      view: "profile",
      pinError: null,
      pinSuccess: false,
    });
  }

  public setCabinetFilter(filter: CabinetFilter): void {
    this.updateState({ cabinetFilter: filter });
  }

  public setView(view: ProfileViewMode): void {
    this.updateState({ view, pinError: null, pinSuccess: false });
  }

  // ---------------------------------------------------------------------------
  // Trophy pinning mutation
  // ---------------------------------------------------------------------------

  /**
   * Toggles a trophy code in the user's pinned showcase.
   * Concurrency-guarded: blocks duplicate calls while a mutation is running.
   */
  public async togglePin(code: string): Promise<void> {
    if (this.state.isPinning) {
      return;
    }
    if (!this.state.profile) {
      return;
    }

    const data = this.state.profile.trophies;
    const max = data?.max || 3;
    const currentPinned = (data?.pinned || []).map((t) => t.code);
    const chosen = (this.state.pendingPinCodes ?? currentPinned).slice();
    const idx = chosen.indexOf(code);

    if (idx >= 0) {
      chosen.splice(idx, 1);
    } else {
      if (chosen.length >= max) {
        this.updateState({
          pinError: t("profile.pinFull").replace("{n}", String(max)),
          pinSuccess: false,
        });
        return;
      }
      chosen.push(code);
    }

    const currentSeq = ++this.pinSeq;
    this.updateState({
      pendingPinCodes: chosen,
      isPinning: true,
      pinError: null,
      pinSuccess: false,
    });

    try {
      const result = await pinTrophies(chosen, this.client);

      if (currentSeq !== this.pinSeq) {
        return;
      }

      if (result.status === "ok" && result.pinned) {
        const updatedTrophies = {
          ...this.state.profile.trophies,
          pinned: result.pinned,
        };

        this.updateState({
          profile: {
            ...this.state.profile,
            trophies: updatedTrophies,
          },
          pendingPinCodes: null,
          isPinning: false,
          pinSuccess: true,
          pinError: null,
        });

        const tg = getTelegramWebApp();
        tg?.HapticFeedback?.notificationOccurred?.("success");
      } else {
        let errorMsg = t("profile.errorGeneric");
        if (result.status === "too_many") {
          errorMsg = t("profile.errorTooMany").replace("{n}", String(max));
        } else if (result.status === "invalid_choice") {
          errorMsg = t("profile.errorInvalidChoice");
        } else if (result.status === "not_owned") {
          errorMsg = t("profile.errorNotOwned");
        }

        this.updateState({
          pendingPinCodes: null,
          isPinning: false,
          pinError: errorMsg,
          pinSuccess: false,
        });
      }
    } catch {
      if (currentSeq !== this.pinSeq) {
        return;
      }

      this.updateState({
        pendingPinCodes: null,
        isPinning: false,
        pinError: t("profile.errorGeneric"),
        pinSuccess: false,
      });
    }
  }
}
