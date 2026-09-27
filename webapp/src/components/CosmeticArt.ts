import { parseResolvedAppearance } from '@/appearance';
import { CARD_PREVIEWS } from '@/appearance/card-previews';
import { escapeHtml as e } from '@/utils/format';
import { t } from '@/i18n';

/** Backend-rendered sample, never a client reconstruction of the purchased finish. */
export function renderCardSample(value: unknown): string {
  const card = parseResolvedAppearance({ card: value }).card!;
  const sample = CARD_PREVIEWS.find(({ style }) =>
    (['finish', 'paper', 'ink', 'glow'] as const).every(key => style[key] === card[key]));
  if (!sample) return '';
  return `<figure class="cosmetic-card-sample"><img src="${e(sample.url)}" width="400" height="500" loading="lazy" alt="${e(t('shop.cardSample'))}"><figcaption>${e(t('shop.cardSample'))}</figcaption></figure>`;
}

/** Referral exclusives: one bounded entrance, then a static formation. */
export function renderFormation(value: unknown): string {
  if (!parseResolvedAppearance(value).theme?.formation) return '';
  const positions = [[50,88],[15,66],[38,70],[62,70],[85,66],[24,45],[50,48],[76,45],[20,20],[50,16],[80,20]];
  return `<div class="cosmetic-formation" aria-hidden="true"><svg viewBox="0 0 100 105"><rect x="4" y="4" width="92" height="97" rx="3"/><path d="M4 52h92 M33 101V82h34v19 M33 4v19h34V4"/><circle cx="50" cy="52" r="12"/>${positions.map(([x,y],i)=>`<circle class="formation-player" style="--player-delay:${i*60}ms" cx="${x}" cy="${y}" r="3"/>`).join('')}</svg></div>`;
}

export function renderProfileCosmeticArt(value: unknown): string {
  const a = parseResolvedAppearance(value);
  const card = a.card?.finish && a.card.finish !== 'plain' ? renderCardSample(a.card) : '';
  const formation = renderFormation(a);
  return card || formation ? `<div class="profile-cosmetic-art">${formation}${card}</div>` : '';
}
