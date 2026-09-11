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
