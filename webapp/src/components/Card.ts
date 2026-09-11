import { escapeHtml } from "@/utils/format";

export interface CardProps {
  id?: string;
  kicker?: string;
  title?: string;
  bodyHtml: string;
  extraClass?: string;
}

export function renderCard(props: CardProps): string {
  const kickerHtml = props.kicker
    ? `<p class="card-kicker">${escapeHtml(props.kicker)}</p>`
    : "";
  const titleHtml = props.title
    ? `<h2 class="card-title">${escapeHtml(props.title)}</h2>`
    : "";
  const headerHtml =
    kickerHtml || titleHtml
      ? `<div class="card-header"><div>${kickerHtml}${titleHtml}</div></div>`
      : "";
  const idAttr = props.id ? ` id="${escapeHtml(props.id)}"` : "";
  const classAttr = `card ${props.extraClass || ""}`.trim();

  return `
    <section class="${classAttr}"${idAttr}>
      ${headerHtml}
      <div class="card-body">
        ${props.bodyHtml}
      </div>
    </section>
  `;
}
