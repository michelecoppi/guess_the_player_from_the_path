/**
 * Past Daily Challenges Archive Feature Module
 * Ownership: Issue #44 (Mini App: migrare feature Archivio)
 */

export interface ArchiveCalendarDay {
  date: string;
  solved: boolean;
  attempts?: number;
  available: boolean;
}

export const ARCHIVE_FEATURE_METADATA = {
  id: "archive",
  name: "Past Challenges Archive",
  owningIssue: 44,
  migrated: false,
} as const;
