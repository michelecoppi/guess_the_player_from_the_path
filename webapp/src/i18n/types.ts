export type SupportedLanguage = "it" | "es" | "en";

export interface TranslationSchema {
  common: {
    appName: string;
    loading: string;
    error: string;
    retry: string;
    points: string;
    streak: string;
    anonymous: string;
  };
  nav: {
    play: string;
    arena: string;
    profile: string;
    leaderboard: string;
  };
  shell: {
    statusTitle: string;
    statusDesc: string;
    toolchainProven: string;
    activeTab: string;
    mockNotice: string;
  };
  pages: {
    dailyTitle: string;
    dailyKicker: string;
    arenaTitle: string;
    arenaKicker: string;
    profileTitle: string;
    profileKicker: string;
    leaderboardTitle: string;
    leaderboardKicker: string;
  };
  migration: {
    badge: string;
    dailyNotice: string;
    arenaNotice: string;
    profileNotice: string;
    leaderboardNotice: string;
  };
}
