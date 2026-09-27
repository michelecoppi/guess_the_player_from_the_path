import type { TelegramWebApp } from "./types";
/** Fixed dark identity. Telegram still owns viewport and safe-area integration. */
export function applyTelegramTheme(tg: TelegramWebApp | null): void {
  const root = document.documentElement;
  root.dataset.theme = "dark";
  const inset = (value: unknown) => typeof value === "number" && Number.isFinite(value) ? Math.max(0, value) : 0;
  for (const edge of ["top", "bottom", "left", "right"] as const) {
    root.style.setProperty(`--tg-safe-${edge}`, `${inset(tg?.safeAreaInset?.[edge]) + inset(tg?.contentSafeAreaInset?.[edge])}px`);
  }
  root.style.setProperty("--tg-viewport-height", `${inset(tg?.viewportHeight)}px`);
  root.style.setProperty("--tg-viewport-stable-height", `${inset(tg?.viewportStableHeight)}px`);
}
export function connectTheme(tg: TelegramWebApp | null): () => void {
  const update = () => applyTelegramTheme(tg);
  update();
  const events = ["themeChanged", "safeAreaChanged", "contentSafeAreaChanged", "viewportChanged"];
  events.forEach((event) => tg?.onEvent?.(event, update));
  return () => events.forEach((event) => tg?.offEvent?.(event, update));
}
