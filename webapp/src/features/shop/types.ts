/**
 * Shop & Cosmetics Feature Module
 * Ownership: Issue #45 (Mini App: migrare feature Shop)
 */

export interface ShopCosmeticItem {
  id: string;
  type: "frame" | "theme" | "symbol";
  name: string;
  description: string;
  price_stars: number;
  unlocked: boolean;
  equipped: boolean;
}

export const SHOP_FEATURE_METADATA = {
  id: "shop",
  name: "Cosmetics Shop",
  owningIssue: 45,
  migrated: false,
} as const;
