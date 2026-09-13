import { escapeHtml, initials } from "@/utils/format";
import { t } from "@/i18n";
import type {
  ReferralState,
  ReferralRewardMilestone,
} from "./types";

const POS: [number, number][] = [
  [50, 86],
  [18, 66],
  [39, 68],
  [61, 68],
  [82, 66],
  [25, 45],
  [50, 49],
  [75, 45],
  [22, 23],
  [50, 17],
  [78, 23],
];

function renderBall(
  radius: number,
  d: string,
  [x, y]: [number, number],
): string {
  const supportsOffsetPath =
    typeof CSS !== "undefined" &&
    Boolean(CSS.supports?.("offset-path", "path('M0 0')"));

  return `<circle class="rf-ball" r="${radius}"${
    supportsOffsetPath ? "" : ` cx="${x}" cy="${y}"`
  } style="offset-path:path('${d}')"/>`;
}

/**
 * Renders the tactical football pitch SVG with animated pass flow and squad positions.
 */
export function renderPitch(
  count = 11,
  labels: string[] = [],
  active = count,
): string {
  const points =
    count === 3
      ? ([
          [50, 20],
          [22, 74],
          [78, 74],
        ] as [number, number][])
      : count === 5
        ? ([
            [50, 78],
            [20, 53],
            [80, 53],
            [30, 23],
            [70, 23],
          ] as [number, number][])
        : POS;

  const d = `${points
    .map(([x, y], i) => `${i ? "L" : "M"}${x} ${y}`)
    .join(" ")} Z`;
  const [firstX, firstY] = points[0];

  const playersSvg = points
    .map(([x, y], i) => {
      const isVacant = i >= active;
      const label = labels[i] || (i === 0 ? "★" : String(i));
      return `<g class="rf-player ${isVacant ? "rf-vacant" : ""}" style="--i:${i}" transform="translate(${x} ${y})"><circle r="4.2"/><text y="1.35">${escapeHtml(label)}</text></g>`;
    })
    .join("");

  return `<svg class="rf-pitch" viewBox="0 0 100 100" aria-hidden="true"><rect class="rf-field" x="6" y="6" width="88" height="88" rx="2"/><path class="rf-lines" d="M6 50H94 M30 6V21H70V6 M30 94V79H70V94"/><circle class="rf-lines" cx="50" cy="50" r="13"/><path class="rf-pass" d="${d}"/>${playersSvg}${renderBall(1.5, d, [firstX, firstY])}</svg>`;
}

export function getMilestoneName(target: number): string {
  if (target === 3) return t("referral.milestone3Name");
  if (target === 5) return t("referral.milestone5Name");
  if (target === 10) return t("referral.milestone10Name");
  return t("referral.milestoneGenericName").replace("{n}", String(target));
}

export function getMilestoneDesc(target: number): string {
  if (target === 3) return t("referral.milestone3Desc");
  if (target === 5) return t("referral.milestone5Desc");
  if (target === 10) return t("referral.milestone10Desc");
  return t("referral.milestoneGenericDesc").replace("{n}", String(target));
}

let watcher: IntersectionObserver | null = null;

export function watchReferralMotion(container: HTMLElement): void {
  const Observer =
    (typeof window !== "undefined" && (window as any).IntersectionObserver) ||
    (typeof globalThis !== "undefined" && (globalThis as any).IntersectionObserver);
  if (!Observer) return;
  if (!watcher) {
    watcher = new Observer(
      (entries: any[]) => {
        for (const entry of entries) {
          entry.target.classList.toggle("rf-paused", !entry.isIntersecting);
        }
      },
      { rootMargin: "60px" },
    );
  }
  if (!watcher) return;
  watcher.disconnect();
  const pitches = container.querySelectorAll(".rf-pitch");
  pitches.forEach((p) => watcher?.observe(p));
}

export function disconnectReferralMotion(): void {
  if (watcher) {
    watcher.disconnect();
  }
}

/**
 * Renders the detail reveal / preview subview for a specific milestone reward.
 */
export function renderRewardReveal(
  target: number,
  milestone: ReferralRewardMilestone | null,
  qualifiedCount: number,
  equippingItemId: string | null,
): string {
  const isUnlocked = qualifiedCount >= target;
  const kicker = isUnlocked ? t("referral.unlock") : t("referral.exclusive");
  const name = getMilestoneName(target);
  const desc = getMilestoneDesc(target);

  const items = milestone?.items || [];
  const piecesHtml = items
    .map((item) => {
      const isEquipping = equippingItemId === item.id;
      const actionHtml = item.owned
        ? `<button
             type="button"
             class="btn small rf-equip-btn"
             data-rf-equip="${escapeHtml(item.id)}"
             ${item.equipped || isEquipping ? "disabled" : ""}
           >
             ${escapeHtml(
               item.equipped
                 ? t("referral.worn")
                 : isEquipping
                   ? t("common.loading")
                   : t("referral.wear"),
             )}
           </button>`
        : `<span class="rf-exclusive">${target} ${escapeHtml(t("referral.people"))}</span>`;

      return `
        <div class="rf-prize-piece">
          <div class="rf-prize-piece-info">
            <strong>${escapeHtml(item.name)}</strong>
            <small>${escapeHtml(item.description)}</small>
          </div>
          ${actionHtml}
        </div>
      `;
    })
    .join("");

  return `
    <section class="rf-reveal" aria-label="${escapeHtml(name)}">
      <button type="button" class="btn ghost small" id="rf-close-preview">
        ← ${escapeHtml(t("referral.close"))}
      </button>
      <p class="rf-kicker">${escapeHtml(kicker)}</p>
      <h1>${escapeHtml(name)}</h1>
      <div class="rf-reveal-art">
        ${renderPitch(
          target === 3 ? 3 : target === 5 ? 5 : 11,
          [],
          isUnlocked ? (target === 3 ? 3 : target === 5 ? 5 : 11) : 0,
        )}
      </div>
      <p class="rf-reveal-desc">${escapeHtml(desc)}</p>
      <div class="rf-prize-pieces">
        ${piecesHtml}
      </div>
    </section>
  `;
}

/**
 * Renders the main Referral view with pitch progress, milestones, and friends list.
 */
export function renderReferralView(state: ReferralState): string {
  const data = state.data;
  if (!data) return "";

  const qualified = data.qualified || 0;
  const requiredDays = data.required_days || 5;
  const nextTarget = [3, 5, 10].find((n) => n > qualified);
  const nextCopy = nextTarget
    ? `${nextTarget - qualified} ${t("referral.next")}`
    : t("referral.done");

  const heroFieldHtml = `
    <div class="rf-hero-field">
      ${renderPitch(11, [], Math.min(qualified + 1, 11))}
      <span class="rf-field-caption">${escapeHtml(t("referral.you"))} + 10</span>
    </div>
  `;

  const linkControlsHtml = data.link
    ? `
      <div class="rf-link-actions">
        <button type="button" class="btn" id="rf-invite">
          ${escapeHtml(t("referral.invite"))} ↗
        </button>
        <button type="button" class="btn ghost small" id="rf-copy">
          ${escapeHtml(t("referral.copy"))}
        </button>
      </div>
      <details class="rf-link">
        <summary>${escapeHtml(t("referral.manual"))}</summary>
        <input readonly value="${escapeHtml(data.link)}" aria-label="${escapeHtml(t("referral.manual"))}">
      </details>
    `
    : `<p class="rf-no-link">${escapeHtml(t("referral.noLink"))}</p>`;

  const milestonesBadges = [3, 5, 10]
    .map((n) => {
      const isDone = qualified >= n;
      return `<span class="${isDone ? "is-done" : ""}">${isDone ? "✓" : n}</span>`;
    })
    .join("");

  const rewardsGridHtml = `
    <div class="rf-rewards">
      ${[3, 5, 10]
        .map((target) => {
          const isUnlocked = qualified >= target;
          const name = getMilestoneName(target);
          const desc = getMilestoneDesc(target);
          const previewLabel = `${t("referral.preview")} · ${name}`;
          const statusText = isUnlocked
            ? t("referral.unlock")
            : `${Math.min(qualified, target)} / ${target} · ${t("referral.people")}`;

          return `
            <button
              type="button"
              class="rf-reward ${isUnlocked ? "is-unlocked" : ""}"
              data-rf-preview="${target}"
              aria-label="${escapeHtml(previewLabel)}"
            >
              <div class="rf-reward-top">
                <span>${escapeHtml(t("referral.exclusive"))}</span>
                <b>${isUnlocked ? "✓" : String(target)}</b>
              </div>
              <div class="rf-reward-art">
                ${renderPitch(
                  target === 3 ? 3 : target === 5 ? 5 : 11,
                  [],
                  isUnlocked ? (target === 3 ? 3 : target === 5 ? 5 : 11) : 0,
                )}
              </div>
              <strong>${escapeHtml(name)}</strong>
              <small>${escapeHtml(desc)}</small>
              <span class="rf-reward-status">${escapeHtml(statusText)} →</span>
            </button>
          `;
        })
        .join("")}
    </div>
  `;

  const friendsList = data.friends || [];
  const friendsRowsHtml =
    friendsList.length > 0
      ? friendsList
          .map((friend) => {
            const isQualified = friend.status === "qualified";
            const statusLabel = isQualified
              ? `✓ ${t("referral.complete")}`
              : `${friend.days}/${requiredDays} · ${t("referral.daily")}`;
            const progressAriaLabel = `${friend.name} · ${t("referral.progress")}`;

            return `
              <div class="rf-friend">
                <span class="rf-friend-avatar" aria-hidden="true">${escapeHtml(initials(friend.name))}</span>
                <div class="rf-friend-info">
                  <strong class="rf-friend-name">${escapeHtml(friend.name)}</strong>
                  <small class="rf-friend-status">${escapeHtml(statusLabel)}</small>
                  <progress value="${friend.days}" max="${requiredDays}" aria-label="${escapeHtml(progressAriaLabel)}"></progress>
                </div>
              </div>
            `;
          })
          .join("")
      : `<p class="muted rf-empty">${escapeHtml(t("referral.empty"))}</p>`;

  const loadMoreHtml = data.next_cursor
    ? `<button type="button" class="btn ghost" id="rf-more" ${state.loadingMore ? "disabled" : ""}>${escapeHtml(state.loadingMore ? t("common.loading") : t("referral.more"))}</button>`
    : "";

  return `
    <section class="rf-hero">
      <p class="rf-kicker">${escapeHtml(t("referral.eyebrow"))}</p>
      <h1>${escapeHtml(t("referral.title"))}</h1>
      <p class="rf-intro">${escapeHtml(t("referral.intro"))}</p>
      ${heroFieldHtml}
      <div class="rf-score">
        <strong>${qualified}<span>/10</span></strong>
        <div>
          <span>${escapeHtml(t("referral.qualified"))}</span>
          <small>${escapeHtml(nextCopy)}</small>
        </div>
      </div>
      <div class="rf-milestones">${milestonesBadges}</div>
      ${linkControlsHtml}
    </section>

    ${rewardsGridHtml}

    <section class="card rf-friends">
      <div class="rf-friends-heading">
        <h2>${escapeHtml(t("referral.friends"))}</h2>
        <button type="button" class="btn ghost small" id="rf-refresh" ${state.refreshing ? "disabled" : ""}>
          ${escapeHtml(state.refreshing ? t("common.loading") : t("referral.refresh"))}
        </button>
      </div>
      ${state.errorNotice ? `<p role="alert" class="alert alert-error">${escapeHtml(state.errorNotice)}</p>` : ""}
      <div class="rf-friends-list">
        ${friendsRowsHtml}
      </div>
      ${loadMoreHtml}
    </section>

    <p class="rf-rules">${escapeHtml(t("referral.rules"))}</p>
  `;
}
