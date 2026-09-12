import { v } from "@/i18n/visual";
import { escapeHtml } from "@/utils/format";

export interface CareerStop {
  team: string;
  league?: string | null;
  country?: string | null;
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

      return `
      <div class="stop${loanClass}" role="listitem">
        <div class="years">${escapeHtml(years)}</div>
        <div class="transfer-node" aria-hidden="true">${String(index + 1).padStart(2, "0")}</div>
        <div class="who">
          <div class="team">${escapeHtml(stop.team)}</div>
          ${meta ? `<div class="meta">${meta}</div>` : ""}
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
    <div class="${classAttr}"${idAttr} role="list" aria-label="Career path">
      ${rows}
    </div>
  `.trim();
}
