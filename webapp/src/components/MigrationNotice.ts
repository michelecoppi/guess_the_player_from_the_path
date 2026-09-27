import { escapeHtml } from "@/utils/format";
import { t } from "@/i18n";

export interface MigrationNoticeProps {
  issueNumber: number;
  messageKey: string;
}

export function renderMigrationNotice(props: MigrationNoticeProps): string {
  const badgeText = t("migration.badge", { issue: props.issueNumber });
  const messageText = t(props.messageKey);

  return `
    <div class="migration-notice-wrapper">
      <span class="migration-notice">
        <span aria-hidden="true">🚧</span>
        <span>${escapeHtml(badgeText)}</span>
      </span>
      <p style="font-size: 12px; color: var(--muted); margin: 6px 0 0 0; line-height: 1.4;">
        ${escapeHtml(messageText)}
      </p>
    </div>
  `;
}
