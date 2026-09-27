import { appearanceFixtures } from "./appearance-fixtures";
/** Design fixtures only. Never interpreted as authenticated user data. */
export interface UserProfileData {
  id: number;
  name: string;
  points: number;
  current_streak: number;
  best_streak: number;
  trophies: Array<{ id: string; name: string; position: number; date: string }>;
  cosmetics?: any;
}

import type { ArenaDuel } from "@/features/arena";
import type { LeaderboardRank } from "@/features/leaderboard";
import type { ShopCosmeticItem } from "@/features/shop";
import type { ReferralProgress } from "@/features/referral";
import type { EventChallenge } from "@/features/events";

export interface PrototypeArchiveDay {
  date: string;
  solved: boolean;
  available: boolean;
  attempts?: number;
}
export const duel: ArenaDuel = {
  duel_id: "sample",
  status: "active",
  opponent: { id: 2, name: "Andrea" },
  current_round: 3,
  total_rounds: 5,
  user_score: 2,
  opponent_score: 1,
};
export const profile: UserProfileData = {
  id: 1,
  name: "Marco Rossi",
  points: 1240,
  current_streak: 7,
  best_streak: 18,
  trophies: [{ id: "sample", name: "Settembre", position: 2, date: "2026-09" }],
  cosmetics: appearanceFixtures.identity,
};
export const rankings: LeaderboardRank[] = [
  { rank: 1, user_id: 2, name: "Andrea Bianchi", points: 148, best_streak: 12 },
  { rank: 2, user_id: 3, name: "Sofia Riva", points: 142, best_streak: 9 },
  { rank: 3, user_id: 4, name: "Luca Ferri", points: 137, best_streak: 11 },
  { rank: 4, user_id: 1, name: "Marco Rossi", points: 128, best_streak: 7 },
  { rank: 5, user_id: 5, name: "Giulia Costa", points: 125, best_streak: 6 },
];
export const days: PrototypeArchiveDay[] = Array.from(
  { length: 30 },
  (_, i) => ({
    date: `2026-09-${String(i + 1).padStart(2, "0")}`,
    solved: i < 11 && i !== 4 && i !== 7,
    available: i < 12,
    attempts: i < 11 ? 3 : undefined,
  }),
);
export const items: ShopCosmeticItem[] = [
  {
    "id": "ghiaccio",
    "kind": "theme",
    "name": "Ghiaccio",
    "description": "Chiarissimo. Per chi gioca alla luce del sole e odia gli schermi neri.",
    "price": 15,
    "full_price": 15,
    "missing": [
      "ghiaccio"
    ],
    "achievement": null,
    "progress": 0,
    "style": {
      "bg": "#eef4fa",
      "bg2": "#e0eaf4",
      "card": "#ffffff",
      "edge": "#cbdbe9",
      "text": "#16283a",
      "muted": "#61798f",
      "accent": "#1f7ae0",
      "accentText": "#ffffff",
      "track": "#d3e2ef"
    },
    "grants": [],
    "owned": false,
    "equipped": false,
    "free": false,
    "featured": false,
    "equippable": true,
    "rarity": "common",
    "completes": [],
    "trophy": null,
    "welcome": false
  },
  {
    "id": "fascia_capitano",
    "kind": "frame",
    "name": "Fascia da capitano",
    "description": "Le righe della fascia, intorno alla tua faccia.",
    "price": 15,
    "full_price": 15,
    "missing": [
      "fascia_capitano"
    ],
    "achievement": null,
    "progress": 0,
    "style": {
      "ring": "repeating-linear-gradient(45deg, #f5c542 0 7px, #1b3a6b 7px 14px)"
    },
    "grants": [],
    "owned": false,
    "equipped": false,
    "free": false,
    "featured": false,
    "equippable": true,
    "rarity": "common",
    "completes": [],
    "trophy": null,
    "welcome": false
  },
  {
    "id": "quadratini_classici",
    "kind": "squares",
    "name": "Quadratini classici",
    "description": "🟩 🟥 ⬜ - quelli che legge tutto il gruppo.",
    "price": 0,
    "full_price": 0,
    "missing": [],
    "achievement": null,
    "progress": 0,
    "style": {
      "correct": "🟩",
      "wrong": "🟥",
      "unused": "⬜"
    },
    "grants": [],
    "owned": true,
    "equipped": true,
    "free": true,
    "featured": false,
    "equippable": true,
    "rarity": "free",
    "completes": [],
    "trophy": null,
    "welcome": false
  }
];
export const referral: ReferralProgress = {
  qualified_count: 2,
  max_rewards: 5,
  friends: [
    { name: "Andrea", days_completed: 3, qualified: true },
    { name: "Sofia", days_completed: 2, qualified: false },
  ],
};
export const event: EventChallenge = {
  event_id: "sample",
  title: "Notti europee",
  theme: "Carriere da Champions",
  starts_at: "2026-09-15",
  ends_at: "2026-09-22",
  active: false,
};
