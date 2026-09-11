import type { TelegramWebApp, TelegramUser } from "./types";
import { createMockTelegramWebApp } from "./mock";

let cachedTg: TelegramWebApp | null = null;
let isMock = false;

/**
 * Returns the Telegram WebApp instance.
 * If running inside Telegram, returns the real window.Telegram.WebApp.
 * If running outside Telegram (e.g. in dev browser), injects a dev mock.
 */
export function getTelegramWebApp(enableMockInDev = true): TelegramWebApp | null {
  if (cachedTg) return cachedTg;

  const win = typeof window !== "undefined" ? window : (typeof globalThis !== "undefined" ? (globalThis as any) : null);

  if (win && win.Telegram && win.Telegram.WebApp) {
    cachedTg = win.Telegram.WebApp;
    isMock = false;
    return cachedTg;
  }

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

  return tg;
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
