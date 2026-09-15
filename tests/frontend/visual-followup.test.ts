import { test } from 'node:test';
import assert from 'node:assert/strict';
import { setTimeout as delay } from 'node:timers/promises';
import type { ApiClient } from '../../webapp/src/api/client';
import { LeaderboardController } from '../../webapp/src/features/leaderboard/controller';
import { renderLeaderboardView, renderPublicProfileView } from '../../webapp/src/features/leaderboard/views';
import { renderStyleInventory } from '../../webapp/src/components/StyleInventory';
import { renderShopCell, renderPreviewBar } from '../../webapp/src/features/shop/views';
import { leaderboardFixture, shopFixture, profileFixture } from '../../webapp/src/prototypes/product-fixtures';
import { createPreviewAppearance } from '../../webapp/src/features/shop/preview';
import { appearanceFixtures } from '../../webapp/src/prototypes/appearance-fixtures';
import { setLanguage } from '../../webapp/src/i18n';
import type { ShopCosmeticItem } from '../../webapp/src/features/shop/types';

test('ranking search starts at two characters, debounces and discards stale responses', async () => {
  const calls: Array<{ query: string; resolve: (value: unknown) => void }> = [];
  const client = { post: (_url: string, body: {query: string}) => new Promise(resolve => calls.push({query: body.query, resolve})) } as unknown as ApiClient;
  const controller = new LeaderboardController(client);
  controller.setSearchQuery('L');
  await delay(280);
  assert.equal(calls.length, 0);
  controller.setSearchQuery('Lu');
  controller.setSearchQuery('Luc');
  await delay(280);
  assert.deepEqual(calls.map(c => c.query), ['Luc']);
  controller.setSearchQuery('Gi');
  await delay(280);
  calls[1]!.resolve({profiles: [{profile_id: 2, name: 'Giulia', points: 8}]});
  await delay(0);
  calls[0]!.resolve({profiles: [{profile_id: 1, name: 'Luca', points: 9}]});
  await delay(0);
  assert.equal(controller.getState().search?.results[0]?.name, 'Giulia');
  controller.setSearchQuery('G');
  assert.equal(controller.getState().search?.status, 'idle');
  assert.deepEqual(controller.getState().search?.results, []);
});

test('ranking search exposes errors and cancellation prevents pending requests', async () => {
  let requests = 0;
  const client = { post: async () => { requests++; throw new Error('offline'); } } as unknown as ApiClient;
  const controller = new LeaderboardController(client);
  controller.setSearchQuery('Lu');
  await delay(280);
  assert.equal(controller.getState().search?.status, 'error');
  controller.setSearchQuery('Gi');
  controller.cancelSearch();
  await delay(280);
  assert.equal(requests, 1);
  assert.equal(controller.getState().search?.status, 'idle');
});

test('Top 10 stays visible beside independent search results, including profiles outside ranking', () => {
  setLanguage('it');
  const state = leaderboardFixture();
  state.search = {query: 'Zoe', status: 'ready', results: [{profile_id: 99, name: 'Zoe <script>', points: 1}]};
  const html = renderLeaderboardView(state);
  assert.equal((html.match(/role="listitem"/g) || []).length, 10);
  assert.ok(html.includes('data-profile-id="99"'));
  assert.ok(html.includes('Zoe &lt;script&gt;'));
  state.globalLeaderboard = [];
  assert.ok(renderLeaderboardView(state).includes('id="leaderboard-search"'));
});

test('public outfit lists all eight categories and owned styles without equip actions', () => {
  const profile = profileFixture().profile!;
  const wardrobe = [{id: 'frame1', kind: 'frame', name: '<Capitano>'}];
  const html = renderPublicProfileView({profileId: 1, status: 'ready', data: {...profile, trophies: [], wearing: wardrobe, wardrobe}});
  assert.equal((html.match(/<dt>/g) || []).length, 8);
  assert.ok(html.includes('&lt;Capitano&gt;'));
  assert.ok(!html.includes('data-equip'));
  assert.ok(!html.includes('data-buy'));
  assert.ok(renderStyleInventory([], [], {}).includes('Nessuno stile'));
});

test('outfit marks customised slots and the collection omits free starter styles', () => {
  setLanguage('it');
  const wardrobe = [
    {id: 'basic-frame', kind: 'frame', name: 'Senza cornice', free: true},
    {id: 'captain', kind: 'frame', name: 'Capitano', free: false},
    {id: 'regista', kind: 'title', name: 'Regista', free: false},
  ];
  const html = renderStyleInventory([], wardrobe, {frame: 'captain', title: 'basic-title'});
  assert.ok(html.includes('1 su 8 personalizzati'));
  assert.equal((html.match(/class="outfit-slot is-basic"/g) || []).length, 7);
  const collection = html.slice(html.indexOf('<details'));
  assert.ok(!collection.includes('Senza cornice'));
  assert.match(collection, /class="style-chip is-worn">Capitano/);
  assert.match(collection, /class="style-chip">Regista/);
});

test('wardrobe honors non-equippable ownership and preview keeps identity and product separate', () => {
  const state = shopFixture();
  const frame = state.catalogue!.sections[0]!.items[1]!;
  assert.ok(!renderShopCell({...frame, owned:true, equippable:false}, state).includes('data-equip'));
  state.preview = {item: frame, appearance: createPreviewAppearance(appearanceFixtures.default, frame)};
  const html = renderPreviewBar(state);
  assert.ok(html.includes('class="preview-layout"'));
  assert.ok(html.includes('class="preview-product"'));
  state.lookMutation = 'wear';
  assert.match(renderPreviewBar(state), /data-equip="[^"]+" disabled/);
});

test('Shop try-on preview shows the wearer identity/avatar exactly once, not duplicated as product artwork (#90)', () => {
  const state = shopFixture();
  const frame = state.catalogue!.sections[0]!.items[1]!;
  assert.equal(frame.kind, 'frame');

  // The catalogue cell IS the item's own preview art — it legitimately renders one avatar.
  const cellHtml = renderShopCell(frame, state);
  assert.equal((cellHtml.match(/class="avatar-wrap/g) || []).length, 1);

  // The try-on bar already shows the wearer's identity once, with this item applied,
  // in its own "preview-person" panel — the product-detail panel must not repeat it.
  state.preview = { item: frame, appearance: createPreviewAppearance(appearanceFixtures.default, frame) };
  const previewHtml = renderPreviewBar(state);
  assert.equal(
    (previewHtml.match(/class="avatar-wrap/g) || []).length,
    1,
    'exactly one avatar (the identity panel) must render in the try-on bar',
  );
  assert.match(previewHtml, /class="preview-person"[\s\S]*class="avatar-wrap/, 'the single avatar belongs to preview-person');
  assert.doesNotMatch(
    previewHtml,
    /class="preview-item-detail"[\s\S]*class="avatar-wrap/,
    'the product-detail panel must not render its own avatar',
  );

  // Appearance slots stay visible without the avatar: the ring itself is still applied
  // to the one identity avatar that remains.
  const ringStyle = String(frame.style.ring);
  assert.match(previewHtml, new RegExp(`class="ring[^"]*" style="background:${ringStyle.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}"`));
});

test('Shop try-on preview for a bundle keeps its contents preview but drops the duplicated identity (#90)', () => {
  const bundle: ShopCosmeticItem = {
    id: 'pack_review',
    kind: 'bundle',
    name: 'Collezione di revisione',
    description: 'Un pacchetto per la prova.',
    price: 80,
    full_price: 100,
    missing: [],
    achievement: null,
    progress: 0,
    style: {},
    grants: ['tema_review', 'cornice_review'],
    owned: false,
    equipped: false,
    free: false,
    featured: false,
    equippable: true,
    rarity: 'collector',
    completes: [],
    trophy: null,
    welcome: false,
    contents: [
      { id: 'tema_review', kind: 'theme', name: 'Tema di revisione', description: '', price: 0, full_price: 0, missing: [], achievement: null, progress: 0, style: { bg: '#0a131e', pattern: 'none' }, grants: [], owned: false, equipped: false, free: false, featured: false, equippable: true, rarity: 'collector', completes: [], trophy: null, welcome: false },
      { id: 'cornice_review', kind: 'frame', name: 'Cornice di revisione', description: '', price: 0, full_price: 0, missing: [], achievement: null, progress: 0, style: { ring: '#123456' }, grants: [], owned: false, equipped: false, free: false, featured: false, equippable: true, rarity: 'collector', completes: [], trophy: null, welcome: false },
      { id: 'stella_review', kind: 'badge', name: 'Distintivo di revisione', description: '', price: 0, full_price: 0, missing: [], achievement: null, progress: 0, style: { emoji: '⭐' }, grants: [], owned: false, equipped: false, free: false, featured: false, equippable: true, rarity: 'collector', completes: [], trophy: null, welcome: false },
    ],
  };

  const state = shopFixture();

  // Catalogue cell still shows the bundle's own single avatar preview.
  const cellHtml = renderShopCell(bundle, state);
  assert.equal((cellHtml.match(/class="avatar-wrap/g) || []).length, 1);

  state.preview = { item: bundle, appearance: createPreviewAppearance(appearanceFixtures.default, bundle) };
  const previewHtml = renderPreviewBar(state);
  assert.equal(
    (previewHtml.match(/class="avatar-wrap/g) || []).length,
    1,
    'a bundle try-on must still show exactly one avatar (the identity panel)',
  );
  assert.doesNotMatch(previewHtml, /class="preview-item-detail"[\s\S]*class="avatar-wrap/);
  // Bundle contents preview (badge glyph) still renders in the product-detail panel.
  assert.match(previewHtml, /class="preview-item-detail"[\s\S]*⭐/);
});
