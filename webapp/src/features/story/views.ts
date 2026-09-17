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
  StoryChapterSummary,
  StoryChapterView,
  StoryComparison,
  StoryFeedback,
  StoryLevelEntry,
  StoryState,
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

function renderClues(comparison?: StoryComparison): string[] {
  if (!comparison?.clues?.length) return [];
  return comparison.clues
    .map((clue) => {
      const fn = CLUES[clue?.key];
      return fn ? fn(clue.args || {}) : "";
    })
    .filter(Boolean);
}

function renderFeedback(feedback?: StoryFeedback | null): string {
  if (!feedback || !feedback.status) return "";
  const isCorrect = feedback.status === "correct";
  let title = isCorrect ? t("story.correct") : t("story.wrong");
  if (feedback.level_failed) {
    title = t("story.levelFailed");
  } else if (feedback.chapter_cleared) {
    title = t("story.chapterCleared");
  } else if (feedback.level_cleared) {
    title = feedback.starred ? t("story.levelClearedStar") : t("story.levelCleared");
  }

  const message = feedback.answer ? t("story.answer", { name: feedback.answer }) : undefined;
  const clues = renderClues(feedback.comparison);
  const status = isCorrect || feedback.level_cleared ? "correct" : "wrong";

  return renderFeedbackBox({
    status,
    title,
    message,
    clues,
    comparedName: feedback.comparison?.name,
    comparedLabel: t("daily.compared"),
  });
}

function renderAlerts(state: StoryState): string {
  if (!state.error) return "";
  const errorText = t(`story.${state.error}`);
  return `<div class="error-box" role="alert"><p>${escapeHtml(errorText)}</p></div>`;
}

function backLink(labelKey: string): string {
  return `<button class="back-link" data-story-back type="button">${icon("back")} ${escapeHtml(t(labelKey))}</button>`;
}

function pageHeader(tagKey: string, titleKey: string): string {
  return `
    <header class="page-heading">
      <p class="eyebrow">${escapeHtml(t(tagKey))}</p>
      <h2 class="page-title">${escapeHtml(t(titleKey))}</h2>
    </header>
  `;
}

/** The episode menu: one card per chapter in data/story.json, locked ones greyed out. */
function renderChapterCard(chapter: StoryChapterSummary): string {
  const stateClass = chapter.locked ? "locked" : chapter.finished ? "cleared" : "";
  const mark = chapter.locked ? icon("lock") : icon("story");
  const progress = chapter.locked
    ? t("story.chapterLocked")
    : t("story.chapterProgress", { cleared: chapter.levels_cleared, total: chapter.total_levels });
  const stars = chapter.locked
    ? ""
    : `<span class="story-chapter-stars">${icon("star")} ${chapter.stars_earned}</span>`;

  const attrs = chapter.locked ? "" : `data-story-chapter="${escapeHtml(chapter.chapter_id)}"`;
  return `
    <button class="story-chapter-card ${stateClass}" type="button" ${attrs} ${chapter.locked ? "disabled" : ""}>
      <span class="story-chapter-mark">${mark}</span>
      <span class="story-chapter-copy">
        <b>${escapeHtml(chapter.title)}</b>
        <small>${escapeHtml(progress)}</small>
      </span>
      ${stars}
      ${chapter.locked ? "" : icon("arrow")}
    </button>
  `.trim();
}

export function renderChapterListView(state: StoryState): string {
  const chapters = state.chapters || [];
  const body = chapters.length
    ? `<div class="story-chapter-list">${chapters.map(renderChapterCard).join("")}</div>`
    : renderLoadingState({ message: t("common.loading") });

  return `
    <div class="story-view" id="story-view">
      ${backLink("story.backToArena")}
      ${pageHeader("story.tag", "story.title")}
      <p class="story-intro">${escapeHtml(t("story.desc"))}</p>
      ${renderAlerts(state)}
      ${body}
    </div>
  `.trim();
}

/** One node in the level map: locked, current (playable) or cleared (with its star or not). */
function renderLevelCard(level: StoryLevelEntry): string {
  const mark =
    level.state === "locked" ? icon("lock") : level.state === "cleared" ? (level.starred ? icon("star") : icon("check")) : `<span class="story-node-number">${level.id}</span>`;
  const clickable = level.state === "current";
  return `
    <button class="story-level-card ${level.state}" type="button"
      ${clickable ? `data-story-level="${level.id}"` : "disabled"}>
      <span class="story-level-mark">${mark}</span>
      <span class="story-level-copy">
        <span class="story-level-eyebrow">${escapeHtml(t("story.levelN", { n: level.id }))}</span>
        <b>${escapeHtml(level.theme)}</b>
      </span>
      ${clickable ? icon("arrow") : ""}
    </button>
  `.trim();
}

export function renderLevelSelectView(state: StoryState): string {
  const chapter = state.data?.chapter;
  if (!chapter) {
    return `
      <div class="story-view" id="story-view">
        ${backLink("story.backToChapters")}
        ${renderLoadingState({ message: t("common.loading") })}
      </div>
    `.trim();
  }

  const perfect = chapter.stars.every(Boolean);
  const clearedBanner = chapter.finished
    ? `<div class="story-reward-card ${perfect ? "perfect" : ""}">
        ${icon(perfect ? "star" : "check")}
        <span>${escapeHtml(perfect ? t("story.perfectRewardUnlocked") : t("story.rewardUnlocked"))}</span>
      </div>`
    : "";

  return `
    <div class="story-view" id="story-view">
      ${backLink("story.backToChapters")}
      <header class="page-heading">
        <p class="eyebrow">${escapeHtml(t("story.tag"))}</p>
        <h2 class="page-title">${escapeHtml(chapter.title)}</h2>
      </header>
      ${renderAlerts(state)}
      ${clearedBanner}
      <div class="story-level-list">
        ${chapter.levels.map(renderLevelCard).join("")}
      </div>
    </div>
  `.trim();
}

function renderStepDots(chapter: StoryChapterView): string {
  const dots = Array.from({ length: chapter.steps_per_level }, (_, index) => {
    const done = index < chapter.step;
    const current = index === chapter.step;
    return `<span class="story-step-dot ${done ? "done" : ""} ${current ? "current" : ""}"></span>`;
  }).join("");
  return `<div class="story-step-dots">${dots}</div>`;
}

function renderLives(chapter: StoryChapterView): string {
  const dots = Array.from({ length: chapter.max_attempts }, (_, index) => {
    const spent = index < chapter.attempts;
    return `<span class="story-life ${spent ? "spent" : ""}" aria-hidden="true">${icon("close")}</span>`;
  }).join("");
  return `<div class="story-lives">${dots}<span class="story-lives-label">${escapeHtml(
    t("story.livesLeft", { n: chapter.max_attempts - chapter.attempts }),
  )}</span></div>`;
}

export function renderChapterClearedView(state: StoryState): string {
  const chapter = state.data!.chapter;
  const perfect = chapter.stars.every(Boolean);
  const starsCount = chapter.stars.filter(Boolean).length;

  return `
    <div class="story-view" id="story-view">
      ${backLink("story.backToLevels")}
      ${pageHeader("story.tag", "story.title")}
      <div class="story-cleared-card">
        <div class="story-cleared-mark" aria-hidden="true">${icon("story")}</div>
        <h3 class="story-cleared-title">${escapeHtml(t("story.chapterCompleteTitle", { title: chapter.title }))}</h3>
        <p class="story-cleared-desc">${escapeHtml(t("story.chapterCompleteDesc"))}</p>

        <div class="story-cleared-stats">
          <div class="story-cleared-stat">
            <strong>${starsCount} / ${chapter.total_levels}</strong>
            <span>${escapeHtml(t("story.starsEarned"))}</span>
          </div>
        </div>

        <div class="story-reward-card ${perfect ? "perfect" : ""}">
          ${icon(perfect ? "star" : "check")}
          <span>${escapeHtml(perfect ? t("story.perfectRewardUnlocked") : t("story.rewardUnlocked"))}</span>
        </div>

        ${renderAlerts(state)}
      </div>
    </div>
  `.trim();
}

export function renderActiveLevelView(state: StoryState): string {
  const chapter = state.data!.chapter;

  const attemptsLeftDisplay = renderLives(chapter);
  const careerPathHtml = chapter.career_path ? renderCareerPath({ stops: chapter.career_path }) : "";

  const guessInputHtml = renderGuessInput({
    inputId: "story-answer",
    submitButtonId: "story-submit",
    placeholder: t("story.placeholder"),
    buttonLabel: t("story.submitBtn"),
    disabled: state.busy,
    value: state.draftAnswer,
  });

  const revealLabel = state.confirming === "reveal" ? t("story.revealSure") : t("story.reveal");
  const revealBtnHtml = renderButton({
    id: "story-reveal",
    label: revealLabel,
    variant: "ghost",
    fullWidth: true,
    disabled: state.busy,
  });

  const difficultyPill = chapter.difficulty_label
    ? `<span class="pill">${escapeHtml(chapter.difficulty_label)}</span>`
    : "";

  return `
    <div class="story-view" id="story-view">
      ${backLink("story.backToLevels")}

      <div class="story-level-header">
        <span class="eyebrow">${escapeHtml(t("story.levelN", { n: (chapter.level_number ?? chapter.level + 1) }))}</span>
        <h3 class="story-theme-title">${escapeHtml(chapter.theme || "")}</h3>
        ${difficultyPill}
      </div>

      ${renderStepDots(chapter)}

      <div class="story-career-container">
        ${careerPathHtml}
      </div>

      ${attemptsLeftDisplay}

      ${guessInputHtml}

      ${renderAlerts(state)}

      ${renderFeedback(state.lastFeedback)}

      <div class="story-actions">
        ${revealBtnHtml}
      </div>
    </div>
  `.trim();
}

export function renderStoryView(state: StoryState): string {
  if (state.status === "loading" && state.mode === "chapters" && !state.chapters) {
    return `
      <div class="story-view" id="story-view">
        ${backLink("story.backToArena")}
        ${pageHeader("story.tag", "story.title")}
        ${renderLoadingState({ message: t("common.loading") })}
      </div>
    `.trim();
  }
  if (state.status === "error" && !state.data && !state.chapters) {
    const errorKey = state.error ? `story.${state.error}` : "story.loadError";
    const translated = t(errorKey);
    const message = translated !== errorKey ? translated : t("story.loadError");
    return `
      <div class="story-view" id="story-view">
        ${backLink("story.backToArena")}
        ${renderErrorState({
          title: t("story.title"),
          message,
          retryLabel: t("common.retry"),
          retryButtonId: "story-retry",
        })}
      </div>
    `.trim();
  }

  if (state.mode === "chapters") {
    return renderChapterListView(state);
  }
  if (state.mode === "levels") {
    return renderLevelSelectView(state);
  }
  if (!state.data?.chapter) {
    return `
      <div class="story-view" id="story-view">
        ${backLink("story.backToLevels")}
        ${renderLoadingState({ message: t("common.loading") })}
      </div>
    `.trim();
  }
  return state.data.chapter.finished ? renderChapterClearedView(state) : renderActiveLevelView(state);
}
