import type { ShopCosmeticItem } from "@/features/shop/types";

/**
 * Referral Program Feature Module
 * Ownership: Issue #46 (Mini App: migrare feature Referral)
 */

/** Authoritative friend row projection from services/referrals.py::dashboard */
export interface ReferralFriendRow {
  name: string;
  days: number;
  status: "qualified" | "pending" | string;
  joined_day?: string;
}

/** Server reward milestone with resolved shop cosmetic items */
export interface ReferralRewardMilestone {
  target: number;
  items: ShopCosmeticItem[];
}

/** Wire contract returned by POST /app/api/referrals */
export interface ReferralDashboardResponse {
  qualified: number;
  required_days: number;
  link: string | null;
  friends: ReferralFriendRow[];
  next_cursor: string | null;
  rewards: ReferralRewardMilestone[];
}

export type ReferralStatus = "idle" | "loading" | "ready" | "error";

export interface ReferralState {
  status: ReferralStatus;
  data: ReferralDashboardResponse | null;
  loadingMore: boolean;
  refreshing: boolean;
  selectedRewardTarget: number | null;
  equippingItemId: string | null;
  toast: string | null;
  errorNotice: string | null;
}

export const REFERRAL_FEATURE_METADATA = {
  id: "referral",
  name: "Referrals & Rewards",
  owningIssue: 46,
  migrated: true,
} as const;

// Legacy prototype typing retained for prototype/fixtures compatibility
export interface ReferralFriend {
  name: string;
  days_completed: number;
  qualified: boolean;
}

export interface ReferralProgress {
  qualified_count: number;
  max_rewards: number;
  referral_link?: string;
  friends: ReferralFriend[];
}
