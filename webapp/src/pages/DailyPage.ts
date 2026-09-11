import { renderCard, renderMigrationNotice, renderButton } from "@/components";
import { t } from "@/i18n";
import { DAILY_FEATURE_METADATA } from "@/features/daily";

export function renderDailyPage(): string {
  const bodyHtml = `
    <div style="display: flex; flex-direction: column; gap: 14px;">
      <div class="shell-status-banner">
        <span class="shell-status-icon" role="img" aria-label="Field">🏟️</span>
        <div class="shell-status-content">
          <h3>Career Path Shell</h3>
          <p>La vista CareerPath e l'input predittivo del calciatore verranno migrati come componenti riusabili in #48 e #40.</p>
        </div>
      </div>

      <div class="details-list">
        <div class="detail-row">
          <span class="detail-label">Stato sfida:</span>
          <span class="detail-value" style="color: var(--accent);">Disponibile</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Tentativi massimi:</span>
          <span class="detail-value">5</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Indizi rimasti:</span>
          <span class="detail-value">3</span>
        </div>
      </div>

      <div style="display: flex; gap: 8px; margin-top: 4px;">
        ${renderButton({ id: "btn-guess-demo", label: "Indovina Calciatore", variant: "primary" })}
        ${renderButton({ id: "btn-hint-demo", label: "Chiedi Indizio", variant: "ghost" })}
      </div>

      ${renderMigrationNotice({
        issueNumber: DAILY_FEATURE_METADATA.owningIssue,
        messageKey: "migration.dailyNotice",
      })}
    </div>
  `;

  return renderCard({
    id: "daily-challenge-card",
    kicker: t("pages.dailyKicker"),
    title: t("pages.dailyTitle"),
    bodyHtml,
  });
}
