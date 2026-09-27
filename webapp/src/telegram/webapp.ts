import type { TelegramWebApp, TelegramUser } from "./types";
import { createMockTelegramWebApp } from "./mock";

let cachedTg: TelegramWebApp | null = null;
let isMock = false;

export function resetTelegramCache(): void {
  cachedTg = null;
  isMock = false;
}

/**
 * Returns the Telegram WebApp instance.
 * If running inside Telegram, returns the real window.Telegram.WebApp.
 * If running outside Telegram (e.g. in dev browser), injects a dev mock.
 */
export function getTelegramWebApp(enableMockInDev = true): TelegramWebApp | null {
  const win = typeof window !== "undefined" ? window : (typeof globalThis !== "undefined" ? (globalThis as any) : null);

  if (win && win.Telegram && win.Telegram.WebApp) {
    cachedTg = win.Telegram.WebApp;
    isMock = Boolean((win.Telegram.WebApp as any).__isMock);
    return cachedTg;
  }

  if (cachedTg) return cachedTg;

  if (enableMockInDev && win) {
    cachedTg = createMockTelegramWebApp();
    isMock = true;
    if (!win.Telegram) {
      win.Telegram = { WebApp: cachedTg };
    } else {
      win.Telegram.WebApp = cachedTg;
    }
    return cachedTg;
  }

  return null;
}

/**
 * Initializes the Telegram Mini App (calls ready(), expand(), and sets header color).
 */
export function initTelegram(enableMock = true): TelegramWebApp | null {
  const tg = getTelegramWebApp(enableMock);
  if (!tg) return null;

  try {
    tg.ready();
    tg.expand();
  } catch (err) {
    console.warn("Telegram WebApp initialization error:", err);
  }
  disableVerticalSwipes(tg);

  return tg;
}

/**
 * Scrolling a long list back up (leaderboard, Shop catalogue) must not turn into Telegram's
 * swipe-down that minimises or closes the Mini App (#183). The header can still be dragged
 * and the close button still works. Needs Bot API 7.7: older clients only log a warning if
 * called, so the version is checked first.
 */
function disableVerticalSwipes(tg: TelegramWebApp): void {
  if (typeof tg.disableVerticalSwipes !== "function") return;
  if (typeof tg.isVersionAtLeast === "function" && !tg.isVersionAtLeast("7.7")) return;
  try {
    tg.disableVerticalSwipes();
  } catch (err) {
    console.warn("Telegram WebApp disableVerticalSwipes error:", err);
  }
}

export function getTelegramUser(): TelegramUser | null {
  const tg = getTelegramWebApp();
  return tg?.initDataUnsafe?.user || null;
}

export function getInitData(): string {
  const tg = getTelegramWebApp();
  return tg?.initData || "";
}

export function isMockTelegramEnvironment(): boolean {
  return isMock;
}
