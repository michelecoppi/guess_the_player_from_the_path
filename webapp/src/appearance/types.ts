/** Wire contract: services/shop.py::appearance, returned as /me.cosmetics.
 * Optional fields allow older responses. No ownership or catalog resolution here. */
export type CosmeticSlot = "theme" | "frame" | "title" | "badge" | "squares" | "number" | "celebration" | "card";
export type EquippedCosmetics = Partial<Record<CosmeticSlot, string | null>>;
export interface ThemeStyle {
  bg?: string; bg2?: string; card?: string; edge?: string; text?: string;
  muted?: string; accent?: string; accentText?: string; track?: string; pattern?: string;
}
export interface FrameStyle { ring?: string; spin?: boolean }
export interface TitleStyle { label?: string; color?: string }
export interface SquaresStyle { correct?: string; wrong?: string; unused?: string }
export interface CardStyle { finish?: string; ink?: string; paper?: string; glow?: string }
export interface ResolvedAppearance {
  equipped?: EquippedCosmetics;
  theme?: ThemeStyle;
  frame?: FrameStyle;
  title?: TitleStyle;
  badge?: string;
  squares?: SquaresStyle;
  number?: string;
  celebration?: string;
  card?: CardStyle;
}
