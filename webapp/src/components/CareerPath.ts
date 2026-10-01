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

// England, Scotland and Wales have their own flags: a black flag followed by tag letters.
const SUBDIVISION_FLAGS: Record<string, string> = { "GB-ENG": "gbeng", "GB-SCT": "gbsct", "GB-WLS": "gbwls" };

/** The emoji flag of an ISO 3166 code; empty for anything that is not a known code. */
export function flagEmoji(code?: string | null): string {
  if (!code) return "";
  const tag = SUBDIVISION_FLAGS[code];
  if (tag) {
    return "\u{1F3F4}" + [...tag].map((c) => String.fromCodePoint(0xe0000 + c.charCodeAt(0))).join("") + "\u{E007F}";
  }
  if (!/^[A-Z]{2}$/.test(code)) return "";
  return String.fromCodePoint(...[...code].map((c) => 0x1f1e6 + c.charCodeAt(0) - 65));
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
      const flag = flagEmoji(stop.country_code);

      return `
      <div class="stop${loanClass}" role="listitem">
        <div class="years">${escapeHtml(years)}</div>
        <div class="transfer-node" aria-hidden="true">${String(index + 1).padStart(2, "0")}</div>
        <div class="who">
          <div class="team">${escapeHtml(stop.team)}</div>
          ${meta ? `<div class="meta">${flag ? `<span class="flag" aria-hidden="true">${flag}</span>` : ""}${meta}</div>` : ""}
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
