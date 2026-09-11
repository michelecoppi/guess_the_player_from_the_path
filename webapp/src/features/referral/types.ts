/**
 * Referral Program Feature Module
 * Ownership: Issue #46 (Mini App: migrare feature Referral)
 */

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

export const REFERRAL_FEATURE_METADATA = {
  id: "referral",
  name: "Referrals & Rewards",
  owningIssue: 46,
  migrated: false,
} as const;
