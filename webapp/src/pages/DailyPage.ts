import { DEFAULT_SQUARE_SYMBOLS } from "@/features/daily/controller";
import {
  renderCareerPath,
  renderGuessInput,
  renderLoadingState,
  renderErrorState,
  renderHintPanel,
  renderEmptyState,
} from "@/components";
import { escapeHtml } from "@/utils/format";
import { v } from "@/i18n/visual";
import { icon } from "@/components/Icon";
import { t } from "@/i18n";
import type {
  DailyState,
  DailyGuessResult,
  DailyComparison,
} from "@/features/daily/types";
import type { DailyController } from "@/features/daily/controller";

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

function renderFeedback(
  feedback: DailyGuessResult | null | undefined,
  state: DailyState,
): string {
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

export function renderDailyPage(state?: DailyState): string {
  const title = `<header class="daily-heading"><p class="eyebrow">Daily Challenge</p><h2>${v("who")}</h2><p class="muted">${v("follow")}</p></header>`;
  if (!state || (state.status === "loading" && !state.challenge)) {
    return `${title}<div class="career-loading">${renderLoadingState({ message: t("daily.loading") })}<div class="loading-lines" aria-hidden="true">${"<i></i>".repeat(5)}</div></div>`;
  }
  if (state.status === "error") {
    return `${title}${renderErrorState({ title: v("connection"), message: state.errorMessage || t("daily.error"), retryLabel: t("common.retry"), retryButtonId: "daily-retry" })}`;
  }
  const today = state.challenge;
  if (!today || !today.available) {
    return `${title}${renderEmptyState({ title: v("wait"), description: t("daily.none") })}`;
  }
  const done = !!today.solved || (today.attempts_left ?? 0) === 0;
  const used = today.attempts_used ?? 0;
  const max = today.max_attempts ?? 5;
  const left = today.attempts_left ?? Math.max(0, max - used);
  const submitting = state.status === "submitting";
  const attempts = Array.from({ length: max }, (_, i) => {
    const status =
      i < used
        ? today.solved && i === used - 1
          ? "scored"
          : "missed"
        : "unused";
    const key =
      status === "scored"
        ? "correct"
        : status === "missed"
          ? "wrong"
          : "unused";
    const custom =
      state.squaresSymbols?.[key] !== DEFAULT_SQUARE_SYMBOLS[key]
        ? state.squaresSymbols?.[key]
        : undefined;
    return `<span class="attempt ${status}" aria-hidden="true">${custom ? escapeHtml(custom) : status === "scored" ? icon("check") : status === "missed" ? icon("close") : i + 1}</span>`;
  }).join("");
  const hints = today.hints;
  return `<article class="daily-page" data-state="${state.status}">
    <header class="daily-heading" id="daily-challenge-card">
      <div class="edition"><span class="eyebrow">Daily Challenge</span><span class="edition-number">Nº ${escapeHtml(today.number ?? 1)}</span></div>
      <h2>${v("who")}</h2><p class="muted">${v("follow")}</p>
      <div class="match-meta"><span>${escapeHtml(today.difficulty_label || t("daily.difficulty"))}</span><span><b>${today.points ?? 0}</b> ${escapeHtml(t("daily.points"))}</span><span>${escapeHtml(today.solved ? t("daily.solved") : done ? v("final") : t("daily.todayTitle"))}</span></div>
    </header>
    <div class="daily-layout">
      <section class="career-sheet" id="daily-career-card" aria-label="${v("career")}">
        <div class="sheet-heading"><h3>${v("career")}</h3>${icon("career")}</div>
        <div class="career-columns" aria-hidden="true"><span>${v("season")}</span><span>${v("club")}</span><span>${v("apps")}</span></div>
        ${renderCareerPath({ stops: today.career_path || [], emptyText: v("missing") })}
      </section>
      <section class="answer-desk" id="daily-interaction-card" aria-label="${v("answer")}">
        <div class="attempts-line"><span>${escapeHtml(done ? v("final") : t("daily.left"))}${done ? "" : ` <b>${left}</b>`}</span><div class="attempts" role="img" aria-label="${used}/${max}">${attempts}</div></div>
        ${done ? (!state.feedback ? `<div class="feedback ${today.solved ? "ok" : "no"}" role="status"><h3>${escapeHtml(today.solved ? t("daily.solved") : v("final"))}</h3><p>${escapeHtml(today.solved ? v("next") : t("daily.outOfAttempts"))}</p></div>` : "") : renderGuessInput({ id: "daily-guess-form", inputId: "answer", submitButtonId: "submit", placeholder: t("daily.placeholder"), buttonLabel: submitting ? t("daily.loading") : t("daily.guessBtn"), loading: submitting, value: state.inputValue })}
        ${state.errorMessage ? `<div class="feedback no" role="alert">${escapeHtml(state.errorMessage)}</div>` : ""}
        ${renderFeedback(state.feedback, state)}
        ${done ? "" : renderHintPanel({ hintsTaken: hints?.taken, hintsTotal: hints?.total, hintsUsed: hints?.used, disabled: submitting, unlockButtonLabel: t("daily.hintBtn"), hintsLeftLabel: t("daily.hintsLeft"), noHintsLabel: t("daily.noHints") })}
        ${today.bonus_available && !done ? `<p class="bonus-note">${escapeHtml(t("daily.bonus"))}</p>` : ""}
      </section>
    </div>
  </article>`;
}

export function attachDailyEventListeners(
  container: HTMLElement,
  controller: DailyController,
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
