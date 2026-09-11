import { escapeHtml } from "@/utils/format";

export interface CareerStop {
  team: string;
  league?: string | null;
  country?: string | null;
  start_year: number | string;
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

  const rows = stops.map((stop) => {
    const meta = [stop.league, stop.country].filter(Boolean).map(escapeHtml).join(" · ");
    const years = stop.end_year ? `${stop.start_year} – ${stop.end_year}` : `${stop.start_year} – …`;
    const apps = stop.apps == null ? "" : (stop.goals == null ? `${stop.apps}` : `${stop.apps} (${stop.goals})`);
    const loanClass = stop.loan ? " loan" : "";
    const loanPrefix = stop.loan ? "→ " : "";

    return `
      <div class="stop${loanClass}" role="listitem">
        <div class="bar" aria-hidden="true"></div>
        <div class="who">
          <div class="team">${escapeHtml(stop.team)}</div>
          ${meta ? `<div class="meta">${meta}</div>` : ""}
        </div>
        <div class="right">
          <div class="years">${loanPrefix}${escapeHtml(years)}</div>
          ${apps ? `<div class="apps">${escapeHtml(apps)}</div>` : ""}
        </div>
      </div>
    `.trim();
  }).join("\n");

  const idAttr = props.id ? ` id="${escapeHtml(props.id)}"` : "";
  const classAttr = `path ${props.extraClass || ""}`.trim();

  return `
    <div class="${classAttr}"${idAttr} role="list" aria-label="Career path">
      ${rows}
    </div>
  `.trim();
}
