import { test } from "node:test";
import assert from "node:assert/strict";
import {
  escapeHtml,
  initials,
  weekNumber,
  squares,
  histogram,
  cabinetCounts,
  mergeProfile,
} from "../../webapp/src/utils";

test("escapeHtml escapes HTML entities correctly", () => {
  assert.equal(
    escapeHtml('<img src=x onerror="alert(1)">'),
    "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;"
  );
  assert.equal(escapeHtml(null), "");
  assert.equal(escapeHtml(undefined), "");
  assert.equal(escapeHtml("a&b's"), "a&amp;b&#39;s");
});

test("initials handles names, empty strings, and whitespace", () => {
  assert.equal(initials(" Anna  Rossi Bianchi "), "AR");
  assert.equal(initials("Marco"), "M");
  assert.equal(initials(" "), "?");
  assert.equal(initials(null), "?");
  assert.equal(initials(undefined), "?");
});

test("weekNumber extracts week from ISO week string", () => {
  assert.equal(weekNumber("2026-W37"), "37");
  assert.equal(weekNumber(""), "");
  assert.equal(weekNumber(null), "");
});

const SQUARES_SYMBOLS = { correct: "V", wrong: "X", unused: "_" };

test("squares calculates attempts without charging wrong attempts on correct guess", () => {
  assert.equal(squares(1, 3, true, SQUARES_SYMBOLS), "V__");
  assert.equal(squares(3, 3, true, SQUARES_SYMBOLS), "XXV");
  assert.equal(squares(3, 3, false, SQUARES_SYMBOLS), "XXX");
  assert.equal(squares(0, 3, false, SQUARES_SYMBOLS), "___");
  assert.equal(squares(5, 3, true, SQUARES_SYMBOLS), "XXXXV");
});

test("histogram calculates percentage width and marks highest bar", () => {
  const chart = histogram([
    { attempts: 1, count: 1 },
    { attempts: 2, count: 10 },
    { attempts: 3, count: 0 },
  ]);
  assert.equal(chart.played, 11);
  assert.deepEqual(
    chart.rows.map((r) => r.width),
    [10, 100, 8]
  );
  assert.deepEqual(
    chart.rows.map((r) => r.best),
    [false, true, false]
  );
});

test("histogram handles empty distribution gracefully", () => {
  const empty = histogram([{ attempts: 1, count: 0 }, { attempts: 2, count: 0 }]);
  assert.equal(empty.played, 0);
  assert.deepEqual(
    empty.rows.map((r) => r.best),
    [false, false]
  );
  assert.equal(histogram(undefined).played, 0);
  assert.deepEqual(histogram(null).rows, []);
});

test("cabinetCounts categorizes trophies into 1st, 2nd, 3rd podium positions", () => {
  const trophies = [
    { position: 1 },
    { position: 3 },
    { position: 3 },
    { position: 9 },
  ];
  assert.deepEqual(cabinetCounts(trophies), [1, 0, 2]);
  assert.deepEqual(cabinetCounts(undefined), [0, 0, 0]);
});

test("mergeProfile merges state without mutating previous state in lightweight mode", () => {
  const previous = { leaderboard: [1], today: { solved: false } };
  const incoming = { today: { solved: true } };
  const merged = mergeProfile(previous, incoming, true);
  assert.deepEqual(merged, { leaderboard: [1], today: { solved: true } });
  assert.equal(previous.today.solved, false);
  assert.deepEqual(mergeProfile(previous, incoming, false), incoming);
});
