import { escapeHtml } from "@/utils/format";

export interface LoadingStateProps {
  id?: string;
  message?: string;
  inline?: boolean;
  extraClass?: string;
}

export function renderLoadingState(props: LoadingStateProps = {}): string {
  const message = props.message || "Caricamento in corso...";
  const inlineClass = props.inline ? "inline" : "";
  const idAttr = props.id ? ` id="${escapeHtml(props.id)}"` : "";
  const classAttr = `loading-state ${inlineClass} ${props.extraClass || ""}`.trim();

  return `
    <div class="${classAttr}"${idAttr} role="status" aria-live="polite">
      <div class="spinner" aria-hidden="true"></div>
      <span>${escapeHtml(message)}</span>
    </div>
  `.trim();
}

export interface SkeletonProps {
  variant?: "text" | "card" | "avatar" | "title";
  count?: number;
  width?: string;
  height?: string;
  extraClass?: string;
}

export function renderSkeleton(props: SkeletonProps = {}): string {
  const variant = props.variant || "text";
  const count = props.count ?? 1;
  const styleParts: string[] = [];
  if (props.width) styleParts.push(`width: ${props.width};`);
  if (props.height) styleParts.push(`height: ${props.height};`);
  const styleAttr = styleParts.length > 0 ? ` style="${styleParts.join(" ")}"` : "";

  let itemClass = "skeleton";
  if (variant === "text") itemClass += " skeleton-text";
  else if (variant === "title") itemClass += " skeleton-text title";
  else if (variant === "card") itemClass += " skeleton-card";
  else if (variant === "avatar") itemClass += " skeleton-avatar";
  if (props.extraClass) itemClass += ` ${props.extraClass}`;

  const items = Array.from({ length: count }, () => `<div class="${itemClass}"${styleAttr} aria-hidden="true"></div>`);
  return items.join("\n");
}
