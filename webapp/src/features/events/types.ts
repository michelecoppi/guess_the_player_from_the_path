/**
 * Special Events Feature Module
 * Ownership: Issue #47 (Mini App: migrare feature Eventi)
 */

export interface EventChallenge {
  event_id: string;
  title: string;
  theme: string;
  starts_at: string;
  ends_at: string;
  active: boolean;
}

export const EVENTS_FEATURE_METADATA = {
  id: "events",
  name: "Special Events",
  owningIssue: 47,
  migrated: false,
} as const;
