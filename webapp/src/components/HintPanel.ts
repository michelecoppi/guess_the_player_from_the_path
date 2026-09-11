import { escapeHtml } from "@/utils/format";
import { renderButton } from "./Button";

export interface HintPanelProps {
  id?: string;
  hintsTaken?: string[];
  hintsTotal?: number;
  hintsUsed?: number;
  disabled?: boolean;
  loading?: boolean;
  unlockButtonId?: string;
  unlockButtonLabel?: string;
  hintsLeftLabel?: string;
  noHintsLabel?: string;
  extraClass?: string;
}

export function renderHintPanel(props: HintPanelProps): string {
  const total = props.hintsTotal ?? 0;
  const used = props.hintsUsed ?? 0;
  const taken = props.hintsTaken || [];
  const unlockButtonId = props.unlockButtonId || "hint";
  const unlockLabel = props.unlockButtonLabel || "Usa indizio";
  const hintsLeftLabel = props.hintsLeftLabel || "indizi rimasti";
  const noHintsLabel = props.noHintsLabel || "Nessun indizio disponibile";

  if (total === 0 && taken.length === 0) {
    return `<p class="muted center" style="margin: 12px 0 0; font-size: 13px;">${escapeHtml(noHintsLabel)}</p>`;
  }

  const takenHtml = taken
    .map(
      (text) =>
        `<div class="hint-taken-item" role="note">${escapeHtml(text)}</div>`
    )
    .join("\n");

  const left = Math.max(0, total - used);
  let unlockButtonHtml = "";
  let remainingHtml = "";

  if (left > 0) {
    unlockButtonHtml = renderButton({
      id: unlockButtonId,
      label: unlockLabel,
      variant: "ghost",
      disabled: props.disabled,
      loading: props.loading,
      fullWidth: true,
    });
    remainingHtml = `<p class="hints-remaining">${left} ${escapeHtml(hintsLeftLabel)}</p>`;
  }

  const idAttr = props.id ? ` id="${escapeHtml(props.id)}"` : "";
  const classAttr = `hint-panel ${props.extraClass || ""}`.trim();

  return `
    <div class="${classAttr}"${idAttr}>
      ${takenHtml}
      ${unlockButtonHtml}
      ${remainingHtml}
    </div>
  `.trim();
}
