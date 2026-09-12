/** Design fixtures only. Never interpreted as authenticated user data. */
import type { ArenaDuel } from "@/features/arena";
import type { UserProfileData } from "@/features/profile";
import type { LeaderboardRank } from "@/features/leaderboard";
import type { ArchiveCalendarDay } from "@/features/archive";
import type { ShopCosmeticItem } from "@/features/shop";
import type { ReferralProgress } from "@/features/referral";
import type { EventChallenge } from "@/features/events";
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
  cosmetics: {},
};
export const rankings: LeaderboardRank[] = [
  { rank: 1, user_id: 2, name: "Andrea Bianchi", points: 148, best_streak: 12 },
  { rank: 2, user_id: 3, name: "Sofia Riva", points: 142, best_streak: 9 },
  { rank: 3, user_id: 4, name: "Luca Ferri", points: 137, best_streak: 11 },
  { rank: 4, user_id: 1, name: "Marco Rossi", points: 128, best_streak: 7 },
  { rank: 5, user_id: 5, name: "Giulia Costa", points: 125, best_streak: 6 },
];
export const days: ArchiveCalendarDay[] = Array.from(
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
    id: "paper",
    type: "theme",
    name: "Match programme",
    description: "Carta, inchiostro, calcio.",
    price_stars: 50,
    unlocked: false,
    equipped: false,
  },
  {
    id: "captain",
    type: "frame",
    name: "Capitano",
    description: "Una fascia per il tuo profilo.",
    price_stars: 30,
    unlocked: false,
    equipped: false,
  },
  {
    id: "squares",
    type: "symbol",
    name: "Il tabellino",
    description: "I tuoi tentativi, in campo.",
    price_stars: 20,
    unlocked: true,
    equipped: true,
  },
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
