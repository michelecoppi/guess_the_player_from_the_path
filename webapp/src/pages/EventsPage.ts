import { escapeHtml } from "@/utils/format";
import {
  renderCareerPath,
  renderErrorState,
  renderLoadingState,
} from "@/components";
import { formatExpiryDate } from "@/features/arena/views";
import { EVENT_MAX_ATTEMPTS } from "@/features/events/types";
import type { EventsController } from "@/features/events/controller";
import type { DailyComparison } from "@/features/daily/types";
import { t } from "@/i18n";

const CLUES: Record<string, (args: Record<string, any>) => string> = {
  "feedback.nationality_same": () => t("daily.sameNat"),
  "feedback.nationality_diff": () => t("daily.diffNat"),
  "feedback.position_same": () => t("daily.samePos"),
  "feedback.position_diff": () => t("daily.diffPos"),
  "feedback.birth_same": (a) => `${t("daily.sameYear")} ${a?.year ?? ""}`,
  "feedback.birth_before": (a) => `${t("daily.older")} ${a?.year ?? ""}`,
  "feedback.birth_after": (a) => `${t("daily.younger")} ${a?.year ?? ""}`,
};

const ERROR_KEYS: Record<string, string> = {
  invalid: "invalid",
  invalid_answer: "invalidAnswer",
  stale: "stale",
  expired: "expired",
  finished: "finished",
  max_answers: "maxAnswers",
  loadError: "loadError",
};

function getErrorMessage(code: string | null): string {
  const key = (code && ERROR_KEYS[code]) || "genericError";
  return t(`events.${key}`);
}

function renderEventEndDate(dates?: string[]): string {
  if (!dates || !dates.length) {
    return "";
  }
  const lastDate = dates[dates.length - 1];
  if (!lastDate) {
    return "";
  }
  const formatted = formatExpiryDate(lastDate);
  if (!formatted) {
    return "";
  }
  return `<small class="event-end-date">${t("events.eventEnd", { date: escapeHtml(formatted) })}</small>`;
}

function renderComparison(data?: DailyComparison | null): string {
  if (!data || !data.clues?.length) {
    return "";
  }
  const items = data.clues
    .map((clue) => {
      const render = CLUES[clue && clue.key];
      return render ? `<li>${escapeHtml(render(clue.args || {}))}</li>` : "";
    })
    .filter(Boolean)
    .join("");

  if (!items) {
    return "";
  }
  return `<div class="event-comparison">${escapeHtml(t("daily.compared"))} <b>${escapeHtml(data.name || "")}</b>:<ul>${items}</ul></div>`;
}

export function renderEventsPage(controller: EventsController): string {
  const state = controller.getState();
  const selectedEvent = state.events.find((x) => x.code === state.selectedCode);

  // Initial loading state
  if (state.status === "loading" && !state.events.length) {
    return renderLoadingState({ message: t("events.title") });
  }

  // Initial error state
  if (state.status === "error" && !state.events.length) {
    return `
      ${renderErrorState({ message: getErrorMessage(state.error) })}
      <button class="btn" id="events-retry">${t("events.refresh")}</button>
    `.trim();
  }

  // Events list view (no event selected or selected event disappeared)
  if (!selectedEvent) {
    const heading = `
      <header class="page-heading">
        <h2>${t("events.title")}</h2>
        <button class="btn ghost" id="events-refresh">${t("events.refresh")}</button>
      </header>
    `.trim();

    const errorHtml = state.error
      ? `<p class="event-error" role="alert">${getErrorMessage(state.error)}</p>`
      : "";

    if (!state.events.length) {
      return `
        ${heading}
        ${errorHtml}
        <div class="arena-empty">
          <h2>${t("events.empty")}</h2>
          <p>${t("events.emptyDesc")}</p>
          <button class="btn" id="events-open-training">${t("training.title")}</button>
        </div>
      `.trim();
    }

    const cardsHtml = state.events
      .map((event) => {
        const endDateHtml = renderEventEndDate(event.dates);
        return `
          <article class="mode-entry events-entry">
            <span>
              <b>${escapeHtml(event.name)}</b>
              <small>${escapeHtml(event.description)}</small>
              <small class="muted">${escapeHtml(event.rules)}</small>
              ${endDateHtml}
            </span>
            <button class="btn" data-event-open="${escapeHtml(event.code)}">
              ${event.progress.finished ? t("events.completed") : t("events.play")}
            </button>
          </article>
        `.trim();
      })
      .join("");

    return `
      ${heading}
      ${errorHtml}
      <section aria-label="${t("events.listLabel")}" class="events-list">
        ${cardsHtml}
      </section>
    `.trim();
  }

  // Event Detail View
  const event = selectedEvent;
  const isHttpsImage =
    typeof event.image_url === "string" && /^https:\/\//i.test(event.image_url);
  const imageHtml = isHttpsImage
    ? `<img class="event-image" src="${escapeHtml(event.image_url)}" alt="${escapeHtml(t("events.imageAlt", { name: event.name }))}" referrerpolicy="no-referrer">`
    : "";

  const remaining = Math.max(0, EVENT_MAX_ATTEMPTS - event.progress.attempts);

  // Type-specific hint / guidance
  let hintHtml = "";
  if (event.type === "career") {
    const minSuffix =
      event.min_correct > 1
        ? ` · ${t("events.minCorrect", { n: event.min_correct })}`
        : "";
    hintHtml = `<p class="muted event-hint">${t("events.careerHint")}${minSuffix}</p>`;
  } else if (event.type === "father_son") {
    hintHtml = `<p class="muted event-hint">${t("events.fatherSonHint")}</p>`;
  } else if (event.type !== "path" && event.type !== "transfer_guess") {
    hintHtml = `<p class="muted event-hint">${t("events.unknownType")}</p>`;
  }

  // Player name for career events
  const playerNameHtml =
    event.player_name && event.type === "career"
      ? `<h3 class="event-player-name">${escapeHtml(event.player_name)}</h3>`
      : "";

  // Content presentation (CareerPath or Image)
  const contentHtml =
    event.career_path && event.career_path.length > 0
      ? renderCareerPath({ stops: event.career_path })
      : imageHtml;

  // Feedback presentation
  let feedbackHtml = "";
  if (state.feedback) {
    const isCorrect = state.feedback.status === "correct";
    const statusText = isCorrect ? t("daily.correct") : t("daily.wrong");
    const pointsText = state.feedback.points
      ? ` · +${state.feedback.points} ${t("events.points")}`
      : "";
    const matchedHtml =
      state.feedback.matched != null
        ? `<p class="event-matched">${t("events.matched", { n: state.feedback.matched })}</p>`
        : "";
    const comparisonHtml = state.feedback.comparison
      ? renderComparison(state.feedback.comparison)
      : "";

    feedbackHtml = `
      <div class="feedback ${isCorrect ? "ok" : "no"}" role="status">
        <b>${statusText}</b>${pointsText}
        ${matchedHtml}
        ${comparisonHtml}
      </div>
    `.trim();
  }

  // Error message presentation
  const errorHtml = state.error
    ? `<p class="event-error" role="alert">${getErrorMessage(state.error)}</p>`
    : "";

  // Terminal state or Guess form
  let interactiveHtml = "";
  if (!event.available) {
    interactiveHtml = `<p class="event-unavailable" role="status">${t("events.unavailable")}</p>`;
  } else if (event.progress.finished) {
    if (event.progress.solved) {
      interactiveHtml = `
        <div class="event-terminal event-solved" role="status">
          <h3>${t("events.solved")}</h3>
          <p class="muted">${t("events.eventWait")}</p>
        </div>
      `.trim();
    } else {
      interactiveHtml = `
        <div class="event-terminal event-exhausted" role="status">
          <h3>${t("events.exhausted")}</h3>
          <p class="muted">${t("events.eventWait")}</p>
        </div>
      `.trim();
    }
  } else {
    interactiveHtml = `
      <form id="events-guess-form" class="events-guess-form">
        <label for="events-answer">${t("events.formLabel")}</label>
        <input
          id="events-answer"
          value="${escapeHtml(state.draftAnswer)}"
          autocomplete="off"
          maxlength="220"
          placeholder="${t("events.guess")}"
          ${state.status === "submitting" || state.status === "loading" ? "disabled" : ""}
        >
        <button class="btn" type="submit" ${state.status === "submitting" || state.status === "loading" ? "disabled" : ""}>
          ${t("events.submit")}
        </button>
      </form>
    `.trim();
  }

  // Leaderboard presentation
  const leaderboardItems = event.leaderboard.length
    ? event.leaderboard
        .map(
          (row) =>
            `<li><span class="leaderboard-player-name">${escapeHtml(row.name)}</span> — <span class="leaderboard-player-pts">${row.points}</span></li>`,
        )
        .join("")
    : `<li>${t("events.leaderboardEmpty")}</li>`;

  const endDateHtml = renderEventEndDate(event.dates);

  return `
    <div class="event-header-actions">
      <button class="btn ghost" id="events-back">${t("events.back")}</button>
      <button class="btn ghost" id="events-refresh">${t("events.refresh")}</button>
    </div>
    <section class="event-detail">
      <h2 id="events-heading" tabindex="-1">${escapeHtml(event.name)}</h2>
      <p class="event-description">${escapeHtml(event.description)}</p>
      <p class="event-rules">${escapeHtml(event.rules)}</p>
      ${endDateHtml}
      <p class="event-meta">
        <span class="pill">${event.points} ${t("events.points")}</span>
        ${event.bonus_available ? ` · <span class="event-bonus">${t("events.bonus")}</span>` : ""}
        · ${t("events.score")}: ${event.progress.points}
      </p>
      ${playerNameHtml}
      ${hintHtml}
      ${contentHtml}
      ${!event.progress.finished && event.available ? `<p class="event-attempts" aria-live="polite">${t("events.attempts")}: ${remaining}</p>` : ""}
      ${feedbackHtml}
      ${errorHtml}
      ${interactiveHtml}
      <section class="event-leaderboard-section">
        <h3>${t("events.leaderboard")}</h3>
        <ol class="event-leaderboard" aria-label="${t("events.leaderboard")}">
          ${leaderboardItems}
        </ol>
      </section>
    </section>
  `.trim();
}

export interface EventsEventListenersOptions {
  onOpenTraining?: () => void;
}

export function attachEventsEventListeners(
  root: HTMLElement,
  controller: EventsController,
  options?: EventsEventListenersOptions,
): void {
  root.querySelector<HTMLButtonElement>("#events-open-training")?.addEventListener("click", (e) => {
    e.preventDefault();
    options?.onOpenTraining?.();
  });

  root
    .querySelectorAll<HTMLButtonElement>("[data-event-open]")
    .forEach((button) => {
      button.onclick = () => {
        const code = button.dataset.eventOpen;
        if (code) {
          controller.select(code);
          const heading = root.querySelector<HTMLElement>("#events-heading");
          if (heading) {
            heading.tabIndex = -1;
            heading.focus({ preventScroll: true });
          }
        }
      };
    });

  root.querySelector<HTMLButtonElement>("#events-back")?.addEventListener("click", () => {
    controller.back();
  });

  root
    .querySelectorAll<HTMLButtonElement>("#events-refresh, #events-retry")
    .forEach((btn) => {
      btn.addEventListener("click", () => {
        void controller.load();
      });
    });

  const input = root.querySelector<HTMLInputElement>("#events-answer");
  if (input) {
    input.oninput = () => {
      controller.setDraftAnswer(input.value);
    };
  }

  root
    .querySelector<HTMLFormElement>("#events-guess-form")
    ?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const value = input?.value || controller.getState().draftAnswer || "";
      await controller.submit(value);

      const active = controller.selected();
      if (active?.progress.finished) {
        const terminalOrFeedback = root.querySelector(
          ".event-terminal, .feedback",
        );
        terminalOrFeedback?.scrollIntoView?.({ block: "nearest" });
      } else {
        const refreshedInput =
          root.querySelector<HTMLInputElement>("#events-answer");
        refreshedInput?.focus({ preventScroll: true });
      }
    });
}
