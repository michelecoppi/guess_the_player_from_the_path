import type { ResolvedAppearance, CosmeticSlot } from "./types";
import { FRAME_PAINTS, THEME_PATTERNS } from "./decorations";
import type { SquareSymbols } from "@/utils/game";
export type * from "./types";

export const DEFAULT_SQUARE_SYMBOLS: SquareSymbols = { correct: "🟩", wrong: "🟥", unused: "⬜" };
export const SKIN_TOKENS = ["--skin-accent", "--skin-accent-text", "--skin-accent-secondary", "--skin-pitch", "--skin-profile-surface", "--skin-profile-glow", "--skin-pattern"] as const;
export type SkinTokens = Partial<Record<typeof SKIN_TOKENS[number], string>>;
const SLOTS: CosmeticSlot[] = ["theme", "frame", "title", "badge", "squares", "number", "celebration", "card"];
const EFFECTS = new Set(["spotlight", "confetti", "dust", "flash", "paper", "snow", "mud", "fireworks"]);
const FINISHES = new Set(["plain", "night", "foil", "grain", "tactics", "eleven", "ticket"]);
const record = (v: unknown): Record<string, unknown> => v !== null && typeof v === "object" && !Array.isArray(v) ? v as Record<string, unknown> : {};
const text = (v: unknown, max = 160): string => typeof v === "string" && v.length <= max ? v : "";
const color = (v: unknown): string => typeof v === "string" && /^#[0-9a-f]{6}$/i.test(v) ? v : "";
const SURFACE_INK = "#0b121b";
/** WCAG relative luminance of a validated #rrggbb colour. */
function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map(i => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  }) as [number, number, number];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** Shape validation only: never resolves IDs, ownership, defaults or collections. */
export function parseResolvedAppearance(value: unknown): ResolvedAppearance {
  const source = record(value), theme = record(source.theme), frame = record(source.frame);
  const title = record(source.title), squares = record(source.squares), card = record(source.card);
  const result: ResolvedAppearance = {
    theme: {}, frame: { ring: FRAME_PAINTS.get(text(frame.ring, 512)) || "", spin: frame.spin === true },
    title: { label: text(title.label), color: color(title.color) }, badge: text(source.badge, 32),
    squares: {}, number: /^\d{1,2}$/.test(text(source.number, 2)) ? source.number as string : "",
    celebration: EFFECTS.has(text(source.celebration)) ? source.celebration as string : "",
    card: { finish: FINISHES.has(text(card.finish)) ? card.finish as string : "", ink: color(card.ink), paper: color(card.paper), glow: color(card.glow) },
  };
  if (frame.tactics === 3 || frame.tactics === 11) result.frame!.tactics = frame.tactics;
  if (theme.formation === true) result.theme!.formation = true;
  // Structural colors are deliberately not forwarded to the presentation layer.
  for (const key of ["accent", "accentText", "edge", "track", "card"] as const) {
    const valid = color(theme[key]);
    if (valid) result.theme![key] = valid;
  }
  const rawPattern = text(theme.pattern, 1024);
  const pattern = THEME_PATTERNS.get(rawPattern) || ([...THEME_PATTERNS.values()].includes(rawPattern) ? rawPattern : undefined);
  if (pattern) result.theme!.pattern = pattern;
  for (const key of ["correct", "wrong", "unused"] as const) {
    const valid = text(squares[key], 32);
    if (valid) result.squares![key] = valid;
  }
  if (source.equipped) {
    result.equipped = {};
    for (const slot of SLOTS) {
      const id = record(source.equipped)[slot];
      if (id === null || (typeof id === "string" && id.length <= 100)) result.equipped[slot] = id;
    }
  }
  return result;
}

export function skinTokens(appearance: ResolvedAppearance): SkinTokens {
  const theme = appearance.theme || {};
  const tokens: SkinTokens = {};
  if (color(theme.accent)) tokens["--skin-accent"] = theme.accent!;
  if (color(theme.accentText)) tokens["--skin-accent-text"] = theme.accentText!;
  if (color(theme.edge)) tokens["--skin-accent-secondary"] = theme.edge!;
  if (color(theme.track)) tokens["--skin-pitch"] = theme.track!;
  // The purchased surface must read as that theme, while product text stays legible:
  // dark cards keep most of their own colour; light cards become a deep tint of their accent.
  if (color(theme.card)) {
    const light = luminance(theme.card!) > 0.35;
    tokens["--skin-profile-surface"] = light
      ? `color-mix(in srgb, ${color(theme.accent) || theme.card} 30%, ${SURFACE_INK})`
      : `color-mix(in srgb, ${theme.card} 70%, ${SURFACE_INK})`;
  }
  if (color(theme.accent)) tokens["--skin-profile-glow"] = `radial-gradient(ellipse 680px 320px at 50% 0, color-mix(in srgb, ${theme.accent} 16%, transparent), transparent)`;
  if (theme.pattern && [...THEME_PATTERNS.values()].includes(theme.pattern)) tokens["--skin-pattern"] = theme.pattern;
  return tokens;
}

let current: ResolvedAppearance = parseResolvedAppearance(undefined);
let generation = 0;
export function appearanceGeneration(): number { return generation; }
export function getResolvedAppearance(): ResolvedAppearance { return structuredClone(current); }
export function clearResolvedAppearance(): void {
  generation++;
  current = parseResolvedAppearance(undefined);
  if (typeof document !== "undefined") {
    for (const token of SKIN_TOKENS) document.documentElement.style.removeProperty(token);
  }
}
export function applyResolvedAppearance(value: unknown): ResolvedAppearance {
  current = parseResolvedAppearance(value);
  if (typeof document !== "undefined") {
    const tokens = skinTokens(current);
    for (const token of SKIN_TOKENS) {
      const value = tokens[token];
      if (value) document.documentElement.style.setProperty(token, value);
      else document.documentElement.style.removeProperty(token);
    }
  }
  return getResolvedAppearance();
}
export function appearanceSquares(appearance: ResolvedAppearance): SquareSymbols {
  const squares = parseResolvedAppearance(appearance).squares;
  return { ...DEFAULT_SQUARE_SYMBOLS, ...squares };
}
/** Explicit surface projection, for own/public profiles and identity rows. No global mutation. */
export function identityAppearance(value: unknown) {
  const a = parseResolvedAppearance(value);
  return { frame: a.frame!, title: a.title!, badge: a.badge!, number: a.number! };
}
export function resultAppearance(value: unknown) {
  const a = parseResolvedAppearance(value);
  const reduce = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  return { squares: appearanceSquares(a), card: a.card!, celebration: reduce ? "" : a.celebration! };
}
