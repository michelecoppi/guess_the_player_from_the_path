import { renderHeader } from "@/components/Header";
import { renderNavBar, type NavTabId } from "@/components/NavBar";
import { renderDailyPage } from "@/pages/DailyPage";
import { renderArenaPage } from "@/pages/ArenaPage";
import { renderProfilePage } from "@/pages/ProfilePage";
import { renderLeaderboardPage } from "@/pages/LeaderboardPage";
import { initTelegram, getTelegramUser, isMockTelegramEnvironment } from "@/telegram/webapp";
import { resolveLanguage, setLanguage, t } from "@/i18n";
import { exposeLegacyBridge } from "@/utils/legacy-bridge";

export class App {
  private rootElement: HTMLElement;
  private activeTab: NavTabId = "play";

  constructor(rootElement: HTMLElement) {
    this.rootElement = rootElement;
    exposeLegacyBridge();
  }

  public init(): void {
    const tg = initTelegram();
    const user = getTelegramUser();
    const userLang = resolveLanguage(user?.language_code || (tg?.initDataUnsafe?.user?.language_code));
    setLanguage(userLang);

    this.render();
  }

  public setTab(tab: NavTabId): void {
    if (this.activeTab !== tab) {
      this.activeTab = tab;
      this.render();
    }
  }

  private render(): void {
    const user = getTelegramUser();
    const isMock = isMockTelegramEnvironment();

    let pageHtml = "";
    switch (this.activeTab) {
      case "play":
        pageHtml = renderDailyPage();
        break;
      case "arena":
        pageHtml = renderArenaPage();
        break;
      case "profile":
        pageHtml = renderProfilePage({ user });
        break;
      case "leaderboard":
        pageHtml = renderLeaderboardPage();
        break;
      default:
        pageHtml = renderDailyPage();
    }

    const mockBannerHtml = isMock && user
      ? `<div style="background: rgba(240, 166, 58, 0.12); border: 1px dashed var(--warn); border-radius: 12px; padding: 10px 12px; font-size: 12px; color: var(--warn); display: flex; align-items: center; gap: 8px;">
          <span>🛠️</span>
          <span>${t("shell.mockNotice", { name: user.first_name })}</span>
        </div>`
      : "";

    this.rootElement.innerHTML = `
      ${renderHeader({ user })}
      ${mockBannerHtml}
      <main id="app-content" role="region" aria-label="Page content">
        ${pageHtml}
      </main>
      ${renderNavBar({ activeTab: this.activeTab })}
    `;

    this.attachEventListeners();
  }

  private attachEventListeners(): void {
    const navButtons = this.rootElement.querySelectorAll<HTMLButtonElement>("nav.app-nav button[data-tab]");
    navButtons.forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        const tab = btn.dataset.tab as NavTabId;
        if (tab) {
          this.setTab(tab);
        }
      });
    });
  }
}
