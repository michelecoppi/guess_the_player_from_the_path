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

test("initTelegram disables vertical swipes on Bot API 7.7+ only (#183)", async () => {
  const { setupTestTelegram } = await import("./helpers");
  const calls: string[] = [];
  const track = (version: string | null) => {
    const { restore } = setupTestTelegram({
      ready: () => calls.push("ready"),
      expand: () => calls.push("expand"),
      disableVerticalSwipes: () => calls.push(`disable@${version}`),
      ...(version ? { isVersionAtLeast: (v: string) => Number(version) >= Number(v) } : {}),
    });
    try {
      initTelegram(false);
    } finally {
      restore();
    }
  };
  track("8.0");
  track("7.0");
  track(null); // no isVersionAtLeast: rely on the method being present
  assert.deepEqual(calls, [
    "ready", "expand", "disable@8.0",
    "ready", "expand",
    "ready", "expand", "disable@null",
  ]);
});

test("initTelegram survives clients without or failing disableVerticalSwipes (#183)", async () => {
  const { setupTestTelegram } = await import("./helpers");
  let expanded = 0;
  for (const overrides of [
    { disableVerticalSwipes: undefined },
    { disableVerticalSwipes: () => { throw new Error("unsupported"); } },
  ]) {
    const { restore } = setupTestTelegram({ ...overrides, expand: () => { expanded++; } });
    const originalWarn = console.warn;
    console.warn = () => {};
    try {
      assert.ok(initTelegram(false));
    } finally {
      console.warn = originalWarn;
      restore();
    }
  }
  assert.equal(expanded, 2);
});

test("the dev mock tracks vertical swipes", () => {
  const mock = createMockTelegramWebApp();
  assert.equal(mock.isVerticalSwipesEnabled, true);
  mock.disableVerticalSwipes?.();
  assert.equal(mock.isVerticalSwipesEnabled, false);
});
