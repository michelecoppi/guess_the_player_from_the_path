import type { DailyState } from "@/features/daily/types";
export const REVIEW_STATES = [
  "ready",
  "typing",
  "submitting",
  "wrong",
  "hint",
  "correct",
  "completed",
  "loading",
  "error",
  "unavailable",
] as const;
export type ReviewState = (typeof REVIEW_STATES)[number];
export function dailyFixture(view: ReviewState): DailyState {
  const state: DailyState = {
    status: "ready",
    inputValue: "",
    squaresSymbols: { correct: "🟩", wrong: "🟥", unused: "⬜" },
    challenge: {
      available: true,
      number: 247,
      solved: false,
      attempts_used: 0,
      attempts_left: 5,
      max_attempts: 5,
      points: 5,
      difficulty_label: "Medio",
      bonus_available: true,
      hints: { total: 3, used: 0, taken: [] },
      career_path: [
        {
          team: "Brescia",
          league: "Serie A",
          country: "Italia",
          start_year: 1995,
          end_year: 1998,
          apps: 47,
          goals: 6,
        },
        {
          team: "Inter",
          league: "Serie A",
          country: "Italia",
          start_year: 1998,
          end_year: 2001,
          apps: 22,
          goals: 0,
        },
        {
          team: "Reggina",
          league: "Serie A",
          country: "Italia",
          start_year: 1999,
          end_year: 2000,
          apps: 28,
          goals: 6,
          loan: true,
        },
        {
          team: "Milan",
          league: "Serie A",
          country: "Italia",
          start_year: 2001,
          end_year: 2011,
          apps: 284,
          goals: 32,
        },
        {
          team: "Juventus",
          league: "Serie A",
          country: "Italia",
          start_year: 2011,
          end_year: 2015,
          apps: 119,
          goals: 16,
        },
        {
          team: "New York City FC",
          league: "MLS",
          country: "Stati Uniti",
          start_year: 2015,
          end_year: 2017,
          apps: 60,
          goals: 1,
        },
      ],
    },
  };
  if (view === "typing" || view === "submitting")
    state.inputValue = "Andrea Pirlo";
  if (view === "submitting") state.status = "submitting";
  if (view === "wrong") {
    state.status = "incorrect";
    state.challenge!.attempts_used = 1;
    state.challenge!.attempts_left = 4;
    state.feedback = {
      status: "wrong",
      attempts_left: 4,
      comparison: {
        name: "Francesco Totti",
        clues: [
          { key: "feedback.nationality_same" },
          { key: "feedback.position_diff" },
          { key: "feedback.birth_after", args: { year: 1976 } },
        ],
      },
    };
  }
  if (view === "hint")
    state.challenge!.hints = {
      total: 3,
      used: 1,
      taken: ["Ha vinto il Mondiale nel 2006."],
    };
  if (view === "correct" || view === "completed") {
    state.status = view;
    state.challenge!.solved = true;
    state.challenge!.attempts_used = 2;
    state.challenge!.attempts_left = 3;
    state.challenge!.bonus_available = false;
  }
  if (view === "correct")
    state.feedback = { status: "correct", points_awarded: 4 };
  if (view === "loading") {
    state.status = "loading";
    state.challenge = null;
  }
  if (view === "error") {
    state.status = "error";
    state.errorMessage =
      "Apri la Mini App dal bot Telegram per giocare la Daily.";
  }
  if (view === "unavailable") {
    state.status = "unavailable";
    state.challenge = null;
  }
  return state;
}
