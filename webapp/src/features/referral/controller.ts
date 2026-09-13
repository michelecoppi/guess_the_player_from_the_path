import { api, type ApiClient } from "@/api/client";
import {
  type ResolvedAppearance,
  applyResolvedAppearance,
} from "@/appearance";
import { getTelegramWebApp } from "@/telegram/webapp";
import { t } from "@/i18n";
import { fetchReferrals, equipReferralItem } from "./api";
import type {
  ReferralState,
  ReferralDashboardResponse,
  ReferralRewardMilestone,
} from "./types";

export type ReferralSubscriber = (state: ReferralState) => void;

export class ReferralController {
  private state: ReferralState = {
    status: "idle",
    data: null,
    loadingMore: false,
    refreshing: false,
    selectedRewardTarget: null,
    equippingItemId: null,
    toast: null,
    errorNotice: null,
  };

  private subscribers: Set<ReferralSubscriber> = new Set();
  private client: ApiClient;

  // Concurrency & sequence guards
  private loadSeq = 0;
  private moreSeq = 0;
  private equipSeq = 0;
  private inFlightLoad: Promise<ReferralDashboardResponse> | null = null;
  private inFlightMore: Promise<ReferralDashboardResponse> | null = null;
  private toastTimeout: ReturnType<typeof setTimeout> | null = null;

  /** Cross-feature coordination hook to update Profile & Daily appearances */
  public onAppearanceChanged?: (appearance: ResolvedAppearance) => void;

  constructor(client: ApiClient = api) {
    this.client = client;
  }

  public getState(): ReferralState {
    return this.state;
  }

  public subscribe(fn: ReferralSubscriber): () => void {
    this.subscribers.add(fn);
    return () => this.subscribers.delete(fn);
  }

  private notify(): void {
    const frozen = { ...this.state };
    for (const sub of this.subscribers) {
      try {
        sub(frozen);
      } catch (err) {
        console.error("[ReferralController] subscriber error:", err);
      }
    }
  }

  public setToast(message: string | null, durationMs = 2500): void {
    if (this.toastTimeout) {
      clearTimeout(this.toastTimeout);
      this.toastTimeout = null;
    }
    this.state.toast = message;
    this.notify();

    if (message) {
      this.toastTimeout = setTimeout(() => {
        this.state.toast = null;
        this.toastTimeout = null;
        this.notify();
      }, durationMs);
    }
  }

  /**
   * Initializes the referral dashboard. Deduplicates concurrent in-flight requests
   * and guards against stale out-of-order responses.
   */
  public async init(force = false): Promise<void> {
    if (!force && this.state.status === "ready" && this.state.data) {
      return;
    }

    if (this.inFlightLoad) {
      try {
        await this.inFlightLoad;
      } catch {
        // Handled by the originating call
      }
      return;
    }

    const seq = ++this.loadSeq;
    this.state.status = "loading";
    this.state.errorNotice = null;
    this.notify();

    const loadPromise = fetchReferrals(null, this.client);
    this.inFlightLoad = loadPromise;

    try {
      const res = await loadPromise;
      if (seq !== this.loadSeq) return;

      this.state.data = res;
      this.state.status = "ready";
      this.state.errorNotice = null;
      this.notify();
    } catch {
      if (seq !== this.loadSeq) return;

      this.state.status = "error";
      this.state.errorNotice = t("referral.unavailable");
      this.notify();
    } finally {
      if (seq === this.loadSeq) {
        this.inFlightLoad = null;
      }
    }
  }

  /**
   * Performs an explicit user-initiated refresh of the referral data.
   * Preserves existing rows in place with refreshing: true indicator.
   */
  public async refresh(): Promise<void> {
    if (this.state.refreshing) return;

    const seq = ++this.loadSeq;
    this.state.refreshing = true;
    this.state.errorNotice = null;
    this.notify();

    try {
      const res = await fetchReferrals(null, this.client);
      if (seq !== this.loadSeq) return;

      this.state.data = res;
      this.state.status = "ready";
      this.state.refreshing = false;
      this.state.errorNotice = null;

      // If viewing a reward preview that is no longer returned, close preview
      if (
        this.state.selectedRewardTarget !== null &&
        !res.rewards?.some((r) => r.target === this.state.selectedRewardTarget)
      ) {
        this.state.selectedRewardTarget = null;
      }

      this.notify();
    } catch {
      if (seq !== this.loadSeq) return;

      this.state.refreshing = false;
      this.setToast(t("referral.unavailable"));
      this.notify();
    }
  }

  /**
   * Loads the next page of friends using cursor pagination.
   * Appends friends without duplicating already-rendered entries.
   */
  public async loadMore(): Promise<void> {
    if (this.state.loadingMore || !this.state.data?.next_cursor) return;

    if (this.inFlightMore) {
      try {
        await this.inFlightMore;
      } catch {
        // Handled by originating call
      }
      return;
    }

    const currentCursor = this.state.data.next_cursor;
    const loadSeqSnapshot = this.loadSeq;
    const seq = ++this.moreSeq;

    this.state.loadingMore = true;
    this.notify();

    const morePromise = fetchReferrals(currentCursor, this.client);
    this.inFlightMore = morePromise;

    try {
      const res = await morePromise;
      if (seq !== this.moreSeq || loadSeqSnapshot !== this.loadSeq) return;
      if (!this.state.data) return;

      // Append new friends avoiding duplicate entries
      const existingFriends = [...this.state.data.friends];
      const existingKeys = new Set(
        existingFriends.map((f, i) => `${f.name}:${f.joined_day ?? i}`),
      );

      for (const friend of res.friends) {
        const key = `${friend.name}:${friend.joined_day ?? existingFriends.length}`;
        if (!existingKeys.has(key)) {
          existingFriends.push(friend);
          existingKeys.add(key);
        }
      }

      this.state.data = {
        ...this.state.data,
        qualified: res.qualified,
        friends: existingFriends,
        next_cursor: res.next_cursor,
        rewards: res.rewards || this.state.data.rewards,
      };
      this.state.loadingMore = false;
      this.notify();
    } catch {
      if (seq !== this.moreSeq || loadSeqSnapshot !== this.loadSeq) return;

      this.state.loadingMore = false;
      this.setToast(t("referral.unavailable"));
      this.notify();
    } finally {
      if (seq === this.moreSeq) {
        this.inFlightMore = null;
      }
    }
  }

  /**
   * Opens the detail reveal preview for a milestone reward.
   */
  public openRewardPreview(target: number): void {
    this.state.selectedRewardTarget = target;
    this.notify();
  }

  /**
   * Closes the reward reveal preview and returns to the main formation view.
   */
  public closeRewardPreview(): void {
    this.state.selectedRewardTarget = null;
    this.notify();
  }

  /**
   * Equips an earned referral cosmetic item via POST /app/api/shop/equip.
   * Sends only the catalogue item ID. Synchronizes global appearance on success.
   */
  public async equipItem(itemId: string): Promise<boolean> {
    if (this.state.equippingItemId) return false;

    // Check ownership from current authoritative data
    const item = this.findRewardItem(itemId);
    if (!item || !item.owned) {
      this.setToast(t("referral.unavailable"));
      return false;
    }

    const seq = ++this.equipSeq;
    this.state.equippingItemId = itemId;
    this.notify();

    try {
      const res = await equipReferralItem(itemId, this.client);
      if (seq !== this.equipSeq) return false;

      if (res.status !== "ok" || !res.cosmetics) {
        this.state.equippingItemId = null;
        this.setToast(t("referral.unavailable"));
        this.notify();
        return false;
      }

      // Apply authoritative appearance globally
      const resolved = applyResolvedAppearance(res.cosmetics);
      this.onAppearanceChanged?.(resolved);

      const tg = getTelegramWebApp();
      tg?.HapticFeedback?.notificationOccurred("success");

      // Silently refresh referral state to update equipped indicators
      await this.refresh();
      this.state.equippingItemId = null;
      this.notify();
      return true;
    } catch {
      if (seq !== this.equipSeq) return false;

      this.state.equippingItemId = null;
      this.setToast(t("referral.unavailable"));
      this.notify();
      return false;
    }
  }

  /**
   * Dispatches the Telegram share action with localized copy.
   */
  public shareInvite(): void {
    const link = this.state.data?.link;
    if (!link) return;

    const shareCopy = t("referral.share");
    const url = `https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent(shareCopy)}`;

    const tg = getTelegramWebApp();
    if (typeof tg?.openTelegramLink === "function") {
      tg.openTelegramLink(url);
    } else if (typeof window !== "undefined" && typeof window.open === "function") {
      window.open(url, "_blank", "noopener");
    }
  }

  /**
   * Copies the personal referral link to the system clipboard.
   * Falls back to revealing the readonly input on failure.
   */
  public async copyLink(): Promise<boolean> {
    const link = this.state.data?.link;
    if (!link) return false;

    try {
      if (
        typeof navigator !== "undefined" &&
        navigator.clipboard &&
        typeof navigator.clipboard.writeText === "function"
      ) {
        await navigator.clipboard.writeText(link);
        this.setToast(t("referral.copied"));
        return true;
      }
      throw new Error("Clipboard API not available");
    } catch {
      // Fallback: reveal details element if present in DOM
      if (typeof document !== "undefined") {
        const detailsEl = document.querySelector<HTMLDetailsElement>(".rf-link");
        if (detailsEl) {
          detailsEl.open = true;
          const input = detailsEl.querySelector<HTMLInputElement>("input");
          input?.focus();
          input?.select();
        }
      }
      return false;
    }
  }

  /**
   * Finds a reward item across all milestone reward tiers.
   */
  public findRewardItem(itemId: string) {
    if (!this.state.data?.rewards) return null;
    for (const tier of this.state.data.rewards) {
      const match = tier.items?.find((i) => i.id === itemId);
      if (match) return match;
    }
    return null;
  }

  public getSelectedMilestone(): ReferralRewardMilestone | null {
    if (this.state.selectedRewardTarget === null || !this.state.data?.rewards) {
      return null;
    }
    return (
      this.state.data.rewards.find(
        (r) => r.target === this.state.selectedRewardTarget,
      ) || null
    );
  }

  public syncAppearance(_appearance: ResolvedAppearance): void {
    // Allows external appearance changes (e.g. Shop equip) to update equipped status
    this.notify();
  }

  public reset(): void {
    this.loadSeq++;
    this.moreSeq++;
    this.equipSeq++;
    this.inFlightLoad = null;
    this.inFlightMore = null;
    if (this.toastTimeout) {
      clearTimeout(this.toastTimeout);
      this.toastTimeout = null;
    }
    this.state = {
      status: "idle",
      data: null,
      loadingMore: false,
      refreshing: false,
      selectedRewardTarget: null,
      equippingItemId: null,
      toast: null,
      errorNotice: null,
    };
  }
}
