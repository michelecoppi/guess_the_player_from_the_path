import { renderCard, renderMigrationNotice, renderButton } from "@/components";
import { t } from "@/i18n";
import { ARENA_FEATURE_METADATA } from "@/features/arena";

export function renderArenaPage(): string {
  const bodyHtml = `
    <div style="display: flex; flex-direction: column; gap: 14px;">
      <div class="shell-status-banner">
        <span class="shell-status-icon" role="img" aria-label="Swords">⚔️</span>
        <div class="shell-status-content">
          <h3>Arena 1v1 Shell</h3>
          <p>Duelli asincroni tra giocatori: sfida un amico o cerca un avversario casuale.</p>
        </div>
      </div>

      <div class="details-list">
        <div class="detail-row">
          <span class="detail-label">Duelli attivi:</span>
          <span class="detail-value">0</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Vittorie Arena:</span>
          <span class="detail-value">0</span>
        </div>
      </div>

      <div style="display: flex; gap: 8px; margin-top: 4px;">
        ${renderButton({ id: "btn-arena-invite", label: "Crea Duello", variant: "primary" })}
        ${renderButton({ id: "btn-arena-refresh", label: "Aggiorna", variant: "ghost" })}
      </div>

      ${renderMigrationNotice({
        issueNumber: ARENA_FEATURE_METADATA.owningIssue,
        messageKey: "migration.arenaNotice",
      })}
    </div>
  `;

  return renderCard({
    id: "arena-card",
    kicker: t("pages.arenaKicker"),
    title: t("pages.arenaTitle"),
    bodyHtml,
  });
}
