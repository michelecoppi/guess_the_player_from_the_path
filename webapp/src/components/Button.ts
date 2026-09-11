import { escapeHtml } from "@/utils/format";

export interface ButtonProps {
  id?: string;
  label: string;
  variant?: "primary" | "ghost" | "destructive";
  size?: "normal" | "small";
  icon?: string;
  disabled?: boolean;
  loading?: boolean;
  fullWidth?: boolean;
  type?: "button" | "submit" | "reset";
  ariaLabel?: string;
  extraClass?: string;
}

export function renderButton(props: ButtonProps): string {
  const variantClass = props.variant === "ghost"
    ? "ghost"
    : props.variant === "destructive"
      ? "destructive"
      : "";
  const sizeClass = props.size === "small" ? "small" : "";
  const widthClass = props.fullWidth ? "full-width" : "";
  const loadingClass = props.loading ? "loading" : "";
  const classes = `btn ${variantClass} ${sizeClass} ${widthClass} ${loadingClass} ${props.extraClass || ""}`.trim();
  const idAttr = props.id ? ` id="${escapeHtml(props.id)}"` : "";
  const disabledAttr = props.disabled || props.loading ? " disabled" : "";
  const busyAttr = props.loading ? ' aria-busy="true"' : "";
  const ariaLabelAttr = props.ariaLabel ? ` aria-label="${escapeHtml(props.ariaLabel)}"` : "";
  const typeAttr = ` type="${props.type || "button"}"`;

  const iconContent = props.loading
    ? '<span class="btn-icon spinner small" aria-hidden="true"></span>'
    : props.icon
      ? `<span class="btn-icon" aria-hidden="true">${props.icon}</span>`
      : "";

  return `
    <button${typeAttr} class="${classes}"${idAttr}${disabledAttr}${busyAttr}${ariaLabelAttr}>
      ${iconContent}
      <span>${escapeHtml(props.label)}</span>
    </button>
  `.trim();
}
