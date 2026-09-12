import { escapeHtml } from "@/utils/format";
import { renderButton } from "./Button";

export interface GuessInputProps {
  id?: string;
  inputId?: string;
  submitButtonId?: string;
  placeholder?: string;
  buttonLabel?: string;
  disabled?: boolean;
  loading?: boolean;
  helperText?: string;
  value?: string;
  extraClass?: string;
}

export function renderGuessInput(props: GuessInputProps): string {
  const inputId = props.inputId || "answer";
  const submitButtonId = props.submitButtonId || "submit";
  const placeholder = props.placeholder || "Indovina il calciatore...";
  const buttonLabel = props.buttonLabel || "Invia risposta";
  const disabledAttr = props.disabled || props.loading ? " disabled" : "";
  const valueAttr = props.value ? ` value="${escapeHtml(props.value)}"` : "";
  const idAttr = props.id ? ` id="${escapeHtml(props.id)}"` : "";
  const classAttr = `guess-box ${props.extraClass || ""}`.trim();

  const helperHtml = props.helperText
    ? `<div class="guess-helper-text" id="${escapeHtml(inputId)}-helper">${escapeHtml(props.helperText)}</div>`
    : "";
  const ariaDescribedBy = props.helperText ? ` aria-describedby="${escapeHtml(inputId)}-helper"` : "";

  const submitButtonHtml = renderButton({
    id: submitButtonId,
    label: buttonLabel,
    disabled: props.disabled,
    loading: props.loading,
    fullWidth: true,
    variant: "primary",
    type: "submit",
  });

  return `
    <form class="${classAttr}"${idAttr} onsubmit="return false;" role="search" aria-label="Guess player form">
      <label for="${escapeHtml(inputId)}" class="guess-label">${escapeHtml(placeholder)}</label>
      <input
        id="${escapeHtml(inputId)}"
        type="text"
        class="guess-input"
        autocomplete="off"
        autocorrect="off"
        autocapitalize="words"
        placeholder="${escapeHtml(placeholder)}"${valueAttr}${disabledAttr}${ariaDescribedBy}
      />
      ${helperHtml}
      ${submitButtonHtml}
    </form>
  `.trim();
}
