import { escapeHtml } from "@/utils/format";
import { icon } from "@/components/Icon";
import {
  renderCareerPath,
  renderGuessInput,
  renderLoadingState,
  renderErrorState,
  renderButton,
  renderFeedbackBox,
} from "@/components";
import { t } from "@/i18n";
import type {
  TrainingState,
  TrainingFeedback,
  TrainingComparison,
} from "./types";

const CLUES: Record<string, (args: Record<string, any>) => string> = {
  "feedback.nationality_same": () => t("daily.sameNat"),
  "feedback.nationality_diff": () => t("daily.diffNat"),
  "feedback.position_same": () => t("daily.samePos"),
  "feedback.position_diff": () => t("daily.diffPos"),
  "feedback.birth_same": (a) => `${t("daily.sameYear")} ${a?.year ?? ""}`.trim(),
  "feedback.birth_before": (a) => `${t("daily.older")} ${a?.year ?? ""}`.trim(),
  "feedback.birth_after": (a) => `${t("daily.younger")} ${a?.year ?? ""}`.trim(),
};

function renderClues(comparison?: TrainingComparison): string[] {
  if (!comparison?.clues?.length) return [];
  return comparison.clues
    .map((clue) => {
      const fn = CLUES[clue?.key];
      return fn ? fn(clue.args || {}) : "";
    })
    .filter(Boolean);
}

function renderFeedback(feedback?: TrainingFeedback | null): string {
  if (!feedback || !feedback.status) return "";
  const isCorrect = feedback.status === "correct";
  const title = isCorrect
    ? t("training.correct")
    : feedback.done
      ? t("training.ended")
      : t("training.wrong");

  const message = feedback.answer
    ? t("training.answer", { name: feedback.answer })
    : undefined;

  const clues = renderClues(feedback.comparison);

  return renderFeedbackBox({
    status: isCorrect ? "correct" : "wrong",
    title,
    message,
    clues,
    comparedName: feedback.comparison?.name,
    comparedLabel: t("daily.compared"),
  });
}

function renderAlerts(state: TrainingState): string {
  const parts: string[] = [];
  if (state.notice) {
    const noticeText = t(`training.${state.notice}`);
    parts.push(`<p class="notice" role="status">${escapeHtml(noticeText)}</p>`);
  }
  if (state.error) {
    const errorText = t(`training.${state.error}`);
    parts.push(
      `<div class="error-box" role="alert"><p>${escapeHtml(errorText)}</p></div>`,
    );
  }
  return parts.join("\n");
}

export function renderNoSessionView(state: TrainingState): string {
  const startBtnHtml = renderButton({
    id: "training-start",
    label: t("training.start"),
    variant: "primary",
    fullWidth: true,
    disabled: state.busy,
  });

  return `
    <div class="training-empty-card">
      <div class="training-icon-wrap" aria-hidden="true">
        ${icon("training")}
      </div>
      <h3>${escapeHtml(t("training.title"))}</h3>
      <p class="training-desc">${escapeHtml(t("training.desc"))}</p>
      <div class="training-rules-card">
        <p>${escapeHtml(t("training.rules"))}</p>
      </div>
      ${renderAlerts(state)}
      <div class="training-actions">
        ${startBtnHtml}
      </div>
    </div>
  `.trim();
}

export function renderFinishedSessionView(state: TrainingState): string {
  const session = state.data!.session!;
  const feedback = state.data?.feedback;
  const isSolved = Boolean(session.solved);

  const nextBtnHtml = renderButton({
    id: "training-next",
    label: t("training.next"),
    variant: "primary",
    fullWidth: true,
    disabled: state.busy,
  });

  return `
    <div class="training-finished-card">
      <div class="training-result-mark ${isSolved ? "ok" : "ended"}" aria-hidden="true">
        ${isSolved ? "✦" : "✓"}
      </div>
      <h3 class="training-result-title">${escapeHtml(t("training.complete"))}</h3>

      ${feedback ? renderFeedback(feedback) : ""}

      <div class="training-score-grid">
        <div class="training-score-tile">
          <strong>${session.solved} / ${session.total}</strong>
          <span>${escapeHtml(t("training.solved"))}</span>
        </div>
        <div class="training-score-tile">
          <strong>${session.spent}</strong>
          <span>${escapeHtml(t("training.spent"))}</span>
        </div>
      </div>

      ${renderAlerts(state)}

      <div class="training-actions">
        ${nextBtnHtml}
      </div>
    </div>
  `.trim();
}

export function renderActiveSessionView(state: TrainingState): string {
  const session = state.data!.session!;
  const attemptsLeft = Math.max(0, session.max_attempts - session.attempts);

  const attemptsHtml = `<p class="training-attempts">${escapeHtml(
    t("training.attempts", { n: attemptsLeft }),
  )}</p>`;

  const careerPathHtml = session.career_path
    ? renderCareerPath({ stops: session.career_path })
    : "";

  const guessInputHtml = renderGuessInput({
    inputId: "training-answer",
    submitButtonId: "training-submit",
    placeholder: t("training.placeholder"),
    buttonLabel: t("training.submitBtn"),
    disabled: state.busy,
    value: state.draftAnswer,
  });

  const revealLabel =
    state.confirming === "reveal"
      ? t("training.revealSure")
      : t("training.reveal");

  const revealBtnHtml = renderButton({
    id: "training-reveal",
    label: revealLabel,
    variant: "ghost",
    fullWidth: true,
    disabled: state.busy,
  });

  const difficultyPill = session.difficulty_label
    ? `<span class="pill">${escapeHtml(session.difficulty_label)}</span>`
    : "";

  return `
    <div class="training-active-challenge">
      <div class="training-round-bar">
        <span class="eyebrow">${escapeHtml(
          t("training.round", { n: session.round + 1, total: session.total }),
        )}</span>
        ${difficultyPill}
      </div>

      <div class="training-career-container">
        ${careerPathHtml}
      </div>

      ${attemptsHtml}

      ${guessInputHtml}

      ${renderAlerts(state)}

      ${renderFeedback(state.data?.feedback)}

      <div class="training-actions">
        ${revealBtnHtml}
      </div>
    </div>
  `.trim();
}

export function renderTrainingView(state: TrainingState): string {
  let content = "";

  if (state.status === "loading" && !state.data) {
    content = renderLoadingState({ message: t("common.loading") });
  } else if (state.status === "error" && !state.data) {
    const errorKey = state.error ? `training.${state.error}` : "training.loadError";
    const translated = t(errorKey);
    const message = translated !== errorKey ? translated : t("training.loadError");
    content = renderErrorState({
      title: t("training.title"),
      message,
      retryLabel: t("common.retry"),
      retryButtonId: "training-retry",
    });
  } else if (!state.data?.session) {
    content = renderNoSessionView(state);
  } else if (state.data.session.finished) {
    content = renderFinishedSessionView(state);
  } else {
    content = renderActiveSessionView(state);
  }

  return `
    <div class="training-view" id="training-view">
      <button class="back-link" data-training-back type="button">
        ${icon("back")} ${escapeHtml(t("training.backToArena"))}
      </button>

      <header class="page-heading">
        <p class="eyebrow">${escapeHtml(t("training.tag"))}</p>
        <h2 class="page-title">${escapeHtml(t("training.title"))}</h2>
      </header>

      ${content}
    </div>
  `.trim();
}
