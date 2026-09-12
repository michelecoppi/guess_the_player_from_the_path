import { api, ApiClient } from "@/api/client";
import { fetchSocialData, fetchPublicProfile } from "./api";
import type {
  LeaderboardState,
  LeaderboardTab,
} from "./types";

export class LeaderboardController {
  private client: ApiClient;
  private state: LeaderboardState;
  private listeners: Set<(state: LeaderboardState) => void> = new Set();
  private loadInFlight: Promise<void> | null = null;
  private requestSeq = 0;
  private publicSeq = 0;

  constructor(client: ApiClient = api) {
    this.client = client;
    this.state = {
      status: "idle",
      error: null,
      activeTab: "global",
      selectedLeagueCode: null,
      globalLeaderboard: [],
      leagues: [],
      publicProfile: null,
    };
  }

  public getState(): LeaderboardState {
    return this.state;
  }

  public subscribe(listener: (state: LeaderboardState) => void): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  private notify(): void {
    this.listeners.forEach((listener) => listener(this.state));
  }

  private updateState(partial: Partial<LeaderboardState>): void {
    this.state = { ...this.state, ...partial };
    this.notify();
  }

  public async init(): Promise<void> {
    if (this.state.status === "ready") {
      return;
    }
    return this.load();
  }

  public async load(force = false): Promise<void> {
    if (!force && this.state.status === "ready") {
      return;
    }
    if (this.loadInFlight && !force) {
      return this.loadInFlight;
    }

    const currentSeq = ++this.requestSeq;
    this.updateState({ status: "loading", error: null });

    this.loadInFlight = (async () => {
      try {
        const social = await fetchSocialData(this.client);
        if (currentSeq !== this.requestSeq) {
          return;
        }
        const selectedLeagueCode = this.state.selectedLeagueCode
          ? (social.leagues.some((l) => l.code === this.state.selectedLeagueCode)
              ? this.state.selectedLeagueCode
              : social.leagues[0]?.code || null)
          : social.leagues[0]?.code || null;

        this.updateState({
          status: "ready",
          error: null,
          globalLeaderboard: social.leaderboard,
          leagues: social.leagues,
          selectedLeagueCode,
        });
      } catch (err: any) {
        if (currentSeq !== this.requestSeq) {
          return;
        }
        const errorMsg = err?.detail || err?.message || "loadError";
        this.updateState({
          status: "error",
          error: String(errorMsg),
        });
      } finally {
        this.loadInFlight = null;
      }
    })();

    return this.loadInFlight;
  }

  public setTab(tab: LeaderboardTab): void {
    if (this.state.activeTab !== tab || this.state.publicProfile) {
      this.updateState({
        activeTab: tab,
        publicProfile: null,
      });
    }
  }

  public selectLeague(code: string): void {
    if (this.state.selectedLeagueCode !== code) {
      this.updateState({
        selectedLeagueCode: code,
      });
    }
  }

  public async openPublicProfile(profileId: number): Promise<void> {
    if (!Number.isSafeInteger(profileId) || profileId <= 0) {
      return;
    }

    const currentPublicSeq = ++this.publicSeq;
    this.updateState({
      publicProfile: {
        profileId,
        status: "loading",
        data: null,
        error: null,
      },
    });

    try {
      const data = await fetchPublicProfile(profileId, this.client);
      if (currentPublicSeq !== this.publicSeq) {
        return;
      }
      this.updateState({
        publicProfile: {
          profileId,
          status: "ready",
          data,
          error: null,
        },
      });
    } catch (err: any) {
      if (currentPublicSeq !== this.publicSeq) {
        return;
      }
      this.updateState({
        publicProfile: {
          profileId,
          status: "error",
          data: null,
          error: err?.detail || "unavailable",
        },
      });
    }
  }

  public closePublicProfile(): void {
    ++this.publicSeq;
    this.updateState({ publicProfile: null });
  }

  public async retryPublicProfile(): Promise<void> {
    const profileId = this.state.publicProfile?.profileId;
    if (profileId) {
      return this.openPublicProfile(profileId);
    }
  }

  public async refresh(): Promise<void> {
    return this.load(true);
  }
}
