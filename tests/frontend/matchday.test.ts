import test from 'node:test';
import assert from 'node:assert/strict';
import { renderDailyPage } from '../../webapp/src/pages/DailyPage';
import { renderProfileView } from '../../webapp/src/features/profile/views';
import { renderHubView } from '../../webapp/src/features/arena/views';
import { dailyFixture } from '../../webapp/src/prototypes/daily-fixtures';
import { profileFixture, arenaFixture } from '../../webapp/src/prototypes/product-fixtures';
import { createTestDom } from './helpers/dom';
import { setLanguage } from '../../webapp/src/i18n';

test('match report uses actual awards, escapes revealed names and preserves result actions', () => {
  const state = dailyFixture('correct');
  state.feedback = {status:'correct', answer:'<Player>', points_awarded:0, attempts_used:3, share:{text:'result',url:'https://t.me/share/url'}};
  const dom = createTestDom(renderDailyPage(state));
  try {
    const report = dom.container.querySelector('.match-report')!;
    assert.equal(report.querySelector('.report-player')?.textContent, '<Player>');
    assert.equal(report.querySelector('Player'), null);
    assert.equal(report.querySelector('.report-stats strong')?.textContent, '0');
    assert.match(report.textContent!, /3 \/ 5/);
    assert.ok(report.querySelector('#share'));
    assert.ok(report.querySelector('#show-card'));
    assert.equal(dom.container.querySelector('#answer'), null);
  } finally { dom.cleanup(); }
});

test('reopened completion never invents awarded points or a name; losses show their answer', () => {
  const state = dailyFixture('completed');
  let dom = createTestDom(renderDailyPage(state));
  try {
    assert.equal(dom.container.querySelector('.report-player'), null);
    assert.equal(dom.container.querySelectorAll('.report-stats strong').length, 1);
    assert.ok(dom.container.querySelector('#show-card'));
  } finally { dom.cleanup(); }
  state.challenge!.solved = false;
  state.challenge!.attempts_left = 0;
  state.feedback = {status:'wrong',attempts_left:0,attempts_used:5,answer:'Andrea Pirlo'};
  dom = createTestDom(renderDailyPage(state));
  try { assert.equal(dom.container.querySelector('.match-report.no .report-player')?.textContent, 'Andrea Pirlo'); }
  finally { dom.cleanup(); }
});

test('profile keeps secondary statistics accessible in every language', () => {
  for (const lang of ['it','en','es'] as const) {
    setLanguage(lang);
    const dom = createTestDom(renderProfileView(profileFixture()));
    try {
      assert.equal(dom.container.querySelectorAll('.primary-stats .tile').length, 3);
      assert.equal(dom.container.querySelectorAll('.secondary-stats .tile').length, 4);
      assert.ok(dom.container.querySelector('.secondary-stats summary')?.textContent);
    } finally { dom.cleanup(); }
  }
  setLanguage('it');
});

test('Arena highlights only an unfinished duel with an opponent, preserving navigation', () => {
  const state = arenaFixture();
  let dom = createTestDom(renderHubView(state));
  try { assert.equal(dom.container.querySelector('.active-duel')?.getAttribute('data-arena-duel'), 'review-duel'); }
  finally { dom.cleanup(); }
  state.data!.open![0]!.complete = true;
  dom = createTestDom(renderHubView(state));
  try {
    assert.equal(dom.container.querySelector('.active-duel'), null);
    assert.equal(dom.container.querySelectorAll('.mode-entry').length, 5);
  } finally { dom.cleanup(); }
});
