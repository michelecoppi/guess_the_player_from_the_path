import {
  type ResolvedAppearance,
  parseResolvedAppearance,
  applyResolvedAppearance,
} from "@/appearance";
import type { ShopCosmeticItem } from "./types";

/**
 * Creates a safely sanitized ResolvedAppearance incorporating the previewed item or bundle.
 * All styles are parsed strictly through #66 allowlists; no raw arbitrary CSS is ever applied.
 */
export function createPreviewAppearance(
  base: ResolvedAppearance,
  item: ShopCosmeticItem,
  lang = "it",
): ResolvedAppearance {
  const candidate: Record<string, unknown> = structuredClone(base) as Record<string, unknown>;

  const pieces: ShopCosmeticItem[] =
    item.kind === "bundle" && item.contents && item.contents.length > 0
      ? item.contents
      : [item];

  for (const piece of pieces) {
    const style = piece.style || {};
    if (piece.kind === "badge") {
      candidate.badge = typeof style.emoji === "string" ? style.emoji : "";
    } else if (piece.kind === "number") {
      candidate.number = typeof style.number === "string" ? style.number : "";
    } else if (piece.kind === "celebration") {
      candidate.celebration = typeof style.effect === "string" ? style.effect : "";
    } else if (piece.kind === "title") {
      const labels = style.label_i18n as Record<string, string> | undefined;
      const label = labels?.[lang] || (typeof style.label === "string" ? style.label : "");
      candidate.title = {
        color: typeof style.color === "string" ? style.color : "",
        label,
      };
    } else if (
      piece.kind === "theme" ||
      piece.kind === "frame" ||
      piece.kind === "squares" ||
      piece.kind === "card"
    ) {
      candidate[piece.kind] = style;
    }
  }

  // Strictly sanitize through parseResolvedAppearance (#66 dark-only & valid tokens allowlist)
  return parseResolvedAppearance(candidate);
}

/**
 * Applies a preview appearance temporarily.
 */
export function applyPreview(previewAppearance: ResolvedAppearance): void {
  applyResolvedAppearance(previewAppearance);
}

/**
 * Restores authoritative appearance cleanly.
 */
export function restoreAppearance(authoritative: ResolvedAppearance): void {
  applyResolvedAppearance(authoritative);
}
