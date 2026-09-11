import { escapeHtml } from "@/utils/format";

export interface ListRowProps {
  id?: string;
  position?: number | string;
  avatarHtml?: string;
  title: string;
  subtitle?: string;
  value?: string | number;
  isCurrent?: boolean;
  actionHtml?: string;
  extraClass?: string;
}

export function renderListRow(props: ListRowProps): string {
  const isCurrentClass = props.isCurrent ? "me" : "";
  const posHtml = props.position != null
    ? `<div class="pos">${escapeHtml(String(props.position))}</div>`
    : "";
  const avatarHtml = props.avatarHtml || "";
  const subtitleHtml = props.subtitle
    ? `<div class="muted" style="font-size: 11.5px;">${escapeHtml(props.subtitle)}</div>`
    : "";
  const valueHtml = props.value != null
    ? `<div class="pts">${escapeHtml(String(props.value))}</div>`
    : "";
  const actionHtml = props.actionHtml
    ? `<div class="row-action">${props.actionHtml}</div>`
    : "";

  const idAttr = props.id ? ` id="${escapeHtml(props.id)}"` : "";
  const classAttr = `row ${isCurrentClass} ${props.extraClass || ""}`.trim();

  return `
    <div class="${classAttr}"${idAttr} role="listitem">
      ${posHtml}
      ${avatarHtml}
      <div class="name">
        <div>${escapeHtml(props.title)}</div>
        ${subtitleHtml}
      </div>
      ${valueHtml}
      ${actionHtml}
    </div>
  `.trim();
}
