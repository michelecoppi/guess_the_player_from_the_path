import { renderPrototype, attachSupportEventListeners } from "@/prototypes/screens";
import { SupportController } from "@/features/support/controller";
import { connectTheme } from "@/telegram/theme";
import { renderHeader } from "@/components/Header";
import { renderNavBar, type NavTabId } from "@/components/NavBar";
import { renderDailyPage, attachDailyEventListeners } from "@/pages/DailyPage";
import {
  renderArenaPage,
  attachArenaEventListeners,
  registerStoryView,
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
  renderReferralPage,
  attachReferralEventListeners,
} from "@/pages/ReferralPage";
import {
  initTelegram,
  getTelegramUser,
  getTelegramWebApp,
  isMockTelegramEnvironment,
} from "@/telegram/webapp";
import type { TelegramBackButton, TelegramWebApp } from "@/telegram/types";
import { onSessionExpired } from "@/api/client";
import { renderErrorState } from "@/components/ErrorState";
import { resolveLanguage, setLanguage, t } from "@/i18n";
import { v } from "@/i18n/visual";
import { DailyController } from "@/features/daily/controller";
import { ArenaController } from "@/features/arena/controller";
import { TrainingController } from "@/features/training/controller";
import { StoryController } from "@/features/story/controller";
import { LeaderboardController } from "@/features/leaderboard/controller";
import { ArchiveController } from "@/features/archive/controller";
import { ProfileController } from "@/features/profile/controller";
import { ShopController } from "@/features/shop/controller";
import { ReferralController } from "@/features/referral/controller";
import { EventsController } from "@/features/events/controller";
import { renderLoadingState } from "@/components/LoadingState";
import { lazyModule, type LazyModule } from "./lazy";

// Shop, Story and Events views are separate chunks, fetched on first use or by
// prefetchLazyViews() once the Daily is on screen (#187).
const shopView = lazyModule(() => import("@/pages/ShopPage"));
const eventsView = lazyModule(() => import("@/pages/EventsPage"));
const storyView = lazyModule(() =>
  import("@/features/story/views").then((views) => {
    registerStoryView(views.renderStoryView);
    return views;
  }),
);
const LAZY_VIEWS: LazyModule<unknown>[] = [shopView, eventsView, storyView];

export class App {
  private rootElement: HTMLElement;
  private activeTab: NavTabId = "play";
  private dailyController: DailyController;
  private arenaController: ArenaController;
  private trainingController: TrainingController;
  private storyController: StoryController;
  private leaderboardController: LeaderboardController;
  private archiveController: ArchiveController;
  private profileController: ProfileController;
  private shopController: ShopController;
  private referralController: ReferralController;
  private eventsController: EventsController;
  private supportController: SupportController;
  private lastArenaSubview: ArenaSubview;
  private firstLoad: Promise<void> = Promise.resolve();
  private resumeListenerAttached = false;
  private sessionExpired = false;
  private stopSessionExpiredListener: (() => void) | null = null;
  private backButton: TelegramBackButton | null = null;
  private closingConfirmationEnabled = false;
  private readonly handleBack = (): void => this.goBack();

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
    storyController?: StoryController,
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
    this.storyController = storyController || new StoryController();
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
      this.syncClosingConfirmation();
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
        } else if (state.subview === "story") {
          if (subviewChanged) {
            // Re-enters at the episode menu every time, so progress made elsewhere shows up.
            void this.storyController.init();
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

    this.storyController.subscribe(() => {
      if (
        this.isArenaTab(this.activeTab) &&
        this.arenaController.getState().subview === "story"
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
      this.syncClosingConfirmation();
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

  public getStoryController(): StoryController {
    return this.storyController;
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
    this.connectBackButton(tg);

    // Deep-link check for duel invite
    const inviteCode = this.arenaController.detectInvitationCode();
    if (inviteCode) {
      this.activeTab = "arena";
    }

    this.sessionExpired = false;
    this.stopSessionExpiredListener ??= onSessionExpired(() => {
      if (this.sessionExpired) return;
      this.sessionExpired = true;
      this.render();
    });
    this.render();
    if (!this.resumeListenerAttached) {
      document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible" && this.activeTab === "play" && !this.sessionExpired &&
            this.dailyController.getState().status !== "submitting") {
          void this.dailyController.loadDailyData({ lightweight: true });
        }
      });
      this.resumeListenerAttached = true;
    }
    this.firstLoad = Promise.resolve(this.dailyController.init());
    if (inviteCode) void this.arenaController.init();
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
    // Every tab would start requests the server rejects: only reopening the app helps (#179).
    if (this.sessionExpired) return;
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
      const storyState = this.storyController.getState();

      if (arenaState.subview === "training") {
        const hadInputFocus =
          typeof document !== "undefined" &&
          document.activeElement?.id === "training-answer";

        mainEl.innerHTML = this.arenaPageHtml();
        attachArenaEventListeners(
          this.rootElement,
          this.arenaController,
          this.trainingController,
          this.storyController,
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
      } else if (arenaState.subview === "story") {
        const hadInputFocus =
          typeof document !== "undefined" &&
          document.activeElement?.id === "story-answer";

        mainEl.innerHTML = this.arenaPageHtml();
        attachArenaEventListeners(
          this.rootElement,
          this.arenaController,
          this.trainingController,
          this.storyController,
        );
        this.attachTabButtons(mainEl as HTMLElement);
        this.attachLazyRetry(mainEl as HTMLElement);

        if (hadInputFocus && storyState.status !== "loading") {
          mainEl
            .querySelector<HTMLInputElement>("#story-answer")
            ?.focus({ preventScroll: true });
        }

        if (storyState.lastFeedback) {
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

        mainEl.innerHTML = this.arenaPageHtml();
        attachArenaEventListeners(
          this.rootElement,
          this.arenaController,
          this.trainingController,
          this.storyController,
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
    const view = shopView.module;
    // Until the chunk is in, the loading/retry state stays; the load re-renders the page.
    if (mainEl && this.activeTab === "shop" && view) {
      mainEl.innerHTML = view.renderShopPage(this.shopController.getState());
      view.attachShopEventListeners(this.rootElement, this.shopController);
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
    const view = eventsView.module;
    if (mainEl && this.activeTab === "events" && view) {
      const hadInputFocus =
        typeof document !== "undefined" &&
        document.activeElement?.id === "events-answer";
      mainEl.innerHTML = view.renderEventsPage(this.eventsController);
      view.attachEventsEventListeners(
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

  /** True once the server rejected the signed initData; only reopening the app recovers (#179). */
  public isSessionExpired(): boolean {
    return this.sessionExpired;
  }

  /**
   * Replaces the whole shell: without #app-content the partial renderXContent() calls of
   * requests still in flight become no-ops, so a late page error cannot cover this screen.
   */
  private renderSessionExpired(): void {
    this.rootElement.innerHTML = `
      <main id="session-expired" class="session-expired" role="region" aria-label="${v("pageContent")}">
        ${renderErrorState({
          title: v("sessionExpiredTitle"),
          message: v("sessionExpiredMessage"),
          retryLabel: v("sessionExpiredAction"),
          retryButtonId: "session-expired-close",
        })}
      </main>
    `;
    this.rootElement.querySelector("#session-expired-close")?.addEventListener("click", () => {
      // close() drops the user back in the bot chat, where the menu button opens a fresh session.
      getTelegramWebApp()?.close();
    });
  }

  /**
   * Telegram's native back arrow (and the Android back gesture) mirrors the page's own back
   * control (#182): a modal's `[data-telegram-back]` button first, then the page's
   * `.back-link`. Clicking that control reuses its exact behavior (Story goes levels ->
   * chapters -> hub, Shop closes the detail...). Any other tab falls back to the Daily; on the
   * Daily itself the arrow is hidden, so back closes the Mini App as before. The Daily has no
   * back control, so visibility only changes with the tab or an expired session - both go
   * through render(); the target is resolved at tap time, after any partial re-render.
   */
  private connectBackButton(tg: TelegramWebApp | null): void {
    this.backButton?.offClick(this.handleBack);
    this.backButton = tg?.BackButton ?? null;
    this.backButton?.onClick(this.handleBack);
  }

  private pageBackControl(): HTMLElement | null {
    return (
      this.rootElement.querySelector<HTMLElement>("#app-content [data-telegram-back]") ??
      this.rootElement.querySelector<HTMLElement>("#app-content .back-link")
    );
  }

  private hasBackTarget(): boolean {
    return !this.sessionExpired && (this.pageBackControl() !== null || this.activeTab !== "play");
  }

  private syncBackButton(): void {
    const button = this.backButton;
    if (!button) return;
    const visible = this.hasBackTarget();
    if (visible === button.isVisible) return;
    if (visible) button.show();
    else button.hide();
  }

  /** Keep Telegram's close prompt scoped to the match currently on screen. */
  private syncClosingConfirmation(): void {
    const arena = this.arenaController.getState();
    const duel = arena.data;
    const event = this.eventsController.selected();
    const activeDuel = this.isArenaTab(this.activeTab) && arena.subview === "duel" &&
      !!arena.activeDuelCode && duel?.code === arena.activeDuelCode &&
      !!duel.session && !duel.session.finished && !duel.complete;
    const activeEvent = this.activeTab === "events" && !!event &&
      event.available && !event.progress.finished;
    const shouldEnable = !this.sessionExpired && (activeDuel || activeEvent);
    const tg = getTelegramWebApp(false);
    if (!tg || (tg.isVersionAtLeast && !tg.isVersionAtLeast("6.2"))) return;
    if (shouldEnable === (tg.isClosingConfirmationEnabled ?? this.closingConfirmationEnabled)) return;
    const method = shouldEnable ? tg.enableClosingConfirmation : tg.disableClosingConfirmation;
    if (typeof method !== "function") return;
    try {
      method.call(tg);
      this.closingConfirmationEnabled = shouldEnable;
    } catch (err) {
      console.warn("Telegram WebApp closing confirmation error:", err);
    }
  }

  public goBack(): void {
    if (!this.hasBackTarget()) return;
    const control = this.pageBackControl();
    if (control) control.click();
    else this.setTab("play");
  }

  /** Loads the Shop, Story and Events chunks ahead of use (after the Daily is on screen). */
  public prefetchLazyViews(): Promise<void> {
    return Promise.allSettled(LAZY_VIEWS.map((view) => view.load())).then(() => undefined);
  }

  private isStoryOpen(): boolean {
    return this.isArenaTab(this.activeTab) && this.arenaController.getState().subview === "story";
  }

  private arenaPageHtml(): string {
    const arenaState = this.arenaController.getState();
    if (arenaState.subview === "story" && !storyView.module) {
      return this.lazyPageHtml(storyView, () => "", () => this.isStoryOpen());
    }
    return renderArenaPage(arenaState, this.trainingController.getState(), this.storyController.getState());
  }

  /**
   * The page of a lazily loaded view: rendered when its chunk is in, otherwise a loading state
   * (starting the load) or, after a failed load, an error with a retry button. When the load
   * settles the shell re-renders - only if that page is still the one on screen, so a prefetch
   * finishing in the background never steals focus from the Daily.
   */
  private lazyPageHtml<T>(
    view: LazyModule<T>,
    render: (module: T) => string,
    stillShown?: () => boolean,
  ): string {
    if (view.module) return render(view.module);
    const tab = this.activeTab;
    const shown = stillShown ?? (() => this.activeTab === tab);
    if (view.failed) {
      return renderErrorState({
        title: t("common.error"),
        message: v("viewLoadError"),
        retryLabel: t("common.retry"),
        retryButtonId: "lazy-view-retry",
      });
    }
    const rerender = () => {
      if (shown() && !this.sessionExpired) this.render();
    };
    void view.load().then(rerender, rerender);
    return renderLoadingState({ message: t("common.loading") });
  }

  private attachLazyRetry(scope: HTMLElement): void {
    scope.querySelector<HTMLButtonElement>("#lazy-view-retry")?.addEventListener("click", (e) => {
      e.preventDefault();
      // Restarting the load clears the failure, so render() shows the spinner and re-renders
      // the page when the chunk arrives.
      LAZY_VIEWS.filter((view) => view.failed).forEach((view) => void view.load().catch(() => undefined));
      this.render();
    });
  }

  private render(): void {
    this.syncClosingConfirmation();
    if (this.sessionExpired) {
      this.renderSessionExpired();
      this.syncBackButton();
      return;
    }
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
        pageHtml = this.arenaPageHtml();
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
        pageHtml = this.lazyPageHtml(shopView, (view) => view.renderShopPage(this.shopController.getState()));
        break;
      case "referral":
        pageHtml = renderReferralPage(
          this.referralController.getState(),
          this.referralController.getSelectedMilestone(),
        );
        break;
      case "events":
        pageHtml = this.lazyPageHtml(eventsView, (view) => view.renderEventsPage(this.eventsController));
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
      <main id="app-content" role="region" aria-label="${v("pageContent")}">
        ${pageHtml}
      </main>
      ${renderNavBar({ activeTab: this.activeTab })}
    `;

    this.attachEventListeners();
    this.syncBackButton();
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
    this.attachLazyRetry(this.rootElement);

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
        this.storyController,
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
      shopView.module?.attachShopEventListeners(
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
      eventsView.module?.attachEventsEventListeners(
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
