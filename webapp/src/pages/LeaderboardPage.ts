import { renderCard, renderMigrationNotice } from "@/components";
import { t } from "@/i18n";
import { LEADERBOARD_FEATURE_METADATA } from "@/features/leaderboard";

export function renderLeaderboardPage(): string {
  const bodyHtml = `
    <div style="display: flex; flex-direction: column; gap: 14px;">
      <div class="shell-status-banner">
        <span class="shell-status-icon" role="img" aria-label="Trophy">🏆</span>
        <div class="shell-status-content">
          <h3>Classifica Globale & Leghe</h3>
          <p>Classifica settimanale, podio e leghe private tra amici.</p>
        </div>
      </div>

      <div class="details-list">
        <div class="detail-row">
          <span class="detail-label">Posizione attuale:</span>
          <span class="detail-value">#1</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Lega principale:</span>
          <span class="detail-value">Amici del Bar</span>
        </div>
      </div>

      ${renderMigrationNotice({
        issueNumber: LEADERBOARD_FEATURE_METADATA.owningIssue,
        messageKey: "migration.leaderboardNotice",
      })}
    </div>
  `;

  return renderCard({
    id: "leaderboard-card",
    kicker: t("pages.leaderboardKicker"),
    title: t("pages.leaderboardTitle"),
    bodyHtml,
  });
}
