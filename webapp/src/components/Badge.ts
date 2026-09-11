import { escapeHtml } from "@/utils/format";

export type BadgeVariant = "success" | "danger" | "warning" | "info" | "neutral";

export interface BadgeProps {
  id?: string;
  label: string;
  variant?: BadgeVariant;
  icon?: string;
  extraClass?: string;
}

export function renderBadge(props: BadgeProps): string {
  const variantClass = props.variant || "neutral";
  const iconHtml = props.icon ? `<span class="badge-icon" aria-hidden="true">${props.icon}</span>` : "";
  const idAttr = props.id ? ` id="${escapeHtml(props.id)}"` : "";
  const classAttr = `pill ${variantClass} ${props.extraClass || ""}`.trim();

  return `
    <span class="${classAttr}"${idAttr}>
      ${iconHtml}
      <span>${escapeHtml(props.label)}</span>
    </span>
  `.trim();
}
