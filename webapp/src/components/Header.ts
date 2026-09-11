import { escapeHtml, initials } from "@/utils/format";
import { t } from "@/i18n";
import type { TelegramUser } from "@/telegram/types";

export interface HeaderProps {
  user?: TelegramUser | null;
}

export function renderHeader(props: HeaderProps = {}): string {
  const user = props.user;
  const displayName = user ? `${user.first_name}${user.last_name ? ` ${user.last_name}` : ""}` : t("common.anonymous");
  const userInitials = initials(displayName);

  return `
    <header class="app-header">
      <div class="header-brand">
        <span class="header-logo" role="img" aria-label="Soccer ball">⚽</span>
        <div class="header-title-group">
          <h1>${escapeHtml(t("common.appName"))}</h1>
          <span class="header-subtitle">Mini App V2 Shell</span>
        </div>
      </div>
      <div class="user-badge" id="header-user-badge">
        <div class="user-avatar">${escapeHtml(userInitials)}</div>
        <span class="user-name">${escapeHtml(displayName)}</span>
      </div>
    </header>
  `;
}
