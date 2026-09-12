import { escapeHtml, initials } from "@/utils/format";
import { t } from "@/i18n";
import { icon } from "@/components/Icon";
import { renderStatTile } from "@/components/StatTile";
import { renderLoadingState } from "@/components/LoadingState";
import { renderErrorState } from "@/components/ErrorState";
import { renderEmptyState } from "@/components/EmptyState";
import type {
  LeaderboardEntry,
  LeaderboardState,
  LeagueStanding,
  PublicProfileState,
} from "./types";

/**
 * Renders a single leaderboard row (used for both global ranking and league standings).
 */
export function renderLeaderboardRow(
  entry: LeaderboardEntry | LeagueStanding,
  badge?: string,
): string {
  const isMe = !!entry.me;
  const pos = escapeHtml(String(entry.position));
  const pts = escapeHtml(String(entry.points));
  const badgeText = badge ? badge + " " : "";
  const displayName = badgeText + entry.name;
  const isClickable =
    Number.isSafeInteger(entry.profile_id) && (entry.profile_id as number) > 0;

  const meTag = isMe
    ? ` <span class="me-tag" aria-label="${escapeHtml(t("leaderboard.youLabel"))}">(${escapeHtml(t("leaderboard.youLabel"))})</span>`
    : "";

  const nameHtml = isClickable
    ? `<button type="button" class="profile-link-btn" data-profile-id="${entry.profile_id}" aria-label="${escapeHtml(t("leaderboard.openProfile") + " · " + entry.name)}"><span class="player-name">${escapeHtml(displayName)}</span>${meTag}</button>`
    : `<span class="player-name">${escapeHtml(displayName)}${meTag}</span>`;

  return `
    <div class="row${isMe ? " me" : ""}" role="listitem" ${isMe ? 'aria-current="true"' : ""}>
      <span class="pos" aria-label="Posizione ${pos}">${pos}</span>
      <div class="name">${nameHtml}</div>
      <span class="pts" aria-label="${pts} punti">${pts}</span>
    </div>
  `.trim();
}

/**
 * Renders the public profile subview when a player row has been clicked.
 */
export function renderPublicProfileView(publicProfile: PublicProfileState): string {
  const backBtn = `
    <button type="button" class="btn ghost back-link" data-action="close-profile" aria-label="${escapeHtml(t("leaderboard.backToLeaderboard"))}">
      ${icon("back")}
      <span>${escapeHtml(t("leaderboard.backToLeaderboard"))}</span>
    </button>
  `.trim();

  if (publicProfile.status === "loading") {
    return `
      <section class="public-profile-view" aria-label="${escapeHtml(t("leaderboard.publicProfileTitle"))}">
        ${backBtn}
        <div class="mt-4">
          ${renderLoadingState({ message: t("common.loading") })}
        </div>
      </section>
    `;
  }

  if (publicProfile.status === "error" || !publicProfile.data) {
    return `
      <section class="public-profile-view" aria-label="${escapeHtml(t("leaderboard.publicProfileTitle"))}">
        ${backBtn}
        <div class="card mt-4">
          <p class="error-msg">${escapeHtml(t("leaderboard.publicProfileUnavailable"))}</p>
          <button type="button" class="btn mt-3" data-action="retry-profile">
            ${escapeHtml(t("common.retry"))}
          </button>
        </div>
      </section>
    `;
  }

  const p = publicProfile.data;
  const u = p.user;
  const cosmetics = p.cosmetics || {};
  const equipped = cosmetics.equipped || {};
  const badge = equipped.badge || "";
  const number = equipped.number || "";
  const shirt = number ? `<span class="shirt">${escapeHtml(number)}</span>` : "";
  const trophiesCount = u.trophies ?? 0;

  const wearingHtml =
    p.wearing && p.wearing.length > 0
      ? `
        <div class="card">
          <h3 class="section-heading">${escapeHtml(t("leaderboard.wearing"))}</h3>
          <div class="pack-contents">
            ${p.wearing.map((item) => `<span class="wearing-chip">${escapeHtml(item.name)}</span>`).join("")}
          </div>
        </div>
      `
      : "";

  return `
    <section class="public-profile-view" aria-label="${escapeHtml(t("leaderboard.publicProfileTitle"))}">
      ${backBtn}
      <div class="card profile-hero mt-3">
        <div class="avatar-wrap large">
          <div class="avatar">${escapeHtml(initials(u.name))}</div>
        </div>
        <div class="hero-info">
          <p class="eyebrow">${escapeHtml(t("leaderboard.publicProfileTitle"))}</p>
          <h1 id="public-profile-heading" tabindex="-1">
            ${shirt}${escapeHtml(u.name)}${badge ? ` ${escapeHtml(badge)}` : ""}
          </h1>
          <p class="muted text-xs">${trophiesCount} ${escapeHtml(t("leaderboard.trophies"))}</p>
        </div>
      </div>
      <div class="card">
        <h3 class="section-heading">${escapeHtml(t("leaderboard.numbers"))}</h3>
        <div class="stat-grid three-cols">
          ${renderStatTile({ value: u.points ?? 0, label: t("leaderboard.totalPoints") })}
          ${renderStatTile({ value: u.monthly_points ?? 0, label: t("leaderboard.monthlyPoints") })}
          ${renderStatTile({ value: u.players_guessed ?? 0, label: t("leaderboard.guessed") })}
          ${renderStatTile({ value: u.streak ?? 0, label: t("leaderboard.streak") })}
          ${renderStatTile({ value: u.best_streak ?? 0, label: t("leaderboard.bestStreak") })}
          ${renderStatTile({ value: u.archive_solved ?? 0, label: t("leaderboard.recovered") })}
        </div>
      </div>
      ${wearingHtml}
    </section>
  `.trim();
}

/**
 * Renders the global ranking tab.
 */
function renderGlobalTab(state: LeaderboardState): string {
  if (state.globalLeaderboard.length === 0) {
    return renderEmptyState({
      icon: icon("ranking"),
      title: t("leaderboard.emptyGlobalTitle"),
      description: t("leaderboard.emptyGlobal"),
    });
  }

  const rowsHtml = state.globalLeaderboard
    .map((entry) => renderLeaderboardRow(entry, entry.badge))
    .join("");

  return `
    <div class="leaderboard-tab-content" id="leaderboard-panel-global" role="tabpanel" aria-labelledby="leaderboard-tab-global">
      <p class="leaderboard-hint muted text-xs">${escapeHtml(t("leaderboard.tapProfileHint"))}</p>
      <div class="leaderboard-columns" aria-hidden="true">
        <span>${escapeHtml(t("leaderboard.colPosPlayer"))}</span>
        <span>${escapeHtml(t("leaderboard.colPoints"))}</span>
      </div>
      <div class="leaderboard-list" role="list" aria-label="${escapeHtml(t("leaderboard.tabGlobal"))}">
        ${rowsHtml}
      </div>
    </div>
  `.trim();
}

/**
 * Renders the private leagues tab.
 */
function renderLeaguesTab(state: LeaderboardState): string {
  if (state.leagues.length === 0) {
    return renderEmptyState({
      icon: icon("ranking"),
      title: t("leaderboard.emptyLeaguesTitle"),
      description: t("leaderboard.emptyLeagues"),
    });
  }

  const selectedCode = state.selectedLeagueCode || state.leagues[0]?.code;
  const activeLeague =
    state.leagues.find((l) => l.code === selectedCode) || state.leagues[0];

  const pillsHtml =
    state.leagues.length > 1
      ? `
        <div class="league-pills" role="tablist" aria-label="${escapeHtml(t("leaderboard.tabLeagues"))}">
          ${state.leagues
            .map((league) => {
              const isSelected = league.code === activeLeague.code;
              return `
                <button
                  type="button"
                  class="league-pill${isSelected ? " active" : ""}"
                  data-select-league="${escapeHtml(league.code)}"
                  role="tab"
                  aria-selected="${isSelected}"
                >
                  ${escapeHtml(league.name)}
                </button>
              `.trim();
            })
            .join("")}
        </div>
      `
      : "";

  const standingsHtml =
    activeLeague.standings && activeLeague.standings.length > 0
      ? activeLeague.standings.map((m) => renderLeaderboardRow(m)).join("")
      : `<p class="muted p-3">${escapeHtml(t("leaderboard.noMembers"))}</p>`;

  const yourStatsHtml = activeLeague.position
    ? ` · ${escapeHtml(t("leaderboard.yourPosition").replace("{n}", String(activeLeague.position)))} · ${escapeHtml(t("leaderboard.yourPoints").replace("{n}", String(activeLeague.points)))}`
    : "";

  return `
    <div class="leaderboard-tab-content" id="leaderboard-panel-leagues" role="tabpanel" aria-labelledby="leaderboard-tab-leagues">
      ${pillsHtml}
      <div class="league-card card mt-3">
        <div class="league-card-header">
          <h3 class="league-name">
            ${escapeHtml(activeLeague.name)}
            <small class="league-code">· ${escapeHtml(activeLeague.code)}</small>
          </h3>
          <p class="league-meta muted text-xs">
            ${activeLeague.members} ${escapeHtml(t("leaderboard.leagueMembers"))}${yourStatsHtml}
          </p>
        </div>
        <div class="leaderboard-columns mt-3" aria-hidden="true">
          <span>${escapeHtml(t("leaderboard.colPosPlayer"))}</span>
          <span>${escapeHtml(t("leaderboard.colPoints"))}</span>
        </div>
        <div class="leaderboard-list" role="list" aria-label="${escapeHtml(activeLeague.name)}">
          ${standingsHtml}
        </div>
      </div>
    </div>
  `.trim();
}

/**
 * Main view renderer for Leaderboard & Leagues.
 */
export function renderLeaderboardView(state: LeaderboardState): string {
  if (state.publicProfile) {
    return renderPublicProfileView(state.publicProfile);
  }

  const headerHtml = `
    <div class="leaderboard-header">
      <span class="eyebrow">${escapeHtml(t("leaderboard.kicker"))}</span>
      <h2 class="page-title">${escapeHtml(t("leaderboard.title"))}</h2>
    </div>
  `.trim();

  if (state.status === "loading" && state.globalLeaderboard.length === 0) {
    return `
      <section class="leaderboard-section" aria-label="${escapeHtml(t("leaderboard.title"))}">
        ${headerHtml}
        <div class="mt-4">
          ${renderLoadingState({ message: t("common.loading") })}
        </div>
      </section>
    `;
  }

  if (state.status === "error" && state.globalLeaderboard.length === 0) {
    return `
      <section class="leaderboard-section" aria-label="${escapeHtml(t("leaderboard.title"))}">
        ${headerHtml}
        <div class="mt-4">
          ${renderErrorState({
            message: t("leaderboard.loadError"),
            retryLabel: t("common.retry"),
            retryButtonId: "refresh-leaderboard-btn",
          })}
        </div>
      </section>
    `;
  }

  const isGlobal = state.activeTab === "global";
  const isLeagues = state.activeTab === "leagues";
  const leaguesBadge =
    state.leagues.length > 0
      ? ` <span class="badge-count">(${state.leagues.length})</span>`
      : "";

  const tabsNav = `
    <div class="leaderboard-tabs" role="tablist" aria-label="${escapeHtml(t("leaderboard.title"))}">
      <button
        type="button"
        id="leaderboard-tab-global"
        class="leaderboard-tab-btn${isGlobal ? " active" : ""}"
        data-leaderboard-tab="global"
        role="tab"
        aria-selected="${isGlobal}"
        aria-controls="leaderboard-panel-global"
      >
        ${escapeHtml(t("leaderboard.tabGlobal"))}
      </button>
      <button
        type="button"
        id="leaderboard-tab-leagues"
        class="leaderboard-tab-btn${isLeagues ? " active" : ""}"
        data-leaderboard-tab="leagues"
        role="tab"
        aria-selected="${isLeagues}"
        aria-controls="leaderboard-panel-leagues"
      >
        ${escapeHtml(t("leaderboard.tabLeagues"))}${leaguesBadge}
      </button>
    </div>
  `.trim();

  const tabContent = isGlobal ? renderGlobalTab(state) : renderLeaguesTab(state);

  return `
    <section class="leaderboard-section" aria-label="${escapeHtml(t("leaderboard.title"))}">
      ${headerHtml}
      ${tabsNav}
      <div class="leaderboard-body mt-3">
        ${tabContent}
      </div>
    </section>
  `.trim();
}
