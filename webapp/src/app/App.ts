import { renderHeader } from "@/components/Header";
import { renderNavBar, type NavTabId } from "@/components/NavBar";
import { renderDailyPage, attachDailyEventListeners } from "@/pages/DailyPage";
import { renderArenaPage } from "@/pages/ArenaPage";
import { renderProfilePage } from "@/pages/ProfilePage";
import { renderLeaderboardPage } from "@/pages/LeaderboardPage";
import { initTelegram, getTelegramUser, isMockTelegramEnvironment } from "@/telegram/webapp";
import { resolveLanguage, setLanguage, t } from "@/i18n";
import { exposeLegacyBridge } from "@/utils/legacy-bridge";
import { DailyController } from "@/features/daily/controller";

export class App {
  private rootElement: HTMLElement;
  private activeTab: NavTabId = "play";
  private dailyController: DailyController;

  constructor(rootElement: HTMLElement, dailyController?: DailyController) {
    this.rootElement = rootElement;
    this.dailyController = dailyController || new DailyController();
    exposeLegacyBridge();

    this.dailyController.subscribe(() => {
      if (this.activeTab === "play") {
        this.renderDailyContent();
      }
    });
  }

  public getDailyController(): DailyController {
    return this.dailyController;
  }

  public init(): void {
    const tg = initTelegram();
    const user = getTelegramUser();
    const userLang = resolveLanguage(user?.language_code || (tg?.initDataUnsafe?.user?.language_code));
    setLanguage(userLang);

    this.render();
    this.dailyController.init().then(() => {
      if (typeof window !== "undefined" && window.location?.search) {
        const p = new URLSearchParams(window.location.search);
        const view = p.get("view");
        if (view === "wrong") {
          this.dailyController.submitGuess("Messi");
        } else if (view === "solved") {
          this.dailyController.submitGuess("Vitolo");
        }
      }
    });
  }

  public setTab(tab: NavTabId): void {
    if (this.activeTab !== tab) {
      this.activeTab = tab;
      this.render();
    }
  }

  private renderDailyContent(): void {
    const mainEl = this.rootElement.querySelector("#app-content");
    if (mainEl && this.activeTab === "play") {
      mainEl.innerHTML = renderDailyPage(this.dailyController.getState());
      attachDailyEventListeners(this.rootElement, this.dailyController);
    }
  }

  private render(): void {
    const user = getTelegramUser();
    const isMock = isMockTelegramEnvironment();

    let pageHtml = "";
    switch (this.activeTab) {
      case "play":
        pageHtml = renderDailyPage(this.dailyController.getState());
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
        pageHtml = renderDailyPage(this.dailyController.getState());
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

    if (this.activeTab === "play") {
      attachDailyEventListeners(this.rootElement, this.dailyController);
    }
  }
}
