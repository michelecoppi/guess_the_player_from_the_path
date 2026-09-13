import { api, type ApiClient } from "@/api/client";
import { getTelegramWebApp } from "@/telegram/webapp";
import {
  type ResolvedAppearance,
  getResolvedAppearance,
  applyResolvedAppearance,
} from "@/appearance";
import { fetchOwnProfile } from "@/features/profile/api";
import { t, getLanguage } from "@/i18n";
import {
  fetchShopCatalogue,
  equipShopItem,
  buyShopItem,
  mutateShopLook,
  fetchShopHistory,
} from "./api";
import {
  createPreviewAppearance,
  applyPreview,
  restoreAppearance,
} from "./preview";
import type {
  ShopState,
  ShopCosmeticItem,
  ShopSubview,
  ShopKindFilter,
  ShopPriceFilter,
  LookAction,
} from "./types";

export const SHOP_ERROR_KEYS: Record<string, string> = {
  not_owned: "shop.errNotOwned",
  already_owned: "shop.errAlreadyOwned",
  unknown_item: "shop.errUnknownItem",
  not_for_sale: "shop.errNotForSale",
  not_equippable: "shop.errNotEquippable",
  welcome_only: "shop.errWelcomeOnly",
  price_changed: "shop.errPriceChanged",
  look_limit: "shop.errLookLimit",
  invalid_name: "shop.errInvalidName",
  payment_failed: "shop.errPaymentFailed",
  invoice_unavailable: "shop.errInvoiceUnavailable",
} as const;

export function mapShopError(status?: string | null): string {
  const key = status ? SHOP_ERROR_KEYS[status] : undefined;
  return t((key || "shop.errGeneric") as any);
}

export class ShopController {
  private client: ApiClient;
  private state: ShopState;
  private subscribers: Array<(state: ShopState) => void> = [];

  /** Sequence guards for async actions */
  private catalogueSeq = 0;
  private historySeq = 0;
  private equipSeq = 0;
  private lookSeq = 0;

  /** In-flight deduplication */
  private catalogueInFlight: Promise<void> | null = null;
  private historyInFlight: Promise<void> | null = null;

  /** Cached authoritative appearance to guarantee safe preview restoration */
  private authoritativeAppearance: ResolvedAppearance | null = null;

  /** Cross-feature coordination callback (Profile, Daily, shell) */
  public onAppearanceChanged?: (appearance: ResolvedAppearance) => void;

  private toastTimeout: any = null;
  private pollIntervalMs: number;

  constructor(client: ApiClient = api, options: { pollIntervalMs?: number } = {}) {
    this.client = client;
    this.pollIntervalMs = options.pollIntervalMs ?? 900;
    this.state = {
      view: "catalog",
      status: "idle",
      catalogue: null,
      kindFilter: "all",
      priceFilter: "all",
      hideOwned: false,
      preview: null,
      buying: false,
      deliveryStatus: "idle",
      buyingItemId: null,
      equippingItemId: null,
      lookMutation: null,
      history: null,
      historyStatus: "idle",
      toast: null,
    };
  }

  public getState(): ShopState {
    return this.state;
  }

  public subscribe(subscriber: (state: ShopState) => void): () => void {
    this.subscribers.push(subscriber);
    return () => {
      this.subscribers = this.subscribers.filter((s) => s !== subscriber);
    };
  }

  private notify(): void {
    for (const sub of this.subscribers) {
      try {
        sub(this.state);
      } catch (err) {
        console.error("[ShopController] Subscriber error:", err);
      }
    }
  }

  private updateState(partial: Partial<ShopState>): void {
    this.state = { ...this.state, ...partial };
    this.notify();
  }

  public setToast(message: string, durationMs = 3000): void {
    if (this.toastTimeout) {
      clearTimeout(this.toastTimeout);
    }
    this.updateState({ toast: message });
    this.toastTimeout = setTimeout(() => {
      this.updateState({ toast: null });
    }, durationMs);
  }

  // ---------------------------------------------------------------------------
  // Catalogue loading
  // ---------------------------------------------------------------------------

  public async init(): Promise<void> {
    if (this.state.status === "ready" || this.state.status === "loading") {
      return this.catalogueInFlight ?? undefined;
    }
    return this._loadCatalogue();
  }

  public async refresh(): Promise<void> {
    return this._loadCatalogue(true);
  }

  private async _loadCatalogue(force = false): Promise<void> {
    if (!force && this.catalogueInFlight) {
      return this.catalogueInFlight;
    }

    const seq = ++this.catalogueSeq;
    this.updateState({ status: "loading", errorMessage: undefined });

    let promise: Promise<void> | null = null;
    promise = (async () => {
      try {
        const catalogue = await fetchShopCatalogue(this.client);
        if (seq !== this.catalogueSeq) return;

        this.authoritativeAppearance = getResolvedAppearance();

        this.updateState({
          status: "ready",
          catalogue,
          errorMessage: undefined,
        });
      } catch (err: any) {
        if (seq !== this.catalogueSeq) return;
        this.updateState({
          status: "error",
          errorMessage: err?.message || t("shop.loadError"),
        });
      } finally {
        if (this.catalogueInFlight === promise) {
          this.catalogueInFlight = null;
        }
      }
    })();

    this.catalogueInFlight = promise;
    return promise;
  }

  // ---------------------------------------------------------------------------
  // Navigation & Filters
  // ---------------------------------------------------------------------------

  public setView(view: ShopSubview): void {
    if (this.state.view === view) return;
    this.state.view = view;
    this.state.kindFilter = "all";
    this.state.priceFilter = "all";

    if (view === "history" && this.state.historyStatus === "idle") {
      void this.loadHistory();
    }

    this.notify();
  }

  public setKindFilter(kind: ShopKindFilter): void {
    this.updateState({ kindFilter: kind });
  }

  public setPriceFilter(price: ShopPriceFilter): void {
    this.updateState({ priceFilter: price });
  }

  public setHideOwned(hide: boolean): void {
    this.updateState({ hideOwned: hide });
  }

  // ---------------------------------------------------------------------------
  // Temporary preview
  // ---------------------------------------------------------------------------

  public allItems(): ShopCosmeticItem[] {
    const cat = this.state.catalogue;
    if (!cat) return [];
    return cat.bundles.concat(
      ...cat.sections.map((s) => s.items),
      ...cat.bundles.map((b) => b.contents || []),
    );
  }

  public startPreview(itemId: string): void {
    const item = this.allItems().find((one) => one.id === itemId);
    if (!item) return;

    if (!this.authoritativeAppearance) {
      this.authoritativeAppearance = getResolvedAppearance();
    }

    const previewAppearance = createPreviewAppearance(
      this.authoritativeAppearance,
      item,
      getLanguage(),
    );

    applyPreview(previewAppearance);
    this.updateState({
      preview: {
        item,
        appearance: previewAppearance,
      },
    });
  }

  public stopPreview(): void {
    if (!this.state.preview) return;
    if (this.authoritativeAppearance) {
      restoreAppearance(this.authoritativeAppearance);
    }
    this.updateState({ preview: null });
  }

  // ---------------------------------------------------------------------------
  // Equip
  // ---------------------------------------------------------------------------

  public async equip(itemId: string): Promise<boolean> {
    if (this.state.equippingItemId) return false;

    const seq = ++this.equipSeq;
    this.updateState({ equippingItemId: itemId });

    try {
      const res = await equipShopItem(itemId, this.client);
      if (seq !== this.equipSeq) return false;

      if (res.status !== "ok") {
        this.updateState({ equippingItemId: null });
        this.setToast(mapShopError(res.status));
        return false;
      }

      // Stop temporary preview if active
      this.state.preview = null;

      // Authoritative appearance returned by backend
      const resolved = applyResolvedAppearance(res.cosmetics);
      this.authoritativeAppearance = resolved;

      // Notify cross-feature coordination hook
      this.onAppearanceChanged?.(resolved);

      const tg = getTelegramWebApp();
      tg?.HapticFeedback?.notificationOccurred("success");

      // Reconcile catalogue to sync equipped indicators
      await this._loadCatalogue(true);
      this.updateState({ equippingItemId: null });
      return true;
    } catch {
      if (seq !== this.equipSeq) return false;
      this.updateState({ equippingItemId: null });
      this.setToast(t("shop.errGeneric"));
      return false;
    }
  }

  // ---------------------------------------------------------------------------
  // Saved Looks
  // ---------------------------------------------------------------------------

  public async lookAction(action: LookAction, name: string): Promise<boolean> {
    if (this.state.lookMutation) return false;

    const trimmed = (name || "").trim();
    if (action === "save" && (!trimmed || trimmed.length > 30)) {
      this.setToast(t("shop.errInvalidName"));
      return false;
    }

    const seq = ++this.lookSeq;
    this.updateState({ lookMutation: action });

    try {
      const res = await mutateShopLook(action, trimmed, this.client);
      if (seq !== this.lookSeq) return false;

      if (res.status !== "ok") {
        this.updateState({ lookMutation: null });
        this.setToast(mapShopError(res.status));
        return false;
      }

      if (action === "wear") {
        // Stop temporary preview
        this.state.preview = null;
        // Fetch fresh authoritative cosmetics from profile /me
        const profile = await fetchOwnProfile(this.client);
        if (profile.cosmetics) {
          const resolved = applyResolvedAppearance(profile.cosmetics);
          this.authoritativeAppearance = resolved;
          this.onAppearanceChanged?.(resolved);
        }
      }

      await this._loadCatalogue(true);

      if (action === "save") {
        this.setToast(t("shop.lookSaved"));
      }

      this.updateState({ lookMutation: null });
      return true;
    } catch {
      if (seq !== this.lookSeq) return false;
      this.updateState({ lookMutation: null });
      this.setToast(t("shop.errGeneric"));
      return false;
    }
  }

  // ---------------------------------------------------------------------------
  // Buy with Telegram Stars
  // ---------------------------------------------------------------------------

  public isItemOwned(itemId: string): boolean {
    const cat = this.state.catalogue;
    if (!cat) return false;
    if (cat.owned && cat.owned.includes(itemId)) return true;
    const all = this.allItems();
    const found = all.find((item) => item.id === itemId);
    return Boolean(found && found.owned);
  }

  public async buy(itemId: string): Promise<void> {
    if (this.state.buying || this.isItemOwned(itemId)) return;

    this.updateState({ buying: true, buyingItemId: itemId });

    try {
      const res = await buyShopItem(itemId, this.client);

      if (res.status !== "ok" || !res.link) {
        this.updateState({ buying: false, buyingItemId: null });
        this.setToast(mapShopError(res.status));
        await this._loadCatalogue(true);
        return;
      }

      const tg = getTelegramWebApp();
      if (!tg || typeof tg.openInvoice !== "function") {
        this.updateState({ buying: false, buyingItemId: null });
        this.setToast(mapShopError("invoice_unavailable"));
        return;
      }

      tg.openInvoice(res.link, async (invoiceStatus: string) => {
        this.updateState({ buying: false, buyingItemId: null });

        if (invoiceStatus !== "paid") {
          if (invoiceStatus === "failed") {
            this.setToast(mapShopError("payment_failed"));
          }
          return;
        }

        tg.HapticFeedback?.notificationOccurred("success");
        this.updateState({ deliveryStatus: "delivering" });
        this.setToast(t("shop.waitingDelivery"));

        // Bounded delivery reconciliation (up to 5 attempts, ~900ms delay)
        let delivered = false;
        for (let attempt = 0; attempt < 5; attempt++) {
          await new Promise((r) => setTimeout(r, this.pollIntervalMs));
          await this._loadCatalogue(true);
          if (this.isItemOwned(itemId)) {
            delivered = true;
            break;
          }
        }

        if (delivered) {
          this.updateState({ deliveryStatus: "delivered" });
          this.setToast(t("shop.thanks"));
        } else {
          this.updateState({ deliveryStatus: "pending" });
          this.setToast(t("shop.deliveryPending"));
        }
      });
    } catch {
      this.updateState({ buying: false, buyingItemId: null });
      this.setToast(t("shop.errGeneric"));
    }
  }

  // ---------------------------------------------------------------------------
  // Purchase History
  // ---------------------------------------------------------------------------

  public async loadHistory(): Promise<void> {
    if (this.historyInFlight) return this.historyInFlight;

    const seq = ++this.historySeq;
    this.updateState({ historyStatus: "loading", historyError: undefined });

    let promise: Promise<void> | null = null;
    promise = (async () => {
      try {
        const history = await fetchShopHistory(this.client);
        if (seq !== this.historySeq) return;

        this.updateState({
          history,
          historyStatus: "ready",
          historyError: undefined,
        });
      } catch (err: any) {
        if (seq !== this.historySeq) return;
        this.updateState({
          historyStatus: "error",
          historyError: err?.message || t("shop.loadError"),
        });
      } finally {
        if (this.historyInFlight === promise) {
          this.historyInFlight = null;
        }
      }
    })();

    this.historyInFlight = promise;
    return promise;
  }
}
