import { renderProfileCosmeticArt } from '@/components/CosmeticArt';
import { renderStyleInventory } from "@/components/StyleInventory";
import { v } from "@/i18n/visual";
import { identityAppearance } from "@/appearance";
import { escapeHtml } from "@/utils/format";
import { renderAvatar } from "@/components/Avatar";
import { profileSurfaceAttributes } from "@/appearance/surfaces";
import { t, tCount } from "@/i18n";
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

  // The frame someone bought is shown where others see it; the server sends it already
  // resolved and parseResolvedAppearance only lets through reviewed paints.
  const frame = identityAppearance({ frame: "frame" in entry ? entry.frame : undefined }).frame;
  // Same effects as on the profile: the reviewed motion (shine, pulse, orbit) and the tactics
  // dots. Perpetual spin stays off everywhere in V2 (appearance/surfaces.ts).
  const avatar = renderAvatar({
    name: entry.name,
    size: "small",
    ringStyle: frame.ring ? `background: ${frame.ring}` : undefined,
    ringMotion: frame.motion,
    tactics: frame.tactics,
    photoUrl: entry.avatar || undefined,
    extraClass: "row-avatar",
  });
  const podium = entry.position >= 1 && entry.position <= 3 ? ` podium podium-${entry.position}` : "";

  return `
    <div class="row${isMe ? " me" : ""}${podium}" role="listitem" ${isMe ? 'aria-current="true"' : ""}>
      <span class="pos" aria-label="${escapeHtml(t("leaderboard.positionLabel", { n: pos }))}">${pos}</span>
      ${avatar}
      <div class="name">${nameHtml}</div>
      <span class="pts" aria-label="${escapeHtml(t("leaderboard.pointsLabel", { n: pts }))}">${pts}</span>
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
  const cosmetics = identityAppearance(p.cosmetics);
  const badge = cosmetics.badge || "";
  const number = cosmetics.number || "";
  const shirt = number ? `<span class="shirt">${escapeHtml(number)}</span>` : "";
  const trophiesCount = u.trophies ?? 0;


  return `
    <section class="public-profile-view" ${profileSurfaceAttributes(p.cosmetics)} aria-label="${escapeHtml(t("leaderboard.publicProfileTitle"))}">
      ${backBtn}
      <div class="card profile-hero mt-3">
        ${renderAvatar({name:u.name,size:'large',photoUrl:u.avatar || undefined,tactics:cosmetics.frame.tactics,ringMotion:cosmetics.frame.motion,ringStyle:cosmetics.frame.ring ? `background: ${cosmetics.frame.ring}` : undefined})}
        <div class="hero-info">
          <p class="eyebrow">${escapeHtml(t("leaderboard.publicProfileTitle"))}</p>
          <h2 id="public-profile-heading" tabindex="-1">
            ${shirt}${escapeHtml(u.name)}${badge ? ` ${escapeHtml(badge)}` : ""}
          </h2>
          ${cosmetics.title.label ? `<p class="cosmetic-title"${cosmetics.title.color ? ` style="border-color:${escapeHtml(cosmetics.title.color)}"` : ''}>${escapeHtml(cosmetics.title.label)}</p>` : ''}
          <p class="muted text-xs">${escapeHtml(tCount("common.trophiesCount", trophiesCount))}</p>
        </div>
      </div>
      ${renderProfileCosmeticArt(p.cosmetics)}
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
      ${renderStyleInventory(p.wearing, p.wardrobe, p.cosmetics?.equipped)}
    </section>
  `.trim();
}

function renderPlayerSearch(state: LeaderboardState): string {
  const expanded = state.searchExpanded !== false && (!!state.searchExpanded || !!state.search?.query);
  const search = state.search;
  const result = search?.status === 'loading' ? `<p role="status">${escapeHtml(t('common.loading'))}</p>`
    : search?.status === 'error' ? `<p role="alert">${escapeHtml(v('searchError'))}</p><button class="btn ghost" id="leaderboard-search-retry">${escapeHtml(t('common.retry'))}</button>`
    : search?.status === 'ready' ? (search.results.length ? `<ul class="player-search-results" aria-label="${escapeHtml(v('results'))}">${search.results.map(user => `<li><button type="button" class="player-search-result" data-profile-id="${user.profile_id}"><span>${escapeHtml(user.name)} ${escapeHtml(user.badge || '')}</span><small>${user.points} ${escapeHtml(t('common.points'))}</small>${icon('arrow')}</button></li>`).join('')}</ul>` : `<p role="status">${escapeHtml(v('noPlayers'))}</p>`)
    : '';
  return `<div class="player-search-control"><button type="button" class="player-search-toggle" id="leaderboard-search-toggle" aria-expanded="${expanded}" aria-controls="leaderboard-player-search">${icon('search')}${escapeHtml(v('findPlayer'))}${icon('arrow')}</button></div>
  ${expanded ? `<section class="player-search" id="leaderboard-player-search" aria-label="${escapeHtml(v('findPlayer'))}">
    <label for="leaderboard-search">${escapeHtml(v('findPlayer'))}</label>
    <input id="leaderboard-search" type="text" inputmode="search" autocomplete="off" maxlength="80" placeholder="${escapeHtml(v('searchPlaceholder'))}" value="${escapeHtml(search?.query || '')}" aria-describedby="leaderboard-search-hint">
    <p id="leaderboard-search-hint" class="muted">${escapeHtml(v('searchHint'))}</p>
    <div aria-live="polite">${result}</div>
  </section>` : ''}`;
}

/**
 * Renders a top-10 ranking tab: the monthly one (points of the current month) or the
 * all-time global one. Same rows, different source list and empty state.
 */
function renderRankingTab(state: LeaderboardState, tab: "monthly" | "global"): string {
  const monthly = tab === "monthly";
  const entries = monthly ? state.monthlyLeaderboard : state.globalLeaderboard;
  const rowsHtml = entries.slice(0, 10)
    .map((entry) => renderLeaderboardRow(entry, entry.badge))
    .join("");
  const empty = monthly
    ? renderEmptyState({ icon: icon('ranking'), title: t('leaderboard.emptyMonthlyTitle'), description: t('leaderboard.emptyMonthly') })
    : renderEmptyState({ icon: icon('ranking'), title: t('leaderboard.emptyGlobalTitle'), description: t('leaderboard.emptyGlobal') });

  return `
    <div class="leaderboard-tab-content" id="leaderboard-panel-${tab}" role="tabpanel" aria-labelledby="leaderboard-tab-${tab}">
      ${renderPlayerSearch(state)}
      <div class="ranking-caption"><h3 class="section-heading">${escapeHtml(v('topTen'))}</h3></div>
      ${monthly ? `<p class="leaderboard-hint muted text-xs">${escapeHtml(t("leaderboard.monthlyHint"))}</p>` : ""}
      <p class="leaderboard-hint muted text-xs">${escapeHtml(t("leaderboard.tapProfileHint"))}</p>
      <div class="leaderboard-columns" aria-hidden="true">
        <span>${escapeHtml(t("leaderboard.colPosPlayer"))}</span>
        <span>${escapeHtml(t("leaderboard.colPoints"))}</span>
      </div>
      <div class="leaderboard-list" role="list" aria-label="${escapeHtml(t(monthly ? "leaderboard.tabMonthly" : "leaderboard.tabGlobal"))}">
        ${rowsHtml || empty}
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

function hasRankings(state: LeaderboardState): boolean {
  return state.globalLeaderboard.length > 0 || state.monthlyLeaderboard.length > 0;
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

  if (state.status === "loading" && !hasRankings(state)) {
    return `
      <section class="leaderboard-section" aria-label="${escapeHtml(t("leaderboard.title"))}">
        ${headerHtml}
        <div class="mt-4">
          ${renderLoadingState({ message: t("common.loading") })}
        </div>
      </section>
    `;
  }

  if (state.status === "error" && !hasRankings(state)) {
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

  const isMonthly = state.activeTab === "monthly";
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
        id="leaderboard-tab-monthly"
        class="leaderboard-tab-btn${isMonthly ? " active" : ""}"
        data-leaderboard-tab="monthly"
        role="tab"
        aria-selected="${isMonthly}"
        aria-controls="leaderboard-panel-monthly"
      >
        ${escapeHtml(t("leaderboard.tabMonthly"))}
      </button>
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

  const tabContent = isLeagues ? renderLeaguesTab(state) : renderRankingTab(state, isGlobal ? "global" : "monthly");

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
