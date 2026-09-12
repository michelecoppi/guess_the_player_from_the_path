import type { TelegramWebApp } from "./types";
/** Telegram surfaces follow the host; accents and feedback preserve their meaning. */
export function applyTelegramTheme(tg: TelegramWebApp | null): void {
  const root = document.documentElement;
  root.dataset.theme =
    tg?.colorScheme ||
    (window.matchMedia?.("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light");
  for (const key of [
    "bg_color",
    "secondary_bg_color",
    "section_bg_color",
    "text_color",
  ] as const) {
    const value =
      tg?.platform !== "dev_browser" ? tg?.themeParams[key] : undefined;
    const name = `--tg-theme-${key.replaceAll("_", "-")}`;
    if (value && /^#[0-9a-f]{6}$/i.test(value))
      root.style.setProperty(name, value);
    else root.style.removeProperty(name);
  }
  for (const edge of ["top", "bottom", "left", "right"] as const) {
    const inset =
      Math.max(0, tg?.safeAreaInset?.[edge] || 0) +
      Math.max(0, tg?.contentSafeAreaInset?.[edge] || 0);
    root.style.setProperty(`--tg-safe-${edge}`, `${inset}px`);
  }
}
export function connectTheme(tg: TelegramWebApp | null): () => void {
  const update = () => applyTelegramTheme(tg);
  update();
  const events = ["themeChanged", "safeAreaChanged", "contentSafeAreaChanged"];
  events.forEach((event) => tg?.onEvent?.(event, update));
  return () => events.forEach((event) => tg?.offEvent?.(event, update));
}
