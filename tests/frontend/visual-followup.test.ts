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
