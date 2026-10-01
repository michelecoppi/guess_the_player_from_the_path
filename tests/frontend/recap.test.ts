import { test } from "node:test";
import assert from "node:assert/strict";
import { setLanguage } from "../../webapp/src/i18n";
import { bindRecapEntries, recapCalendar, renderRecapBannerSlot } from "../../webapp/src/features/recap/entry";
import { buildSlides } from "../../webapp/src/features/recap/story";
import { monthName, rs } from "../../webapp/src/features/recap/strings";
import type { MonthlyRecap } from "../../webapp/src/features/recap/types";
import { captureFetchRequests, setupGlobalDom } from "./helpers";

const FULL: MonthlyRecap = {
  month: "2026-09",
  available: true,
  played: 24,
  days: 30,
  solved: 19,
  calendar: Array.from({ length: 30 }, (_, i) => (i % 5 === 0 ? "skip" : i % 7 === 0 ? "lost" : "won")),
  attempts: [9, 6, 4],
  best_streak: 11,
  style: { key: "sniper", value: 9 },
  gem: { day: "2026-09-14", rate: 6, attempts: 2, name: "Jari Litmanen",
    path: Array.from({ length: 10 }, (_, i) => ({ team: `Club ${i}`, start_year: 1990 + i, end_year: 1991 + i })) },
  lucky_club: { team: "Juventus", count: 7, players: ["Del Piero", "Trezeguet", "Vidal"] },
  better_than: 82,
  firsts: 3,
};

test("a full recap has every slide, ending with the shareable card", () => {
  setLanguage("it");
  const slides = buildSlides(FULL, "Anna");
  assert.equal(slides.length, 9);
  assert.match(slides[0].html, /Anna/);
  assert.match(slides[0].html, /settembre/);
  assert.match(slides[4].html, /Jari Litmanen/);
  assert.match(slides[5].html, /Juventus/);
  assert.match(slides[6].html, /Il Cecchino/);
  assert.match(slides[7].html, /data-count="82"/);
  assert.match(slides[8].html, /TOP 18%/);
  assert.equal(slides[8].duration, Number.POSITIVE_INFINITY);
});

test("slides without data are skipped, not shown empty", () => {
  setLanguage("it");
  const lean: MonthlyRecap = { ...FULL, gem: undefined, lucky_club: undefined, better_than: undefined, firsts: undefined, best_streak: 1 };
  const slides = buildSlides(lean, "Anna");
  assert.equal(slides.length, 5);
  assert.doesNotMatch(slides.map((s) => s.html).join(""), /Litmanen|Juventus|TOP /);
});

test("a long career is shortened to its start and its end", () => {
  setLanguage("it");
  const gem = buildSlides(FULL, "Anna")[4].html;
  assert.match(gem, /Club 0/);
  assert.match(gem, /Club 9/);
  assert.doesNotMatch(gem, /Club 5/);
  assert.match(gem, /recap-path-gap/);
});

test("names are escaped", () => {
  setLanguage("it");
  const slides = buildSlides({ ...FULL, lucky_club: { team: "<b>x</b>", count: 2, players: [] } }, "<img>");
  const html = slides.map((s) => s.html).join("");
  assert.doesNotMatch(html, /<img>|<b>x<\/b>/);
});

test("the recap speaks the three languages", () => {
  setLanguage("es");
  assert.equal(monthName("2026-09"), "septiembre");
  assert.equal(rs("style.sniper"), "El Francotirador");
  setLanguage("en");
  assert.equal(rs("bannerTitle", { month: monthName("2026-09") }), "Your September is ready");
  setLanguage("it");
});

test("the final card wears the equipped card colours, title and number", () => {
  setLanguage("it");
  const look = { card: { paper: "#10112e", ink: "#fdf7ff", glow: "#ff9ce3", finish: "foil" }, title: "Al novantesimo", number: "10" };
  const final = buildSlides(FULL, "Anna", look).at(-1)!.html;
  assert.match(final, /--recap-paper:#10112e/);
  assert.match(final, /data-finish="foil"/);
  assert.match(final, /Al novantesimo/);
  assert.match(final, /<small>10<\/small>/);
});

test("invalid cosmetic colours never reach the style attribute", () => {
  setLanguage("it");
  const final = buildSlides(FULL, "Anna", { card: { paper: "red;background:url(x)" } }).at(-1)!.html;
  assert.doesNotMatch(final, /url\(x\)/);
});

test("the Daily asks for the recap only in the banner week, whatever today is (#281)", async () => {
  const { container, cleanup } = setupGlobalDom();
  const { requests, restore } = captureFetchRequests({ recap: { ...FULL, available: false } });
  try {
    container.innerHTML = renderRecapBannerSlot();
    bindRecapEntries(container);
    assert.equal(requests.length, 0, "setupGlobalDom pins a mid-month day");

    recapCalendar.today = () => new Date(2026, 9, 3, 12);
    bindRecapEntries(container);
    await new Promise((resolve) => setTimeout(resolve, 0));
    assert.deepEqual(requests.map((r) => r.url), ["/app/api/recap"]);
  } finally {
    restore();
    cleanup();
  }
});
