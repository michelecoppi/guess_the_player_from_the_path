import { escapeHtml } from "@/utils/format";
import { icon } from "@/components/Icon";
import { renderCareerPath, renderGuessInput, renderLoadingState, renderErrorState } from "@/components";
import { t, getLanguage } from "@/i18n";
import type {
  ArenaState,
  DuelData,
  DuelFeedback,
  DuelComparison,
  OpenDuelSummary,
  DuelLedger,
  OpponentProfile,
} from "./types";

const CLUES: Record<string, (args: Record<string, any>) => string> = {
  "feedback.nationality_same": () => t("daily.sameNat"),
  "feedback.nationality_diff": () => t("daily.diffNat"),
  "feedback.position_same": () => t("daily.samePos"),
  "feedback.position_diff": () => t("daily.diffPos"),
  "feedback.birth_same": (a) => `${t("daily.sameYear")} ${a?.year ?? ""}`,
  "feedback.birth_before": (a) => `${t("daily.older")} ${a?.year ?? ""}`,
  "feedback.birth_after": (a) => `${t("daily.younger")} ${a?.year ?? ""}`,
};

function renderComparison(data?: DuelComparison): string {
  if (!data || !data.clues?.length) return "";
  const items = data.clues
    .map((clue) => {
      const render = CLUES[clue && clue.key];
      return render ? `<li>${escapeHtml(render(clue.args || {}))}</li>` : "";
    })
    .filter(Boolean)
    .join("");

  return `<div>${escapeHtml(t("daily.compared"))} <b>${escapeHtml(data.name || "")}</b>:<ul>${items}</ul></div>`;
}

export function formatExpiryDate(value?: string): string {
  if (!value) return "";
  const d = new Date(value.length === 10 ? value + "T12:00:00" : value);
  const lang = getLanguage() || "en";
  return Number.isNaN(d.getTime())
    ? value
    : d.toLocaleDateString(lang, { day: "numeric", month: "short" });
}

function usesText(n: number): string {
  return t(n === 1 ? "arena.used1" : "arena.used", { n });
}

function renderFeedback(feedback?: DuelFeedback | null): string {
  if (!feedback || !feedback.status) return "";
  const isCorrect = feedback.status === "correct";
  const statusLabel = isCorrect
    ? t("arena.correct")
    : feedback.done
      ? t("arena.ended")
      : t("arena.wrong");

  return `
    <div class="feedback ${isCorrect ? "ok" : "no"}" role="status">
      <strong>${escapeHtml(statusLabel)}</strong>
      ${feedback.answer ? `<p>${escapeHtml(t("arena.answer", { name: feedback.answer }))}</p>` : ""}
      ${renderComparison(feedback.comparison)}
    </div>
  `.trim();
}

function renderPaths(d: DuelData): string {
  const rows = d.rounds || [];
  if (!rows.length) return "";
  const opponentName = d.opponent ? d.opponent.name : "";

  return `
    <section class="arena-paths">
      <h3>${escapeHtml(t("arena.paths"))}</h3>
      ${rows
        .map(
          (row) => `
        <div class="arena-path">
          <span class="arena-path-mark ${row.solved ? "ok" : "no"}" aria-hidden="true">${row.solved ? "✓" : "×"}</span>
          <div>
            <strong>${escapeHtml(row.answer || t("arena.hidden"))}</strong>
            <p>${escapeHtml(t("arena.you"))} · ${escapeHtml(usesText(row.attempts))}${
              row.opponent
                ? ` · ${escapeHtml(opponentName)} ${row.opponent.solved ? "✓" : "×"} · ${escapeHtml(usesText(row.opponent.attempts))}`
                : ""
            }</p>
          </div>
        </div>
      `,
        )
        .join("")}
    </section>
  `.trim();
}

function renderHistory(ledger?: DuelLedger): string {
  if (!ledger) return "";
  const record = ledger.record;
  const matches = ledger.matches || [];
  if (!record && !matches.length) return "";

  return `
    <section class="arena-history">
      ${
        record
          ? `
        <div class="arena-h2h">
          <span class="arena-eyebrow">${escapeHtml(t("arena.h2h"))}</span>
          <strong>${record.won}–${record.lost}</strong>
          <span>${escapeHtml(t("arena.h2hLine", { name: record.name, n: record.drawn }))}</span>
        </div>
      `
          : ""
      }
      ${
        matches.length
          ? `
        <h3>${escapeHtml(t("arena.pastTitle"))}</h3>
        ${matches
          .map(
            (match) => `
          <details class="arena-past">
            <summary>
              <span class="arena-badge ${match.outcome === "win" ? "ok" : match.outcome === "loss" ? "no" : ""}">${escapeHtml(t(`arena.${match.outcome}Short`))}</span>
              <span class="arena-past-name">${escapeHtml(match.name || t("arena.someone"))}</span>
              <span class="arena-past-score">${match.you.solved}–${match.them.solved}</span>
              <small>${escapeHtml(formatExpiryDate(match.ended_at))}</small>
            </summary>
            ${(match.rounds || [])
              .map(
                (row, i) => `
              <div class="arena-past-row">
                <strong>${i + 1}. ${escapeHtml(row.answer)}</strong>
                <p>${row.you.solved ? "✓" : "×"} ${escapeHtml(t("arena.you"))} · ${escapeHtml(usesText(row.you.attempts))} — ${row.them.solved ? "✓" : "×"} ${escapeHtml(match.name || t("arena.someone"))} · ${escapeHtml(usesText(row.them.attempts))}</p>
              </div>
            `,
              )
              .join("")}
          </details>
        `,
          )
          .join("")}
      `
          : ""
      }
    </section>
  `.trim();
}

function renderOpenDuelsList(state: ArenaState): string {
  const rows = state.data?.open || [];
  const statusLabel = (o: OpenDuelSummary) =>
    o.complete
      ? t("arena.duelRowDone")
      : o.opponent
        ? t("arena.progress", { n: o.round, total: o.total })
        : t("arena.duelRowWaiting");

  if (!rows.length) {
    return `
      <div class="arena-empty">
        <p>${escapeHtml(t("arena.duelListEmpty"))}</p>
      </div>
    `.trim();
  }

  return `
    <section class="arena-open-list">
      <h3>${escapeHtml(t("arena.duelListTitle"))}</h3>
      ${rows
        .map((o) => {
          const isDeleting = state.confirming === `delete:${o.code}`;
          return `
          <div class="arena-open-row">
            <button class="arena-open-open" data-arena-duel="${escapeHtml(o.code)}" ${state.busy ? "disabled" : ""}>
              <span class="arena-path-mark ${o.complete ? "ok" : ""}" aria-hidden="true">${o.complete ? "✓" : o.opponent ? "…" : "★"}</span>
              <span>
                <strong>${escapeHtml(o.opponent || t("arena.duelRowPending"))}</strong>
                <small>${escapeHtml(statusLabel(o))}</small>
              </span>
            </button>
            ${
              !o.opponent
                ? `<button class="btn ghost btn-sm" data-arena-delete="${escapeHtml(o.code)}" ${state.busy ? "disabled" : ""}>${escapeHtml(t(isDeleting ? "arena.deleteSure" : "arena.delete"))}</button>`
                : ""
            }
          </div>
        `;
        })
        .join("")}
    </section>
  `.trim();
}

export function renderHubView(state: ArenaState): string {
  const openDuels = state.data?.open || [];
  const activeDuel = openDuels.find((d) => !d.complete && d.opponent);

  const activeDuelHtml = activeDuel
    ? `
      <button class="active-duel" data-arena-duel="${escapeHtml(activeDuel.code)}">
        <span class="duel-indicator">${icon("arena")}</span>
        <span>
          <b>${escapeHtml(t("arena.activeDuelWith", { name: activeDuel.opponent || "" }))}</b>
          <small>${escapeHtml(t("arena.progress", { n: activeDuel.round, total: activeDuel.total }))}</small>
        </span>
        <strong>${activeDuel.round} : ${activeDuel.total}</strong>
        ${icon("arrow")}
      </button>
    `.trim()
    : "";

  return `
    <div class="arena-view arena-hub">
      <header class="page-heading">
        <p class="eyebrow">${escapeHtml(t("pages.arenaKicker"))}</p>
        <h2 class="page-title">${escapeHtml(t("pages.arenaTitle"))}</h2>
      </header>

      <button class="arena-feature" data-arena-nav="challenge" type="button">
        <div class="arena-feature-copy">
          <span class="mode-label">${escapeHtml(t("arena.featureSubtitle"))}</span>
          <h3>${escapeHtml(t("arena.featureTitle"))}</h3>
          <p>${escapeHtml(t("arena.featureDesc"))}</p>
          <span class="feature-action">${escapeHtml(t("arena.featureAction"))} ${icon("arrow")}</span>
        </div>
        <div class="versus-mark" aria-hidden="true">
          <span>VS</span>
        </div>
      </button>

      ${activeDuelHtml}

      ${state.notice ? `<p class="arena-notice" role="status">${escapeHtml(state.notice)}</p>` : ""}
      ${state.error ? `<div class="arena-error" role="alert"><p>${escapeHtml(t(`arena.${state.error}`))}</p></div>` : ""}

      ${renderOpenDuelsList(state)}

      ${renderHistory(state.data?.ledger)}

      <section class="training-hub-section">
        <h3>${escapeHtml(t("training.title"))}</h3>
        <button class="mode-entry training-entry" data-arena-nav="training" type="button">
          <span class="mode-icon">${icon("training")}</span>
          <span>
            <b>${escapeHtml(t("training.title"))}</b>
            <small>${escapeHtml(t("training.desc"))}</small>
          </span>
          ${icon("arrow")}
        </button>
      </section>

      <section class="extra-modes">
        <h3>${escapeHtml(t("arena.extraModes"))}</h3>
        <button class="mode-entry archive-entry" data-tab="archive" type="button">
          <span class="mode-icon">${icon("archive")}</span>
          <span>
            <b>${escapeHtml(t("arena.archiveTitle"))}</b>
            <small>${escapeHtml(t("arena.archiveDesc"))}</small>
          </span>
          ${icon("arrow")}
        </button>
        <button class="mode-entry events-entry" data-tab="events" type="button">
          <span class="mode-icon">${icon("events")}</span>
          <span>
            <b>${escapeHtml(t("arena.eventsTitle"))}</b>
            <small>${escapeHtml(t("arena.eventsDesc"))}</small>
          </span>
          ${icon("arrow")}
        </button>
      </section>
    </div>
  `.trim();
}

export function renderChallengeView(state: ArenaState): string {
  const searchResultsHtml = state.searchResults.length
    ? `
      <div class="profile-search-results" role="list">
        ${state.searchResults
          .map(
            (p: OpponentProfile) => `
          <div class="profile-search-card" role="listitem">
            <div class="profile-info">
              <strong>${escapeHtml(p.name)}</strong>
              <small>${p.points} ${escapeHtml(t("common.points"))} · ${p.trophies} 🏆</small>
            </div>
            <button class="btn ghost btn-sm" data-arena-challenge-user="${p.profile_id}" data-arena-invite-user="${p.profile_id}" ${state.busy ? "disabled" : ""}>
              ${escapeHtml(t("arena.inviteOpponentBtn"))}
            </button>
          </div>
        `,
          )
          .join("")}
      </div>
    `.trim()
    : state.searchQuery.trim().length >= 2 && state.status !== "searching"
      ? `<p class="muted arena-empty-search">${escapeHtml(t("arena.searchEmpty"))}</p>`
      : "";

  return `
    <div class="arena-view arena-challenge">
      <button class="back-link" data-arena-nav="hub" type="button">
        ${icon("back")}${escapeHtml(t("arena.backToList"))}
      </button>

      <header class="page-heading">
        <p class="eyebrow">${escapeHtml(t("arena.featureSubtitle"))}</p>
        <h2 class="page-title">${escapeHtml(t("arena.featureTitle"))}</h2>
      </header>

      <div class="challenge-intro">
        <span class="mode-icon">${icon("referral")}</span>
        <h3>${escapeHtml(t("arena.challengeSectionTitle"))}</h3>
        <p class="muted">${escapeHtml(t("arena.challengeSectionSubtitle"))}</p>
      </div>

      <div class="challenge-search-section">
        <label class="guess-label" for="opponent-search">${escapeHtml(t("arena.searchPlaceholder"))}</label>
        <input class="guess-input" id="opponent-search" placeholder="${escapeHtml(t("arena.searchPlaceholder"))}" value="${escapeHtml(state.searchQuery)}" autocomplete="off" autocorrect="off">
        <p class="muted arena-search-note">${escapeHtml(t("arena.searchInviteNote"))}</p>
        ${state.status === "searching" ? `<p class="muted arena-search-loading">${escapeHtml(t("arena.searching"))}</p>` : ""}
        ${state.searchError ? `<div class="feedback no mt-2" role="alert">${escapeHtml(state.searchError)}</div>` : ""}
        ${searchResultsHtml}
      </div>

      <div class="challenge-direct-invite">
        <h3>${escapeHtml(t("arena.directInviteTitle"))}</h3>
        <p class="muted mb-4">${escapeHtml(t("arena.directInviteDesc"))}</p>
        <button class="btn" id="arena-create-free-duel" ${state.busy ? "disabled" : ""}>
          ${escapeHtml(t("arena.createFreeDuel"))}
        </button>
      </div>
    </div>
  `.trim();
}

export function renderDuelView(state: ArenaState): string {
  const d = state.data;
  if (!d || (!d.session && state.status === "loading")) {
    return renderLoadingState({ message: t("arena.loading") });
  }

  if (state.status === "error" && !d) {
    return renderErrorState({
      title: t("common.error"),
      message: t(`arena.${state.error || "loadError"}`),
      retryLabel: t("common.retry"),
      retryButtonId: "arena-retry",
    });
  }

  const s = d?.session;
  const backBtn = `<button class="back-link" data-arena-nav="hub" type="button">${icon("back")}${escapeHtml(t("arena.backToList"))}</button>`;

  if (!s) {
    return `
      <div class="arena-view arena-session">
        ${backBtn}
        <div class="arena-empty">
          <p>${escapeHtml(t("arena.rules"))}</p>
          <button class="btn" id="arena-create-duel" ${state.busy ? "disabled" : ""}>${escapeHtml(t("arena.create"))}</button>
        </div>
        ${renderHistory(d?.ledger)}
      </div>
    `.trim();
  }

  const versusHtml = `
    <div class="arena-versus">
      <div>
        <span>${escapeHtml(t("arena.you"))}</span>
        <strong>${escapeHtml(t("arena.progress", { n: s.round, total: s.total }))}</strong>
      </div>
      <span class="arena-vs" aria-hidden="true">${escapeHtml(t("arena.versus"))}</span>
      <div>
        <span>${escapeHtml(d.opponent ? d.opponent.name : t("arena.waiting"))}</span>
        <strong>${d.opponent ? escapeHtml(t("arena.progress", { n: d.opponent.round ?? 0, total: s.total })) : "—"}</strong>
      </div>
    </div>
  `.trim();

  // Waiting for opponent to join
  if (!d.opponent && !s.finished) {
    return `
      <div class="arena-view arena-session">
        ${backBtn}
        ${versusHtml}
        <div class="arena-actions">
          ${d.invite_url ? `<button class="btn" data-arena-action="invite">${escapeHtml(t("arena.invite"))}</button>` : ""}
          <button class="btn ghost" data-arena-action="refresh">${escapeHtml(t("arena.refresh"))}</button>
        </div>
        ${
          d.invite_url
            ? `
          <label class="arena-link-label" for="arena-link">${escapeHtml(t("arena.codeLabel"))}</label>
          <div class="arena-link">
            <input id="arena-link" readonly value="${escapeHtml(d.invite_url)}">
            <button class="btn ghost" data-arena-action="copy">${escapeHtml(t("arena.copy"))}</button>
          </div>
        `
            : ""
        }
        <p class="muted arena-small">${escapeHtml(t("arena.expires", { date: formatExpiryDate(d.expires_at) }))}</p>
        ${state.notice ? `<p class="arena-notice" role="status">${escapeHtml(state.notice)}</p>` : ""}
        ${state.error ? `<div class="arena-error" role="alert"><p>${escapeHtml(t(`arena.${state.error}`))}</p></div>` : ""}
        <div class="arena-empty">
          <p>${escapeHtml(t("arena.waitingOpponentBody"))}</p>
        </div>
        ${renderHistory(d.ledger)}
      </div>
    `.trim();
  }

  // Finished duel
  if (s.finished) {
    const outcomeTitle = d.complete
      ? t(`arena.${d.outcome || "draw"}`)
      : t("arena.waitingEnd");

    return `
      <div class="arena-view arena-session">
        ${backBtn}
        ${versusHtml}
        ${state.notice ? `<p class="arena-notice" role="status">${escapeHtml(state.notice)}</p>` : ""}
        ${state.error ? `<div class="arena-error" role="alert"><p>${escapeHtml(t(`arena.${state.error}`))}</p></div>` : ""}
        ${renderFeedback(d.feedback)}
        <div class="arena-result">
          <span class="arena-result-mark" aria-hidden="true">${d.outcome === "win" ? "✦" : "✓"}</span>
          <h2>${escapeHtml(outcomeTitle)}</h2>
          <div class="arena-score">
            <div><strong>${s.solved}/${s.total}</strong><span>${escapeHtml(t("arena.solved"))}</span></div>
            <div><strong>${s.spent}</strong><span>${escapeHtml(t("arena.spent"))}</span></div>
          </div>
          ${
            d.complete && d.opponent
              ? `<p class="opponent-final-score">${escapeHtml(d.opponent.name)} · ${d.opponent.solved}/${s.total} · ${d.opponent.spent} ${escapeHtml(t("arena.spent"))}</p>`
              : ""
          }
          ${d.complete ? `<button class="btn" id="arena-new-duel">${escapeHtml(t("arena.newDuel"))}</button>` : ""}
        </div>
        ${renderPaths(d)}
        ${renderHistory(d.ledger)}
      </div>
    `.trim();
  }

  // Active round
  const pips = Array.from({ length: s.total }, (_, i) => {
    const isDone = i < s.round;
    const isCurrent = i === s.round;
    const pastRound = s.history?.[i];
    const mark = isDone ? (pastRound?.solved ? "✓" : "×") : i + 1;
    const pipClass = isDone ? "done" : isCurrent ? "current" : "";
    return `<span class="${pipClass}" aria-hidden="true">${mark}</span>`;
  }).join("");

  const attemptsLeft = Math.max(0, s.max_attempts - s.attempts);
  const isSkipping = state.confirming === "skip";
  const submitting = state.status === "submitting";

  return `
    <div class="arena-view arena-session">
      ${backBtn}
      ${versusHtml}
      <div class="arena-round">
        <span class="arena-eyebrow">${escapeHtml(t("arena.round", { n: s.round + 1, total: s.total }))}</span>
        ${s.difficulty_label ? `<span class="pill">${escapeHtml(s.difficulty_label)}</span>` : ""}
      </div>
      <div class="arena-rounds" aria-label="${escapeHtml(t("arena.progress", { n: s.round, total: s.total }))}">
        ${pips}
      </div>
      <div class="arena-career">
        ${renderCareerPath({ stops: (s.career_path as any) || [], emptyText: t("daily.none") })}
      </div>
      <p class="arena-attempts">${escapeHtml(t("arena.attempts", { n: attemptsLeft }))}</p>
      ${renderGuessInput({
        id: "arena-guess-form",
        inputId: "arena-answer",
        submitButtonId: "arena-submit",
        placeholder: t("daily.placeholder"),
        buttonLabel: submitting ? t("daily.loading") : t("daily.guessBtn"),
        loading: submitting,
        value: state.draftAnswer,
      })}
      ${state.notice ? `<p class="arena-notice" role="status">${escapeHtml(state.notice)}</p>` : ""}
      ${state.error ? `<div class="arena-error" role="alert"><p>${escapeHtml(t(`arena.${state.error}`))}</p></div>` : ""}
      ${renderFeedback(d.feedback)}
      ${d.feedback?.done ? `<p role="status" class="arena-small">${escapeHtml(t("arena.nextRound"))}</p>` : ""}
      <div class="arena-actions">
        <button class="btn ghost" data-arena-action="skip" ${state.busy ? "disabled" : ""}>
          ${escapeHtml(t(isSkipping ? "arena.skipSure" : "arena.skip"))}
        </button>
      </div>
      ${renderPaths(d)}
      ${renderHistory(d.ledger)}
    </div>
  `.trim();
}

export function renderInvitationView(state: ArenaState): string {
  return `
    <div class="arena-view arena-invitation">
      <header class="page-heading">
        <p class="eyebrow">${escapeHtml(t("arena.duelTag"))}</p>
        <h2 class="page-title">${escapeHtml(t("arena.join"))}</h2>
      </header>
      <div class="arena-empty">
        <p>${escapeHtml(t("arena.joinIntro"))}</p>
        <p class="muted">${escapeHtml(t("arena.rules"))}</p>
        ${state.notice ? `<p class="arena-notice" role="status">${escapeHtml(state.notice)}</p>` : ""}
        ${state.error ? `<div class="arena-error" role="alert"><p>${escapeHtml(t(`arena.${state.error}`))}</p></div>` : ""}
        <button class="btn" id="arena-accept-invite" ${state.busy ? "disabled" : ""}>
          ${escapeHtml(t("arena.join"))}
        </button>
      </div>
    </div>
  `.trim();
}

export function renderArenaPage(state?: ArenaState): string {
  if (!state) {
    return renderLoadingState({ message: t("arena.loading") });
  }

  switch (state.subview) {
    case "challenge":
      return renderChallengeView(state);
    case "duel":
      return renderDuelView(state);
    case "invitation":
      return renderInvitationView(state);
    case "hub":
    default:
      return renderHubView(state);
  }
}
