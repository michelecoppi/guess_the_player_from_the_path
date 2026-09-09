const { test } = require("node:test");
const assert = require("node:assert/strict");
const { escapeHtml, initials, mergeProfile, squares, histogram,
        cabinetCounts, languageFromCode, weekNumber } = require("../webapp/client.js");
test("untrusted names are escaped as text", () => {
  assert.equal(escapeHtml('<img src=x onerror="alert(1)">'), '&lt;img src=x onerror=&quot;alert(1)&quot;&gt;');
  assert.equal(escapeHtml(null), "");
  assert.equal(escapeHtml("a&b's"), "a&amp;b&#39;s");
});
test("initials handle empty names and whitespace", () => {
  assert.equal(initials(" Anna  Rossi Bianchi "), "AR");
  assert.equal(initials(" "), "?");
  assert.equal(initials(null), "?");
});
test("light profile preserves social data, replaces gameplay state without mutation", () => {
  const previous = { leaderboard: [1], leagues: [2], today: { solved: false, hints: [1] } };
  const incoming = { today: { solved: true } };
  const merged = mergeProfile(previous, incoming, true);
  assert.deepEqual(merged, { leaderboard: [1], leagues: [2], today: { solved: true } });
  assert.equal(previous.today.solved, false);
  assert.deepEqual(mergeProfile(previous, incoming, false), incoming);
});

const SQUARES = { correct: "V", wrong: "X", unused: "_" };
test("result squares do not charge a wrong attempt to whoever guessed", () => {
  assert.equal(squares(1, 3, true, SQUARES), "V__");
  assert.equal(squares(3, 3, true, SQUARES), "XXV");
  assert.equal(squares(3, 3, false, SQUARES), "XXX");
  assert.equal(squares(0, 3, false, SQUARES), "___");
});
test("result squares never overflow the row", () => {
  assert.equal(squares(5, 3, false, SQUARES).length, 5);
  assert.equal(squares(5, 3, true, SQUARES), "XXXXV");
  assert.equal(squares(1, 1, true, SQUARES), "V");
});
test("histogram scales on the tallest bar and marks it", () => {
  const chart = histogram([
    { attempts: 1, count: 1 }, { attempts: 2, count: 10 }, { attempts: 3, count: 0 },
  ]);
  assert.equal(chart.played, 11);
  assert.deepEqual(chart.rows.map(r => r.width), [10, 100, 8]);
  assert.deepEqual(chart.rows.map(r => r.best), [false, true, false]);
});
test("histogram of someone who never played has no bar to mark", () => {
  const empty = histogram([{ attempts: 1, count: 0 }, { attempts: 2, count: 0 }]);
  assert.equal(empty.played, 0);
  assert.deepEqual(empty.rows.map(r => r.best), [false, false]);
  assert.equal(histogram(undefined).played, 0);
  assert.deepEqual(histogram(null).rows, []);
});
test("cabinet counts trophies by podium position", () => {
  const all = [{ position: 1 }, { position: 3 }, { position: 3 }, { position: 9 }];
  assert.deepEqual(cabinetCounts(all), [1, 0, 2]);
  assert.deepEqual(cabinetCounts(undefined), [0, 0, 0]);
});
test("client language follows the same rule as the server", () => {
  assert.equal(languageFromCode("es-MX"), "es");
  assert.equal(languageFromCode("IT"), "it");
  assert.equal(languageFromCode("pt-BR"), "en");
  assert.equal(languageFromCode(undefined), "en");
  assert.equal(languageFromCode(""), "en");
});
test("showcase week survives a missing or odd identifier", () => {
  assert.equal(weekNumber("2026-W37"), "37");
  assert.equal(weekNumber(""), "");
  assert.equal(weekNumber(undefined), "");
});

/*
  Parita' fra le lingue delle stringhe della mini app.

  E' il gemello di tests/test_i18n_keys.py, che fa lo stesso controllo sui messaggi del bot.
  Serve perche' una chiave che manca in una lingua non rompe niente: l'interfaccia scrive
  "undefined" al posto della parola e va avanti, quindi il difetto arriva all'utente senza
  passare da nessun errore.
*/
const strings = require("../webapp/strings.js");

function flatten(value, prefix = "") {
  const keys = [];
  for (const [key, inner] of Object.entries(value)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (inner && typeof inner === "object" && !Array.isArray(inner)) keys.push(...flatten(inner, path));
    else keys.push(path);
  }
  return keys.sort();
}

for (const [name, table] of Object.entries(strings)) {
  test(`${name}: every language has exactly the same keys`, () => {
    const reference = flatten(table.it);
    assert.ok(reference.length > 0, `${name}.it is empty`);
    for (const lang of ["es", "en"]) {
      assert.deepStrictEqual(flatten(table[lang]), reference, `${name}.${lang} diverges from ${name}.it`);
    }
  });

  test(`${name}: no language is left with an untranslated placeholder`, () => {
    for (const lang of Object.keys(table)) {
      for (const [path, text] of Object.entries(table[lang])) {
        if (typeof text === "string") assert.ok(text.trim().length > 0, `${name}.${lang}.${path} is empty`);
      }
    }
  });

  test(`${name}: the same {placeholders} appear in all three languages`, () => {
    // Un {n} dimenticato in una traduzione lascia la parentesi graffa a schermo: il testo
    // arriva all'utente cosi' com'e', senza che niente vada in errore.
    const placeholders = text => (String(text).match(/\{\w+\}/g) || []).sort().join(",");
    const walk = (obj, prefix = "") => Object.entries(obj).reduce((acc, [key, value]) => {
      const path = prefix ? `${prefix}.${key}` : key;
      if (value && typeof value === "object") Object.assign(acc, walk(value, path));
      else acc[path] = placeholders(value);
      return acc;
    }, {});
    const reference = walk(table.it);
    for (const lang of ["es", "en"]) {
      assert.deepStrictEqual(walk(table[lang]), reference, `${name}.${lang} does not use the same placeholders`);
    }
  });
}
