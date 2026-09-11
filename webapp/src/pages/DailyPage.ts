import {
  renderCareerPath,
  renderGuessInput,
  renderLoadingState,
  renderErrorState,
} from "@/components";
import { escapeHtml } from "@/utils/format";
import { squares } from "@/utils/game";
import { t } from "@/i18n";
import type { DailyState, DailyGuessResult, DailyComparison } from "@/features/daily/types";
import type { DailyController } from "@/features/daily/controller";
import { DEFAULT_SQUARE_SYMBOLS } from "@/features/daily/controller";

const CLUES: Record<string, (args: Record<string, any>) => string> = {
  "feedback.nationality_same": () => t("daily.sameNat"),
  "feedback.nationality_diff": () => t("daily.diffNat"),
  "feedback.position_same": () => t("daily.samePos"),
  "feedback.position_diff": () => t("daily.diffPos"),
  "feedback.birth_same": (a) => `${t("daily.sameYear")} ${a?.year ?? ""}`,
  "feedback.birth_before": (a) => `${t("daily.older")} ${a?.year ?? ""}`,
  "feedback.birth_after": (a) => `${t("daily.younger")} ${a?.year ?? ""}`,
};

function renderComparison(data?: DailyComparison): string {
  if (!data) return "";
  const items = (data.clues || [])
    .map((clue) => {
      const render = CLUES[clue && clue.key];
      return render ? `<li>${escapeHtml(render(clue.args || {}))}</li>` : "";
    })
    .filter(Boolean)
    .join("");

  return `<div>${escapeHtml(t("daily.compared"))} <b>${escapeHtml(data.name)}</b>:<ul>${items}</ul></div>`;
}

function renderResultCard(state: DailyState): string {
  if (state.cardImage) {
    return `
      <div class="result-card">
        <img src="${escapeHtml(state.cardImage)}" alt="${escapeHtml(t("daily.share"))}">
        <p class="muted center" style="text-align: center; margin-top: 8px; font-size: 12px;">
          ${escapeHtml(t("daily.cardHint"))}
        </p>
      </div>
    `.trim();
  }

  const disabledAttr = state.cardLoading ? " disabled" : "";
  const label = state.cardLoading ? t("daily.loading") : t("daily.showCard");
  return `
    <button class="btn ghost" style="margin-top: 8px;" id="show-card"${disabledAttr}>
      ${escapeHtml(label)}
    </button>
  `.trim();
}

function renderFeedback(feedback: DailyGuessResult | null | undefined, state: DailyState): string {
  if (!feedback) return "";

  if (feedback.status === "correct") {
    const shareHtml = feedback.share
      ? `<button class="btn ghost" style="margin-top: 10px;" id="share">${escapeHtml(t("daily.share"))}</button>${renderResultCard(state)}`
      : "";

    return `
      <div class="feedback ok" role="status" aria-live="polite">
        <b>${escapeHtml(t("daily.correct"))}</b> ${feedback.points_awarded ?? 0} ${escapeHtml(t("daily.gotPoints"))}.
        ${shareHtml}
      </div>
    `.trim();
  }

  if (feedback.status === "wrong") {
    let tail = "";
    if ((feedback.attempts_left ?? 0) > 0) {
      tail = `${escapeHtml(t("daily.left"))}: ${feedback.attempts_left}.`;
    } else if (feedback.answer) {
      tail = `<b>${escapeHtml(t("daily.answerWas"))} ${escapeHtml(feedback.answer)}</b>`;
    } else {
      tail = escapeHtml(t("daily.outOfAttempts"));
    }

    const shareHtml = feedback.share
      ? `<button class="btn ghost" style="margin-top: 10px;" id="share">${escapeHtml(t("daily.share"))}</button>${renderResultCard(state)}`
      : "";

    return `
      <div class="feedback no" role="status" aria-live="polite">
        <b>${escapeHtml(t("daily.wrong"))}</b> ${tail}
        ${renderComparison(feedback.comparison)}
        ${shareHtml}
      </div>
    `.trim();
  }

  if (feedback.status === "refused") {
    return `
      <div class="feedback no" role="status" aria-live="polite">
        ${escapeHtml(t("daily.already"))}
      </div>
    `.trim();
  }

  return "";
}

function renderHints(hints: any): string {
  if (!hints || !hints.total) {
    return `<p class="muted center" style="margin: 12px 0 0;">${escapeHtml(t("daily.noHints"))}</p>`;
  }

  const takenHtml = (hints.taken || [])
    .map((text: string) => `<div class="feedback">${escapeHtml(text)}</div>`)
    .join("\n");

  const left = Math.max(0, hints.total - (hints.used || 0));
  const unlockHtml =
    left > 0
      ? `
        <button class="btn ghost" id="hint" style="margin-top: 10px;">${escapeHtml(t("daily.hintBtn"))}</button>
        <p class="muted center" style="margin: 6px 0 0; font-size: 12px;">${left} ${escapeHtml(t("daily.hintsLeft"))}</p>
      `
      : "";

  return `
    ${takenHtml}
    ${unlockHtml}
  `.trim();
}

export function renderDailyPage(state?: DailyState): string {
  if (!state || (state.status === "loading" && !state.challenge)) {
    return renderLoadingState({ message: t("daily.loading") });
  }

  if (state.status === "error") {
    return renderErrorState({
      message: state.errorMessage || t("daily.error"),
      retryLabel: t("common.retry"),
      retryButtonId: "daily-retry",
    });
  }

  const today = state.challenge;
  if (!today || !today.available) {
    return `<div class="card center muted">${escapeHtml(t("daily.none"))}</div>`;
  }

  const done = !!today.solved || (today.attempts_left ?? 0) === 0;
  const attemptsUsed = today.attempts_used ?? 0;
  const maxAttempts = today.max_attempts ?? 5;
  const attemptsLeft = today.attempts_left ?? Math.max(0, maxAttempts - attemptsUsed);

  const statusPill = today.solved
    ? `<span class="pill done">${escapeHtml(t("daily.solved"))}</span>`
    : attemptsUsed > 0
      ? `<span class="pill">${escapeHtml(t("daily.left"))}: ${attemptsLeft}</span>`
      : `<span class="pill">${escapeHtml(t("daily.notPlayed"))}</span>`;

  const squaresHtml = squares(
    attemptsUsed,
    maxAttempts,
    !!today.solved,
    state.squaresSymbols || DEFAULT_SQUARE_SYMBOLS
  );

  const challengeHeaderCardHtml = `
    <div class="card" id="daily-challenge-card">
      <h2>${escapeHtml(t("daily.todayTitle"))} #${today.number ?? 1}</h2>
      <div style="display: flex; align-items: center; justify-content: space-between; gap: 10px;">
        <div>
          <div><b>${escapeHtml(today.difficulty_label || "")}</b> · ${today.points ?? 0} ${escapeHtml(t("daily.points"))}</div>
          <div class="squares" aria-label="Tentativi">${squaresHtml}</div>
        </div>
        ${statusPill}
      </div>
      ${today.bonus_available && !done ? `<p class="muted" style="margin: 8px 0 0; font-size: 12.5px;">${escapeHtml(t("daily.bonus"))}</p>` : ""}
    </div>
  `.trim();

  const careerCardHtml = `
    <div class="card" id="daily-career-card">
      ${renderCareerPath({ stops: today.career_path || [] })}
    </div>
  `.trim();

  const isSubmitting = state.status === "submitting";
  const guessBoxHtml = done
    ? ""
    : renderGuessInput({
        id: "daily-guess-form",
        inputId: "answer",
        submitButtonId: "submit",
        placeholder: t("daily.placeholder"),
        buttonLabel: isSubmitting ? t("daily.loading") : t("daily.guessBtn"),
        disabled: isSubmitting,
        value: state.inputValue,
      });

  const feedbackHtml = renderFeedback(state.feedback, state);
  const hintsHtml = done ? "" : renderHints(today.hints);

  const interactionCardHtml = `
    <div class="card" id="daily-interaction-card">
      ${guessBoxHtml}
      ${feedbackHtml}
      ${hintsHtml}
    </div>
  `.trim();

  return `
    <div style="display: flex; flex-direction: column; gap: 12px;">
      ${challengeHeaderCardHtml}
      ${careerCardHtml}
      ${interactionCardHtml}
    </div>
  `.trim();
}

export function attachDailyEventListeners(
  container: HTMLElement,
  controller: DailyController
): void {
  const input = container.querySelector<HTMLInputElement>("#answer");
  if (input) {
    input.oninput = () => {
      controller.setInputValue(input.value);
    };
    input.onkeydown = (event: KeyboardEvent) => {
      if (event.key === "Enter") {
        event.preventDefault();
        controller.submitGuess(input.value);
      }
    };
  }

  const submit = container.querySelector<HTMLButtonElement>("#submit");
  if (submit) {
    submit.onclick = (event: MouseEvent) => {
      event.preventDefault();
      const currentInput = container.querySelector<HTMLInputElement>("#answer");
      const answer = currentInput ? currentInput.value : "";
      controller.submitGuess(answer);
    };
  }

  const hint = container.querySelector<HTMLButtonElement>("#hint");
  if (hint) {
    hint.onclick = (event: MouseEvent) => {
      event.preventDefault();
      controller.takeHint();
    };
  }

  const showCard = container.querySelector<HTMLButtonElement>("#show-card");
  if (showCard) {
    showCard.onclick = (event: MouseEvent) => {
      event.preventDefault();
      controller.loadResultCard();
    };
  }

  const share = container.querySelector<HTMLButtonElement>("#share");
  if (share) {
    share.onclick = (event: MouseEvent) => {
      event.preventDefault();
      controller.openShareUrl();
    };
  }

  const retry = container.querySelector<HTMLButtonElement>("#daily-retry");
  if (retry) {
    retry.onclick = (event: MouseEvent) => {
      event.preventDefault();
      controller.retry();
    };
  }
}
