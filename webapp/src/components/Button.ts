import { escapeHtml } from "@/utils/format";

export interface ButtonProps {
  id?: string;
  label: string;
  variant?: "primary" | "ghost";
  size?: "normal" | "small";
  icon?: string;
  disabled?: boolean;
  extraClass?: string;
}

export function renderButton(props: ButtonProps): string {
  const variantClass = props.variant === "ghost" ? "ghost" : "";
  const sizeClass = props.size === "small" ? "small" : "";
  const classes = `btn ${variantClass} ${sizeClass} ${props.extraClass || ""}`.trim();
  const idAttr = props.id ? ` id="${escapeHtml(props.id)}"` : "";
  const disabledAttr = props.disabled ? " disabled" : "";
  const iconHtml = props.icon ? `<span class="btn-icon" aria-hidden="true">${props.icon}</span>` : "";

  return `
    <button type="button" class="${classes}"${idAttr}${disabledAttr}>
      ${iconHtml}
      <span>${escapeHtml(props.label)}</span>
    </button>
  `;
}
