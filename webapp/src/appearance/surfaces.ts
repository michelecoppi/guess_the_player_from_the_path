import { identityAppearance, resultAppearance, parseResolvedAppearance, skinTokens } from "./index";
import { renderAvatar } from "@/components/Avatar";
import { escapeHtml as e } from "@/utils/format";
/** Scope a person's decorative theme to their profile; never inherit another user's skin. */
export function profileSurfaceAttributes(value: unknown): string {
  const tokens = {
    '--skin-accent': '#46cc91', '--skin-accent-secondary': '#314253',
    '--skin-pitch': '#2a3c4b', '--skin-profile-surface': '#1a2734', '--skin-profile-glow': 'none', '--skin-pattern': 'none',
    ...skinTokens(parseResolvedAppearance(value)),
  };
  return `data-cosmetic-profile style="${e(Object.entries(tokens).map(([key,value])=>`${key}:${value}`).join(';'))}"`;
}
/** Identity-only rendering. Caller chooses whose resolved payload to display. */
export function renderAppearanceIdentity(name: string, value: unknown): string {
  const a = identityAppearance(value);
  // No perpetual frame spin in V2; ring paint is a reviewed literal.
  return `${renderAvatar({ name, tactics: a.frame.tactics, ringStyle: a.frame.ring ? `background: ${a.frame.ring}` : undefined })}<div class="cosmetic-identity"><b>${e(name)}</b>${a.badge ? `<span class="cosmetic-badge">${e(a.badge)}</span>` : ""}${a.title.label ? `<p class="cosmetic-title"${a.title.color ? ` style="border-color: ${a.title.color}"` : ""}>${e(a.title.label)}</p>` : ""}${a.number ? `<span class="cosmetic-number">Nº ${e(a.number)}</span>` : ""}</div>`;
}
/** Image pixels stay backend-owned. The frame is decorative, never success/error ink. */
export function resultCardAttributes(value: unknown): string {
  const { card } = resultAppearance(value);
  return `data-card-finish="${e(card.finish || "plain")}"${card.glow ? ` style="--result-finish-accent: ${card.glow}"` : ""}`;
}
