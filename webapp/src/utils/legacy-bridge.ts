/**
 * Compatibility boundary and bridge between new TypeScript modules
 * and the existing legacy JavaScript client (webapp/client.js, webapp/strings.js).
 */

import * as format from "./format";
import * as game from "./game";

export interface LegacyPlayerClient {
  escapeHtml: typeof format.escapeHtml;
  initials: typeof format.initials;
  weekNumber: typeof format.weekNumber;
  squares: typeof game.squares;
  histogram: typeof game.histogram;
  cabinetCounts: typeof game.cabinetCounts;
  mergeProfile: typeof game.mergeProfile;
  languageFromCode: (code?: string, supported?: string[]) => string;
}

declare global {
  interface Window {
    PlayerClient?: LegacyPlayerClient;
    PlayerStrings?: Record<string, any>;
    referrals?: Record<string, any>;
  }
}

/**
 * Ensures PlayerClient global is available on window for legacy scripts
 * if loaded in an environment where modern bundle executes first.
 */
export function exposeLegacyBridge(): void {
  if (typeof window === "undefined") return;

  if (!window.PlayerClient) {
    window.PlayerClient = {
      escapeHtml: format.escapeHtml,
      initials: format.initials,
      weekNumber: format.weekNumber,
      squares: game.squares,
      histogram: game.histogram,
      cabinetCounts: game.cabinetCounts,
      mergeProfile: game.mergeProfile,
      languageFromCode: (code?: string, supported?: string[]) => {
        const langs = supported || ["it", "es", "en"];
        const short = String(code || "").toLowerCase().split("-")[0];
        return langs.indexOf(short) === -1 ? "en" : short;
      },
    };
  }
}
