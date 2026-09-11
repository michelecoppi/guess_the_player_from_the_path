import { escapeHtml } from "@/utils/format";
import { t } from "@/i18n";

export type NavTabId = "play" | "arena" | "profile" | "leaderboard";

export interface NavItem {
  id: NavTabId;
  labelKey: string;
  icon: string;
}

export const NAV_ITEMS: NavItem[] = [
  { id: "play", labelKey: "nav.play", icon: "⚽" },
  { id: "arena", labelKey: "nav.arena", icon: "⚔️" },
  { id: "profile", labelKey: "nav.profile", icon: "👤" },
  { id: "leaderboard", labelKey: "nav.leaderboard", icon: "🏆" },
];

export interface NavBarProps {
  activeTab: NavTabId;
}

export function renderNavBar(props: NavBarProps): string {
  const buttonsHtml = NAV_ITEMS.map((item) => {
    const isSelected = item.id === props.activeTab;
    const label = t(item.labelKey);
    return `
      <button
        type="button"
        id="nav-tab-${item.id}"
        data-tab="${item.id}"
        aria-selected="${isSelected}"
        aria-label="${escapeHtml(label)}"
      >
        <span class="nav-icon" aria-hidden="true">${item.icon}</span>
        <span>${escapeHtml(label)}</span>
      </button>
    `;
  }).join("");

  return `
    <nav class="app-nav" aria-label="Main navigation">
      ${buttonsHtml}
    </nav>
  `;
}
