import { test } from 'node:test';
import assert from 'node:assert/strict';
import { renderHeader } from '../../webapp/src/components/Header';
import { renderPrototype } from '../../webapp/src/prototypes/screens';
import { setLanguage } from '../../webapp/src/i18n';

// Terms and privacy must be reachable from every screen (the header menu), not only the Shop.
test('header menu links the terms of service and the privacy policy in the user language', () => {
  setLanguage('en');
  const html = renderHeader();
  assert.match(html, /href="\/terms\?lang=en"[^>]*>.*Terms of service<\/a>/);
  assert.match(html, /href="\/privacy\?lang=en"[^>]*>.*Privacy policy<\/a>/);
  setLanguage('it');
});

test('refunds and delete-my-data pages link their legal document', () => {
  setLanguage('es');
  assert.match(renderPrototype('refunds'), /href="\/terms\?lang=es#refunds"/);
  assert.match(renderPrototype('privacy'), /href="\/privacy\?lang=es"/);
  setLanguage('it');
});

test('support pages follow the user language instead of always showing Italian', () => {
  setLanguage('en');
  assert.match(renderPrototype('reports'), /What to include/);
  assert.match(renderPrototype('refunds'), /Ask for support/);
  assert.match(renderPrototype('privacy'), /Manage your data/);
  assert.doesNotMatch(renderPrototype('privacy'), /Gestisci i tuoi dati/);
  setLanguage('it');
});
