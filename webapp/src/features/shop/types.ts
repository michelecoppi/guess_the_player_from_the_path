import type { CosmeticSlot, ResolvedAppearance } from "@/appearance";

/**
 * Shop & Cosmetics Feature Module
 * Ownership: Issue #45 (Mini App: migrare feature Shop)
 */

export type ShopRarity = "free" | "earned" | "common" | "rare" | "collector" | string;

export interface ShopCardCompletionItem {
  id: string;
  name: string;
  owned: boolean;
}

/** Server-calculated shop card from services/shop.py::_card. */
export interface ShopCosmeticItem {
  id: string;
  kind: CosmeticSlot | "bundle";
  name: string;
  description: string;
  price: number;
  full_price: number;
  missing: string[];
  achievement: { field: string; target: number } | null;
  progress: number;
  style: Record<string, unknown>;
  grants: string[];
  owned: boolean;
  equipped: boolean;
  free: boolean;
  featured: boolean;
  equippable: boolean;
  rarity: ShopRarity;
  completes: ShopCardCompletionItem[];
  trophy: { position: number } | null;
  welcome: boolean;
  contents?: ShopCosmeticItem[];
}

export interface ShopSection {
  kind: CosmeticSlot;
  items: ShopCosmeticItem[];
}

export interface WeeklyShowcase {
  week: string;
  items: ShopCosmeticItem[];
}

export interface SavedLook {
  name: string;
  equipped: Partial<Record<CosmeticSlot, string | null>>;
}

/** Wire contract returned by POST /app/api/shop */
export interface ShopCatalogueResponse {
  sections: ShopSection[];
  bundles: ShopCosmeticItem[];
  showcase: WeeklyShowcase;
  equipped: Partial<Record<CosmeticSlot, string | null>>;
  owned: string[];
  looks: SavedLook[];
}

export interface PurchaseHistoryItem {
  name: string;
  day: string;
  stars: number;
  refunded: boolean;
  charge_id: string;
}

/** Wire contract returned by POST /app/api/shop/history */
export interface ShopPurchaseHistoryResponse {
  purchases: PurchaseHistoryItem[];
  support_url: string;
}

export type EquipStatus =
  | "ok"
  | "not_owned"
  | "unknown_item"
  | "not_equippable"
  | string;

export interface EquipResponseOk {
  status: "ok";
  cosmetics: ResolvedAppearance;
}

export interface EquipResponseFail {
  status: Exclude<EquipStatus, "ok">;
  cosmetics?: never;
}

export type EquipResponse = EquipResponseOk | EquipResponseFail;

export type BuyStatus =
  | "ok"
  | "unknown_item"
  | "not_for_sale"
  | "welcome_only"
  | "already_owned"
  | string;

export interface BuyResponseOk {
  status: "ok";
  link: string;
}

export interface BuyResponseFail {
  status: Exclude<BuyStatus, "ok">;
  link?: never;
}

export type BuyResponse = BuyResponseOk | BuyResponseFail;

export type LookAction = "save" | "wear" | "delete";

export type LookStatus =
  | "ok"
  | "invalid_name"
  | "look_limit"
  | "not_owned"
  | "unknown_item"
  | string;

export interface LookResponse {
  status: LookStatus;
}

export type ShopSubview = "catalog" | "wardrobe" | "achievements" | "history";
export type ShopKindFilter = "all" | CosmeticSlot | "bundle";
export type ShopPriceFilter = "all" | "15" | "25" | "55" | "75";
export type ShopDeliveryStatus = "idle" | "delivering" | "delivered" | "pending";

export interface ShopPreviewState {
  item: ShopCosmeticItem;
  appearance: ResolvedAppearance;
}

export interface ShopState {
  view: ShopSubview;
  status: "idle" | "loading" | "ready" | "error";
  errorMessage?: string;
  catalogue: ShopCatalogueResponse | null;
  kindFilter: ShopKindFilter;
  priceFilter: ShopPriceFilter;
  hideOwned: boolean;
  preview: ShopPreviewState | null;
  buying: boolean;
  deliveryStatus: ShopDeliveryStatus;
  buyingItemId: string | null;
  equippingItemId: string | null;
  lookMutation: LookAction | null;
  history: ShopPurchaseHistoryResponse | null;
  historyStatus: "idle" | "loading" | "ready" | "error";
  historyError?: string;
  toast?: string | null;
}

export const SHOP_FEATURE_METADATA = {
  id: "shop",
  name: "Cosmetics Shop",
  owningIssue: 45,
  migrated: true,
} as const;
