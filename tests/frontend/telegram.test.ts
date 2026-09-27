import { test } from "node:test";
import assert from "node:assert/strict";
import {
  createMockTelegramWebApp,
  initTelegram,
  getTelegramUser,
  getInitData,
  isMockTelegramEnvironment,
} from "../../webapp/src/telegram";

test("createMockTelegramWebApp creates a fully formed mock WebApp", () => {
  const mock = createMockTelegramWebApp();
  assert.equal(mock.initDataUnsafe.user?.first_name, "Marco");
  assert.equal(mock.initDataUnsafe.user?.id, 42);
  assert.equal(mock.colorScheme, "dark");
  assert.ok(mock.MainButton);
  assert.ok(mock.HapticFeedback);
});

test("initTelegram injects mock when running in node/browser without window.Telegram", () => {
  // In node environment without browser window.Telegram:
  const tg = initTelegram(true);
  assert.ok(tg);
  assert.equal(getTelegramUser()?.first_name, "Marco");
  assert.ok(getInitData().includes("mock_init_data"));
  assert.ok(isMockTelegramEnvironment());
});
