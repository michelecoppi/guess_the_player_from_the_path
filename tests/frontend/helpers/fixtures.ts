import type { CareerStop } from "@/components/CareerPath";

export function createTestCareerStop(overrides: Partial<CareerStop> = {}): CareerStop {
  return {
    team: "Juventus",
    league: "Serie A",
    country: "Italia",
    start_year: 2001,
    end_year: 2018,
    apps: 509,
    goals: 0,
    loan: false,
    ...overrides,
  };
}

export function createTestCareerPath(): CareerStop[] {
  return [
    createTestCareerStop({
      team: "Parma",
      league: "Serie A",
      country: "Italia",
      start_year: 1995,
      end_year: 2001,
      apps: 168,
      goals: 0,
    }),
    createTestCareerStop({
      team: "Juventus",
      league: "Serie A",
      country: "Italia",
      start_year: 2001,
      end_year: 2018,
      apps: 509,
      goals: 0,
    }),
    createTestCareerStop({
      team: "Paris Saint-Germain",
      league: "Ligue 1",
      country: "Francia",
      start_year: 2018,
      end_year: 2019,
      apps: 17,
      goals: 0,
      loan: true,
    }),
  ];
}

export interface TestDailyChallengeState {
  available: boolean;
  number: number;
  difficulty_label: string;
  points: number;
  attempts_used: number;
  attempts_left: number;
  max_attempts: number;
  solved: boolean;
  bonus_available: boolean;
  career_path: CareerStop[];
  hints: {
    total: number;
    used: number;
    taken: string[];
  };
}

export function createTestDailyChallenge(
  overrides: Partial<TestDailyChallengeState> = {}
): TestDailyChallengeState {
  return {
    available: true,
    number: 42,
    difficulty_label: "Media",
    points: 100,
    attempts_used: 1,
    attempts_left: 4,
    max_attempts: 5,
    solved: false,
    bonus_available: true,
    career_path: createTestCareerPath(),
    hints: {
      total: 3,
      used: 1,
      taken: ["Ha vinto un Mondiale nel 2006"],
    },
    ...overrides,
  };
}

export interface TestLeaderboardItem {
  profile_id: number;
  name: string;
  points: number;
  streak: number;
  position: number;
  badge?: string;
}

export function createTestLeaderboard(): TestLeaderboardItem[] {
  return [
    { profile_id: 101, name: "Alessandro Del Piero", points: 1540, streak: 12, position: 1, badge: "👑" },
    { profile_id: 102, name: "Francesco Totti", points: 1480, streak: 9, position: 2, badge: "🥈" },
    { profile_id: 103, name: "Roberto Baggio", points: 1390, streak: 7, position: 3, badge: "🥉" },
    { profile_id: 104, name: "Andrea Pirlo", points: 1210, streak: 4, position: 4 },
  ];
}

export function createTestDuelSession(overrides: Record<string, any> = {}) {
  return {
    round: 0,
    attempts: 0,
    solved: 0,
    spent: 0,
    revision: 0,
    finished: false,
    history: [],
    total: 5,
    max_attempts: 3,
    career_path: [
      { year: "2010-2015", team: "Palermo", apps: 115 },
      { year: "2015-2022", team: "Juventus", apps: 293 },
      { year: "2022-2026", team: "Roma", apps: 85 },
    ],
    difficulty_label: "Media",
    ...overrides,
  };
}

export function createTestTrainingSession(
  overrides: Partial<import("@/features/training/types").TrainingSession> = {},
): import("@/features/training/types").TrainingSession {
  return {
    round: 0,
    attempts: 0,
    solved: 0,
    spent: 0,
    revision: 1,
    finished: false,
    history: [],
    total: 1,
    max_attempts: 5,
    difficulty_label: "Media",
    career_path: createTestCareerPath(),
    ...overrides,
  };
}

export const TEST_DUEL_CODE = "000000000000000000000001"; // pragma: allowlist secret

export function createTestDuelData(overrides: Record<string, any> = {}) {
  return {
    code: TEST_DUEL_CODE,
    expires_at: "2026-09-20T12:00:00Z",
    invite_url: `https://t.me/TestBot?start=duel_${TEST_DUEL_CODE}`,
    session: createTestDuelSession(),
    opponent: {
      name: "Andrea",
      round: 0,
      finished: false,
    },
    complete: false,
    rounds: [],
    ledger: {
      record: { name: "Andrea", won: 3, lost: 2, drawn: 1 },
      matches: [],
    },
    open: [
      {
        code: TEST_DUEL_CODE,
        opponent: "Andrea",
        complete: false,
        round: 0,
        total: 5,
        expires_at: "2026-09-20T12:00:00Z",
      },
    ],
    ...overrides,
  };
}

export function createTestOpponentProfile(overrides: Record<string, any> = {}) {
  return {
    profile_id: 999,
    name: "Giorgio",
    badge: "⭐",
    points: 320,
    trophies: 2,
    ...overrides,
  };
}

export function createTestTrainingData(
  overrides: Partial<import("@/features/training/types").TrainingData> = {},
): import("@/features/training/types").TrainingData {
  return {
    session: createTestTrainingSession(),
    feedback: null,
    ...overrides,
  };
}

export function createTestFullProfile(overrides: Record<string, any> = {}) {
  return {
    user: {
      name: "Mario",
      points: 450,
      monthly_points: 120,
      players_guessed: 45,
      bonus_first_guessed: 3,
      streak: 5,
      best_streak: 12,
      archive_solved: 8,
      trophies: 2,
    },
    leaderboard: [
      { position: 1, profile_id: 101, name: "Alessandro Del Piero", badge: "👑", points: 1540, me: false },
      { position: 2, profile_id: 102, name: "Francesco Totti", badge: "🥈", points: 1480, me: false },
      { position: 3, profile_id: 103, name: "Mario", badge: "⭐", points: 450, me: true },
      { position: 4, profile_id: 104, name: "Andrea Pirlo", points: 400, me: false },
    ],
    leagues: [
      {
        code: "BAR01",
        name: "Amici del Bar",
        members: 4,
        position: 2,
        points: 450,
        standings: [
          { position: 1, profile_id: 101, name: "Alessandro Del Piero", points: 1540, me: false },
          { position: 2, profile_id: 103, name: "Mario", points: 450, me: true },
          { position: 3, profile_id: 102, name: "Francesco Totti", points: 300, me: false },
          { position: 4, profile_id: 104, name: "Andrea Pirlo", points: 200, me: false },
        ],
      },
    ],
    ...overrides,
  };
}

export function createTestPublicProfile(overrides: Record<string, any> = {}) {
  return {
    user: {
      name: "Alessandro Del Piero",
      points: 1540,
      monthly_points: 320,
      players_guessed: 150,
      bonus_first_guessed: 15,
      streak: 12,
      best_streak: 25,
      archive_solved: 30,
      trophies: 5,
    },
    cosmetics: {
      equipped: {
        theme: "notturno",
        frame: "fascia_capitano",
        title: "veterano",
        badge: "distintivo_stella",
        squares: "quadratini_classici",
        number: "maglia_dieci",
        celebration: "nessuna_esultanza",
        card: "card_classica",
      },
      badge: "⭐",
      number: "10",
      frame: {
        ring: "repeating-linear-gradient(45deg, #f5c542 0 7px, #1b3a6b 7px 14px)",
      },
      title: {
        label: "Veterano del pallone",
        color: "#d9b45b",
      },
      theme: {
        bg: "#0a131e",
      },
    },
    trophies: ["Trophy 1", "Trophy 2"],
    wearing: [
      { kind: "number", name: "Maglia numero 10" },
      { kind: "badge", name: "Stella" },
    ],
    ...overrides,
  };
}

import type { ArchiveCalendarDay, ArchiveChallenge, ArchiveGuessResult } from "@/features/archive/types";

export function createTestArchiveDay(overrides: Partial<ArchiveCalendarDay> = {}): ArchiveCalendarDay {
  return {
    day: "2026-09-01",
    label: "01/09/26",
    number: 42,
    difficulty: "medium",
    difficulty_label: "Media",
    status: "solved",
    attempts: 2,
    hints: 0,
    playable: false,
    ...overrides,
  };
}

export function createTestCalendar(): ArchiveCalendarDay[] {
  return [
    createTestArchiveDay({ day: "2026-09-01", number: 40, status: "solved", playable: false, attempts: 2 }),
    createTestArchiveDay({ day: "2026-09-02", number: 41, status: "lost", playable: true, attempts: 5 }),
    createTestArchiveDay({ day: "2026-09-03", number: 42, status: "recovered", playable: false, attempts: 3 }),
    createTestArchiveDay({ day: "2026-09-04", number: 43, status: "missed", playable: true, attempts: null }),
  ];
}

export function createTestArchiveChallenge(overrides: Partial<ArchiveChallenge> = {}): ArchiveChallenge {
  return {
    day: "2026-09-02",
    label: "02/09/26",
    number: 41,
    difficulty: "medium",
    difficulty_label: "Media",
    solved: false,
    attempts_used: 0,
    attempts_left: 5,
    max_attempts: 5,
    career_path: createTestCareerPath(),
    ...overrides,
  };
}

export function createTestArchiveGuessResult(overrides: Partial<ArchiveGuessResult> = {}): ArchiveGuessResult {
  return {
    status: "wrong",
    attempts_used: 1,
    attempts_left: 4,
    comparison: {
      name: "Pirlo",
      clues: [
        { key: "feedback.nationality_same", args: {} },
        { key: "feedback.position_diff", args: {} },
      ],
    },
    ...overrides,
  };
}



