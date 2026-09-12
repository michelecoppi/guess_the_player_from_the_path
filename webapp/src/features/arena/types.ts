export type DuelAction =
  | "get"
  | "create"
  | "join"
  | "guess"
  | "reveal"
  | "delete"
  | "list";

export type DuelOutcome = "win" | "loss" | "draw";

export interface DuelCareerStop {
  year: string;
  team: string;
  apps?: number;
  appearances?: number;
}

export interface DuelSession {
  round: number;
  attempts: number;
  solved: number;
  spent: number;
  revision: number;
  finished: boolean;
  history: Array<{ solved: boolean; attempts: number }>;
  total: number;
  max_attempts: number;
  career_path?: DuelCareerStop[];
  difficulty_label?: string;
}

export interface DuelOpponent {
  id?: number;
  name: string;
  round?: number;
  finished?: boolean;
  solved?: number;
  spent?: number;
  avatar?: string;
  score?: number;
}

export interface ArenaDuel {
  duel_id: string;
  status: "waiting" | "active" | "completed";
  opponent?: DuelOpponent;
  current_round: number;
  total_rounds: number;
  user_score: number;
  opponent_score: number;
}

export const ARENA_FEATURE_METADATA = {
  id: "arena",
  name: "Arena Duels",
  owningIssue: 41,
  migrated: true,
} as const;

export interface DuelRoundSummary {
  n: number;
  solved: boolean;
  attempts: number;
  answer?: string;
  opponent?: { solved: boolean; attempts: number };
}

export interface DuelComparisonClue {
  key: string;
  args?: Record<string, any>;
}

export interface DuelComparison {
  name?: string;
  clues?: DuelComparisonClue[];
}

export interface DuelFeedback {
  status: "correct" | "wrong" | "refused";
  done: boolean;
  answer?: string;
  comparison?: DuelComparison;
  matched?: number;
  points?: number;
}

export interface DuelMatchRound {
  answer: string;
  you: { solved: boolean; attempts: number };
  them: { solved: boolean; attempts: number };
}

export interface DuelMatch {
  code: string;
  outcome: DuelOutcome;
  ended_at: string;
  name: string;
  you: { solved: number; spent: number };
  them: { solved: number; spent: number };
  rounds: DuelMatchRound[];
}

export interface DuelHeadToHead {
  name: string;
  won: number;
  lost: number;
  drawn: number;
}

export interface DuelLedger {
  record: DuelHeadToHead | null;
  matches: DuelMatch[];
}

export interface OpenDuelSummary {
  code: string;
  opponent: string | null;
  complete: boolean;
  round: number;
  total: number;
  expires_at: string;
}

export interface DuelData {
  code?: string;
  expires_at?: string;
  invite_url?: string | null;
  session?: DuelSession | null;
  opponent?: DuelOpponent | null;
  complete?: boolean;
  outcome?: DuelOutcome;
  feedback?: DuelFeedback | null;
  rounds?: DuelRoundSummary[];
  ledger?: DuelLedger;
  open?: OpenDuelSummary[];
  deleted?: string;
}

export interface OpponentProfile {
  profile_id: number;
  name: string;
  badge: string;
  points: number;
  trophies: number;
}

export type ArenaSubview = "hub" | "challenge" | "duel" | "invitation";

export interface ArenaState {
  subview: ArenaSubview;
  status: "idle" | "loading" | "submitting" | "searching" | "error";
  busy: boolean;
  error: string | null;
  notice: string | null;
  confirming: string | null;
  data: DuelData | null;
  activeDuelCode: string | null;
  invitationCode: string | null;
  searchQuery: string;
  searchResults: OpponentProfile[];
  searchError: string | null;
  draftAnswer: string;
}
