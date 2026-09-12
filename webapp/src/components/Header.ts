import { escapeHtml, initials } from "@/utils/format";
import { t } from "@/i18n";
import { v } from "@/i18n/visual";
import { icon } from "./Icon";
import type { TelegramUser } from "@/telegram/types";
export interface HeaderProps {
  user?: TelegramUser | null;
  activeTab?: string;
}
export function renderHeader({ user, activeTab }: HeaderProps = {}): string {
  const name = user?.first_name || t("common.anonymous");
  return `<header class="app-header"><div class="header-brand"><span class="header-logo">${icon("career")}</span><div class="header-title-group"><h1>GUESS THE PLAYER</h1><span class="header-subtitle">From the path</span></div></div><div class="header-actions"><span class="user-avatar" aria-label="${escapeHtml(name)}">${escapeHtml(initials(name))}</span><details class="more-nav"><summary aria-label="${v("more")}">${icon("more")}</summary><div class="more-menu">${(["shop", "referral", "events"] as const).map((id) => `<button type="button" data-tab="${id}" ${activeTab === id ? 'aria-current="page"' : ""}>${icon(id)}${v(id)}</button>`).join("")}</div></details></div></header>`;
}
