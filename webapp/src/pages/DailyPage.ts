import {
  renderCard,
  renderMigrationNotice,
  renderCareerPath,
  renderGuessInput,
  renderHintPanel,
  renderBadge,
  type CareerStop,
} from "@/components";
import { t } from "@/i18n";
import { DAILY_FEATURE_METADATA } from "@/features/daily";

const DEMO_CAREER: CareerStop[] = [
  {
    team: "Parma",
    league: "Serie A",
    country: "Italia",
    start_year: 1995,
    end_year: 2001,
    apps: 168,
    goals: 0,
  },
  {
    team: "Juventus",
    league: "Serie A",
    country: "Italia",
    start_year: 2001,
    end_year: 2018,
    apps: 509,
    goals: 0,
  },
  {
    team: "Paris Saint-Germain",
    league: "Ligue 1",
    country: "Francia",
    start_year: 2018,
    end_year: 2019,
    apps: 17,
    goals: 0,
    loan: true,
  },
];

export function renderDailyPage(): string {
  const challengeHeaderHtml = renderCard({
    id: "daily-challenge-card",
    kicker: t("pages.dailyKicker"),
    title: t("pages.dailyTitle"),
    actionHtml: renderBadge({ label: "Media · 100 pts", variant: "success" }),
    bodyHtml: `
      <div style="display: flex; align-items: center; justify-content: space-between; gap: 10px;">
        <div style="font-size: 13px; color: var(--muted);">
          Tentativi rimasti: <b>5</b> · Sfida #42
        </div>
        ${renderBadge({ label: "In corso", variant: "warning" })}
      </div>
    `,
  });

  const careerCardHtml = renderCard({
    id: "daily-career-card",
    kicker: "Carriera",
    title: "Percorso club",
    bodyHtml: renderCareerPath({ stops: DEMO_CAREER }),
  });

  const interactionCardHtml = renderCard({
    id: "daily-interaction-card",
    kicker: "Risposta",
    title: "Indovina il calciatore",
    bodyHtml: `
      ${renderGuessInput({
        id: "daily-guess-box",
        placeholder: "Nome calciatore...",
        buttonLabel: "Invia risposta",
        helperText: "Componente condiviso GuessInput (migrazione logica in #40)",
      })}
      ${renderHintPanel({
        hintsTaken: ["Ha vinto un Mondiale nel 2006"],
        hintsTotal: 3,
        hintsUsed: 1,
        unlockButtonLabel: "Chiedi indizio",
        hintsLeftLabel: "indizi rimanenti",
      })}
    `,
  });

  const noticeHtml = renderMigrationNotice({
    issueNumber: DAILY_FEATURE_METADATA.owningIssue,
    messageKey: "migration.dailyNotice",
  });

  return `
    <div style="display: flex; flex-direction: column; gap: 12px;">
      ${challengeHeaderHtml}
      ${careerCardHtml}
      ${interactionCardHtml}
      ${noticeHtml}
    </div>
  `.trim();
}
