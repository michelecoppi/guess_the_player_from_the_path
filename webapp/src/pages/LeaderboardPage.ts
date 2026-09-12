import type { LeaderboardController } from "@/features/leaderboard/controller";
import type { LeaderboardState, LeaderboardTab } from "@/features/leaderboard/types";
import { renderLeaderboardView } from "@/features/leaderboard/views";

/**
 * Renders the real Leaderboard page view using the current controller state.
 */
export function renderLeaderboardPage(state: LeaderboardState): string {
  return renderLeaderboardView(state);
}

/**
 * Attaches DOM event listeners for Leaderboard interactions.
 */
export function attachLeaderboardEventListeners(
  root: HTMLElement,
  controller: LeaderboardController,
): void {
  // Leaderboard sub-tabs: Global vs Leagues
  const tabButtons = root.querySelectorAll<HTMLButtonElement>("button[data-leaderboard-tab]");
  tabButtons.forEach((btn) => {
    btn.onclick = (e) => {
      e.preventDefault();
      const tab = btn.dataset.leaderboardTab as LeaderboardTab;
      if (tab === "global" || tab === "leagues") {
        controller.setTab(tab);
      }
    };
  });

  // League pills selection
  const leagueButtons = root.querySelectorAll<HTMLButtonElement>("button[data-select-league]");
  leagueButtons.forEach((btn) => {
    btn.onclick = (e) => {
      e.preventDefault();
      const code = btn.dataset.selectLeague;
      if (code) {
        controller.selectLeague(code);
      }
    };
  });

  // Public profile open clicks
  const profileButtons = root.querySelectorAll<HTMLButtonElement>("button[data-profile-id]");
  profileButtons.forEach((btn) => {
    btn.onclick = (e) => {
      e.preventDefault();
      const rawId = btn.dataset.profileId;
      const profileId = Number(rawId);
      if (Number.isSafeInteger(profileId) && profileId > 0) {
        void controller.openPublicProfile(profileId);
      }
    };
  });

  // Close public profile
  const closeProfileBtn = root.querySelector<HTMLButtonElement>("button[data-action='close-profile']");
  if (closeProfileBtn) {
    closeProfileBtn.onclick = (e) => {
      e.preventDefault();
      controller.closePublicProfile();
    };
  }

  // Retry public profile
  const retryProfileBtn = root.querySelector<HTMLButtonElement>("button[data-action='retry-profile']");
  if (retryProfileBtn) {
    retryProfileBtn.onclick = (e) => {
      e.preventDefault();
      void controller.retryPublicProfile();
    };
  }

  // Refresh leaderboard
  const refreshBtn = root.querySelector<HTMLButtonElement>(
    "button[data-action='refresh-leaderboard'], #refresh-leaderboard-btn"
  );
  if (refreshBtn) {
    refreshBtn.onclick = (e) => {
      e.preventDefault();
      void controller.refresh();
    };
  }
}
