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
  const worn = slots.map(kind => ({
    kind,
    item: (equipped && wardrobe?.find(item => item.id === equipped[kind] && item.kind === kind))
      || wearing.find(item => item.kind === kind),
  }));
  const customised = worn.filter(({item}) => item && !item.free).length;
  // Free starter styles belong to everyone: listing them would bury what the player earned or bought.
  const collected = wardrobe?.filter(item => !item.free) || [];
  const wornIds = new Set(worn.map(({item}) => item?.id).filter(Boolean));

  return `<section class="style-inventory" aria-label="${escapeHtml(v('outfit'))}">
    <div class="style-section-heading"><h3 class="section-heading">${escapeHtml(v('outfit'))}</h3><span class="style-count">${escapeHtml(v('customised').replace('{n}', String(customised)))}</span></div>
    <dl class="outfit-sheet">${worn.map(({kind, item}) => {
      const basic = !item || item.free;
      return `<div class="outfit-slot${basic ? ' is-basic' : ''}"><dt>${escapeHtml(styleKindLabel(kind))}</dt><dd>${escapeHtml(item?.name || '—')}</dd></div>`;
    }).join('')}</dl>
    ${wardrobe ? `<details class="style-collection" open><summary><span>${escapeHtml(v('ownedStyles'))}</span><span class="style-count">${collected.length}</span></summary>
      ${collected.length ? slots.map(kind => {
        const items = collected.filter(item => item.kind === kind);
        return items.length ? `<div class="style-collection-row"><h4>${escapeHtml(styleKindLabel(kind))}</h4><ul>${items.map(item => {
          const isWorn = wornIds.has(item.id);
          return `<li class="style-chip${isWorn ? ' is-worn' : ''}">${escapeHtml(item.name)}${isWorn ? `<span class="sr-only"> · ${escapeHtml(v('equippedStyle'))}</span>` : ''}</li>`;
        }).join('')}</ul></div>` : '';
      }).join('') : `<p class="muted">${escapeHtml(v('noStyles'))}</p>`}
    </details>` : ''}
  </section>`;
}
