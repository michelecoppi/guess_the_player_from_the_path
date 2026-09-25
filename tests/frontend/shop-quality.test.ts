import { setLanguage } from '../../webapp/src/i18n';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import catalogue from '../../data/shop.json';
import { parseResolvedAppearance } from '../../webapp/src/appearance';
import { renderCardSample, renderFormation, renderProfileCosmeticArt } from '../../webapp/src/components/CosmeticArt';
import { renderAvatar } from '../../webapp/src/components/Avatar';
import { createPreviewAppearance } from '../../webapp/src/features/shop/preview';
import { renderPreviewBar } from '../../webapp/src/features/shop/views';
import { ShopController } from '../../webapp/src/features/shop/controller';
import type { ShopCosmeticItem } from '../../webapp/src/features/shop/types';
import { setupGlobalDom } from './helpers';

test('all real frame, pattern, formation, tactics and card finishes survive appearance parsing', () => {
  for (const item of catalogue.items) {
    if (!['theme', 'frame', 'card'].includes(item.kind)) continue;
    const kind = item.kind as 'theme' | 'frame' | 'card';
    const style = item.style as Record<string, unknown>;
    const result = parseResolvedAppearance({ [kind]: style })[kind] as Record<string, unknown>;
    for (const key of ['ring', 'pattern', 'formation', 'tactics', 'finish', 'motion']) {
      if (style[key]) assert.ok(result[key], `${item.id}: missing ${key}`);
    }
  }
});

test('every real card has a backend sample; unsupported styles cannot inject image URLs', () => {
  for (const item of catalogue.items.filter(i => i.kind === 'card')) {
    assert.match(renderCardSample(item.style), /<img /, item.id);
  }
  assert.equal(renderCardSample({ finish: 'https://example.invalid/evil', paper: '#ffffff' }), '');
  assert.equal(parseResolvedAppearance({frame:{tactics:999},theme:{formation:'yes'}}).frame?.tactics, undefined);
});

test('referral decorations belong to the displayed user and reset without residue', () => {
  assert.equal((renderFormation({theme:{formation:true}}).match(/class="formation-player"/g) || []).length, 11);
  assert.match(renderAvatar({name:'Player',tactics:3}), /avatar-tactics/);
  assert.equal(renderFormation({theme:{}}), '');
  assert.equal(renderProfileCosmeticArt(undefined), '');
});

test('travel try-on includes one identity, four slots and the actual shared card sample', () => {
  const { cleanup } = setupGlobalDom();
  try {
    const bundle = catalogue.items.find(i => i.id === 'pacchetto_trasferta')!;
    const item = {...bundle, contents: bundle.grants!.map(id=>catalogue.items.find(i=>i.id===id))} as unknown as ShopCosmeticItem;
    setLanguage('en');
    const appearance = createPreviewAppearance({}, item, 'en');
    assert.equal(appearance.title?.label, 'Always away');
    assert.equal(appearance.card?.finish, 'ticket');
    const controller = new ShopController();
    const html = renderPreviewBar({...controller.getState(),preview:{item,appearance}});
    assert.equal((html.match(/class="avatar-wrap/g) || []).length, 1);
    assert.match(html, /card_trasferta\.png/);
    assert.match(html, /data-cosmetic-preview/);
    assert.equal((html.match(/Always away/g) || []).length, 2);
    assert.doesNotMatch(html, /Sempre in trasferta/);
  } finally { setLanguage('it'); cleanup(); }
});

test('final minute collection and new slot items survive try-on parsing', () => {
  const pieces = (catalogue.items.find(i => i.id === 'pacchetto_ultimo_minuto')!.grants || [])
    .map(id => catalogue.items.find(i => i.id === id)!);
  const bundle = {...catalogue.items.find(i => i.id === 'pacchetto_ultimo_minuto')!, contents: pieces} as unknown as ShopCosmeticItem;
  const appearance = createPreviewAppearance({}, bundle, 'en');
  assert.equal(appearance.theme?.accent, '#ff824e');
  assert.ok(appearance.theme?.pattern);
  assert.ok(appearance.frame?.ring);
  assert.equal(appearance.title?.label, '90th minute');
  assert.equal(appearance.badge, '🏁');
  assert.equal(appearance.squares?.correct, '✦');
  const number = catalogue.items.find(i => i.id === 'maglia_novanta')! as unknown as ShopCosmeticItem;
  const celebration = catalogue.items.find(i => i.id === 'festa_onda_stadio')! as unknown as ShopCosmeticItem;
  assert.equal(createPreviewAppearance({}, number).number, '90');
  assert.equal(createPreviewAppearance({}, celebration).celebration, 'stadium_wave');
});

const NEW_COLLECTIONS = ['pacchetto_aurora', 'pacchetto_curva', 'pacchetto_arcade', 'pacchetto_hanami', 'pacchetto_spiaggia', 'pacchetto_galassia', 'pacchetto_temporale'];

test('animated collections survive try-on parsing with their motion, pieces and extras', () => {
  for (const id of NEW_COLLECTIONS) {
    const raw = catalogue.items.find(i => i.id === id)!;
    const pieces = (raw.grants || []).map(g => catalogue.items.find(i => i.id === g)!);
    const appearance = createPreviewAppearance({}, { ...raw, contents: pieces } as unknown as ShopCosmeticItem, 'en');
    assert.ok(appearance.theme?.pattern, `${id}: pattern`);
    assert.ok(appearance.theme?.motion, `${id}: theme motion`);
    assert.ok(appearance.frame?.ring && appearance.frame.motion, `${id}: animated ring`);
    assert.ok(appearance.title?.label && appearance.badge, `${id}: identity`);
    for (const piece of pieces) {
      const style = piece.style as unknown as Record<string, string>;
      if (piece.kind === 'celebration') assert.equal(appearance.celebration, style.effect, `${id}: celebration`);
      if (piece.kind === 'card') assert.equal(appearance.card?.finish, style.finish, `${id}: card`);
    }
  }
});

test('theme motion becomes one reviewed animation token; unknown motion is ignored', async () => {
  const { skinTokens } = await import('../../webapp/src/appearance');
  const galaxy = catalogue.items.find(i => i.id === 'galassia')!.style as Record<string, unknown>;
  assert.match(skinTokens(parseResolvedAppearance({ theme: galaxy }))['--skin-motion'] || '', /^skin-twinkle /);
  for (const motion of ['spin 1s infinite', 'url(x)', 'sway; color:red', 42]) {
    const parsed = parseResolvedAppearance({ theme: { ...galaxy, motion }, frame: { ring: '', motion } });
    assert.equal(parsed.theme?.motion, undefined);
    assert.equal(parsed.frame?.motion, undefined);
    assert.equal(skinTokens(parsed)['--skin-motion'], undefined);
  }
});

test('frame flourishes render as a bounded data attribute, never as free CSS', () => {
  const ring = catalogue.items.find(i => i.id === 'cornice_pixel')!.style as unknown as Record<string, string>;
  const html = renderAvatar({ name: 'M', ringStyle: `background:${ring.ring}`, ringMotion: 'orbit' });
  assert.match(html, /class="ring" data-motion="orbit"/);
  assert.doesNotMatch(renderAvatar({ name: 'M', ringStyle: 'background:red', ringMotion: 'spin" onload="x' }), /data-motion|onload/);
});

test('new celebrations run to completion without throwing and clean up their canvas', async () => {
  const { celebrate } = await import('../../webapp/src/features/daily/celebrate');
  const { cleanup } = setupGlobalDom();
  try {
    window.matchMedia = (() => ({ matches: false })) as unknown as typeof window.matchMedia;
    for (const effect of ['petals', 'pixels', 'comets', 'bubbles', 'flares', 'lightning', 'bounce']) {
      assert.ok(parseResolvedAppearance({ celebration: effect }).celebration, effect);
      assert.doesNotThrow(() => celebrate(effect), effect);
    }
  } finally { cleanup(); }
});
