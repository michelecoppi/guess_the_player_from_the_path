import { escapeHtml } from "@/utils/format";
import { renderButton } from "./Button";

export interface FeedbackClue {
  text: string;
}

export interface FeedbackBoxProps {
  id?: string;
  status: "correct" | "wrong" | "refused" | "info";
  title?: string;
  message?: string;
  clues?: string[];
  comparedName?: string;
  comparedLabel?: string;
  shareLabel?: string;
  shareId?: string;
  onShare?: boolean;
  extraClass?: string;
}

export function renderFeedbackBox(props: FeedbackBoxProps): string {
  const statusClass =
    props.status === "correct"
      ? "ok"
      : props.status === "wrong" || props.status === "refused"
        ? "no"
        : "";

  const titleHtml = props.title
    ? `<b>${escapeHtml(props.title)}</b> `
    : "";
  const messageHtml = props.message
    ? `<span>${escapeHtml(props.message)}</span>`
    : "";

  let cluesHtml = "";
  if (props.clues && props.clues.length > 0) {
    const items = props.clues
      .map((c) => `<li>${escapeHtml(c)}</li>`)
      .join("");
    const compLabel = props.comparedLabel ?? (props.comparedName ? "Confronto con" : "");
    const compared = props.comparedName
      ? `<div>${escapeHtml(compLabel)} <b>${escapeHtml(props.comparedName)}</b>:</div>`
      : "";
    cluesHtml = `<div class="clues-container" style="margin-top: 8px;">${compared}<ul>${items}</ul></div>`;
  }

  let shareButtonHtml = "";
  if (props.onShare && props.shareLabel) {
    shareButtonHtml = renderButton({
      id: props.shareId || "share",
      label: props.shareLabel,
      variant: "ghost",
      fullWidth: true,
      extraClass: "share-btn",
    });
  }

  const idAttr = props.id ? ` id="${escapeHtml(props.id)}"` : "";
  const classAttr = `feedback ${statusClass} ${props.extraClass || ""}`.trim();

  return `
    <div class="${classAttr}"${idAttr} role="status" aria-live="polite">
      ${titleHtml}${messageHtml}
      ${cluesHtml}
      ${shareButtonHtml ? `<div style="margin-top: 10px;">${shareButtonHtml}</div>` : ""}
    </div>
  `.trim();
}
