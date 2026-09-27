import type { TelegramUser, TelegramWebApp } from "@/telegram/types";
import { createMockTelegramWebApp } from "@/telegram/mock";
import { resetTelegramCache } from "@/telegram/webapp";

/**
 * Creates a valid mock TelegramUser with configurable overrides.
 */
export function createTestTelegramUser(overrides: Partial<TelegramUser> = {}): TelegramUser {
  return {
    id: 123456789,
    first_name: "TestPlayer",
    last_name: "Azzurri",
    username: "testplayer_az",
    language_code: "it",
    is_premium: false,
    ...overrides,
  };
}

/**
 * Encodes a mock initData string with user payload matching Telegram WebApp URL-encoded spec.
 */
export function createTestInitData(userOverrides: Partial<TelegramUser> = {}): string {
  const user = createTestTelegramUser(userOverrides);
  const userJson = JSON.stringify(user);
  const authDate = Math.floor(Date.now() / 1000);
  return `query_id=AAHdF6IQAAAAAN0XohD9_fake&user=${encodeURIComponent(userJson)}&auth_date=${authDate}&hash=fake_hmac_hash_for_test`;
}

/**
 * Sets up a mock Telegram WebApp on global window.Telegram.WebApp and returns a restore callback.
 */
export function setupTestTelegram(overrides: Partial<TelegramWebApp> = {}): {
  mock: TelegramWebApp;
  restore: () => void;
} {
  resetTelegramCache();
  const baseMock = createMockTelegramWebApp();
  const mock: TelegramWebApp = {
    ...baseMock,
    ...overrides,
  };

  const originalTelegram = (globalThis as any).Telegram;
  const originalWindow = (globalThis as any).window;

  if (!(globalThis as any).window) {
    (globalThis as any).window = globalThis;
  }

  (globalThis as any).Telegram = {
    WebApp: mock,
  };
  (globalThis as any).window.Telegram = (globalThis as any).Telegram;

  return {
    mock,
    restore: () => {
      resetTelegramCache();
      if (originalTelegram !== undefined) {
        (globalThis as any).Telegram = originalTelegram;
        if ((globalThis as any).window) {
          (globalThis as any).window.Telegram = originalTelegram;
        }
      } else {
        delete (globalThis as any).Telegram;
        if ((globalThis as any).window) {
          delete (globalThis as any).window.Telegram;
        }
      }

      if (originalWindow === undefined && (globalThis as any).window === globalThis) {
        delete (globalThis as any).window;
      }
    },
  };
}
