import { renderPrototype, attachSupportEventListeners } from "@/prototypes/screens";
import { SupportController } from "@/features/support/controller";
import { connectTheme } from "@/telegram/theme";
import { renderHeader } from "@/components/Header";
import { renderNavBar, type NavTabId } from "@/components/NavBar";
import { renderDailyPage, attachDailyEventListeners } from "@/pages/DailyPage";
import {
  renderArenaPage,
  attachArenaEventListeners,
  type ArenaSubview,
} from "@/pages/ArenaPage";
import {
  renderProfilePage,
  attachProfileEventListeners,
} from "@/pages/ProfilePage";
import {
  renderLeaderboardPage,
  attachLeaderboardEventListeners,
} from "@/pages/LeaderboardPage";
import {
  renderArchivePage,
  attachArchiveEventListeners,
} from "@/pages/ArchivePage";
import {
  renderShopPage,
  attachShopEventListeners,
} from "@/pages/ShopPage";
import {
  renderReferralPage,
  attachReferralEventListeners,
} from "@/pages/ReferralPage";
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
import { ArchiveController } from "@/features/archive/controller";
import { ProfileController } from "@/features/profile/controller";
import { ShopController } from "@/features/shop/controller";
import { ReferralController } from "@/features/referral/controller";
import { EventsController } from "@/features/events/controller";
import { renderEventsPage, attachEventsEventListeners } from "@/pages/EventsPage";

export class App {
  private rootElement: HTMLElement;
  private activeTab: NavTabId = "play";
  private dailyController: DailyController;
  private arenaController: ArenaController;
  private trainingController: TrainingController;
  private leaderboardController: LeaderboardController;
  private archiveController: ArchiveController;
  private profileController: ProfileController;
  private shopController: ShopController;
  private referralController: ReferralController;
  private eventsController: EventsController;
  private supportController: SupportController;
  private lastArenaSubview: ArenaSubview;
  private firstLoad: Promise<void> = Promise.resolve();

  constructor(
    rootElement: HTMLElement,
    dailyController?: DailyController,
    arenaController?: ArenaController,
    trainingController?: TrainingController,
    leaderboardController?: LeaderboardController,
    archiveController?: ArchiveController,
    profileController?: ProfileController,
    shopController?: ShopController,
    referralController?: ReferralController,
    eventsController?: EventsController,
    supportController?: SupportController,
  ) {
    this.rootElement = rootElement;
    // The purchased theme's surface/glow/pattern now show behind every tab and the header,
    // not just the profile card - see [data-cosmetic-shell] in editorial.css. It's a plain
    // attribute (no inline style): the tokens already live on <html> from applyResolvedAppearance,
    // so nothing here needs to know the current appearance or re-set this on every render.
    this.rootElement.setAttribute("data-cosmetic-shell", "");
    this.dailyController = dailyController || new DailyController();
    this.arenaController = arenaController || new ArenaController();
    this.trainingController = trainingController || new TrainingController();
    this.leaderboardController =
      leaderboardController || new LeaderboardController();
    this.archiveController = archiveController || new ArchiveController();
    this.profileController = profileController || new ProfileController();
    this.shopController = shopController || new ShopController();
    this.referralController = referralController || new ReferralController();
    this.eventsController = eventsController || new EventsController();
    this.supportController = supportController || new SupportController();
    this.referralController.setEquipHandler((itemId: string) => {
      return this.shopController.equip(itemId);
    });
    this.lastArenaSubview = this.arenaController.getState().subview;
    exposeLegacyBridge();

    this.shopController.onAppearanceChanged = (appearance) => {
      this.profileController.syncAppearance(appearance);
      this.dailyController.syncAppearance(appearance);
      this.referralController.syncAppearance(appearance);
    };

    this.referralController.onAppearanceChanged = (appearance) => {
      this.profileController.syncAppearance(appearance);
      this.dailyController.syncAppearance(appearance);
    };

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

    this.archiveController.subscribe(() => {
      if (this.activeTab === "archive") {
        this.renderArchiveContent();
      }
    });

    this.profileController.subscribe(() => {
      if (this.activeTab === "profile") {
        this.renderProfileContent();
      }
    });

    this.shopController.subscribe(() => {
      if (this.activeTab === "shop") {
        this.renderShopContent();
      }
    });

    this.referralController.subscribe(() => {
      if (this.activeTab === "referral") {
        this.renderReferralContent();
      }
    });

    this.eventsController.subscribe(() => {
      if (this.activeTab === "events") {
        this.renderEventsContent();
      }
    });

    this.supportController.subscribe(() => {
      if (this.activeTab === "reports") {
        this.renderReportsContent();
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

  public getArchiveController(): ArchiveController {
    return this.archiveController;
  }

  public getProfileController(): ProfileController {
    return this.profileController;
  }

  public getShopController(): ShopController {
    return this.shopController;
  }

  public getReferralController(): ReferralController {
    return this.referralController;
  }

  public getEventsController(): EventsController {
    return this.eventsController;
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
    this.firstLoad = Promise.resolve(this.dailyController.init());
    this.arenaController.init();
    if (this.activeTab === "leaderboard") {
      void this.leaderboardController.init();
    }
    if (this.activeTab === "profile") {
      void this.profileController.init();
    }
    if (this.activeTab === "shop") {
      void this.shopController.init();
    }
    if (this.activeTab === "referral") {
      void this.referralController.init();
    }
    if (this.activeTab === "events") {
      void this.eventsController.load();
    }
  }

  /** Settles when the first Daily load of `init()` is done (startup timing, #32). */
  public whenFirstLoaded(): Promise<void> {
    return this.firstLoad;
  }

  public setTab(tab: NavTabId): void {
    if (this.activeTab !== tab) {
      if (this.activeTab === "shop" && tab !== "shop") {
        this.shopController.stopPreview();
        this.profileController.invalidateInventory();
      }
      if (this.activeTab === "leaderboard") this.leaderboardController.cancelSearch();
      if (this.activeTab === "reports") this.supportController.reset();
      this.activeTab = tab;

      if (tab === "arena") {
        this.arenaController.setSubview("hub");
      } else if (tab === "duels") {
        this.arenaController.setSubview("duel");
      } else if (tab === "challenge") {
        this.arenaController.setSubview("challenge");
      } else if (tab === "leaderboard") {
        void this.leaderboardController.init();
      } else if (tab === "archive") {
        void this.archiveController.init();
      } else if (tab === "profile") {
        void this.profileController.init();
      } else if (tab === "shop") {
        void this.shopController.init();
      } else if (tab === "referral") {
        void this.referralController.init();
      } else if (tab === "events") {
        void this.eventsController.load();
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

  public getActiveTab(): NavTabId {
    return this.activeTab;
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
        this.attachTabButtons(mainEl as HTMLElement);

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
        this.attachTabButtons(mainEl as HTMLElement);

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
      const search = mainEl.querySelector<HTMLInputElement>('#leaderboard-search');
      const focused = search === document.activeElement;
      const cursor = search?.selectionStart ?? null;
      mainEl.innerHTML = renderLeaderboardPage(
        this.leaderboardController.getState(),
      );
      attachLeaderboardEventListeners(
        this.rootElement,
        this.leaderboardController,
      );
      if (focused) {
        const next = mainEl.querySelector<HTMLInputElement>('#leaderboard-search');
        next?.focus({ preventScroll: true });
        if (cursor !== null) next?.setSelectionRange(cursor, cursor);
      }
      const heading = mainEl.querySelector<HTMLElement>(
        "#public-profile-heading",
      );
      if (heading) {
        heading.tabIndex = -1;
        heading.focus({ preventScroll: true });
      }
    }
  }

  private renderArchiveContent(): void {
    const mainEl = this.rootElement.querySelector("#app-content");
    if (mainEl && this.activeTab === "archive") {
      const hadInputFocus =
        typeof document !== "undefined" &&
        document.activeElement?.id === "archive-answer";
      mainEl.innerHTML = renderArchivePage(this.archiveController.getState());
      attachArchiveEventListeners(this.rootElement, this.archiveController);
      this.attachTabButtons(mainEl as HTMLElement);
      if (hadInputFocus && this.archiveController.getState().status !== "submitting") {
        mainEl
          .querySelector<HTMLInputElement>("#archive-answer")
          ?.focus({ preventScroll: true });
      }
      const feedback = this.rootElement.querySelector(".feedback");
      if (feedback) {
        feedback.scrollIntoView?.({ block: "nearest" });
      }
    }
  }

  private renderProfileContent(): void {
    const mainEl = this.rootElement.querySelector("#app-content");
    if (mainEl && this.activeTab === "profile") {
      mainEl.innerHTML = renderProfilePage(
        this.profileController.getState(),
      );
      attachProfileEventListeners(
        this.rootElement,
        this.profileController,
      );
      this.attachTabButtons(mainEl as HTMLElement);
      const heading = mainEl.querySelector<HTMLElement>("#profile-heading");
      if (heading) {
        heading.tabIndex = -1;
        heading.focus({ preventScroll: true });
      }
    }
  }

  private renderShopContent(): void {
    const mainEl = this.rootElement.querySelector("#app-content");
    if (mainEl && this.activeTab === "shop") {
      mainEl.innerHTML = renderShopPage(this.shopController.getState());
      attachShopEventListeners(this.rootElement, this.shopController);
    }
  }

  private renderReportsContent(): void {
    const mainEl = this.rootElement.querySelector("#app-content");
    if (mainEl && this.activeTab === "reports") {
      mainEl.innerHTML = renderPrototype("reports", this.supportController.getState());
      attachSupportEventListeners(this.rootElement, this.supportController);
      this.attachTabButtons(mainEl as HTMLElement);
    }
  }

  private renderEventsContent(): void {
    const mainEl = this.rootElement.querySelector("#app-content");
    if (mainEl && this.activeTab === "events") {
      const hadInputFocus =
        typeof document !== "undefined" &&
        document.activeElement?.id === "events-answer";
      mainEl.innerHTML = renderEventsPage(this.eventsController);
      attachEventsEventListeners(
        this.rootElement,
        this.eventsController,
        {
          onOpenTraining: () => {
            this.activeTab = "arena";
            this.arenaController.setSubview("training");
            if (
              !this.trainingController.getState().data &&
              this.trainingController.getState().status === "idle"
            ) {
              void this.trainingController.init();
            }
            this.render();
          },
        },
      );
      this.attachTabButtons(mainEl as HTMLElement);
      const state = this.eventsController.getState();
      const event = this.eventsController.selected();
      if (
        hadInputFocus &&
        state.status !== "submitting" &&
        state.status !== "loading" &&
        event &&
        !event.progress.finished
      ) {
        mainEl
          .querySelector<HTMLInputElement>("#events-answer")
          ?.focus({ preventScroll: true });
      }
      const terminalOrFeedback = this.rootElement.querySelector(
        ".event-terminal, .feedback",
      );
      if (terminalOrFeedback && event?.progress.finished) {
        terminalOrFeedback.scrollIntoView?.({ block: "nearest" });
      }
    }
  }

  private renderReferralContent(): void {
    const mainEl = this.rootElement.querySelector("#app-content");
    if (mainEl && this.activeTab === "referral") {
      mainEl.innerHTML = renderReferralPage(
        this.referralController.getState(),
        this.referralController.getSelectedMilestone(),
      );
      attachReferralEventListeners(
        this.rootElement,
        this.referralController,
        (tab) => this.setTab(tab),
      );
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
        pageHtml = renderProfilePage(this.profileController.getState());
        break;
      case "leaderboard":
        pageHtml = renderLeaderboardPage(
          this.leaderboardController.getState(),
        );
        break;
      case "archive":
        pageHtml = renderArchivePage(this.archiveController.getState());
        break;
      case "shop":
        pageHtml = renderShopPage(this.shopController.getState());
        break;
      case "referral":
        pageHtml = renderReferralPage(
          this.referralController.getState(),
          this.referralController.getSelectedMilestone(),
        );
        break;
      case "events":
        pageHtml = renderEventsPage(this.eventsController);
        break;
      default:
        pageHtml = renderPrototype(
          this.activeTab,
          this.activeTab === "reports" ? this.supportController.getState() : undefined,
        );
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

  /**
   * Any button[data-tab] inside `scope` navigates via setTab() - the header, nav bar and
   * every page that links elsewhere (profile -> referral, arena -> events/archive, the
   * support screens' back link...) relies on this. A partial re-render of a single page
   * (renderXContent()) replaces that page's DOM, so its data-tab buttons need rewiring here
   * too, not just the header/nav bar that a full render() already covers.
   */
  private attachTabButtons(scope: HTMLElement): void {
    scope
      .querySelectorAll<HTMLButtonElement>("button[data-tab]")
      .forEach((btn) => {
        btn.addEventListener("click", (e) => {
          e.preventDefault();
          const tab = btn.dataset.tab as NavTabId;
          if (tab) {
            this.setTab(tab);
          }
        });
      });
  }

  private attachEventListeners(): void {
    this.attachTabButtons(this.rootElement);

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
    } else if (this.activeTab === "archive") {
      attachArchiveEventListeners(
        this.rootElement,
        this.archiveController,
      );
    } else if (this.activeTab === "profile") {
      attachProfileEventListeners(
        this.rootElement,
        this.profileController,
      );
    } else if (this.activeTab === "shop") {
      attachShopEventListeners(
        this.rootElement,
        this.shopController,
      );
    } else if (this.activeTab === "referral") {
      attachReferralEventListeners(
        this.rootElement,
        this.referralController,
        (tab) => this.setTab(tab),
      );
    } else if (this.activeTab === "events") {
      attachEventsEventListeners(
        this.rootElement,
        this.eventsController,
        {
          onOpenTraining: () => {
            this.activeTab = "arena";
            this.arenaController.setSubview("training");
            if (
              !this.trainingController.getState().data &&
              this.trainingController.getState().status === "idle"
            ) {
              void this.trainingController.init();
            }
            this.render();
          },
        },
      );
    } else if (this.activeTab === "reports") {
      attachSupportEventListeners(this.rootElement, this.supportController);
    }
  }
}
