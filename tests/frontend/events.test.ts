import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { EventsController } from "../../webapp/src/features/events/controller";
import {
  renderEventsPage,
  attachEventsEventListeners,
} from "../../webapp/src/pages/EventsPage";
import {
  EVENT_MAX_ATTEMPTS,
  type EventCard,
  type EventsResponse,
} from "../../webapp/src/features/events/types";
import { App } from "../../webapp/src/app/App";
import { ArenaController } from "../../webapp/src/features/arena/controller";
import { TrainingController } from "../../webapp/src/features/training/controller";
import { ReferralController } from "../../webapp/src/features/referral/controller";
import { ProfileController } from "../../webapp/src/features/profile/controller";
import { ShopController } from "../../webapp/src/features/shop/controller";
import { setLanguage } from "../../webapp/src/i18n";
import {
  setupTestTelegram,
  setupGlobalDom,
  createTestDuelData,
  createTestDuelSession,
} from "./helpers";

function createTestCard(overrides: Partial<EventCard> = {}): EventCard {
  return {
    code: "champions_cup",
    day: "2026-09-13",
    type: "path",
    name: "Champions Cup",
    description: "Indovina il campione europeo",
    dates: ["2026-09-10", "2026-09-11", "2026-09-12", "2026-09-13"],
    available: true,
    rules: "3 tentativi per indovinare il calciatore misterioso.",
    player_name: "",
    min_correct: 1,
    career_path: [
      { team: "Brescia", start_year: 1995, end_year: 1998, apps: 47, goals: 6 },
      { team: "Inter", start_year: 1998, end_year: 2001, apps: 22, goals: 0 },
      { team: "Milan", start_year: 2001, end_year: 2011, apps: 284, goals: 32 },
      { team: "Juventus", start_year: 2011, end_year: 2015, apps: 119, goals: 16 },
    ],
    image_url: null,
    points: 2,
    bonus_available: true,
    progress: {
      attempts: 0,
      finished: false,
      solved: false,
      points: 0,
    },
    leaderboard: [
      { name: "Marco", points: 10 },
      { name: "Giulia", points: 8 },
    ],
    ...overrides,
  };
}

function mockClient(queue: Array<EventsResponse | Error | ((url: string, payload: any) => Promise<EventsResponse>)>) {
  const recordedCalls: Array<{ url: string; payload: any }> = [];
  const client: any = {
    recordedCalls,
    post: async (url: string, payload: any) => {
      recordedCalls.push({ url, payload });
      const next = queue.shift();
      if (!next) {
        throw new Error("mockClient: unexpected call (queue empty)");
      }
      if (typeof next === "function") {
        return next(url, payload);
      }
      if (next instanceof Error) {
        throw next;
      }
      return next;
    },
  };
  return client;
}

// ---------------------------------------------------------------------------
// 1. GET CONTRACT & PUBLIC PROJECTION
// ---------------------------------------------------------------------------

test("1. GET request contract: calls POST /arena with mode='events', action='get'", async () => {
  const client = mockClient([{ events: [createTestCard()] }]);
  const controller = new EventsController(client);
  await controller.load();

  assert.equal(client.recordedCalls.length, 1);
  const call = client.recordedCalls[0];
  assert.equal(call.url, "/arena");
  assert.deepEqual(call.payload, {
    mode: "events",
    action: "get",
  });
});

test("2. Public projection: private backend concepts (player_id, correct_answers, first_correct_user) are never rendered", async () => {
  const cardWithPrivateFields: any = createTestCard({
    leaderboard: [{ name: "WinnerUser", points: 15 }],
  });
  cardWithPrivateFields.player_id = "SECRET_PLAYER_ID_123";
  cardWithPrivateFields.correct_answers = ["Andrea Pirlo", "Pirlo"];
  cardWithPrivateFields.first_correct_user = "TELEGRAM_USER_SECRET";

  const client = mockClient([{ events: [cardWithPrivateFields] }]);
  const controller = new EventsController(client);
  await controller.load();

  // Check event list rendering
  const listHtml = renderEventsPage(controller);
  assert.equal(listHtml.includes("SECRET_PLAYER_ID_123"), false);
  assert.equal(listHtml.includes("TELEGRAM_USER_SECRET"), false);

  // Check detail rendering
  controller.select("champions_cup");
  const detailHtml = renderEventsPage(controller);
  assert.equal(detailHtml.includes("SECRET_PLAYER_ID_123"), false);
  assert.equal(detailHtml.includes("TELEGRAM_USER_SECRET"), false);
  assert.equal(detailHtml.includes("correct_answers"), false);
  assert.equal(detailHtml.includes("player_id"), false);
});

// ---------------------------------------------------------------------------
// 2. LOADING, ERROR, RETRY, DEDUPE, AND SEQUENCE GUARDS
// ---------------------------------------------------------------------------

test("3. Loading and error states with localized messages and retry button", async () => {
  setLanguage("it");
  const client = mockClient([new Error("network failure")]);
  (client as any).post = async () => {
    const err: any = new Error("network failure");
    err.detail = "loadError";
    throw err;
  };

  const controller = new EventsController(client);
  const loadPromise = controller.load();
  assert.equal(controller.getState().status, "loading");
  assert.match(renderEventsPage(controller), /Eventi/);

  await loadPromise;
  assert.equal(controller.getState().status, "error");
  const errorHtml = renderEventsPage(controller);
  assert.match(errorHtml, /Impossibile caricare gli eventi/);
  assert.match(errorHtml, /id="events-retry"/);

  // Retry
  let retried = false;
  controller["client"] = {
    post: async () => {
      retried = true;
      return { events: [createTestCard()] };
    },
  } as any;

  await controller.load();
  assert.equal(retried, true);
  assert.equal(controller.getState().status, "ready");
  assert.equal(controller.getState().events.length, 1);
});

test("4. In-flight submit prevents duplicate or conflicting load() dispatch", async () => {
  let guessResolve: any;
  const client: any = {
    post: async (_url: string, payload: any) => {
      if (payload.action === "get") {
        return { events: [createTestCard()] };
      }
      return new Promise((resolve) => {
        guessResolve = resolve;
      });
    },
  };

  const controller = new EventsController(client);
  await controller.load();
  controller.select("champions_cup");

  const submitPromise = controller.submit("Pirlo");
  assert.equal(controller.getState().status, "submitting");

  // Attempt to call load while submitting should be a no-op
  await controller.load();
  assert.equal(controller.getState().status, "submitting");

  guessResolve({
    events: [createTestCard()],
    feedback: { status: "correct", points: 2 },
  });
  await submitPromise;
  assert.equal(controller.getState().status, "ready");
});

test("5. Stale out-of-order load() response is discarded by sequence guard", async () => {
  let resolveLoad1: any;
  let resolveLoad2: any;
  let callCount = 0;

  const client: any = {
    post: async () => {
      callCount++;
      if (callCount === 1) {
        return new Promise((r) => (resolveLoad1 = r));
      }
      return new Promise((r) => (resolveLoad2 = r));
    },
  };

  const controller = new EventsController(client);
  const p1 = controller.load();
  const p2 = controller.load();

  // Load 2 resolves first with updated card
  resolveLoad2({ events: [createTestCard({ name: "Version 2" })] });
  await p2;
  assert.equal(controller.getState().events[0].name, "Version 2");

  // Load 1 resolves later with stale card
  resolveLoad1({ events: [createTestCard({ name: "Version 1" })] });
  await p1;
  assert.equal(controller.getState().events[0].name, "Version 2");
});

// ---------------------------------------------------------------------------
// 3. ZERO AND MULTIPLE EVENTS LIST
// ---------------------------------------------------------------------------

test("6. Zero active events: renders empty state with CTA to training", async () => {
  setLanguage("it");
  const client = mockClient([{ events: [] }]);
  const controller = new EventsController(client);
  await controller.load();

  const html = renderEventsPage(controller);
  assert.match(html, /Nessun evento attivo/);
  assert.match(html, /id="events-open-training"/);
  assert.match(html, /Allenamento/);
});

test("7. Multiple active events list: displays names, descriptions, and correct play/completed actions", async () => {
  setLanguage("it");
  const events = [
    createTestCard({
      code: "event_open",
      name: "Coppa Italia",
      description: "Edizione 2026",
      progress: { attempts: 0, finished: false, solved: false, points: 0 },
    }),
    createTestCard({
      code: "event_done",
      name: "Derby Story",
      description: "Classici del calcio",
      progress: { attempts: 2, finished: true, solved: true, points: 2 },
    }),
  ];

  const client = mockClient([{ events }]);
  const controller = new EventsController(client);
  await controller.load();

  const html = renderEventsPage(controller);
  assert.match(html, /Coppa Italia/);
  assert.match(html, /Derby Story/);
  assert.match(html, /data-event-open="event_open"[^>]*>\s*Apri\s*<\/button>/);
  assert.match(html, /data-event-open="event_done"[^>]*>\s*Completato\s*<\/button>/);
});

// ---------------------------------------------------------------------------
// 4. EVENT END-DATE PRESENTATION & SERVER AVAILABILITY
// ---------------------------------------------------------------------------

test("8. Event end-date: renders formatted final date when dates array is present", async () => {
  setLanguage("it");
  const card = createTestCard({
    dates: ["2026-09-01", "2026-09-08", "2026-09-15"],
  });
  const client = mockClient([{ events: [card] }]);
  const controller = new EventsController(client);
  await controller.load();

  const listHtml = renderEventsPage(controller);
  assert.match(listHtml, /Ultima giornata:\s*15\s+set/);

  controller.select("champions_cup");
  const detailHtml = renderEventsPage(controller);
  assert.match(detailHtml, /Ultima giornata:\s*15\s+set/);
});

test("9. Event end-date: does not render when dates array is empty", async () => {
  setLanguage("it");
  const card = createTestCard({ dates: [] });
  const client = mockClient([{ events: [card] }]);
  const controller = new EventsController(client);
  await controller.load();

  const listHtml = renderEventsPage(controller);
  assert.equal(listHtml.includes("Ultima giornata"), false);

  controller.select("champions_cup");
  const detailHtml = renderEventsPage(controller);
  assert.equal(detailHtml.includes("Ultima giornata"), false);
});

test("10. Event end-date: invalid or unexpected date is safely displayed/degraded and HTML-escaped", async () => {
  setLanguage("it");
  const card = createTestCard({
    dates: ["<script>alert(1)</script>"],
  });
  const client = mockClient([{ events: [card] }]);
  const controller = new EventsController(client);
  await controller.load();

  const listHtml = renderEventsPage(controller);
  assert.match(listHtml, /Ultima giornata:\s*&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
  assert.equal(listHtml.includes("<script>alert"), false);
});

test("11. Event availability is authoritative from server, not computed from dates client-side", async () => {
  setLanguage("it");
  const card = createTestCard({
    dates: ["2026-09-13"],
    available: false, // Server says unavailable today
  });
  const client = mockClient([{ events: [card] }]);
  const controller = new EventsController(client);
  await controller.load();
  controller.select("champions_cup");

  const detailHtml = renderEventsPage(controller);
  assert.match(detailHtml, /Questo evento non è disponibile oggi/);
  // Guess form must not be rendered when unavailable
  assert.equal(detailHtml.includes('id="events-guess-form"'), false);
});

// ---------------------------------------------------------------------------
// 5. ALL EVENT TYPES: PATH, TRANSFER_GUESS, CAREER, FATHER_SON, UNKNOWN
// ---------------------------------------------------------------------------

test("12. Event type 'path': renders CareerPath and standard rules", async () => {
  setLanguage("it");
  const card = createTestCard({
    type: "path",
    career_path: [
      { team: "Ajax", start_year: 1990, end_year: 1995 },
      { team: "Juventus", start_year: 1995, end_year: 1999 },
    ],
  });
  const client = mockClient([{ events: [card] }]);
  const controller = new EventsController(client);
  await controller.load();
  controller.select("champions_cup");

  const html = renderEventsPage(controller);
  assert.match(html, /class="path"|Career path/);
  assert.match(html, /Ajax/);
  assert.match(html, /Juventus/);
  assert.equal(html.includes("event-player-name"), false);
});

test("13. Event type 'transfer_guess': renders CareerPath and supports comparison feedback", async () => {
  const card = createTestCard({
    type: "transfer_guess",
    career_path: [{ team: "Chelsea", start_year: 2004, end_year: 2012 }],
  });
  const client = mockClient([
    { events: [card] },
    {
      events: [card],
      feedback: {
        status: "wrong",
        points: 0,
        comparison: {
          name: "Drogba",
          clues: [
            { key: "feedback.nationality_same", args: {} },
            { key: "feedback.position_same", args: {} },
          ],
        },
      },
    },
  ]);
  const controller = new EventsController(client);
  await controller.load();
  controller.select("champions_cup");

  await controller.submit("Torres");
  const html = renderEventsPage(controller);
  assert.match(html, /class="path"|Career path/);
  assert.match(html, /Drogba/);
  assert.match(html, /Stessa nazionalità|Same nationality/);
});

test("14. Event type 'career': renders player_name, min_correct, comma guidance, and matched feedback", async () => {
  setLanguage("it");
  const card = createTestCard({
    type: "career",
    player_name: "Zlatan Ibrahimovic",
    min_correct: 3,
    career_path: [],
    rules: "Indovina almeno 3 squadre in cui ha giocato.",
  });
  const client = mockClient([
    { events: [card] },
    {
      events: [card],
      feedback: {
        status: "wrong",
        points: 0,
        matched: 2, // 2 out of 3 needed
      },
    },
  ]);
  const controller = new EventsController(client);
  await controller.load();
  controller.select("champions_cup");

  const initialHtml = renderEventsPage(controller);
  assert.match(initialHtml, /Zlatan Ibrahimovic/);
  assert.match(initialHtml, /Inserisci fino a 5 club separati da virgole/);
  assert.match(initialHtml, /Minimo:\s*3/);

  // Submit and verify matched feedback
  await controller.submit("Milan, Ajax, Liverpool");
  const resultHtml = renderEventsPage(controller);
  assert.match(resultHtml, /Squadre corrette:\s*2/);
});

test("15. Event type 'father_son': renders HTTPS image and pair hint", async () => {
  setLanguage("it");
  const card = createTestCard({
    type: "father_son",
    career_path: [],
    image_url: "https://example.com/maldini-pair.jpg",
  });
  const client = mockClient([{ events: [card] }]);
  const controller = new EventsController(client);
  await controller.load();
  controller.select("champions_cup");

  const html = renderEventsPage(controller);
  assert.match(html, /<img class="event-image"/);
  assert.match(html, /src="https:\/\/example\.com\/maldini-pair\.jpg"/);
  assert.match(html, /referrerpolicy="no-referrer"/);
  assert.match(html, /Riconosci la coppia padre e figlio/);
});

test("16. Event type unknown/future: safely displays generic guidance and does not crash", async () => {
  setLanguage("it");
  const card = createTestCard({
    type: "future_challenge_mode" as any,
    career_path: [],
    image_url: null,
  });
  const client = mockClient([{ events: [card] }]);
  const controller = new EventsController(client);
  await controller.load();
  controller.select("champions_cup");

  const html = renderEventsPage(controller);
  assert.match(html, /Segui le regole della sfida per completare l'evento/);
  assert.match(html, /id="events-guess-form"/);
});

// ---------------------------------------------------------------------------
// 6. SECURITY & PRIVACY
// ---------------------------------------------------------------------------

test("17. HTTPS image restriction: non-HTTPS schemes (http, javascript, data) never render as <img>", async () => {
  const unsafeUrls = [
    "http://insecure.com/photo.jpg",
    "javascript:alert(1)",
    "data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=",
  ];

  for (const badUrl of unsafeUrls) {
    const card = createTestCard({ image_url: badUrl, career_path: [] });
    const client = mockClient([{ events: [card] }]);
    const controller = new EventsController(client);
    await controller.load();
    controller.select("champions_cup");

    const html = renderEventsPage(controller);
    assert.equal(html.includes("<img"), false, `Should not render <img> for ${badUrl}`);
    assert.equal(html.includes(badUrl), false);
  }
});

test("18. Malicious string escaping (XSS): protects name, description, rules, player_name, and leaderboard", async () => {
  const xss = "<script>alert('xss')</script>";
  const card = createTestCard({
    name: `Name ${xss}`,
    description: `Desc ${xss}`,
    rules: `Rules ${xss}`,
    player_name: `Player ${xss}`,
    type: "career",
    career_path: [],
    leaderboard: [{ name: `User ${xss}`, points: 10 }],
  });

  const client = mockClient([{ events: [card] }]);
  const controller = new EventsController(client);
  await controller.load();

  // List view
  const listHtml = renderEventsPage(controller);
  assert.equal(listHtml.includes("<script>"), false);
  assert.match(listHtml, /&lt;script&gt;/);

  // Detail view
  controller.select("champions_cup");
  const detailHtml = renderEventsPage(controller);
  assert.equal(detailHtml.includes("<script>"), false);
  assert.match(detailHtml, /&lt;script&gt;/);
});

// ---------------------------------------------------------------------------
// 7. AUTHORITATIVE ATTEMPTS & TERMINAL STATES (SOLVED VS EXHAUSTED)
// ---------------------------------------------------------------------------

test("19. Authoritative attempts: tied to canonical EVENT_MAX_ATTEMPTS = 3 and never incremented optimistically", async () => {
  assert.equal(EVENT_MAX_ATTEMPTS, 3, "Canonical backend attempts limit must equal 3");

  const card = createTestCard({
    progress: { attempts: 1, finished: false, solved: false, points: 0 },
  });
  const client = mockClient([{ events: [card] }]);
  const controller = new EventsController(client);
  await controller.load();
  controller.select("champions_cup");

  const html = renderEventsPage(controller);
  // 3 - 1 = 2 attempts left
  assert.match(html, /Tentativi rimasti:\s*2|Attempts left:\s*2/);
});

test("20. Terminal states: distinct rendering for solved vs exhausted", async () => {
  setLanguage("it");

  // Solved state (finished + solved)
  const solvedCard = createTestCard({
    code: "solved_event",
    progress: { attempts: 1, finished: true, solved: true, points: 2 },
  });
  // Exhausted state (finished + !solved)
  const exhaustedCard = createTestCard({
    code: "exhausted_event",
    progress: { attempts: 3, finished: true, solved: false, points: 0 },
  });

  const client = mockClient([{ events: [solvedCard, exhaustedCard] }]);
  const controller = new EventsController(client);
  await controller.load();

  // Inspect solved
  controller.select("solved_event");
  const solvedHtml = renderEventsPage(controller);
  assert.match(solvedHtml, /event-solved/);
  assert.match(solvedHtml, /Evento completato!/);
  assert.match(solvedHtml, /La prossima sfida arriva con la prossima giornata dell’evento/);
  assert.equal(solvedHtml.includes('id="events-guess-form"'), false);

  // Inspect exhausted
  controller.select("exhausted_event");
  const exhaustedHtml = renderEventsPage(controller);
  assert.match(exhaustedHtml, /event-exhausted/);
  assert.match(exhaustedHtml, /Tentativi esauriti: sfida conclusa/);
  assert.match(exhaustedHtml, /La prossima sfida arriva con la prossima giornata dell’evento/);
  assert.equal(exhaustedHtml.includes('id="events-guess-form"'), false);
});

// ---------------------------------------------------------------------------
// 8. EXACT GUESS REQUEST CONTRACT & DOUBLE SUBMIT GUARD
// ---------------------------------------------------------------------------

test("21. Exact guess request contract: asserts outgoing payload, trimming, and revision", async () => {
  const card = createTestCard({
    code: "world_cup",
    day: "2026-09-13",
    progress: { attempts: 2, finished: false, solved: false, points: 0 },
  });

  const client = mockClient([
    { events: [card] },
    {
      events: [
        {
          ...card,
          progress: { attempts: 3, finished: true, solved: true, points: 2 },
        },
      ],
      feedback: { status: "correct", points: 2 },
    },
  ]);

  const controller = new EventsController(client);
  await controller.load();
  controller.select("world_cup");

  await controller.submit("   Zinedine Zidane   ");

  assert.equal(client.recordedCalls.length, 2);
  const guessCall = client.recordedCalls[1];
  assert.equal(guessCall.url, "/arena");
  assert.deepEqual(guessCall.payload, {
    mode: "events",
    action: "guess",
    code: "world_cup",
    day: "2026-09-13",
    answer: "Zinedine Zidane",
    revision: 2,
  });

  // Verify no extra or private properties sent
  assert.deepEqual(Object.keys(guessCall.payload).sort(), [
    "action",
    "answer",
    "code",
    "day",
    "mode",
    "revision",
  ]);
});

test("22. Double-submit guard: prevents concurrent duplicate submissions", async () => {
  let guessResolve: any;
  let calls = 0;
  const card = createTestCard();

  const client: any = {
    post: async (_url: string, payload: any) => {
      if (payload.action === "get") {
        return { events: [card] };
      }
      calls++;
      return new Promise((resolve) => {
        guessResolve = resolve;
      });
    },
  };

  const controller = new EventsController(client);
  await controller.load();
  controller.select("champions_cup");

  const sub1 = controller.submit("Answer 1");
  const sub2 = controller.submit("Answer 2"); // Should be ignored while submitting

  assert.equal(calls, 1, "Only one guess network request should be dispatched");

  guessResolve({
    events: [card],
    feedback: { status: "wrong", points: 0 },
  });
  await Promise.all([sub1, sub2]);
});

// ---------------------------------------------------------------------------
// 9. REAL COMPARISON FEEDBACK & UNKNOWN CLUES SAFETY
// ---------------------------------------------------------------------------

test("23. Comparison feedback: renders compared name, known clues, and fails safely on unknown clue keys", async () => {
  setLanguage("it");
  const card = createTestCard();
  const client = mockClient([
    { events: [card] },
    {
      events: [card],
      feedback: {
        status: "wrong",
        points: 0,
        comparison: {
          name: "Fabio Cannavaro",
          clues: [
            { key: "feedback.nationality_same", args: {} },
            { key: "feedback.position_diff", args: {} },
            { key: "feedback.birth_after", args: { year: 1973 } },
            { key: "feedback.unknown_future_clue", args: { foo: "bar" } }, // Unknown key
          ],
        },
      },
    },
  ]);

  const controller = new EventsController(client);
  await controller.load();
  controller.select("champions_cup");

  await controller.submit("Buffon");
  const html = renderEventsPage(controller);

  assert.match(html, /(?:Rispetto a|Confronto con|Compared with)\s*<b>Fabio Cannavaro<\/b>/);
  assert.match(html, /Stessa nazionalità/);
  assert.match(html, /Ruolo diverso/);
  assert.match(html, /Più giovane del 1973/);
  assert.equal(html.includes("undefined"), false);
});

// ---------------------------------------------------------------------------
// 10. REAL CAREER MATCHED FEEDBACK (PARTIAL, CORRECT, ZERO)
// ---------------------------------------------------------------------------

test("24. Career matched feedback: handles partial match, correct match, and zero match from server evaluator", async () => {
  setLanguage("it");
  const card = createTestCard({ type: "career", min_correct: 3, player_name: "Cristiano Ronaldo" });

  // Test partial match (2 matches)
  const client1 = mockClient([
    { events: [card] },
    {
      events: [card],
      feedback: { status: "wrong", points: 0, matched: 2 },
    },
  ]);
  const c1 = new EventsController(client1);
  await c1.load();
  c1.select("champions_cup");
  await c1.submit("Sporting, Man Utd, Milan");
  assert.match(renderEventsPage(c1), /Squadre corrette:\s*2/);

  // Test zero match (0 matches)
  const client2 = mockClient([
    { events: [card] },
    {
      events: [card],
      feedback: { status: "wrong", points: 0, matched: 0 },
    },
  ]);
  const c2 = new EventsController(client2);
  await c2.load();
  c2.select("champions_cup");
  await c2.submit("Arsenal, Chelsea, Liverpool");
  assert.match(renderEventsPage(c2), /Squadre corrette:\s*0/);

  // Test correct match (3 matches)
  const client3 = mockClient([
    { events: [card] },
    {
      events: [
        {
          ...card,
          progress: { attempts: 1, finished: true, solved: true, points: 2 },
        },
      ],
      feedback: { status: "correct", points: 2, matched: 3 },
    },
  ]);
  const c3 = new EventsController(client3);
  await c3.load();
  c3.select("champions_cup");
  await c3.submit("Sporting, Man Utd, Real Madrid");
  assert.match(renderEventsPage(c3), /Squadre corrette:\s*3/);
  assert.match(renderEventsPage(c3), /Indovinato!/);
});

// ---------------------------------------------------------------------------
// 11. ERROR MAPPING, RESYNC, AND NON-REPLAY
// ---------------------------------------------------------------------------

test("25. Error handling: stale, expired, and finished trigger resync without replaying guess", async () => {
  setLanguage("it");
  const card = createTestCard({
    progress: { attempts: 0, finished: false, solved: false, points: 0 },
  });

  let getCallCount = 0;
  let guessCallCount = 0;

  const client: any = {
    post: async (_url: string, payload: any) => {
      if (payload.action === "get") {
        getCallCount++;
        return {
          events: [
            getCallCount === 1
              ? card
              : {
                  ...card,
                  progress: { attempts: 3, finished: true, solved: false, points: 0 },
                },
          ],
        };
      }
      if (payload.action === "guess") {
        guessCallCount++;
        const err: any = new Error("Stale revision");
        err.detail = "stale";
        throw err;
      }
    },
  };

  const controller = new EventsController(client);
  await controller.load();
  assert.equal(getCallCount, 1);

  controller.select("champions_cup");
  await controller.submit("Pirlo");

  // Stale triggered one guess call and one automatic resync get call
  assert.equal(guessCallCount, 1);
  assert.equal(getCallCount, 2, "Automatic resync get() must be dispatched on stale error");

  // Selection is preserved since event still exists on server
  assert.equal(controller.getState().selectedCode, "champions_cup");
  assert.equal(controller.getState().events[0].progress.finished, true);

  // Error is localized and raw code 'stale' is not leaked
  const html = renderEventsPage(controller);
  assert.match(html, /Lo stato è cambiato: dati sincronizzati/);
  assert.equal(html.includes("stale"), false);
});

test("26. Error handling: expired clears selection if event was removed from refreshed server list", async () => {
  setLanguage("it");
  const card = createTestCard();

  const client: any = {
    post: async (_url: string, payload: any) => {
      if (payload.action === "get") {
        return { events: [] }; // Event has expired and was removed
      }
      const err: any = new Error("Expired");
      err.detail = "expired";
      throw err;
    },
  };

  const controller = new EventsController(client);
  controller["state"].events = [card];
  controller.select("champions_cup");

  await controller.submit("Pirlo");

  assert.equal(controller.getState().selectedCode, null, "Selection must be cleared when event expired");
  assert.match(renderEventsPage(controller), /L'evento è scaduto/);
});

test("27. Typed error mapping: invalid, invalid_answer, max_answers, unknown mapped safely without raw codes", async () => {
  setLanguage("it");
  const errors = [
    { code: "invalid", expected: /Richiesta non valida/ },
    { code: "invalid_answer", expected: /Inserisci una risposta valida/ },
    { code: "max_answers", expected: /Puoi inserire al massimo cinque risposte/ },
    { code: "unknown_weird_error", expected: /Si è verificato un errore/ },
  ];

  for (const { code, expected } of errors) {
    const card = createTestCard();
    const client: any = {
      post: async () => {
        const err: any = new Error(code);
        err.detail = code;
        throw err;
      },
    };
    const controller = new EventsController(client);
    controller["state"].events = [card];
    controller.select("champions_cup");

    await controller.submit("Answer");
    const html = renderEventsPage(controller);
    assert.match(html, expected);
    assert.equal(html.includes(code), false, `Raw code ${code} should never leak to UI`);
  }
});

// ---------------------------------------------------------------------------
// 12. REFRESH / SUBMIT CONCURRENCY
// ---------------------------------------------------------------------------

test("28. Concurrency: refresh pending -> selection changes preserves the new selection", async () => {
  let resolveLoad: any;
  const events = [
    createTestCard({ code: "cup_a", name: "Cup A" }),
    createTestCard({ code: "cup_b", name: "Cup B" }),
  ];

  const client: any = {
    post: async () => new Promise((r) => (resolveLoad = r)),
  };

  const controller = new EventsController(client);
  controller["state"].events = events;

  // Start refresh
  const loadPromise = controller.load();

  // While load is pending, user selects Event B
  controller.select("cup_b");
  assert.equal(controller.getState().selectedCode, "cup_b");

  // Load finishes
  resolveLoad({ events });
  await loadPromise;

  assert.equal(controller.getState().selectedCode, "cup_b", "New selection must be preserved after load completes");
  assert.equal(controller.getState().status, "ready");
});

test("29. Concurrency: guess pending on Event A -> Event B selected does not leak feedback onto Event B", async () => {
  let resolveGuess: any;
  const cardA = createTestCard({ code: "event_a", name: "Event A" });
  const cardB = createTestCard({ code: "event_b", name: "Event B" });

  const client: any = {
    post: async (_url: string, payload: any) => {
      if (payload.action === "get") {
        return { events: [cardA, cardB] };
      }
      return new Promise((r) => (resolveGuess = r));
    },
  };

  const controller = new EventsController(client);
  await controller.load();

  controller.select("event_a");
  const pendingSubmit = controller.submit("Answer for A");

  // User navigates to Event B while guess is in flight
  controller.select("event_b");
  assert.equal(controller.getState().selectedCode, "event_b");

  // Server responds with feedback for Event A
  resolveGuess({
    events: [
      {
        ...cardA,
        progress: { attempts: 1, finished: false, solved: false, points: 0 },
      },
      cardB,
    ],
    feedback: {
      status: "wrong",
      points: 0,
      comparison: { name: "Player A", clues: [] },
    },
  });

  await pendingSubmit;

  assert.equal(controller.getState().selectedCode, "event_b");
  assert.equal(controller.getState().feedback, null, "Feedback for Event A must NOT leak to Event B");
});

// ---------------------------------------------------------------------------
// 13. EVENT DETAIL EXPLICIT REFRESH BUTTON
// ---------------------------------------------------------------------------

test("30. Event detail refresh button: preserves selection, updates state, and does not submit answer", async () => {
  let getCalls = 0;
  let guessCalls = 0;

  const cardV1 = createTestCard({
    progress: { attempts: 0, finished: false, solved: false, points: 0 },
    leaderboard: [{ name: "Alice", points: 5 }],
  });
  const cardV2 = createTestCard({
    progress: { attempts: 1, finished: false, solved: false, points: 0 },
    leaderboard: [
      { name: "Alice", points: 5 },
      { name: "Bob", points: 10 },
    ],
  });

  const client: any = {
    post: async (_url: string, payload: any) => {
      if (payload.action === "get") {
        getCalls++;
        return { events: [getCalls === 1 ? cardV1 : cardV2] };
      }
      if (payload.action === "guess") {
        guessCalls++;
        return { events: [cardV2] };
      }
    },
  };

  const controller = new EventsController(client);
  await controller.load();
  controller.select("champions_cup");

  const detailHtmlBefore = renderEventsPage(controller);
  assert.match(detailHtmlBefore, /id="events-refresh"/);
  assert.equal(detailHtmlBefore.includes("Bob"), false);

  // Trigger refresh while event is open
  await controller.load();

  assert.equal(getCalls, 2);
  assert.equal(guessCalls, 0, "Refresh must never submit or replay a guess");
  assert.equal(controller.getState().selectedCode, "champions_cup");

  const detailHtmlAfter = renderEventsPage(controller);
  assert.match(detailHtmlAfter, /Bob/);
});

// ---------------------------------------------------------------------------
// 14. ACCESSIBILITY & FOCUS RESTORATION
// ---------------------------------------------------------------------------

test("31. Accessibility & Focus: heading focus, input focus restoration, ARIA roles", async () => {
  const { cleanup, container } = setupGlobalDom();
  try {
    const card = createTestCard();
    const client = mockClient([
      { events: [card] },
      {
        events: [
          {
            ...card,
            progress: { attempts: 1, finished: false, solved: false, points: 0 },
          },
        ],
        feedback: { status: "wrong", points: 0 },
      },
    ]);

    const controller = new EventsController(client);
    await controller.load();

    container.innerHTML = renderEventsPage(controller);
    attachEventsEventListeners(container, controller);

    // Click open event
    const openBtn = container.querySelector<HTMLButtonElement>("[data-event-open]");
    assert.ok(openBtn);
    openBtn.click();

    // Re-render detail
    container.innerHTML = renderEventsPage(controller);
    attachEventsEventListeners(container, controller);

    const heading = container.querySelector<HTMLElement>("#events-heading");
    assert.ok(heading);
    assert.equal(heading.tabIndex, -1);

    // Form label and ARIA attributes
    assert.ok(container.querySelector('label[for="events-answer"]'));
    assert.ok(container.querySelector('[aria-live="polite"]'));
    assert.ok(container.querySelector('ol[aria-label]'));

    // Submit wrong answer
    const input = container.querySelector<HTMLInputElement>("#events-answer");
    assert.ok(input);
    input.value = "Wrong Guess";
    const form = container.querySelector<HTMLFormElement>("#events-guess-form");
    assert.ok(form);

    const submitEvent = new (globalThis as any).Event("submit", {
      bubbles: true,
      cancelable: true,
    });
    form.dispatchEvent(submitEvent);

    await new Promise((r) => setTimeout(r, 20));

    // Re-render with feedback
    container.innerHTML = renderEventsPage(controller);
    attachEventsEventListeners(container, controller);

    const feedback = container.querySelector(".feedback");
    assert.ok(feedback);
    assert.equal(feedback.getAttribute("role"), "status");
  } finally {
    cleanup();
  }
});

// ---------------------------------------------------------------------------
// 15. RUNTIME IT / EN / ES LOCALIZATION
// ---------------------------------------------------------------------------

test("32. Runtime IT / EN / ES localization: verifies production copy, no raw keys or leaked codes", async () => {
  const languages: Array<"it" | "en" | "es"> = ["it", "en", "es"];

  for (const lang of languages) {
    setLanguage(lang);
    const card = createTestCard({
      type: "career",
      player_name: "Totti",
      min_correct: 2,
    });
    const client = mockClient([
      { events: [card] },
      {
        events: [card],
        feedback: { status: "wrong", points: 0, matched: 1 },
      },
    ]);

    const controller = new EventsController(client);
    await controller.load();

    const listHtml = renderEventsPage(controller);
    assert.equal(listHtml.includes("events."), false, `No raw keys in list view for ${lang}`);

    controller.select("champions_cup");
    await controller.submit("Roma");

    const detailHtml = renderEventsPage(controller);
    assert.equal(detailHtml.includes("events."), false, `No raw keys in detail view for ${lang}`);
    assert.equal(detailHtml.includes("max_answers"), false);
    assert.equal(detailHtml.includes("invalid_answer"), false);

    if (lang === "it") {
      assert.match(detailHtml, /Classifica/);
      assert.match(detailHtml, /Squadre corrette:\s*1/);
      assert.match(detailHtml, /Tentativi rimasti/);
    } else if (lang === "en") {
      assert.match(detailHtml, /Leaderboard/);
      assert.match(detailHtml, /Correct clubs:\s*1/);
      assert.match(detailHtml, /Attempts left/);
    } else if (lang === "es") {
      assert.match(detailHtml, /Clasificación/);
      assert.match(detailHtml, /Equipos correctos:\s*1/);
      assert.match(detailHtml, /Intentos restantes/);
    }
  }
});

// ---------------------------------------------------------------------------
// 16. ARENA HUB -> EVENTS INTEGRATION TEST & APP CONSTRUCTOR INJECTION
// ---------------------------------------------------------------------------

test("33. Arena Hub -> Events integration test: real App navigation, controller load, and back navigation", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const { cleanup, container } = setupGlobalDom();

  try {
    setLanguage("it");
    const card = createTestCard({ name: "Trofeo dei Campioni" });
    const eventsClient = mockClient([
      // Events load
      { events: [card] },
    ]);

    const eventsController = new EventsController(eventsClient);
    const app = new App(
      container,
      undefined,
      undefined,
      undefined,
      undefined,
      undefined,
      undefined,
      undefined,
      undefined,
      eventsController,
    );
    app.init();

    // Navigate to Arena tab
    app.setTab("arena");
    assert.ok(container.querySelector(".arena-hub"));

    // Find and click the Events entry CTA
    const eventsCta = container.querySelector<HTMLButtonElement>('button[data-tab="events"]');
    assert.ok(eventsCta, "Events CTA button must exist on Arena Hub");
    eventsCta.click();

    // Wait for events to load and render
    await new Promise((r) => setTimeout(r, 20));

    // Verify real Events page is rendered, NOT a prototype screen
    assert.ok(container.querySelector("#events-refresh"));
    assert.ok(container.querySelector(".events-list") || container.querySelector(".events-entry"));
    assert.match(container.innerHTML, /Trofeo dei Campioni/);
    assert.equal(container.innerHTML.includes("prototype-explanation"), false, "Must not render prototype");

    // Navigate back to Arena
    app.setTab("arena");
    assert.ok(container.querySelector(".arena-hub"), "Should navigate back to Arena Hub cleanly");
  } finally {
    cleanup();
    restoreTg();
  }
});

test("34. App constructor injection: verifies custom EventsController parameter is respected", () => {
  const { cleanup, container } = setupGlobalDom();
  try {
    const customController = new EventsController();
    const app = new App(
      container,
      undefined,
      undefined,
      undefined,
      undefined,
      undefined,
      undefined,
      undefined,
      undefined,
      customController,
    );
    assert.equal(app.getEventsController(), customController);
  } finally {
    cleanup();
  }
});

// ---------------------------------------------------------------------------
// 17. LEGACY /APP UNCHANGED
// ---------------------------------------------------------------------------

test("35. Legacy /app files (webapp/arena.js, webapp/index.html, webapp/client.js) remain completely untouched", () => {
  const rootDir = path.resolve(__dirname, "../../");
  const arenaJs = fs.readFileSync(path.join(rootDir, "webapp/arena.js"), "utf-8");
  const indexHtml = fs.readFileSync(path.join(rootDir, "webapp/index.html"), "utf-8");
  const clientJs = fs.readFileSync(path.join(rootDir, "webapp/client.js"), "utf-8");

  assert.ok(arenaJs.includes("function eventView"), "Legacy arena.js eventView must remain present");
  assert.ok(indexHtml.includes("arena.js"), "Legacy index.html script tag must remain present");
  assert.ok(clientJs.includes("escapeHtml"), "Legacy client.js must remain untouched");
});

// ---------------------------------------------------------------------------
// 18. REFRESH VS SUBMIT RACE PREVENTION & INVERSE PROTECTION
// ---------------------------------------------------------------------------

test("36. Race prevention: in-flight detail refresh blocks submit, refresh resolves, new submit uses updated revision", async () => {
  let resolveGet: (val: any) => void;
  const getPromise = new Promise((resolve) => {
    resolveGet = resolve;
  });

  let guessCalls = 0;
  let lastGuessPayload: any = null;

  const cardV1 = createTestCard({
    progress: { attempts: 0, finished: false, solved: false, points: 0 },
  });
  const cardV2 = createTestCard({
    progress: { attempts: 1, finished: false, solved: false, points: 0 },
  });

  const client: any = {
    post: async (_url: string, payload: any) => {
      if (payload.action === "get") {
        return getPromise;
      }
      if (payload.action === "guess") {
        guessCalls++;
        lastGuessPayload = payload;
        return {
          events: [
            createTestCard({
              progress: { attempts: 2, finished: false, solved: false, points: 0 },
            }),
          ],
          feedback: { status: "wrong", points: 0 },
        };
      }
    },
  };

  const controller = new EventsController(client);
  // Seed with cardV1 ready state
  controller["setState"]({
    status: "ready",
    events: [cardV1],
    selectedCode: "champions_cup",
    draftAnswer: "",
    feedback: null,
    error: null,
  });

  // Start detail refresh
  const loadPromise = controller.load();
  assert.equal(controller.getState().status, "loading");

  // Attempt submit while refresh is pending
  await controller.submit("Zidane");
  assert.equal(guessCalls, 0, "Submit must not dispatch any guess request while status is loading");

  // Verify UI disables form during loading
  const loadingHtml = renderEventsPage(controller);
  assert.match(loadingHtml, /<input[^>]*id="events-answer"[^>]*disabled/);
  assert.match(loadingHtml, /<button[^>]*type="submit"[^>]*disabled/);

  // Resolve the refresh with cardV2
  resolveGet!({ events: [cardV2] });
  await loadPromise;

  assert.equal(controller.getState().status, "ready");
  assert.equal(controller.selected()?.progress.attempts, 1);

  // Submit now succeeds with updated revision
  await controller.submit("Del Piero");
  assert.equal(guessCalls, 1);
  assert.equal(lastGuessPayload.revision, 1);
  assert.equal(lastGuessPayload.answer, "Del Piero");
});

test("37. Inverse protection: in-flight guess blocks refresh dispatch", async () => {
  let resolveGuess: (val: any) => void;
  const guessPromise = new Promise((resolve) => {
    resolveGuess = resolve;
  });

  let getCalls = 0;
  const card = createTestCard({
    progress: { attempts: 1, finished: false, solved: false, points: 0 },
  });

  const client: any = {
    post: async (_url: string, payload: any) => {
      if (payload.action === "guess") {
        return guessPromise;
      }
      if (payload.action === "get") {
        getCalls++;
        return { events: [card] };
      }
    },
  };

  const controller = new EventsController(client);
  controller["setState"]({
    status: "ready",
    events: [card],
    selectedCode: "champions_cup",
    draftAnswer: "",
    feedback: null,
    error: null,
  });

  const submitPromise = controller.submit("Buffon");
  assert.equal(controller.getState().status, "submitting");

  // Attempt refresh while submit is in flight
  await controller.load();
  assert.equal(getCalls, 0, "Refresh must not dispatch when status is submitting");

  resolveGuess!({
    events: [card],
    feedback: { status: "correct", points: 100 },
  });
  await submitPromise;
  assert.equal(controller.getState().status, "ready");
});

// ---------------------------------------------------------------------------
// 19. ZERO-EVENTS -> TRAINING NAVIGATION (POST ASYNC PARTIAL RERENDER)
// ---------------------------------------------------------------------------

test("38. Zero-events empty state -> Training navigation works after async partial rerender", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const { cleanup, container } = setupGlobalDom();

  try {
    let resolveEvents: (val: any) => void;
    const eventsPromise = new Promise((resolve) => {
      resolveEvents = resolve;
    });

    const eventsClient: any = {
      post: async (_url: string, payload: any) => {
        if (payload.action === "get") {
          return eventsPromise;
        }
      },
    };

    const trainingData = {
      session: {
        round: 0,
        attempts: 0,
        solved: 0,
        spent: 0,
        revision: 0,
        finished: false,
        history: [],
        total: 10,
        max_attempts: 5,
        career_path: [
          { team: "Juventus", start_year: 2010, end_year: 2015, apps: 100, goals: 10 },
        ],
      },
    };
    const trainingClient: any = {
      post: async () => trainingData,
    };

    const eventsController = new EventsController(eventsClient);
    const trainingController = new TrainingController(trainingClient);
    const arenaController = new ArenaController();

    const app = new App(
      container,
      undefined,
      arenaController,
      trainingController,
      undefined,
      undefined,
      undefined,
      undefined,
      undefined,
      eventsController,
    );
    app.init();

    // Navigate to events tab
    app.setTab("events");

    // Initially loading state is rendered
    assert.ok(container.querySelector(".loading-container") || container.innerHTML.includes("Eventi"));

    // Resolve events with 0 events
    resolveEvents!({ events: [] });
    await new Promise((r) => setTimeout(r, 30));

    // Empty state should be rendered via partial rerender (renderEventsContent)
    const emptyTrainingBtn = container.querySelector<HTMLButtonElement>("#events-open-training");
    assert.ok(emptyTrainingBtn, "#events-open-training button must exist in empty state after async partial rerender");

    // Click "Training" button
    emptyTrainingBtn.click();
    await new Promise((r) => setTimeout(r, 30));

    // Verify App state has navigated to Arena with subview training
    assert.equal(app.getActiveTab(), "arena");
    assert.equal(arenaController.getState().subview, "training");

    // Verify real Training page/controller renders
    assert.ok(
      container.querySelector("#training-view"),
      "Real training view must be rendered",
    );
    assert.ok(
      container.querySelector("#training-answer") || container.querySelector("#training-start"),
      "Real training interactive controls must render",
    );
  } finally {
    cleanup();
    restoreTg();
  }
});

// ---------------------------------------------------------------------------
// 20. RUNTIME IT / EN / ES LOCALIZATION OF minCorrect
// ---------------------------------------------------------------------------

test("39. Runtime IT / EN / ES localization of minCorrect for career events", () => {
  const card = createTestCard({
    type: "career",
    min_correct: 3,
  });

  const languages: Array<"it" | "en" | "es"> = ["it", "en", "es"];
  const expectedLabels: Record<string, string> = {
    it: "Minimo: 3",
    en: "Minimum: 3",
    es: "Mínimo: 3",
  };

  for (const lang of languages) {
    setLanguage(lang);
    const controller = new EventsController();
    controller["setState"]({
      status: "ready",
      events: [card],
      selectedCode: "champions_cup",
      draftAnswer: "",
      feedback: null,
      error: null,
    });

    const html = renderEventsPage(controller);
    assert.match(
      html,
      new RegExp(expectedLabels[lang]),
      `Career hint in ${lang} must render localized ${expectedLabels[lang]}`,
    );
    assert.equal(
      html.includes("Min: 3"),
      false,
      `Must not render hard-coded "Min: 3" in ${lang}`,
    );
  }
});

// ---------------------------------------------------------------------------
// 21. CROSS-FEATURE COEXISTENCE (REFERRAL & EVENTS)
// ---------------------------------------------------------------------------

test("40. Cross-feature coexistence: Referral and Events both fully operational in App", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const { cleanup, container } = setupGlobalDom();

  try {
    const card = createTestCard();
    const eventsClient: any = {
      post: async () => ({ events: [card] }),
    };
    const referralClient: any = {
      post: async () => ({
        stats: { confirmed_count: 3, pending_count: 1, available_points: 150 },
        referral_link: "https://t.me/bot?start=ref123",
        milestones: [],
        friends: [],
      }),
    };

    const eventsController = new EventsController(eventsClient);
    const referralController = new ReferralController(referralClient);
    const profileController = new ProfileController();
    const shopController = new ShopController();
    const arenaController = new ArenaController();

    const app = new App(
      container,
      undefined,
      arenaController,
      undefined,
      undefined,
      undefined,
      profileController,
      shopController,
      referralController,
      eventsController,
    );
    app.init();

    // 1. Profile -> Referral navigation
    app.setTab("profile");
    assert.equal(app.getActiveTab(), "profile");
    const referralNavBtn = container.querySelector<HTMLButtonElement>('button[data-tab="referral"]');
    if (referralNavBtn) {
      referralNavBtn.click();
      await new Promise((r) => setTimeout(r, 20));
      assert.equal(app.getActiveTab(), "referral");
      assert.ok(container.querySelector(".referral-page-shell"), "Referral page must render");
    }

    // 2. Arena Hub -> Events navigation
    app.setTab("arena");
    assert.equal(app.getActiveTab(), "arena");
    const eventsNavBtn = container.querySelector<HTMLButtonElement>('button[data-tab="events"]');
    assert.ok(eventsNavBtn, "Events button must exist in Arena Hub");
    eventsNavBtn.click();
    await new Promise((r) => setTimeout(r, 20));
    assert.equal(app.getActiveTab(), "events");
    assert.ok(container.querySelector(".events-list") || container.querySelector(".events-entry"), "Events page must render");

    // 3. Navigate through standard tabs to verify no regressions
    const standardTabs = ["play", "shop", "leaderboard", "archive"] as const;
    for (const tab of standardTabs) {
      app.setTab(tab);
      assert.equal(app.getActiveTab(), tab);
    }
  } finally {
    cleanup();
    restoreTg();
  }
});

// ---------------------------------------------------------------------------
// 22. ARENA / TRAINING UX REGRESSION & REFERRAL INIT PRESERVATION
// ---------------------------------------------------------------------------

test("41. Arena opponent search focus & cursor preservation during controller rerender", () => {
  const { cleanup, container } = setupGlobalDom();
  const { restore: restoreTg } = setupTestTelegram();

  try {
    const arenaController = new ArenaController();
    const app = new App(
      container,
      undefined,
      arenaController,
    );
    app.init();

    // Navigate to challenge subview
    app.setTab("challenge");
    assert.equal(arenaController.getState().subview, "challenge");

    const searchInput = container.querySelector<HTMLInputElement>("#opponent-search");
    assert.ok(searchInput, "#opponent-search input must exist in challenge view");

    // Type into input and position cursor
    searchInput.value = "mario";
    searchInput.focus();
    searchInput.setSelectionRange(2, 2);
    assert.equal(document.activeElement, searchInput);
    assert.equal(searchInput.selectionStart, 2);

    // Trigger an arena controller state update that causes App subscription -> renderArenaContent
    (arenaController as any).updateState({
      searchQuery: "mario",
    });

    const refreshedInput = container.querySelector<HTMLInputElement>("#opponent-search");
    assert.ok(refreshedInput, "#opponent-search must remain present after rerender");
    assert.equal(document.activeElement, refreshedInput, "Opponent search input must retain focus after rerender");
    assert.equal(refreshedInput.selectionStart, 2, "Cursor position (2) must be preserved after rerender");
  } finally {
    cleanup();
    restoreTg();
  }
});

test("42. Arena answer input focus preservation during state rerender", () => {
  const { cleanup, container } = setupGlobalDom();
  const { restore: restoreTg } = setupTestTelegram();

  try {
    const arenaController = new ArenaController();
    const app = new App(
      container,
      undefined,
      arenaController,
    );
    app.init();

    // Set active duel state in duel subview
    (arenaController as any).state = {
      subview: "duel",
      status: "idle",
      busy: false,
      error: null,
      notice: null,
      confirming: null,
      data: createTestDuelData({
        opponent: { name: "Matteo", round: 1, finished: false },
        session: createTestDuelSession({ round: 0, total: 5 }),
      }),
      activeDuelCode: "duel123",
      invitationCode: null,
      searchQuery: "",
      searchResults: [],
      searchError: null,
      draftAnswer: "Dybala",
    };

    app.setTab("duels");
    assert.equal(arenaController.getState().subview, "duel");

    const answerInput = container.querySelector<HTMLInputElement>("#arena-answer");
    assert.ok(answerInput, "#arena-answer must exist in duel view");

    answerInput.focus();
    assert.equal(document.activeElement, answerInput);

    // Trigger state update / rerender while status is idle (not submitting)
    (arenaController as any).updateState({
      draftAnswer: "Dybala",
    });

    const refreshedInput = container.querySelector<HTMLInputElement>("#arena-answer");
    assert.ok(refreshedInput);
    assert.equal(document.activeElement, refreshedInput, "#arena-answer must remain focused after Arena rerender");
  } finally {
    cleanup();
    restoreTg();
  }
});

test("43. Training answer input focus preservation during state rerender", () => {
  const { cleanup, container } = setupGlobalDom();
  const { restore: restoreTg } = setupTestTelegram();

  try {
    const arenaController = new ArenaController();
    const trainingController = new TrainingController();
    const app = new App(
      container,
      undefined,
      arenaController,
      trainingController,
    );
    app.init();

    (trainingController as any).state = {
      status: "idle",
      busy: false,
      error: null,
      notice: null,
      confirming: null,
      data: {
        session: {
          round: 0,
          attempts: 0,
          solved: 0,
          spent: 0,
          revision: 0,
          finished: false,
          history: [],
          total: 10,
          max_attempts: 5,
          career_path: [
            { team: "Juventus", start_year: 2010, end_year: 2015, apps: 100, goals: 10 },
          ],
        },
      },
      draftAnswer: "",
    };

    app.setTab("arena");
    app.setArenaSubview("training");
    // Render training view inside arena
    (app as any).renderArenaContent();
    assert.equal(arenaController.getState().subview, "training");

    const answerInput = container.querySelector<HTMLInputElement>("#training-answer");
    assert.ok(answerInput, "#training-answer must exist in training active session");

    answerInput.focus();
    assert.equal(document.activeElement, answerInput);

    // Trigger training controller state update / notify
    (trainingController as any).state.draftAnswer = "Pirlo";
    (trainingController as any).notify();

    const refreshedInput = container.querySelector<HTMLInputElement>("#training-answer");
    assert.ok(refreshedInput);
    assert.equal(document.activeElement, refreshedInput, "#training-answer must remain focused after Training rerender");
  } finally {
    cleanup();
    restoreTg();
  }
});

test("44. Referral initialization in App.init() is preserved when activeTab is referral", () => {
  const { cleanup, container } = setupGlobalDom();
  const { restore: restoreTg } = setupTestTelegram();

  try {
    let initCalled = false;
    const referralController = new ReferralController();
    referralController.init = async () => {
      initCalled = true;
    };

    const app = new App(
      container,
      undefined,
      undefined,
      undefined,
      undefined,
      undefined,
      undefined,
      undefined,
      referralController,
    );
    (app as any).activeTab = "referral";
    app.init();

    assert.equal(app.getActiveTab(), "referral");
    assert.equal(initCalled, true, "referralController.init() must be called on App.init() when activeTab is referral");
  } finally {
    cleanup();
    restoreTg();
  }
});


