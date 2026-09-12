import type { CosmeticSlot } from "@/appearance";
/**
 * Shop & Cosmetics Feature Module
 * Ownership: Issue #45 (Mini App: migrare feature Shop)
 */

/** Server-calculated shop card. Bundles are products, never an equipped slot. */
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
  rarity: string;
  completes: Array<{ id: string; name: string; owned: boolean }>;
  trophy: { position: number } | null;
  welcome: boolean;
  contents?: ShopCosmeticItem[];
}

export const SHOP_FEATURE_METADATA = {
  id: "shop",
  name: "Cosmetics Shop",
  owningIssue: 45,
  migrated: false,
} as const;
