import { v } from "@/i18n/visual";
import { escapeHtml } from "@/utils/format";

export interface CareerStop {
  team: string;
  league?: string | null;
  country?: string | null;
  /** ISO 3166 code from the server (services/content_i18n.py COUNTRY_CODES), for the flag. */
  country_code?: string | null;
  start_year?: number | string | null;
  end_year?: number | string | null;
  apps?: number | null;
  goals?: number | null;
  loan?: boolean;
}

export interface CareerPathProps {
  stops?: CareerStop[] | null;
  extraClass?: string;
  emptyText?: string;
  id?: string;
}

/**
 * The flag image of a country code from the server (services/content_i18n.py COUNTRY_CODES:
 * ISO 3166 plus GB-ENG, GB-SCT, GB-WLS and YU); empty for anything that is not a code.
 * Images, not emoji: Windows has no emoji flags. Sources and licence in NOTICE.
 */
export function flagUrl(code?: string | null): string {
  if (!code || !/^[A-Z]{2}(-[A-Z]{3})?$/.test(code)) return "";
  return new URL(`../assets/flags/${code.toLowerCase()}.webp`, import.meta.url).href;
}

export function renderCareerPath(props: CareerPathProps): string {
  const stops = props.stops;
  if (!stops || !stops.length) {
    if (props.emptyText) {
      return `<div class="path-empty muted center" style="padding: 16px;">${escapeHtml(props.emptyText)}</div>`;
    }
    return "";
  }

  const rows = stops
    .map((stop, index) => {
      const meta = [stop.league, stop.country]
        .filter(Boolean)
        .map(escapeHtml)
        .join(" · ");
      const startStr = stop.start_year != null ? String(stop.start_year) : "";
      const years = stop.end_year
        ? `${startStr} – ${stop.end_year}`
        : `${startStr} – …`;
      const apps =
        stop.apps == null
          ? ""
          : stop.goals == null
            ? `${stop.apps}`
            : `${stop.apps} (${stop.goals})`;
      const loanClass = stop.loan ? " loan" : "";
      const flag = flagUrl(stop.country_code);

      return `
      <div class="stop${loanClass}" role="listitem">
        <div class="years">${escapeHtml(years)}</div>
        <div class="transfer-node" aria-hidden="true">${String(index + 1).padStart(2, "0")}</div>
        <div class="who">
          <div class="team">${escapeHtml(stop.team)}</div>
          ${meta ? `<div class="meta">${flag ? `<img class="flag" src="${escapeHtml(flag)}" alt="" width="18" height="14" loading="lazy" decoding="async">` : ""}${meta}</div>` : ""}
          ${stop.loan ? `<span class="loan-label">${v("loan")}</span>` : ""}
        </div>
        <div class="apps">${apps ? escapeHtml(apps) : "—"}</div>
      </div>
    `.trim();
    })
    .join("\n");

  const idAttr = props.id ? ` id="${escapeHtml(props.id)}"` : "";
  const classAttr = `path ${props.extraClass || ""}`.trim();

  return `
    <div class="${classAttr}"${idAttr} role="list" aria-label="${v("careerPathLabel")}">
      ${rows}
    </div>
  `.trim();
}
