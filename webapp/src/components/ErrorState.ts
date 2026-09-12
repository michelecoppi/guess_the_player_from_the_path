import { icon as renderIcon } from "./Icon";
import { escapeHtml } from "@/utils/format";
import { renderButton } from "./Button";

export interface ErrorStateProps {
  id?: string;
  title?: string;
  message: string;
  icon?: string;
  retryLabel?: string;
  retryButtonId?: string;
  extraClass?: string;
}

export function renderErrorState(props: ErrorStateProps): string {
  const icon = props.icon || renderIcon("warning");
  const titleHtml = props.title
    ? `<h3 class="error-state-title">${escapeHtml(props.title)}</h3>`
    : "";
  const retryButtonHtml = props.retryLabel
    ? `<div style="margin-top: 8px;">
        ${renderButton({
          id: props.retryButtonId || "retry-button",
          label: props.retryLabel,
          variant: "ghost",
          size: "small",
        })}
      </div>`
    : "";

  const idAttr = props.id ? ` id="${escapeHtml(props.id)}"` : "";
  const classAttr = `error-state ${props.extraClass || ""}`.trim();

  return `
    <div class="${classAttr}"${idAttr} role="alert">
      <div class="error-state-icon" aria-hidden="true">${icon}</div>
      ${titleHtml}
      <p class="error-state-message">${escapeHtml(props.message)}</p>
      ${retryButtonHtml}
    </div>
  `.trim();
}
