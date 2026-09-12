import { renderPrototype } from "@/prototypes/screens";
import { connectTheme } from "@/telegram/theme";
import { renderHeader } from "@/components/Header";
import { renderNavBar, type NavTabId } from "@/components/NavBar";
import { renderDailyPage, attachDailyEventListeners } from "@/pages/DailyPage";
import {
  renderArenaPage,
  attachArenaEventListeners,
  type ArenaSubview,
} from "@/pages/ArenaPage";
import { renderProfilePage } from "@/pages/ProfilePage";
import {
  renderLeaderboardPage,
  attachLeaderboardEventListeners,
} from "@/pages/LeaderboardPage";
import {
  initTelegram,
  getTelegramUser,
  isMockTelegramEnvironment,
} from "@/telegram/webapp";
import { resolveLanguage, setLanguage } from "@/i18n";
import { exposeLegacyBridge } from "@/utils/legacy-bridge";
import { DailyController } from "@/features/daily/controller";
import { ArenaController } from "@/features/arena/controller";
import { TrainingController } from "@/features/training/controller";
import { LeaderboardController } from "@/features/leaderboard/controller";

export class App {
  private rootElement: HTMLElement;
  private activeTab: NavTabId = "play";
  private dailyController: DailyController;
  private arenaController: ArenaController;
  private trainingController: TrainingController;
  private leaderboardController: LeaderboardController;
  private lastArenaSubview: ArenaSubview;

  constructor(
    rootElement: HTMLElement,
    dailyController?: DailyController,
    arenaController?: ArenaController,
    trainingController?: TrainingController,
    leaderboardController?: LeaderboardController,
  ) {
    this.rootElement = rootElement;
    this.dailyController = dailyController || new DailyController();
    this.arenaController = arenaController || new ArenaController();
    this.trainingController = trainingController || new TrainingController();
    this.leaderboardController =
      leaderboardController || new LeaderboardController();
    this.lastArenaSubview = this.arenaController.getState().subview;
    exposeLegacyBridge();

    this.dailyController.subscribe(() => {
      if (this.activeTab === "play") {
        this.renderDailyContent();
      }
    });

    this.leaderboardController.subscribe(() => {
      if (this.activeTab === "leaderboard") {
        this.renderLeaderboardContent();
      }
    });

    this.arenaController.subscribe((state) => {
      if (this.isArenaTab(this.activeTab)) {
        const subviewChanged = state.subview !== this.lastArenaSubview;
        this.lastArenaSubview = state.subview;

        if (state.subview === "training") {
          if (subviewChanged) {
            if (
              !this.trainingController.getState().data &&
              this.trainingController.getState().status === "idle"
            ) {
              void this.trainingController.init();
            }
            this.renderArenaContent();
          }
        } else {
          this.renderArenaContent();
        }
      } else {
        this.lastArenaSubview = state.subview;
      }
    });

    this.trainingController.subscribe(() => {
      if (
        this.isArenaTab(this.activeTab) &&
        this.arenaController.getState().subview === "training"
      ) {
        this.renderArenaContent();
      }
    });
  }

  public getDailyController(): DailyController {
    return this.dailyController;
  }

  public getArenaController(): ArenaController {
    return this.arenaController;
  }

  public getTrainingController(): TrainingController {
    return this.trainingController;
  }

  public getLeaderboardController(): LeaderboardController {
    return this.leaderboardController;
  }

  public isArenaTab(tab: NavTabId): boolean {
    return tab === "arena" || tab === "duels" || tab === "challenge";
  }

  public init(): void {
    this.dailyController.reset();
    const tg = initTelegram();
    connectTheme(tg);
    const user = getTelegramUser();
    const userLang = resolveLanguage(
      user?.language_code || tg?.initDataUnsafe?.user?.language_code,
    );
    setLanguage(userLang);

    // Deep-link check for duel invite
    const inviteCode = this.arenaController.detectInvitationCode();
    if (inviteCode) {
      this.activeTab = "arena";
    }

    this.render();
    this.dailyController.init();
    this.arenaController.init();
    if (this.activeTab === "leaderboard") {
      void this.leaderboardController.init();
    }
  }

  public setTab(tab: NavTabId): void {
    if (this.activeTab !== tab) {
      this.activeTab = tab;

      if (tab === "arena") {
        this.arenaController.setSubview("hub");
      } else if (tab === "duels") {
        this.arenaController.setSubview("duel");
      } else if (tab === "challenge") {
        this.arenaController.setSubview("challenge");
      } else if (tab === "leaderboard") {
        void this.leaderboardController.init();
      }

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

  public setArenaSubview(subview: ArenaSubview): void {
    this.arenaController.setSubview(subview);
  }

  private renderDailyContent(): void {
    const mainEl = this.rootElement.querySelector("#app-content");
    if (mainEl && this.activeTab === "play") {
      const state = this.dailyController.getState();
      const hadInputFocus =
        typeof document !== "undefined" && document.activeElement?.id === "answer";
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

  private renderArenaContent(): void {
    const mainEl = this.rootElement.querySelector("#app-content");
    if (mainEl && this.isArenaTab(this.activeTab)) {
      const arenaState = this.arenaController.getState();
      const trainingState = this.trainingController.getState();

      if (arenaState.subview === "training") {
        const hadInputFocus =
          typeof document !== "undefined" &&
          document.activeElement?.id === "training-answer";

        mainEl.innerHTML = renderArenaPage(arenaState, trainingState);
        attachArenaEventListeners(
          this.rootElement,
          this.arenaController,
          this.trainingController,
        );

        if (hadInputFocus && trainingState.status !== "loading") {
          mainEl
            .querySelector<HTMLInputElement>("#training-answer")
            ?.focus({ preventScroll: true });
        }

        if (trainingState.data?.feedback) {
          mainEl
            .querySelector(".feedback")
            ?.scrollIntoView?.({ block: "nearest" });
        }
      } else {
        const hadAnswerFocus =
          typeof document !== "undefined" &&
          document.activeElement?.id === "arena-answer";
        const hadSearchFocus =
          typeof document !== "undefined" &&
          document.activeElement?.id === "opponent-search";
        const searchCursorPos =
          hadSearchFocus && typeof document !== "undefined"
            ? (document.activeElement as HTMLInputElement).selectionStart
            : null;

        mainEl.innerHTML = renderArenaPage(arenaState, trainingState);
        attachArenaEventListeners(
          this.rootElement,
          this.arenaController,
          this.trainingController,
        );

        if (hadAnswerFocus && arenaState.status !== "submitting") {
          mainEl
            .querySelector<HTMLInputElement>("#arena-answer")
            ?.focus({ preventScroll: true });
        } else if (hadSearchFocus) {
          const searchInput =
            mainEl.querySelector<HTMLInputElement>("#opponent-search");
          if (searchInput) {
            searchInput.focus({ preventScroll: true });
            if (searchCursorPos !== null) {
              searchInput.setSelectionRange(searchCursorPos, searchCursorPos);
            }
          }
        }

        if (arenaState.data?.feedback) {
          mainEl
            .querySelector(".feedback")
            ?.scrollIntoView?.({ block: "nearest" });
        }
      }
    }
  }

  private renderLeaderboardContent(): void {
    const mainEl = this.rootElement.querySelector("#app-content");
    if (mainEl && this.activeTab === "leaderboard") {
      mainEl.innerHTML = renderLeaderboardPage(
        this.leaderboardController.getState(),
      );
      attachLeaderboardEventListeners(
        this.rootElement,
        this.leaderboardController,
      );
      const heading = mainEl.querySelector<HTMLElement>(
        "#public-profile-heading",
      );
      if (heading) {
        heading.tabIndex = -1;
        heading.focus({ preventScroll: true });
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
      case "duels":
      case "challenge":
        pageHtml = renderArenaPage(
          this.arenaController.getState(),
          this.trainingController.getState(),
        );
        break;
      case "profile":
        pageHtml = renderProfilePage({ user });
        break;
      case "leaderboard":
        pageHtml = renderLeaderboardPage(
          this.leaderboardController.getState(),
        );
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
    } else if (this.isArenaTab(this.activeTab)) {
      attachArenaEventListeners(
        this.rootElement,
        this.arenaController,
        this.trainingController,
      );
    } else if (this.activeTab === "leaderboard") {
      attachLeaderboardEventListeners(
        this.rootElement,
        this.leaderboardController,
      );
    }
  }
}
