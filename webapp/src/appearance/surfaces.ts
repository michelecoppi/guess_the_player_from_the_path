import { identityAppearance, resultAppearance } from "./index";
import { renderAvatar } from "@/components/Avatar";
import { escapeHtml as e } from "@/utils/format";
/** Identity-only rendering. Caller chooses whose resolved payload to display. */
export function renderAppearanceIdentity(name: string, value: unknown): string {
  const a = identityAppearance(value);
  // No perpetual frame spin in V2; ring paint is a reviewed literal.
  return `${renderAvatar({ name, ringStyle: a.frame.ring ? `background: ${a.frame.ring}` : undefined })}<div class="cosmetic-identity"><b>${e(name)}</b>${a.badge ? `<span class="cosmetic-badge">${e(a.badge)}</span>` : ""}${a.title.label ? `<p class="cosmetic-title"${a.title.color ? ` style="border-color: ${a.title.color}"` : ""}>${e(a.title.label)}</p>` : ""}${a.number ? `<span class="cosmetic-number">Nº ${e(a.number)}</span>` : ""}</div>`;
}
/** Image pixels stay backend-owned. The frame is decorative, never success/error ink. */
export function resultCardAttributes(value: unknown): string {
  const { card } = resultAppearance(value);
  return `data-card-finish="${e(card.finish || "plain")}"${card.glow ? ` style="--result-finish-accent: ${card.glow}"` : ""}`;
}
