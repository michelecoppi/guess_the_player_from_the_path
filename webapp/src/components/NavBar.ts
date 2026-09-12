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
  | "events"
  | "duels"
  | "challenge"
  | "reports"
  | "refunds"
  | "privacy";
export const NAV_ITEMS: {
  id: NavTabId;
  label: () => string;
  icon: IconName;
}[] = [
  { id: "play", label: () => "Daily", icon: "career" },
  { id: "arena", label: () => t("nav.arena"), icon: "arena" },
  { id: "leaderboard", label: () => t("nav.leaderboard"), icon: "ranking" },
  { id: "shop", label: () => v("shop"), icon: "shop" },
  { id: "profile", label: () => t("nav.profile"), icon: "profile" },
];
export function primaryDestination(tab: NavTabId): NavTabId | null {
  if (["archive", "events", "duels", "challenge"].includes(tab)) return "arena";
  if (tab === "referral") return "profile";
  if (["reports", "refunds", "privacy"].includes(tab)) return null;
  return tab;
}
export interface NavBarProps {
  activeTab: NavTabId;
}
export function renderNavBar({ activeTab }: NavBarProps): string {
  return `<nav class="app-nav" aria-label="Main navigation">${NAV_ITEMS.map((item) => `<button type="button" id="nav-tab-${item.id}" data-tab="${item.id}" ${item.id === primaryDestination(activeTab) ? 'aria-current="page"' : ""} aria-label="${escapeHtml(item.label())}">${icon(item.icon)}<span>${escapeHtml(item.label())}</span></button>`).join("")}</nav>`;
}
