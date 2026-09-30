import { icon } from "@/components/Icon";
import { getTelegramWebApp } from "@/telegram/webapp";
import { escapeHtml } from "@/utils/format";
import { fetchRecap } from "./api";
import { openRecapStory } from "./story";
import { monthName, rs } from "./strings";
import type { RecapResponse } from "./types";

/**
 * Where the monthly recap (#245) enters the app:
 *
 * - a banner at the top of the Daily tab, from the 1st to the 7th of the month, only when the
 *   last month's recap exists and has not been watched on this device yet;
 * - a permanent "Your recaps" entry in the Profile.
 *
 * The banner asks the server once per session and only in that week, so the Daily tab costs
 * nothing extra the other 23 days of the month. `?recap` in the URL forces it (local demo).
 */

const SEEN_KEY = "gtp.recap.seen";
const BANNER_DAYS = 7;
const SLOT_ID = "recap-banner-slot";

let loaded: RecapResponse | null = null;
let loading: Promise<RecapResponse | null> | null = null;

function lastMonth(now = new Date()): string {
  const date = new Date(now.getFullYear(), now.getMonth() - 1, 1);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
}

function forced(): boolean {
  try {
    return new URLSearchParams(window.location.search).has("recap");
  } catch {
    return false;
  }
}

function seen(month: string): boolean {
  try {
    return localStorage.getItem(SEEN_KEY) === month;
  } catch {
    return false;
  }
}

function markSeen(month: string): void {
  try {
    localStorage.setItem(SEEN_KEY, month);
  } catch {
    /* private mode: the banner simply comes back next time */
  }
}

function load(month?: string): Promise<RecapResponse | null> {
  if (!month && loaded) return Promise.resolve(loaded);
  if (!month && loading) return loading;
  const request = fetchRecap(month).then((response) => {
    if (!month) loaded = response;
    return response;
  }).catch(() => null).finally(() => {
    if (!month) loading = null;
  });
  if (!month) loading = request;
  return request;
}

function bannerHtml(): string {
  const recap = loaded?.recap;
  if (!recap?.available || (seen(recap.month) && !forced())) return "";
  return `<button type="button" class="recap-banner" data-recap-open="${escapeHtml(recap.month)}">
    <span class="recap-banner-icon" aria-hidden="true">${icon("star")}</span>
    <span class="recap-banner-text"><b>${escapeHtml(rs("bannerTitle", { month: monthName(recap.month) }))}</b>
    <small>${escapeHtml(rs("bannerSub", { played: recap.played, solved: recap.solved ?? 0 }))}</small></span>
    ${icon("arrow")}
  </button>`;
}

/** The slot the Daily page renders; filled as soon as the recap is known. */
export function renderRecapBannerSlot(): string {
  return `<div id="${SLOT_ID}">${bannerHtml()}</div>`;
}

/** The Profile entry: opens the last closed month, or explains why there is none. */
export function renderRecapProfileEntry(): string {
  return `<button type="button" class="mode-entry recap-entry mt-2" data-recap-open="">
    <span class="mode-icon">${icon("star")}</span>
    <span class="mode-text"><b>${escapeHtml(rs("profileEntry"))}</b>
    <small class="muted">${escapeHtml(rs("profileEntrySub"))}</small></span>
    ${icon("arrow")}
  </button>`;
}

/** Binds recap buttons under `root` and, in the banner week, loads the banner. */
export function bindRecapEntries(root: ParentNode): void {
  root.querySelectorAll<HTMLButtonElement>("[data-recap-open]").forEach((button) => {
    button.onclick = (event) => {
      event.preventDefault();
      void openRecap(button.dataset.recapOpen || undefined);
    };
  });
  const slot = root.querySelector<HTMLElement>(`#${SLOT_ID}`);
  const offer = forced() || new Date().getDate() <= BANNER_DAYS;
  if (!slot || !offer || loaded || (seen(lastMonth()) && !forced())) return;
  void load().then(() => {
    const target = document.getElementById(SLOT_ID);
    if (!target) return;
    target.innerHTML = bannerHtml();
    bindRecapEntries(target);
  });
}

export async function openRecap(month?: string): Promise<void> {
  const response = month && loaded?.recap?.month === month ? loaded : await load(month);
  const recap = response?.recap;
  if (!recap) return;
  if (!recap.available) {
    const text = rs("tooFew", { month: monthName(recap.month), min: recap.min_played ?? 8, played: recap.played });
    const tg = getTelegramWebApp();
    if (tg?.showAlert) tg.showAlert(text);
    else window.alert(text);
    return;
  }
  markSeen(recap.month);
  document.getElementById(SLOT_ID)?.replaceChildren();
  openRecapStory(recap, response?.name || "", response?.look);
}
