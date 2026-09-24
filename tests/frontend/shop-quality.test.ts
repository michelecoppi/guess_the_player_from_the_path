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
    for (const key of ['ring', 'pattern', 'formation', 'tactics', 'finish']) {
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
