/**
 * ArchivePage — Issue #44
 *
 * Thin page component: delegates rendering to views.ts, wires DOM events.
 */

import type { ArchiveController } from "@/features/archive/controller";
import type { ArchiveState } from "@/features/archive/types";
import { renderArchiveViews } from "@/features/archive/views";
import { t } from "@/i18n";
import { escapeHtml } from "@/utils/format";

/**
 * Renders the full archive page (calendar or challenge view, depending on state).
 */
export function renderArchivePage(state: ArchiveState): string {
  const heading = `
    <header class="page-heading">
      <p class="eyebrow">${escapeHtml(t("archive.kicker"))}</p>
      <h2>${escapeHtml(t("archive.heading"))}</h2>
    </header>
  `.trim();

  return `${heading}\n${renderArchiveViews(state)}`;
}

/**
 * Attaches all DOM event listeners needed by the archive feature.
 * Called after every render to wire freshly created elements.
 */
export function attachArchiveEventListeners(
  root: HTMLElement,
  controller: ArchiveController,
): void {
  // --- Calendar: click a day to open challenge ---
  const dayButtons = root.querySelectorAll<HTMLButtonElement>("button[data-archive-day]");
  dayButtons.forEach((btn) => {
    btn.onclick = (e) => {
      e.preventDefault();
      const day = btn.dataset.archiveDay;
      if (day) {
        void controller.openDay(day);
      }
    };
  });

  // --- Challenge: back to calendar ---
  const backBtn = root.querySelector<HTMLButtonElement>("[data-archive-back]");
  if (backBtn) {
    backBtn.onclick = (e) => {
      e.preventDefault();
      void controller.backToCalendar();
    };
  }

  // --- Challenge: guess form submit ---
  const form = root.querySelector<HTMLFormElement>("#archive-guess-form");
  if (form) {
    form.onsubmit = (e) => {
      e.preventDefault();
      const input = root.querySelector<HTMLInputElement>("#archive-answer");
      const answer = (input?.value ?? controller.getState().draftAnswer).trim();
      if (answer) {
        void controller.submitGuess(answer);
      }
    };
  }

  // --- Challenge: track input value ---
  const answerInput = root.querySelector<HTMLInputElement>("#archive-answer");
  if (answerInput) {
    answerInput.oninput = () => {
      controller.setDraftAnswer(answerInput.value);
      const submitBtn = root.querySelector<HTMLButtonElement>("#archive-submit");
      if (submitBtn) {
        submitBtn.disabled = !answerInput.value.trim();
      }
    };
    // Also handle Enter key on input (in case form submit doesn't fire)
    answerInput.onkeydown = (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        const answer = answerInput.value.trim();
        if (answer) {
          void controller.submitGuess(answer);
        }
      }
    };
  }

  // --- Calendar retry button ---
  const retryBtn = root.querySelector<HTMLButtonElement>("#archive-retry");
  if (retryBtn) {
    retryBtn.onclick = (e) => {
      e.preventDefault();
      void controller.retry();
    };
  }

  // --- Challenge retry button ---
  const retryChallBtn = root.querySelector<HTMLButtonElement>("#archive-challenge-retry");
  if (retryChallBtn) {
    retryChallBtn.onclick = (e) => {
      e.preventDefault();
      void controller.retryChallenge();
    };
  }

  // --- Share button ---
  const shareBtn = root.querySelector<HTMLButtonElement>("#archive-share");
  if (shareBtn) {
    shareBtn.onclick = (e) => {
      e.preventDefault();
      const url = controller.getState().feedback?.share?.url;
      if (url) {
        controller.openShareUrl(url);
      }
    };
  }
}
