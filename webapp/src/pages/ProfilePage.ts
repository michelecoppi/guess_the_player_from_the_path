import { renderCard, renderMigrationNotice } from "@/components";
import { t } from "@/i18n";
import { PROFILE_FEATURE_METADATA } from "@/features/profile";
import type { TelegramUser } from "@/telegram/types";

export interface ProfilePageProps {
  user?: TelegramUser | null;
}

export function renderProfilePage(props: ProfilePageProps = {}): string {
  const user = props.user;
  const lang = user?.language_code || "it";

  const bodyHtml = `
    <div style="display: flex; flex-direction: column; gap: 14px;">
      <div class="shell-status-banner">
        <span class="shell-status-icon" role="img" aria-label="Player">🎖️</span>
        <div class="shell-status-content">
          <h3>Statistiche e Bacheca</h3>
          <p>Visualizzazione carriera, bacheca trofei e gestione cosmetici.</p>
        </div>
      </div>

      <div class="details-list">
        <div class="detail-row">
          <span class="detail-label">ID Telegram:</span>
          <span class="detail-value">${user?.id || 42}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Lingua account:</span>
          <span class="detail-value">${lang.toUpperCase()}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Serie record:</span>
          <span class="detail-value">0 🔥</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Punti totali:</span>
          <span class="detail-value">0 ⭐️</span>
        </div>
      </div>

      ${renderMigrationNotice({
        issueNumber: PROFILE_FEATURE_METADATA.owningIssue,
        messageKey: "migration.profileNotice",
      })}
    </div>
  `;

  return renderCard({
    id: "profile-card",
    kicker: t("pages.profileKicker"),
    title: t("pages.profileTitle"),
    bodyHtml,
  });
}
