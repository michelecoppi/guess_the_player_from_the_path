import { escapeHtml } from "@/utils/format";

export interface ModalProps {
  id?: string;
  title: string;
  bodyHtml: string;
  footerHtml?: string;
  closeButtonId?: string;
  extraClass?: string;
}

export function renderModal(props: ModalProps): string {
  const idAttr = props.id ? ` id="${escapeHtml(props.id)}"` : "";
  const titleId = props.id ? `${props.id}-title` : "modal-title";
  const closeButtonId = props.closeButtonId || "modal-close-btn";
  const classAttr = `modal-backdrop ${props.extraClass || ""}`.trim();

  const footerHtml = props.footerHtml
    ? `<div class="modal-footer">${props.footerHtml}</div>`
    : "";

  return `
    <div class="${classAttr}"${idAttr} role="presentation">
      <div class="modal-dialog" role="dialog" aria-modal="true" aria-labelledby="${escapeHtml(titleId)}">
        <div class="modal-header">
          <h2 id="${escapeHtml(titleId)}" class="modal-title">${escapeHtml(props.title)}</h2>
          <button type="button" class="modal-close" id="${escapeHtml(closeButtonId)}" aria-label="Chiudi finestra">✕</button>
        </div>
        <div class="modal-body">
          ${props.bodyHtml}
        </div>
        ${footerHtml}
      </div>
    </div>
  `.trim();
}
