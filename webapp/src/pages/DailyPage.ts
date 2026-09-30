import { getResolvedAppearance } from "@/appearance";
import { resultCardAttributes } from "@/appearance/surfaces";
import { DEFAULT_SQUARE_SYMBOLS } from "@/features/daily/controller";
import { bindRecapEntries, renderRecapBannerSlot } from "@/features/recap/entry";
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

let answerDockObserver: IntersectionObserver | null = null;

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

/**
 * The card as a small preview in the final report (#254): a tap enlarges it in place, where
 * it can be pressed and held to save or forward, as before.
 */
function renderResultCard(state: DailyState): string {
  if (state.cardImage) {
    return `
      <div class="result-card report-card" ${resultCardAttributes(getResolvedAppearance())}>
        <button type="button" class="report-card-preview" id="card-preview" aria-expanded="false">
          <img src="${escapeHtml(state.cardImage)}" alt="${escapeHtml(v("cardShort"))}">
          <span class="report-card-caption"><b>${escapeHtml(v("cardShort"))}</b><small>${escapeHtml(v("cardEnlarge"))}</small></span>
        </button>
        <p class="report-card-hint">${escapeHtml(t("daily.cardHint"))}</p>
      </div>
    `.trim();
  }
  if (state.cardLoading && state.feedback?.share) {
    return `<div class="report-card is-loading" aria-hidden="true"><span></span></div>`;
  }

  const disabledAttr = state.cardLoading ? " disabled" : "";
  const label = state.cardLoading ? t("daily.loading") : t("daily.showCard");
  return `
    <button class="btn ghost" style="margin-top: 8px;" id="show-card"${disabledAttr}>
      ${escapeHtml(label)}
    </button>
  `.trim();
}

function renderMatchReport(state: DailyState, feedback?: DailyGuessResult): string {
  const won = feedback ? feedback.status === "correct" : !!state.challenge?.solved;
  const attempts = feedback?.attempts_used ?? state.challenge?.attempts_used ?? 0;
  // Only the server's post-game response may reveal a name or awarded score.
  const answer = feedback?.answer;
  return `<section class="feedback match-report ${won ? "ok" : "no"}" role="status" aria-live="polite">
    <div class="report-top"><span class="eyebrow">${v("matchReport")}</span><span class="report-emblem" aria-hidden="true">${icon(won ? "ranking" : "career")}</span></div>
    <h3>${escapeHtml(won ? t("daily.correct") : v("final"))}</h3>
    ${answer ? renderReveal(answer, won, !!state.revealPending, editionLabel(state)) : won ? "" : renderSealed(editionLabel(state))}
    <div class="report-stats">
      ${feedback?.points_awarded != null ? `<div><strong>${feedback.points_awarded}</strong><span>${escapeHtml(t("daily.gotPoints"))}</span></div>` : ""}
      <div><strong>${attempts}<small> / ${state.challenge?.max_attempts ?? 5}</small></strong><span>${v("attemptsUsed")}</span></div>
    </div>
    <p class="report-note">${escapeHtml(won ? v("next") : t("daily.outOfAttempts"))}</p>
    ${feedback?.share ? renderShareRow(state) : ""}
    ${feedback?.share && !state.cardImage && !state.cardLoading ? "" : renderResultCard(state)}
    <div id="daily-next-event-slot"></div>
  </section>`;
}

/**
 * Share, copy and card in a single row (#254): the Telegram share stays the main action,
 * copy (#150) and the card become icon buttons with their own accessible names.
 */
function renderShareRow(state: DailyState): string {
  const notice = state.copyNotice
    ? `<p class="share-copy-notice" role="status">${escapeHtml(state.copyNotice)}</p>`
    : "";
  const cardBusy = state.cardLoading ? " disabled" : "";
  return `<div class="report-actions">
      <button class="btn" id="share">${icon("share")}${escapeHtml(v("shareShort"))}</button>
      <button type="button" class="btn ghost icon-btn" id="share-copy" aria-label="${escapeHtml(v("copyShort"))}" title="${escapeHtml(v("copyShort"))}">${icon("copy")}</button>
      <button type="button" class="btn ghost icon-btn" id="show-card" aria-label="${escapeHtml(v("cardShort"))}" title="${escapeHtml(v("cardShort"))}"${cardBusy}>${icon("image")}</button>
    </div>${notice}`;
}

function editionLabel(state: DailyState): string {
  return state.challenge?.number != null ? `Nº ${state.challenge.number}` : "";
}

/**
 * The name as a football sticker turning over: back of the card first, then the player.
 * It flips once, right after the final answer; any later render shows it already turned.
 */
function renderReveal(answer: string, won: boolean, animate: boolean, edition: string): string {
  return `<div class="reveal-card ${won ? "won" : "lost"}${animate ? " flipping" : ""}" data-reveal>
    <div class="reveal-inner">
      <div class="reveal-face reveal-back" aria-hidden="true"><span>?</span></div>
      <div class="reveal-face reveal-front">
        <span class="reveal-edition">${escapeHtml(edition)}</span>
        <span class="reveal-label">${escapeHtml(t(won ? "daily.revealWon" : "daily.revealLost"))}</span>
        <p class="report-player">${escapeHtml(answer)}</p>
      </div>
    </div>
  </div>`;
}

/** A lost Daily keeps its sticker face down: the name is only turned at midnight. */
function renderSealed(edition: string): string {
  return `<div class="reveal-card sealed">
    <div class="reveal-inner">
      <div class="reveal-face reveal-back"><span>?</span><small>${escapeHtml(edition)} · ${escapeHtml(t("daily.revealMidnight"))}</small></div>
    </div>
  </div>`;
}

/** "Copy the result" and its outcome, next to the Telegram share button (#150). */
function renderCopy(state: DailyState): string {
  const notice = state.copyNotice
    ? `<p class="share-copy-notice" role="status">${escapeHtml(state.copyNotice)}</p>`
    : "";
  return `<button class="btn ghost" style="margin-top: 10px;" id="share-copy">📋 ${escapeHtml(t("daily.copyResult"))}</button>${notice}`;
}

function renderFeedback(
  feedback: DailyGuessResult | null | undefined,
  state: DailyState,
): string {
  if (!feedback) return "";

  if (feedback.status === "correct" ||
      (feedback.status === "wrong" && feedback.attempts_left === 0)) {
    return renderMatchReport(state, feedback);
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
      ? `<button class="btn ghost" style="margin-top: 10px;" id="share">${escapeHtml(t("daily.share"))}</button>${renderCopy(state)}${renderResultCard(state)}`
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
  const title = `<header class="daily-heading"><p class="eyebrow">${escapeHtml(t("pages.dailyKicker"))}</p><h2>${v("who")}</h2><p class="muted">${v("follow")}</p></header>`;
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
  // Once the Daily is over the result comes first and the career folds away (#254).
  const careerSheet = `<section class="career-sheet" id="daily-career-card" aria-label="${v("career")}">
        <div class="sheet-heading"><div><h3>${v("career")}</h3><p class="career-caption">${v("clubCount").replace("{n}", String(today.career_path?.length ?? 0))}</p></div>${icon("career")}</div>
        <div class="career-columns" aria-hidden="true"><span>${v("season")}</span><span>${v("club")}</span><span>${v("apps")}</span></div>
        ${renderCareerPath({ stops: today.career_path || [], emptyText: v("missing") })}
      </section>`;
  return `<article class="daily-page" data-state="${state.status}">
    ${renderRecapBannerSlot()}
    <header class="daily-heading" id="daily-challenge-card">
      <div class="edition"><span class="eyebrow">${escapeHtml(t("pages.dailyKicker"))}</span><span class="edition-number">Nº ${escapeHtml(today.number ?? 1)}</span></div>
      <h2>${v("who")}</h2><p class="muted">${v("follow")}</p>
      <div class="match-meta"><span>${escapeHtml(today.difficulty_label || t("daily.difficulty"))}</span><span><b>${today.points ?? 0}</b> ${escapeHtml(t("daily.points"))}</span><span>${escapeHtml(today.solved ? t("daily.solved") : done ? v("final") : t("daily.todayTitle"))}</span></div>
    </header>
    ${state.introVisible && !done ? `<section class="daily-intro" aria-labelledby="daily-intro-title">
      <h3 id="daily-intro-title">${v("introTitle")}</h3>
      <ol><li>${v("introPath")}</li><li>${v("introAttempts")}</li><li>${v("introHints")}</li></ol>
      <button type="button" class="btn ghost" id="daily-intro-dismiss">${v("introDismiss")}</button>
    </section>` : ""}
    ${done ? "" : `<button type="button" class="daily-answer-dock" id="daily-answer-dock" aria-controls="daily-interaction-card"><span>${v("answer")}</span><strong>${escapeHtml(t("daily.left"))} ${left}</strong>${icon("arrow")}</button>`}
    <div class="daily-layout${done ? " is-done" : ""}">
      ${done ? "" : careerSheet}
      <section class="answer-desk" id="daily-interaction-card" aria-label="${v("answer")}">
        <div class="attempts-line"><span>${escapeHtml(done ? v("final") : t("daily.left"))}${done ? "" : ` <b>${left}</b>`}</span><div class="attempts" role="img" aria-label="${used}/${max}">${attempts}</div></div>
        ${done ? (!state.feedback ? renderMatchReport(state) : "") : renderGuessInput({ id: "daily-guess-form", inputId: "answer", submitButtonId: "submit", placeholder: t("daily.placeholder"), buttonLabel: submitting ? t("daily.loading") : t("daily.guessBtn"), loading: submitting, value: state.inputValue })}
        ${state.errorMessage ? `<div class="feedback no" role="alert">${escapeHtml(state.errorMessage)}</div>` : ""}
        ${renderFeedback(state.feedback, state)}
        ${done ? "" : renderHintPanel({ hintsTaken: hints?.taken, hintsTotal: hints?.total, hintsUsed: hints?.used, disabled: submitting, unlockButtonLabel: t("daily.hintBtn"), hintsLeftLabel: t("daily.hintsLeft"), noHintsLabel: t("daily.noHints") })}
        ${today.bonus_available && !done ? `<p class="bonus-note">${escapeHtml(t("daily.bonus"))}</p>` : ""}
      </section>
      ${done ? `<details class="career-fold"><summary>${icon("career")}<span><b>${v("showCareer")}</b><small>${v("clubCount").replace("{n}", String(today.career_path?.length ?? 0))}</small></span></summary>${careerSheet}</details>` : ""}
    </div>
  </article>`;
}

export function attachDailyEventListeners(
  container: HTMLElement,
  controller: DailyController,
): void {
  answerDockObserver?.disconnect();
  bindRecapEntries(container);
  if (container.querySelector(".reveal-card.flipping")) controller.consumeReveal();
  container.querySelector<HTMLButtonElement>("#daily-intro-dismiss")?.addEventListener("click", () => {
    controller.dismissIntro();
    container.querySelector<HTMLInputElement>("#answer")?.focus();
  });
  answerDockObserver = null;
  const dock = container.querySelector<HTMLButtonElement>("#daily-answer-dock");
  const input = container.querySelector<HTMLInputElement>("#answer");
  if (dock && input) {
    dock.onclick = () => input.focus();
    if (typeof IntersectionObserver !== "undefined") {
      answerDockObserver = new IntersectionObserver(([entry]) => {
        dock.hidden = entry.isIntersecting;
      }, { rootMargin: "0px 0px -110px 0px" });
      answerDockObserver.observe(input);
    }
  }
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

  const preview = container.querySelector<HTMLButtonElement>("#card-preview");
  const toggleCard = () => {
    const card = preview?.closest<HTMLElement>(".report-card");
    if (!preview || !card) return;
    const open = !card.classList.contains("is-open");
    card.classList.toggle("is-open", open);
    preview.setAttribute("aria-expanded", String(open));
  };
  if (preview) preview.onclick = (event: MouseEvent) => { event.preventDefault(); toggleCard(); };

  const showCard = container.querySelector<HTMLButtonElement>("#show-card");
  if (showCard) {
    showCard.onclick = (event: MouseEvent) => {
      event.preventDefault();
      // The icon in the share row enlarges a card already there, or asks for it.
      if (preview) toggleCard();
      else controller.loadResultCard();
    };
  }

  const share = container.querySelector<HTMLButtonElement>("#share");
  if (share) {
    share.onclick = (event: MouseEvent) => {
      event.preventDefault();
      controller.shareResult();
    };
  }

  const copy = container.querySelector<HTMLButtonElement>("#share-copy");
  if (copy) {
    copy.onclick = (event: MouseEvent) => {
      event.preventDefault();
      void controller.copyShareText();
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
