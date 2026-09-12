import { escapeHtml } from "@/utils/format";
import { t } from "@/i18n";
import { v } from "@/i18n/visual";
import { icon, type IconName } from "./Icon";
export type NavTabId =
  | "play"
  | "arena"
  | "leaderboard"
  | "archive"
  | "profile"
  | "shop"
  | "referral"
  | "events";
export const NAV_ITEMS: {
  id: NavTabId;
  label: () => string;
  icon: IconName;
}[] = [
  { id: "play", label: () => "Daily", icon: "career" },
  { id: "arena", label: () => t("nav.arena"), icon: "arena" },
  { id: "leaderboard", label: () => t("nav.leaderboard"), icon: "ranking" },
  { id: "archive", label: () => v("archive"), icon: "archive" },
  { id: "profile", label: () => t("nav.profile"), icon: "profile" },
];
export interface NavBarProps {
  activeTab: NavTabId;
}
export function renderNavBar({ activeTab }: NavBarProps): string {
  return `<nav class="app-nav" aria-label="Main navigation">${NAV_ITEMS.map((item) => `<button type="button" id="nav-tab-${item.id}" data-tab="${item.id}" ${item.id === activeTab ? 'aria-current="page"' : ""} aria-label="${escapeHtml(item.label())}">${icon(item.icon)}<span>${escapeHtml(item.label())}</span></button>`).join("")}</nav>`;
}
