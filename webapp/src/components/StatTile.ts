import { escapeHtml } from "@/utils/format";

export interface StatTileProps {
  id?: string;
  value: string | number;
  label: string;
  subtext?: string;
  icon?: string;
  extraClass?: string;
}

export function renderStatTile(props: StatTileProps): string {
  const iconHtml = props.icon ? `<span class="tile-icon" aria-hidden="true">${props.icon} </span>` : "";
  const subHtml = props.subtext ? `<div class="tile-sub">${escapeHtml(props.subtext)}</div>` : "";
  const idAttr = props.id ? ` id="${escapeHtml(props.id)}"` : "";
  const classAttr = `tile ${props.extraClass || ""}`.trim();

  return `
    <div class="${classAttr}"${idAttr}>
      <div class="tile-value">${iconHtml}${escapeHtml(String(props.value))}</div>
      <div class="tile-label">${escapeHtml(props.label)}</div>
      ${subHtml}
    </div>
  `.trim();
}
