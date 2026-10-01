import { renderProfileCosmeticArt } from '@/components/CosmeticArt';
import { renderStyleInventory } from "@/components/StyleInventory";
import { renderAvatar } from "@/components/Avatar";
import { renderStatTile } from "@/components/StatTile";
import { renderLoadingState } from "@/components/LoadingState";
import { renderErrorState } from "@/components/ErrorState";
import { icon } from "@/components/Icon";
import { escapeHtml } from "@/utils/format";
import { renderRecapProfileEntry } from "@/features/recap/entry";
import { histogram, cabinetCounts } from "@/utils/game";
import { identityAppearance } from "@/appearance";
import { profileSurfaceAttributes } from "@/appearance/surfaces";
import { t, tCount, getLanguage } from "@/i18n";
import type { ArchiveCalendarDay } from "@/features/archive/types";
import { v } from "@/i18n/visual";
import type {
  CabinetFilter,
  ProfileState,
  TrophyPlate,
} from "./types";

/**
 * Resolves a localized accessible placement label for assistive technology.
 * Relies strictly on the authoritative backend `position` number.
 */
export function getTrophyPlacementLabel(position?: number): string {
  if (typeof position !== "number" || isNaN(position) || position <= 0) {
    return "";
  }
  if (position === 1) return t("profile.placementFirst");
  if (position === 2) return t("profile.placementSecond");
  if (position === 3) return t("profile.placementThird");
  return t("profile.placementOther").replace("{n}", String(position));
}

/**
 * Renders a single trophy plate badge (used in profile showcase and pinned preview).
 */
export function renderTrophyPlate(tag: TrophyPlate): string {
  const placementLabel = getTrophyPlacementLabel(tag.position);
  const placementHtml = placementLabel
    ? `<span class="sr-only">${escapeHtml(placementLabel)}</span>`
    : "";
  return `
    <span class="trophy-tag" style="--plate: ${escapeHtml(tag.color)}">
      <span class="medal" aria-hidden="true">${escapeHtml(tag.medal)}</span>
      ${placementHtml}
      <span class="plate-name">${escapeHtml(tag.label)}</span>
      <span class="plate-detail">${escapeHtml(tag.detail)}</span>
    </span>
  `.trim();
}

/**
 * Renders a collection of trophy plates.
 */
export function renderTrophyPlates(tags: TrophyPlate[]): string {
  if (!tags || tags.length === 0) {
    return "";
  }
  return `
    <div class="trophy-tags">
      ${tags.map((tag) => renderTrophyPlate(tag)).join("")}
    </div>
  `.trim();
}

/**
 * Renders a single interactive trophy row in the cabinet list.
 */
function renderCabinetRow(
  tag: TrophyPlate,
  chosen: boolean,
  isPinning: boolean,
): string {
  const pinLabel = chosen ? t("profile.cabinetPinned") : t("profile.cabinetPin");
  const placementLabel = getTrophyPlacementLabel(tag.position);
  const placementHtml = placementLabel
    ? `<span class="sr-only">${escapeHtml(placementLabel)}</span>`
    : "";
  return `
    <button
      type="button"
      class="cabinet-row"
      data-pin="${escapeHtml(tag.code)}"
      aria-pressed="${chosen}"
      ${isPinning ? "disabled" : ""}
      style="--plate: ${escapeHtml(tag.color)}"
    >
      <span class="medal" aria-hidden="true">${escapeHtml(tag.medal)}</span>
      ${placementHtml}
      <span class="cabinet-row-info">
        <span class="nm">${escapeHtml(tag.label)}</span>
        <span class="ds">${escapeHtml(tag.detail)}</span>
      </span>
      <span class="pin">${escapeHtml(pinLabel)}</span>
    </button>
  `.trim();
}

/**
 * Renders the Trophy Cabinet subview.
 */
export function renderCabinetView(state: ProfileState): string {
  const profile = state.profile;
  const backBtn = `
    <button type="button" class="btn ghost back-link" id="close-cabinet" aria-label="${escapeHtml(t("profile.cabinetBack"))}">
      ${icon("back")}
      <span>${escapeHtml(t("profile.cabinetBack"))}</span>
    </button>
  `.trim();

  if (!profile) {
    return `
      <section class="cabinet-view" aria-label="${escapeHtml(t("profile.cabinetTitle"))}">
        ${backBtn}
        <div class="card mt-3">
          <p class="muted">${escapeHtml(t("profile.noTrophies"))}</p>
        </div>
      </section>
    `.trim();
  }

  const trophiesData = profile.trophies || { pinned: [], all: [], max: 3 };
  const all = trophiesData.all || [];
  const max = trophiesData.max || 3;
  const chosenCodes =
    state.pendingPinCodes ?? (trophiesData.pinned || []).map((t) => t.code);

  if (all.length === 0) {
    return `
      <section class="cabinet-view" aria-label="${escapeHtml(t("profile.cabinetTitle"))}">
        ${backBtn}
        <div class="card mt-3">
          <h2 class="section-heading">${escapeHtml(t("profile.cabinetTitle"))}</h2>
          <p class="muted mt-2">${escapeHtml(t("profile.noTrophies"))}</p>
        </div>
      </section>
    `.trim();
  }

  // Podium medal counts: [1st, 2nd, 3rd]
  const counts = cabinetCounts(all);
  const medalsConfig: Array<{ color: string; count: number; label: string }> = [
    { color: "#e8b647", count: counts[0], label: t("profile.cabinetGold") },
    { color: "#c3ccd6", count: counts[1], label: t("profile.cabinetSilver") },
    { color: "#c98652", count: counts[2], label: t("profile.cabinetBronze") },
  ];

  const filterKeys: Array<{ key: CabinetFilter; label: string; ariaLabel?: string }> = [
    { key: "all", label: t("profile.cabinetAll") },
    { key: "1", label: "🥇", ariaLabel: t("profile.filterFirstPlace") },
    { key: "2", label: "🥈", ariaLabel: t("profile.filterSecondPlace") },
    { key: "3", label: "🥉", ariaLabel: t("profile.filterThirdPlace") },
    { key: "event", label: t("profile.cabinetEvents") },
    { key: "monthly", label: t("profile.cabinetMonthly") },
  ];

  const activeFilter = state.cabinetFilter || "all";
  const matches = (tag: TrophyPlate) =>
    activeFilter === "all" ||
    String(tag.position) === activeFilter ||
    tag.kind === activeFilter;

  const filtered = all.filter(matches);

  // Group by year descending
  const yearsMap = new Map<string, TrophyPlate[]>();
  for (const tag of filtered) {
    const yr = tag.year || "";
    if (!yearsMap.has(yr)) {
      yearsMap.set(yr, []);
    }
    yearsMap.get(yr)!.push(tag);
  }

  const sortedYears = Array.from(yearsMap.entries()).sort(
    ([a], [b]) => Number(b) - Number(a),
  );

  const pinnedPlatesHtml = renderTrophyPlates(trophiesData.pinned || []);

  const pinnedSection = pinnedPlatesHtml
    ? `
      <div class="card cabinet-pinned mt-3">
        <div class="cap eyebrow">${escapeHtml(t("profile.cabinetPinned"))}</div>
        ${pinnedPlatesHtml}
      </div>
    `
    : "";

  const alertHtml = state.pinError
    ? `<div class="alert alert-error mt-2 mb-2" role="alert">${escapeHtml(state.pinError)}</div>`
    : state.pinSuccess
      ? `<div class="alert alert-success mt-2 mb-2" role="status">${escapeHtml(t("profile.pinSaved"))}</div>`
      : "";

  const trophyListHtml =
    sortedYears.length > 0
      ? sortedYears
          .map(
            ([year, items]) => `
          <div class="cabinet-year">${escapeHtml(year)}</div>
          <div class="cabinet-list">
            ${items
              .map((tag) =>
                renderCabinetRow(
                  tag,
                  chosenCodes.includes(tag.code),
                  state.isPinning,
                ),
              )
              .join("")}
          </div>
        `,
          )
          .join("")
      : `<p class="cabinet-empty muted p-3 text-center">${escapeHtml(t("profile.cabinetNone"))}</p>`;

  return `
    <section class="cabinet-view" aria-label="${escapeHtml(t("profile.cabinetTitle"))}">
      ${backBtn}

      <div class="card mt-3">
        <div class="cabinet-head">
          <h2 class="section-heading">${escapeHtml(t("profile.cabinetTitle"))}</h2>
          <span class="muted text-xs">${escapeHtml(tCount("common.trophiesCount", all.length))}</span>
        </div>
        <div class="cabinet-medals mt-3">
          ${medalsConfig
            .map(
              (m) => `
            <div class="cabinet-medal" style="--plate: ${m.color}">
              <div class="value">${m.count}</div>
              <div class="label text-xs">${escapeHtml(m.label)}</div>
            </div>
          `,
            )
            .join("")}
        </div>
      </div>

      ${pinnedSection}

      <div class="card mt-3">
        <p class="cabinet-hint muted text-xs mb-3">
          ${escapeHtml(t("profile.cabinetHint").replace("{n}", String(max)))}
        </p>

        <div class="cabinet-filters" role="group" aria-label="${escapeHtml(t("profile.cabinetFilters"))}">
          ${filterKeys
            .map(
              (f) => `
            <button
              type="button"
              class="cabinet-filter-btn${activeFilter === f.key ? " active" : ""}"
              data-cabinet-filter="${escapeHtml(f.key)}"
              aria-pressed="${activeFilter === f.key}"
              ${f.ariaLabel ? `aria-label="${escapeHtml(f.ariaLabel)}"` : ""}
            >
              ${f.ariaLabel ? `<span aria-hidden="true">${escapeHtml(f.label)}</span>` : escapeHtml(f.label)}
            </button>
          `,
            )
            .join("")}
        </div>

        ${alertHtml}

        <div class="cabinet-collection mt-3">
          ${trophyListHtml}
        </div>
      </div>
    </section>
  `.trim();
}

/**
 * Main own-profile view renderer.
 */
/** The squares pop in once per session, not on every tap. */
let heatmapIntroPlayed = false;
/** Collapsed by default; stays open across re-renders (tapping a day re-renders). */
let heatmapOpen = false;

/** Back to a fresh session: dropdown closed, pop-in still to play. */
export function resetHeatmapView(): void {
  heatmapOpen = false;
  heatmapIntroPlayed = false;
}

/** Records the dropdown state; true when this opening should play the pop-in. */
export function setHeatmapOpen(open: boolean): boolean {
  heatmapOpen = open;
  const intro = open && !heatmapIntroPlayed;
  if (open) heatmapIntroPlayed = true;
  return intro;
}

/** Heat level of one day: what colour it gets and what its caption says. */
function heatLevel(day: ArchiveCalendarDay): { level: string; text: string } {
  if (day.status === "solved") {
    return day.attempts === 1
      ? { level: "first", text: t("profile.heatFirst") }
      : { level: "solved", text: t("profile.heatSolved", { n: day.attempts ?? 0 }) };
  }
  if (day.status === "recovered") return { level: "recovered", text: t("profile.heatRecovered") };
  if (day.status === "lost") return { level: "lost", text: t("profile.heatLost") };
  return { level: "missed", text: t("profile.heatMissed") };
}

/**
 * The last weeks of Daily as a calendar of squares, Monday first, like GitHub
 * contributions. Built from /calendar, the same days the archive lists.
 */
export function renderHeatmap(calendar: ArchiveCalendarDay[] | null, selected: string | null): string {
  if (!calendar || !calendar.length) return "";
  const days = [...calendar].sort((a, b) => a.day.localeCompare(b.day));
  const weekday = (iso: string) => (new Date(`${iso}T12:00:00Z`).getUTCDay() + 6) % 7;
  const lead = weekday(days[0].day);
  const played = days.filter((d) => d.status !== "missed").length;
  const solved = days.filter((d) => d.status === "solved").length;
  const names = Array.from({ length: 7 }, (_, i) =>
    new Intl.DateTimeFormat(getLanguage(), { weekday: "narrow", timeZone: "UTC" }).format(new Date(Date.UTC(2024, 0, 1 + i))));
  const cells = [
    ...Array.from({ length: lead }, () => `<span class="heat-cell pad" aria-hidden="true"></span>`),
    ...days.map((day, i) => {
      const { level, text } = heatLevel(day);
      return `<button type="button" class="heat-cell ${level}${day.day === selected ? " selected" : ""}" style="--i:${i}" data-heat-day="${escapeHtml(day.day)}" aria-label="${escapeHtml(`${day.label} · ${text}`)}"></button>`;
    }),
  ].join("");
  const pick = days.find((d) => d.day === selected);
  const detail = pick
    ? `<p class="heat-detail"><b>${escapeHtml(pick.label)} · Nº ${pick.number}</b> ${escapeHtml(heatLevel(pick).text)}${
        pick.playable ? ` <button type="button" class="link-btn" data-tab="archive">${escapeHtml(t("profile.heatReplay"))} →</button>` : ""}</p>`
    : `<p class="heat-detail muted">${escapeHtml(t("profile.heatmapHint"))}</p>`;
  const legend = (["first", "solved", "recovered", "lost", "missed"] as const)
    .map((level) => `<span><i class="heat-cell ${level}"></i>${escapeHtml(t(`profile.legend${level[0].toUpperCase()}${level.slice(1)}`))}</span>`)
    .join("");
  // The pop-in plays the first time the squares are actually on show.
  const intro = heatmapOpen && !heatmapIntroPlayed ? " intro" : "";
  if (heatmapOpen) heatmapIntroPlayed = true;
  return `
    <details class="card mt-3 heatmap-card"${heatmapOpen ? " open" : ""}>
      <summary>
        <span><h3 class="section-heading">${escapeHtml(t("profile.heatmapTitle"))}</h3>
        <span class="muted text-xs">${escapeHtml(t("profile.heatmapSummary", { played, total: days.length, solved }))}</span></span>
        <span class="heatmap-chevron" aria-hidden="true">${icon("arrow")}</span>
      </summary>
      <div class="heatmap-body">
      <div class="heatmap${intro}">
        ${names.map((n) => `<span class="heat-weekday" aria-hidden="true">${escapeHtml(n)}</span>`).join("")}
        ${cells}
      </div>
      <div class="heatmap-side">
        ${detail}
        <div class="heat-legend">${legend}</div>
      </div>
      </div>
    </details>`;
}

export function renderProfileView(state: ProfileState): string {
  if (state.view === "cabinet") {
    return renderCabinetView(state);
  }

  if (state.status === "loading" && !state.profile) {
    return `
      <section class="profile-page" aria-label="${escapeHtml(t("profile.title"))}">
        <div class="profile-header">
          <span class="eyebrow">${escapeHtml(t("profile.kicker"))}</span>
          <h2 class="page-title">${escapeHtml(t("profile.title"))}</h2>
        </div>
        <div class="mt-4">
          ${renderLoadingState({ message: t("common.loading") })}
        </div>
      </section>
    `.trim();
  }

  if (state.status === "error" && !state.profile) {
    return `
      <section class="profile-page" aria-label="${escapeHtml(t("profile.title"))}">
        <div class="profile-header">
          <span class="eyebrow">${escapeHtml(t("profile.kicker"))}</span>
          <h2 class="page-title">${escapeHtml(t("profile.title"))}</h2>
        </div>
        <div class="mt-4">
          ${renderErrorState({
            message: state.error || t("common.error"),
            retryLabel: t("common.retry"),
            retryButtonId: "profile-retry-btn",
          })}
        </div>
      </section>
    `.trim();
  }

  const profile = state.profile!;
  const u = profile.user;
  const cosmetics = identityAppearance(profile.cosmetics);
  const badge = cosmetics.badge ? ` ${escapeHtml(cosmetics.badge)}` : "";
  const number = cosmetics.number ? `<span class="shirt">${escapeHtml(cosmetics.number)}</span>` : "";
  const titleTag = cosmetics.title.label
    ? `<div class="title-tag"${cosmetics.title.color ? ` style="border-color: ${escapeHtml(cosmetics.title.color)}"` : ""}>${escapeHtml(cosmetics.title.label)}</div>`
    : "";

  const pinnedTrophies = profile.trophies?.pinned || [];
  const pinnedHtml =
    pinnedTrophies.length > 0
      ? renderTrophyPlates(pinnedTrophies)
      : `<p class="muted text-xs profile-empty-pinned">${escapeHtml(t("profile.noPinnedTrophies"))}</p>`;

  // Wordle-like attempt distribution histogram
  const chart = histogram(profile.distribution);
  const distributionBars =
    chart.played > 0
      ? `
        <div class="distribution-bars" role="group" aria-label="${escapeHtml(t("profile.distribution"))}">
          ${chart.rows
            .map(
              (row) => `
            <div
              class="distribution-row"
              aria-label="${escapeHtml(
                t("profile.distributionAttemptLabel")
                  .replace("{n}", String(row.attempts))
                  .replace("{count}", String(row.count)),
              )}"
            >
              <span class="distribution-attempt" aria-hidden="true">${row.attempts}</span>
              <div class="distribution-bar-track">
                <span
                  class="distribution-bar-fill${row.best ? " best" : ""}"
                  style="width: ${row.width}%"
                >
                  <span class="distribution-count">${row.count}</span>
                </span>
              </div>
            </div>
          `,
            )
            .join("")}
        </div>
      `
      : `<p class="muted text-xs">${escapeHtml(t("profile.noGames"))}</p>`;

  const cabinetOpenAction =
    u.trophies > 0
      ? `<button type="button" class="btn ghost btn-open-cabinet mt-3" id="open-cabinet">${escapeHtml(t("profile.cabinetOpen"))}</button>`
      : `<p class="muted text-xs mt-2">${escapeHtml(t("profile.noTrophies"))}</p>`;

  return `
    <section class="profile-page" ${profileSurfaceAttributes(state.profile?.cosmetics)} aria-label="${escapeHtml(t("profile.title"))}">
      <div class="profile-header">
        <span class="eyebrow">${escapeHtml(t("profile.kicker"))}</span>
        <h2 class="page-title">${escapeHtml(t("profile.title"))}</h2>
      </div>

      <!-- Player Pass Hero Card -->
      <div class="card profile-hero mt-3">
        <div class="player-pass-label"><span>${v("playerPass")}</span>${icon("career")}</div>
        ${renderAvatar({
          name: u.name,
          ringStyle: cosmetics.frame.ring ? `background: ${cosmetics.frame.ring}` : undefined,
          size: "large",
          tactics: cosmetics.frame.tactics,
          ringMotion: cosmetics.frame.motion,
        })}
        <div class="hero-info">
          <h3 id="profile-heading" tabindex="-1" class="profile-player-name">
            ${number}${escapeHtml(u.name)}${badge}
          </h3>
          ${titleTag}
          <div class="profile-hero-meta muted text-xs mt-1">
            ${u.points} ${escapeHtml(t("common.points"))} · ${escapeHtml(tCount("common.trophiesCount", u.trophies))}
          </div>
        </div>
        <div class="profile-showcase-container mt-3">
          ${pinnedHtml}
        </div>
      </div>

      ${renderProfileCosmeticArt(profile.cosmetics)}

      <!-- Core Numbers / Stat Grid Card -->
      <div class="card mt-3">
        <h3 class="section-heading">${escapeHtml(t("profile.yourNumbers"))}</h3>
        <div class="stat-grid three-cols mt-3 primary-stats">
          ${renderStatTile({ value: u.points, label: t("profile.totalPoints") })}
          ${renderStatTile({ value: u.players_guessed, label: t("profile.guessed") })}
          ${renderStatTile({ value: u.streak, label: t("profile.streak") })}
        </div>
        <details class="secondary-stats"><summary>${v("moreStats")}</summary>
        <div class="stat-grid three-cols mt-3">
          ${renderStatTile({ value: u.monthly_points, label: t("profile.monthlyPoints") })}
          ${renderStatTile({ value: u.best_streak, label: t("profile.bestStreak") })}
          ${renderStatTile({ value: u.archive_solved, label: t("profile.recovered") })}
          ${renderStatTile({ value: u.bonus_first_guessed, label: t("profile.bonusFirstGuesser") })}
        </div>
        </details>
      </div>

      ${renderHeatmap(state.calendar, state.heatmapDay)}

      <!-- Attempt Distribution Card -->
      <div class="card mt-3">
        <h3 class="section-heading">${escapeHtml(t("profile.distribution"))}</h3>
        <div class="distribution-container mt-3">
          ${distributionBars}
        </div>
      </div>

      <!-- Trophy Cabinet Card -->
      <div class="card mt-3">
        <div class="cabinet-head">
          <h3 class="section-heading">${escapeHtml(t("profile.cabinet"))}</h3>
          <span class="muted text-xs">${escapeHtml(tCount("common.trophiesCount", u.trophies))}</span>
        </div>
        ${cabinetOpenAction}
      </div>

      ${renderStyleInventory([], profile.wardrobe, profile.cosmetics.equipped)}

      <!-- Mode Handoffs: Shop & Referral -->
      <div class="profile-actions mt-3">
        <button type="button" class="mode-entry shop-entry" data-tab="shop">
          <span class="mode-icon">${icon("profile")}</span>
          <span class="mode-text">
            <b>${escapeHtml(t("profile.customizeStyle"))}</b>
          </span>
          ${icon("arrow")}
        </button>

        ${renderRecapProfileEntry()}

        <button type="button" class="mode-entry referral-entry mt-2" data-tab="referral">
          <span class="mode-icon">${icon("referral")}</span>
          <span class="mode-text">
            <b>${escapeHtml(t("profile.inviteFriends"))}</b>
            <small class="muted">${escapeHtml(t("profile.inviteFriendsSub"))}</small>
          </span>
          ${icon("arrow")}
        </button>
      </div>
    </section>
  `.trim();
}
