import { icon as renderIcon } from "./Icon";
import { escapeHtml } from "@/utils/format";
import { renderButton } from "./Button";

export interface EmptyStateProps {
  id?: string;
  icon?: string;
  title?: string;
  description: string;
  actionLabel?: string;
  actionButtonId?: string;
  extraClass?: string;
}

export function renderEmptyState(props: EmptyStateProps): string {
  const icon = props.icon || renderIcon("career");
  const titleHtml = props.title
    ? `<h3 class="empty-state-title">${escapeHtml(props.title)}</h3>`
    : "";
  const actionButtonHtml = props.actionLabel
    ? `<div style="margin-top: 8px;">
        ${renderButton({
          id: props.actionButtonId || "empty-action",
          label: props.actionLabel,
          variant: "primary",
          size: "small",
        })}
      </div>`
    : "";

  const idAttr = props.id ? ` id="${escapeHtml(props.id)}"` : "";
  const classAttr = `empty-state ${props.extraClass || ""}`.trim();

  return `
    <div class="${classAttr}"${idAttr}>
      <div class="empty-state-icon" aria-hidden="true">${icon}</div>
      ${titleHtml}
      <p class="empty-state-description">${escapeHtml(props.description)}</p>
      ${actionButtonHtml}
    </div>
  `.trim();
}
