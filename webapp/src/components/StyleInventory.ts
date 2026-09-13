import { escapeHtml } from '@/utils/format';
import { t } from '@/i18n';
import { v } from '@/i18n/visual';
import type { CosmeticSlot, EquippedCosmetics } from '@/appearance';
import type { ApiPublicProfileItem } from '@/api/types';

const slots: CosmeticSlot[] = ['theme', 'frame', 'title', 'badge', 'squares', 'number', 'celebration', 'card'];
export function styleKindLabel(kind: string): string {
  return slots.includes(kind as CosmeticSlot)
    ? t(`shop.section${kind.charAt(0).toUpperCase()}${kind.slice(1)}`) : kind;
}

/** Shared, read-only outfit sheet. Ownership comes from the server's public projection. */
export function renderStyleInventory(
  wearing: ApiPublicProfileItem[] = [],
  wardrobe?: ApiPublicProfileItem[],
  equipped?: EquippedCosmetics,
): string {
  return `<section class="style-inventory" aria-label="${escapeHtml(v('outfit'))}">
    <div class="style-section-heading"><h3 class="section-heading">${escapeHtml(v('outfit'))}</h3><span class="eyebrow">${escapeHtml(v('equippedStyle'))}</span></div>
    <dl class="outfit-sheet">${slots.map(kind => {
      const item = equipped && wardrobe
        ? wardrobe.find(item => item.id === equipped[kind] && item.kind === kind)
        : wearing.find(item => item.kind === kind);
      return `<div><dt>${escapeHtml(styleKindLabel(kind))}</dt><dd>${escapeHtml(item?.name || '—')}</dd></div>`;
    }).join('')}</dl>
    ${wardrobe ? `<details class="style-collection" open><summary>${escapeHtml(v('ownedStyles'))}<span>${wardrobe.length}</span></summary>
      ${wardrobe.length ? slots.map(kind => {
        const items = wardrobe.filter(item => item.kind === kind);
        return items.length ? `<div class="style-collection-row"><h4>${escapeHtml(styleKindLabel(kind))}</h4><ul>${items.map(item => `<li>${escapeHtml(item.name)}</li>`).join('')}</ul></div>` : '';
      }).join('') : `<p class="muted">${escapeHtml(v('noStyles'))}</p>`}
    </details>` : ''}
  </section>`;
}
