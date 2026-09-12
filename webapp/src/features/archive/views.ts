/**
 * Archive Feature Views — Issue #44
 *
 * Pure rendering functions. No side effects, no DOM manipulation.
 * All dynamic strings are passed through escapeHtml().
 */

import { escapeHtml } from "@/utils/format";
import { t } from "@/i18n";
import { renderCareerPath, renderLoadingState, renderErrorState } from "@/components";
import type { ArchiveState, ArchiveCalendarDay, ArchiveGuessResult } from "./types";
import type { DailyComparison } from "@/features/daily/types";

// ---------------------------------------------------------------------------
// Comparison feedback (identical logic to DailyPage — same backend format)
// ---------------------------------------------------------------------------

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
  return `<div>${escapeHtml(t("daily.compared"))} <b>${escapeHtml(data.name ?? "")}</b>:<ul>${items}</ul></div>`;
}

// ---------------------------------------------------------------------------
// Guess feedback panel
// ---------------------------------------------------------------------------

function renderArchiveFeedback(feedback: ArchiveGuessResult | null): string {
  if (!feedback) return "";

  if (feedback.status === "correct") {
    const shareHtml = feedback.share
      ? `<button class="btn ghost archive-share-btn" id="archive-share" style="margin-top: 10px;">${escapeHtml(t("archive.share"))}</button>`
      : "";
    return `
      <div class="feedback ok" role="status" aria-live="polite">
        <b>${escapeHtml(t("archive.correct"))}</b>
        ${shareHtml}
      </div>
    `.trim();
  }

  if (feedback.status === "wrong") {
    let tail = "";
    if ((feedback.attempts_left ?? 0) > 0) {
      tail = `${escapeHtml(t("archive.attemptsLeft"))}: ${feedback.attempts_left}.`;
    } else if (feedback.answer) {
      tail = `<b>${escapeHtml(t("daily.answerWas"))} ${escapeHtml(feedback.answer)}</b>`;
    } else {
      tail = escapeHtml(t("archive.outOfAttempts"));
    }

    const shareHtml = feedback.share
      ? `<button class="btn ghost archive-share-btn" id="archive-share" style="margin-top: 10px;">${escapeHtml(t("archive.share"))}</button>`
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
        ${escapeHtml(t("archive.alreadySolved"))}
      </div>
    `.trim();
  }

  if (feedback.status === "no_challenge") {
    return `
      <div class="feedback no" role="status" aria-live="polite">
        ${escapeHtml(t("archive.dayUnavailable"))}
      </div>
    `.trim();
  }

  return "";
}

// ---------------------------------------------------------------------------
// Calendar view
// ---------------------------------------------------------------------------

const STATUS_ICON: Record<string, string> = {
  solved: "✅",
  lost: "❌",
  recovered: "🔄",
  missed: "⬜",
};

function renderCalendarDay(day: ArchiveCalendarDay): string {
  const icon = STATUS_ICON[day.status] ?? "⬜";
  const statusLabel = t(`archive.${day.status}` as any);
  const ariaLabel = `${day.label} · ${statusLabel}${day.attempts != null ? ` · ${day.attempts} ${t("archive.attemptsSuffix")}` : ""}`;
  const diffLabel = day.difficulty_label ? `<span class="archive-day-diff">${escapeHtml(day.difficulty_label)}</span>` : "";
  const numLabel = `<span class="archive-day-number">#${day.number}</span>`;
  const inner = `
    <span class="archive-day-icon" aria-hidden="true">${icon}</span>
    ${numLabel}
    <span class="archive-day-label">${escapeHtml(day.label)}</span>
    ${diffLabel}
    <span class="archive-day-status-text sr-only">${escapeHtml(statusLabel)}</span>
  `.trim();

  if (day.playable) {
    return `<button class="archive-day-card ${day.status}" data-archive-day="${escapeHtml(day.day)}" aria-label="${escapeHtml(ariaLabel)}" type="button">${inner}</button>`;
  }

  return `<div class="archive-day-card ${day.status}" aria-label="${escapeHtml(ariaLabel)}">${inner}</div>`;
}

function renderCalendarView(state: ArchiveState): string {
  if (state.status === "loading" || state.status === "idle") {
    return renderLoadingState({ message: t("archive.loading") });
  }

  if (state.status === "error") {
    return `
      ${renderErrorState({ message: t("archive.error") })}
      <button class="btn ghost" id="archive-retry" style="margin-top: 12px;">${escapeHtml(t("archive.retry"))}</button>
    `.trim();
  }

  if (state.calendar.length === 0) {
    return `<p class="muted center" style="padding: 40px 20px;">${escapeHtml(t("archive.empty"))}</p>`;
  }

  const days = state.calendar
    .map((d) => renderCalendarDay(d))
    .join("\n");

  return `
    <section class="archive-calendar" aria-label="${escapeHtml(t("archive.calendarLabel"))}">
      ${days}
    </section>
  `.trim();
}

// ---------------------------------------------------------------------------
// Challenge view
// ---------------------------------------------------------------------------

function renderAttemptDots(used: number, max: number): string {
  const dots = Array.from({ length: max }, (_, i) =>
    `<span class="archive-attempt-dot ${i < used ? "used" : "empty"}" aria-hidden="true"></span>`,
  ).join("");
  return `<div class="archive-attempts-bar" role="img" aria-label="${used}/${max}">${dots}</div>`;
}

function renderChallengeView(state: ArchiveState): string {
  const { challenge, feedback, status, error, draftAnswer } = state;

  const backBtn = `
    <button class="btn ghost archive-back-btn" id="archive-back" data-archive-back="1" style="margin-bottom: 12px;">
      ‹ ${escapeHtml(t("archive.back"))}
    </button>
  `.trim();

  if (status === "challenge_loading") {
    return `${backBtn}${renderLoadingState({ message: t("archive.loading") })}`;
  }

  if (status === "challenge_error") {
    return `
      ${backBtn}
      ${renderErrorState({ message: error || t("archive.error") })}
      <button class="btn ghost" id="archive-challenge-retry" style="margin-top: 12px;">${escapeHtml(t("archive.retry"))}</button>
    `.trim();
  }

  if (!challenge) {
    return `${backBtn}${renderLoadingState({ message: t("archive.loading") })}`;
  }

  const meta = `
    <div class="archive-challenge-meta">
      <span class="pill">#${challenge.number} · ${escapeHtml(challenge.label)}</span>
      <span class="pill">${escapeHtml(challenge.difficulty_label)}</span>
    </div>
  `.trim();

  const attemptsBar = renderAttemptDots(challenge.attempts_used, challenge.max_attempts);

  const careerHtml = challenge.career_path?.length
    ? renderCareerPath({ stops: challenge.career_path })
    : `<p class="muted">${escapeHtml(t("archive.error"))}</p>`;

  const feedbackHtml = renderArchiveFeedback(feedback);

  const isGameOver =
    challenge.solved ||
    challenge.attempts_left <= 0 ||
    feedback?.status === "correct" ||
    (feedback?.status === "wrong" && (feedback.attempts_left ?? 0) <= 0) ||
    feedback?.status === "refused";

  const submitting = status === "submitting";

  const inputHtml = isGameOver
    ? ""
    : `
    <form id="archive-guess-form" style="margin-top: 12px;" autocomplete="off">
      <div class="guess-box">
        <input
          type="text"
          id="archive-answer"
          name="archive-answer"
          class="guess-input"
          placeholder="${escapeHtml(t("archive.placeholder"))}"
          value="${escapeHtml(draftAnswer)}"
          autocomplete="off"
          autocorrect="off"
          autocapitalize="off"
          spellcheck="false"
          ${submitting ? "disabled" : ""}
        >
      </div>
      <button
        class="btn"
        id="archive-submit"
        type="submit"
        style="margin-top: 8px;"
        ${submitting || !draftAnswer.trim() ? "disabled" : ""}
      >${escapeHtml(submitting ? t("archive.loading") : t("archive.submitBtn"))}</button>
    </form>
  `.trim();

  const errorBanner = error
    ? `<p class="muted" style="color: var(--danger); margin-top: 8px;">${escapeHtml(error)}</p>`
    : "";

  return `
    ${backBtn}
    <section class="archive-challenge-header" aria-label="${escapeHtml(t("archive.challengeLabel"))}">
      ${meta}
      ${attemptsBar}
    </section>
    ${careerHtml}
    ${feedbackHtml}
    ${inputHtml}
    ${errorBanner}
  `.trim();
}

// ---------------------------------------------------------------------------
// Main dispatcher
// ---------------------------------------------------------------------------

export function renderArchiveViews(state: ArchiveState): string {
  if (state.view === "challenge") {
    return renderChallengeView(state);
  }
  return renderCalendarView(state);
}
