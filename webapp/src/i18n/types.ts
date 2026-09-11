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
  daily: {
    todayTitle: string;
    solved: string;
    notPlayed: string;
    left: string;
    none: string;
    points: string;
    difficulty: string;
    bonus: string;
    placeholder: string;
    guessBtn: string;
    hintBtn: string;
    hintsLeft: string;
    noHints: string;
    correct: string;
    wrong: string;
    gotPoints: string;
    outOfAttempts: string;
    compared: string;
    sameNat: string;
    diffNat: string;
    samePos: string;
    diffPos: string;
    older: string;
    younger: string;
    sameYear: string;
    share: string;
    answerWas: string;
    showCard: string;
    cardHint: string;
    loading: string;
    already: string;
    error: string;
    notRegistered: string;
  };
  migration: {
    badge: string;
    dailyNotice: string;
    arenaNotice: string;
    profileNotice: string;
    leaderboardNotice: string;
  };
}
