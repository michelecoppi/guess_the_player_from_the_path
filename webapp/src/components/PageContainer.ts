import { escapeHtml } from "@/utils/format";

export interface PageContainerProps {
  id?: string;
  title?: string;
  kicker?: string;
  headerActionHtml?: string;
  contentHtml: string;
  extraClass?: string;
}

export function renderPageContainer(props: PageContainerProps): string {
  const kickerHtml = props.kicker
    ? `<p class="page-kicker">${escapeHtml(props.kicker)}</p>`
    : "";
  const titleHtml = props.title
    ? `<h1 class="page-title">${escapeHtml(props.title)}</h1>`
    : "";
  const actionHtml = props.headerActionHtml
    ? `<div>${props.headerActionHtml}</div>`
    : "";

  const headerHtml =
    kickerHtml || titleHtml || actionHtml
      ? `<header class="page-header" style="display:flex;align-items:center;justify-content:space-between;gap:12px;">
          <div>${kickerHtml}${titleHtml}</div>
          ${actionHtml}
        </header>`
      : "";

  const idAttr = props.id ? ` id="${escapeHtml(props.id)}"` : "";
  const classAttr = `page-container ${props.extraClass || ""}`.trim();

  return `
    <div class="${classAttr}"${idAttr}>
      ${headerHtml}
      ${props.contentHtml}
    </div>
  `.trim();
}
