import { test } from "node:test";
import assert from "node:assert/strict";
import { App } from "../../webapp/src/app/App";
import {
  hasPendingEvent,
  hoursLeftToday,
  renderEventNext,
  renderEventSpotlight,
  spotlightEvent,
  timeLeftLabel,
} from "../../webapp/src/features/events/spotlight";
import type { EventCard } from "../../webapp/src/features/events/types";
import { setLanguage } from "../../webapp/src/i18n";
import { createTestDailyChallenge, setupGlobalDom, setupTestTelegram } from "./helpers";

function card(overrides: Partial<EventCard> = {}): EventCard {
  return {
    code: "carriera_al_buio",
    day: "2026-09-30",
    type: "blind_path",
    name: "Carriera al buio",
    description: "",
    dates: ["2026-09-28", "2026-09-29", "2026-09-30", "2026-10-01", "2026-10-02"],
    available: true,
    rules: "",
    player_name: "",
    min_correct: 1,
    career_path: [],
    image_url: null,
    points: 5,
    bonus_available: true,
    max_attempts: 3,
    progress: { attempts: 0, finished: false, solved: false, points: 0 },
    leaderboard: [],
    ...overrides,
  };
}

const solved = { attempts: 1, finished: true, solved: true, points: 6 };
// 19:00 in Rome (UTC+2 in summer time): five hours to midnight.
const EVENING = new Date("2026-09-30T17:00:00Z");

test("the spotlight prefers an event still to play and ignores unavailable ones", () => {
  const done = card({ code: "done", progress: solved });
  const todo = card({ code: "todo" });
  assert.equal(spotlightEvent([done, todo])?.code, "todo");
  assert.equal(spotlightEvent([done])?.code, "done");
  assert.equal(spotlightEvent([card({ available: false })]), null);
  assert.equal(spotlightEvent([]), null);
  assert.equal(hasPendingEvent([done]), false);
  assert.equal(hasPendingEvent([done, todo]), true);
  assert.equal(hasPendingEvent([card({ available: false })]), false);
});

test("time left counts today and shows hours to the Italian midnight on the last day", () => {
  setLanguage("it");
  assert.equal(hoursLeftToday(EVENING), 5);
  assert.equal(timeLeftLabel(card(), EVENING), "Ancora 3 giorni");
  assert.equal(timeLeftLabel(card({ day: "2026-10-02" }), EVENING), "Ultimo giorno · Finisce tra 5 h");
});

test("banner invites to play, lists the prizes and becomes a quiet recap once played", () => {
  setLanguage("it");
  const pending = renderEventSpotlight(card(), "daily_banner", EVENING);
  assert.match(pending, /class="event-spotlight is-pending"/);
  assert.match(pending, /data-event-open="carriera_al_buio"/);
  assert.match(pending, /data-event-entry="daily_banner"/);
  assert.match(pending, /Carriera al buio/);
  assert.match(pending, /5 pt oggi/);
  assert.match(pending, /\+1 al primo/);
  assert.match(pending, /🏆 podio/);
  assert.match(pending, /live-dot/);
  assert.match(pending, />Gioca</);

  const done = renderEventSpotlight(card({ progress: solved, bonus_available: false }), "arena_card", EVENING);
  assert.match(done, /is-done/);
  assert.match(done, /Risolto oggi · \+6 pt/);
  assert.doesNotMatch(done, /al primo/);
  assert.doesNotMatch(done, /live-dot/);
  assert.match(done, />Vedi</);

  const out = renderEventSpotlight(card({ progress: { attempts: 3, finished: true, solved: false, points: 0 } }), "daily_banner", EVENING);
  assert.match(out, /Tentativi finiti per oggi/);
  assert.equal(renderEventSpotlight(null, "daily_banner"), "");
});

test("banner text is translated", () => {
  setLanguage("en");
  assert.match(renderEventSpotlight(card(), "daily_banner", EVENING), /Live event[\s\S]*3 days left[\s\S]*Play/);
  setLanguage("es");
  assert.match(renderEventSpotlight(card(), "daily_banner", EVENING), /Evento en curso[\s\S]*Quedan 3 días[\s\S]*Jugar/);
  setLanguage("it");
});

/** A server with a Daily and a mutable list of events; records every /arena request. */
function fakeServer(events: EventCard[], today = createTestDailyChallenge()) {
  const state = { events, today };
  const arena: any[] = [];
  const original = globalThis.fetch;
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const body = init?.body ? JSON.parse(String(init.body)) : {};
    if (url.endsWith("/arena")) {
      arena.push(body);
      return new Response(JSON.stringify({ events: state.events, feedback: null }), { status: 200 });
    }
    return new Response(JSON.stringify({ user: { name: "Marco" }, today: state.today }), { status: 200 });
  }) as typeof fetch;
  return { state, arena, restore: () => { globalThis.fetch = original; } };
}

const settle = () => new Promise((resolve) => setTimeout(resolve, 20));

test("app: the Daily banner and the Arena dot appear after the Daily and open the event", async () => {
  setLanguage("it");
  const { container, cleanup } = setupGlobalDom();
  const { restore: restoreTg } = setupTestTelegram();
  const server = fakeServer([card()]);
  try {
    const app = new App(container);
    app.init();
    await app.whenFirstLoaded();
    await settle();

    const banner = container.querySelector<HTMLButtonElement>("#event-spotlight-slot [data-event-open]");
    assert.ok(banner, "the Daily shows the running event");
    const arenaTab = container.querySelector<HTMLElement>("#nav-tab-arena");
    assert.ok(arenaTab?.classList.contains("has-alert"));
    assert.match(arenaTab?.getAttribute("aria-label") || "", /evento da giocare/);
    assert.equal(server.arena[0].entry, undefined, "the background load is not a visit");

    banner.click();
    await settle();
    assert.equal(app.getActiveTab(), "events");
    assert.equal(app.getEventsController().getState().selectedCode, "carriera_al_buio");
    assert.equal(server.arena.at(-1).entry, "daily_banner");

    // Played: the dot and the Daily banner go away; the Arena keeps the card as a recap.
    server.state.events = [card({ progress: solved })];
    await app.getEventsController().load();
    assert.equal(container.querySelector("#nav-tab-arena")?.classList.contains("has-alert"), false);
    app.setTab("play");
    await settle();
    assert.equal(container.querySelector("#event-spotlight-slot")?.innerHTML, "");
    app.setTab("arena");
    assert.ok(container.querySelector("#arena-event-slot .event-spotlight.is-done"));

    // Out of attempts counts as played too.
    server.state.events = [card({ progress: { attempts: 3, finished: true, solved: false, points: 0 } })];
    await app.getEventsController().load();
    app.setTab("play");
    assert.equal(container.querySelector("#event-spotlight-slot")?.innerHTML, "");
  } finally {
    server.restore();
    restoreTg();
    cleanup();
  }
});

test("app: the Arena hub highlights the event; the plain Events row is tracked as arena_list", async () => {
  setLanguage("it");
  const { container, cleanup } = setupGlobalDom();
  const { restore: restoreTg } = setupTestTelegram();
  const server = fakeServer([card()]);
  try {
    const app = new App(container);
    app.init();
    await app.whenFirstLoaded();
    await settle();
    app.setTab("arena");
    const hubCard = container.querySelector<HTMLButtonElement>("#arena-event-slot [data-event-open]");
    assert.ok(hubCard, "the hub shows the running event on top");
    assert.equal(hubCard.dataset.eventEntry, "arena_card");

    container.querySelector<HTMLButtonElement>('.arena-modes button[data-tab="events"]')?.click();
    await settle();
    assert.equal(app.getActiveTab(), "events");
    assert.equal(server.arena.at(-1).entry, "arena_list");
  } finally {
    server.restore();
    restoreTg();
    cleanup();
  }
});

test("app: no running event means no banner, no card and no dot", async () => {
  const { container, cleanup } = setupGlobalDom();
  const { restore: restoreTg } = setupTestTelegram();
  const server = fakeServer([]);
  try {
    const app = new App(container);
    app.init();
    await app.whenFirstLoaded();
    await settle();
    assert.equal(container.querySelector("#event-spotlight-slot")?.innerHTML, "");
    assert.equal(container.querySelector("#nav-tab-arena")?.classList.contains("has-alert"), false);
    app.setTab("arena");
    assert.equal(container.querySelector("#arena-event-slot")?.innerHTML, "");
  } finally {
    server.restore();
    restoreTg();
    cleanup();
  }
});

// ---------------------------------------------------------------------------
// #252: "up next" in the Daily's final report
// ---------------------------------------------------------------------------

test("#252 the report invitation names the event, time left and prizes, only while it is to play", () => {
  setLanguage("it");
  const html = renderEventNext(card(), EVENING);
  assert.match(html, /class="event-next"/);
  assert.match(html, /data-event-entry="daily_result"/);
  assert.match(html, /Non è finita qui/);
  assert.match(html, /Gioca l&#39;evento Carriera al buio/);
  assert.match(html, /Ancora 3 giorni[\s\S]*5 pt oggi/);
  assert.equal(renderEventNext(card({ progress: solved })), "");
  assert.equal(renderEventNext(card({ available: false })), "");
  assert.equal(renderEventNext(null), "");
  setLanguage("en");
  assert.match(renderEventNext(card(), EVENING), /Not done yet[\s\S]*Play the Carriera al buio event/);
  setLanguage("it");
});

const finishedDaily = createTestDailyChallenge({ solved: true, attempts_used: 2, attempts_left: 3 });

test("app #252: a finished Daily moves the invitation from the top banner into the report", async () => {
  setLanguage("it");
  const { container, cleanup } = setupGlobalDom();
  const { restore: restoreTg } = setupTestTelegram();
  const server = fakeServer([card()], finishedDaily);
  try {
    const app = new App(container);
    app.init();
    await app.whenFirstLoaded();
    await settle();
    assert.equal(container.querySelector("#event-spotlight-slot"), null, "no top banner once the Daily is over");
    const invite = container.querySelector<HTMLButtonElement>(".match-report #daily-next-event-slot .event-next");
    assert.ok(invite, "the final report invites to the event");
    invite.click();
    await settle();
    assert.equal(app.getActiveTab(), "events");
    assert.equal(app.getEventsController().getState().selectedCode, "carriera_al_buio");
    assert.equal(server.arena.at(-1).entry, "daily_result");
  } finally {
    server.restore();
    restoreTg();
    cleanup();
  }
});

test("app #252: no invitation in the report when today's event is already played", async () => {
  const { container, cleanup } = setupGlobalDom();
  const { restore: restoreTg } = setupTestTelegram();
  const server = fakeServer([card({ progress: solved })], finishedDaily);
  try {
    const app = new App(container);
    app.init();
    await app.whenFirstLoaded();
    await settle();
    assert.ok(container.querySelector(".match-report"));
    assert.equal(container.querySelector("#daily-next-event-slot")?.innerHTML, "");
  } finally {
    server.restore();
    restoreTg();
    cleanup();
  }
});
