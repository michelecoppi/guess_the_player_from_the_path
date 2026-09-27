import { escapeHtml } from "@/utils/format";

export interface CardProps {
  id?: string;
  kicker?: string;
  title?: string;
  actionHtml?: string;
  bodyHtml: string;
  extraClass?: string;
  as?: "section" | "article" | "div";
}

export function renderCard(props: CardProps): string {
  const tag = props.as || "section";
  const kickerHtml = props.kicker
    ? `<p class="card-kicker">${escapeHtml(props.kicker)}</p>`
    : "";
  const titleHtml = props.title
    ? `<h2 class="card-title">${escapeHtml(props.title)}</h2>`
    : "";
  const actionHtml = props.actionHtml
    ? `<div class="card-action">${props.actionHtml}</div>`
    : "";

  const headerHtml =
    kickerHtml || titleHtml || actionHtml
      ? `<div class="card-header"><div>${kickerHtml}${titleHtml}</div>${actionHtml}</div>`
      : "";
  const idAttr = props.id ? ` id="${escapeHtml(props.id)}"` : "";
  const classAttr = `card ${props.extraClass || ""}`.trim();

  return `
    <${tag} class="${classAttr}"${idAttr}>
      ${headerHtml}
      <div class="card-body">
        ${props.bodyHtml}
      </div>
    </${tag}>
  `.trim();
}
