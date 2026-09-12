import { renderPrototype } from "@/prototypes/screens";
import { connectTheme } from "@/telegram/theme";
import { renderHeader } from "@/components/Header";
import { renderNavBar, type NavTabId } from "@/components/NavBar";
import { renderDailyPage, attachDailyEventListeners } from "@/pages/DailyPage";
import { renderArenaPage } from "@/pages/ArenaPage";
import { renderProfilePage } from "@/pages/ProfilePage";
import { renderLeaderboardPage } from "@/pages/LeaderboardPage";
import {
  initTelegram,
  getTelegramUser,
  isMockTelegramEnvironment,
} from "@/telegram/webapp";
import { resolveLanguage, setLanguage } from "@/i18n";
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
    connectTheme(tg);
    const user = getTelegramUser();
    const userLang = resolveLanguage(
      user?.language_code || tg?.initDataUnsafe?.user?.language_code,
    );
    setLanguage(userLang);

    this.render();
    this.dailyController.init();
  }

  public setTab(tab: NavTabId): void {
    if (this.activeTab !== tab) {
      this.activeTab = tab;
      this.render();
      const heading =
        this.rootElement.querySelector<HTMLElement>("#app-content h2");
      if (heading) {
        heading.tabIndex = -1;
        heading.focus({ preventScroll: true });
      }
      window.scrollTo?.({ top: 0 });
    }
  }

  private renderDailyContent(): void {
    const mainEl = this.rootElement.querySelector("#app-content");
    if (mainEl && this.activeTab === "play") {
      const state = this.dailyController.getState();
      const hadInputFocus = document.activeElement?.id === "answer";
      mainEl.innerHTML = renderDailyPage(state);
      attachDailyEventListeners(this.rootElement, this.dailyController);
      if (hadInputFocus && state.status !== "submitting")
        mainEl
          .querySelector<HTMLInputElement>("#answer")
          ?.focus({ preventScroll: true });
      if (
        ["incorrect", "correct", "completed"].includes(state.status) &&
        state.feedback
      ) {
        mainEl
          .querySelector(".feedback")
          ?.scrollIntoView?.({ block: "nearest" });
      }
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
        pageHtml = renderPrototype(this.activeTab);
    }

    const mockBannerHtml =
      isMock && user
        ? `<p class="environment-note">Local preview · Telegram not connected</p>`
        : "";

    this.rootElement.innerHTML = `
      ${renderHeader({ user, activeTab: this.activeTab })}
      ${mockBannerHtml}
      <main id="app-content" role="region" aria-label="Page content">
        ${pageHtml}
      </main>
      ${renderNavBar({ activeTab: this.activeTab })}
    `;

    this.attachEventListeners();
  }

  private attachEventListeners(): void {
    const navButtons =
      this.rootElement.querySelectorAll<HTMLButtonElement>("button[data-tab]");
    navButtons.forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        const tab = btn.dataset.tab as NavTabId;
        if (tab) {
          this.setTab(tab);
        }
      });
    });

    const details =
      this.rootElement.querySelector<HTMLDetailsElement>(".more-nav");
    if (details)
      details.onkeydown = (event) => {
        if (event.key === "Escape") {
          details.open = false;
          details.querySelector("summary")?.focus();
        }
      };
    if (this.activeTab === "play") {
      attachDailyEventListeners(this.rootElement, this.dailyController);
    }
  }
}
