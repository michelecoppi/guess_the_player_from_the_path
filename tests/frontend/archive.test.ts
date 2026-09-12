import { test } from "node:test";
import assert from "node:assert/strict";
import { ArchiveController } from "../../webapp/src/features/archive/controller";
import {
  renderArchiveViews,
} from "../../webapp/src/features/archive/views";
import {
  renderArchivePage,
  attachArchiveEventListeners,
} from "../../webapp/src/pages/ArchivePage";
import { setLanguage } from "../../webapp/src/i18n";
import {
  setupTestTelegram,
  mockFetchResponse,
  mockFetchError,
  captureFetchRequests,
  createTestArchiveDay,
  createTestCalendar,
  createTestArchiveChallenge,
  createTestArchiveGuessResult,
  createTestDom,
} from "./helpers";

// ===========================================================================
// CALENDAR TESTS (1-10)
// ===========================================================================

test("1. init load: calls POST /app/api/calendar with initData and transitions to ready", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const calendarData = { days: createTestCalendar() };
  const { requests, restore: restoreFetch } = captureFetchRequests(calendarData);

  try {
    const controller = new ArchiveController();
    assert.equal(controller.getState().status, "idle");

    await controller.init();

    assert.equal(requests.length, 1);
    const req = requests[0];
    assert.equal(req.url, "/app/api/calendar");
    assert.equal(req.method, "POST");
    assert.ok(req.body.initData, "Telegram initData must be included in body");
    // day should NOT be present when fetching calendar
    assert.equal(req.body.day, undefined);

    const state = controller.getState();
    assert.equal(state.status, "ready");
    assert.equal(state.calendar.length, 4);
    assert.equal(state.view, "calendar");
  } finally {
    restoreFetch();
    restoreTg();
  }
});

test("2. empty state: renders empty message when calendar has 0 days", async () => {
  setLanguage("it");
  const html = renderArchiveViews({
    view: "calendar",
    status: "ready",
    calendar: [],
    selectedDay: null,
    challenge: null,
    feedback: null,
    draftAnswer: "",
    challengeFinished: false,
    error: null,
  });

  assert.ok(html.includes("Nessuna sfida passata"), "Empty state message should be rendered");
});

test("3. solved and recovered days render as non-interactive div cards", () => {
  const daySolved = createTestArchiveDay({ status: "solved", playable: false, number: 10 });
  const dayRecovered = createTestArchiveDay({ status: "recovered", playable: false, number: 11 });

  const html = renderArchiveViews({
    view: "calendar",
    status: "ready",
    calendar: [daySolved, dayRecovered],
    selectedDay: null,
    challenge: null,
    feedback: null,
    draftAnswer: "",
    challengeFinished: false,
    error: null,
  });

  // Non-interactive days should NOT be buttons
  assert.ok(!html.includes('button class="archive-day-card solved"'));
  assert.ok(!html.includes('button class="archive-day-card recovered"'));
  assert.ok(html.includes('div class="archive-day-card solved"'));
  assert.ok(html.includes('div class="archive-day-card recovered"'));
});

test("4. lost and missed days render as playable buttons with data-archive-day", () => {
  const dayLost = createTestArchiveDay({ day: "2026-09-02", status: "lost", playable: true, number: 20 });
  const dayMissed = createTestArchiveDay({ day: "2026-09-03", status: "missed", playable: true, number: 21 });

  const html = renderArchiveViews({
    view: "calendar",
    status: "ready",
    calendar: [dayLost, dayMissed],
    selectedDay: null,
    challenge: null,
    feedback: null,
    draftAnswer: "",
    challengeFinished: false,
    error: null,
  });

  assert.ok(html.includes('button class="archive-day-card lost" data-archive-day="2026-09-02"'));
  assert.ok(html.includes('button class="archive-day-card missed" data-archive-day="2026-09-03"'));
});

test("5. playable flag from server is authoritative (playable=false creates div even if status is lost)", () => {
  const nonPlayableLost = createTestArchiveDay({ day: "2026-09-05", status: "lost", playable: false, number: 30 });

  const html = renderArchiveViews({
    view: "calendar",
    status: "ready",
    calendar: [nonPlayableLost],
    selectedDay: null,
    challenge: null,
    feedback: null,
    draftAnswer: "",
    challengeFinished: false,
    error: null,
  });

  assert.ok(!html.includes('button class="archive-day-card lost"'));
  assert.ok(html.includes('div class="archive-day-card lost"'));
});

test("6. calendar day metadata correctly displayed: #number, label, difficulty_label", () => {
  const day = createTestArchiveDay({
    number: 99,
    label: "05/09/26",
    difficulty_label: "Difficile",
    attempts: 4,
    status: "lost",
    playable: true,
  });

  const html = renderArchiveViews({
    view: "calendar",
    status: "ready",
    calendar: [day],
    selectedDay: null,
    challenge: null,
    feedback: null,
    draftAnswer: "",
    challengeFinished: false,
    error: null,
  });

  assert.ok(html.includes("#99"));
  assert.ok(html.includes("05/09/26"));
  assert.ok(html.includes("Difficile"));
});

test("7. calendar API error renders accessible error state with retry button", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const restoreFetch = mockFetchError(500, "Server Down");

  try {
    const controller = new ArchiveController();
    await controller.init();

    const state = controller.getState();
    assert.equal(state.status, "error");

    const html = renderArchiveViews(state);
    assert.ok(html.includes('role="alert"'));
    assert.ok(html.includes('id="archive-retry"'));
  } finally {
    restoreFetch();
    restoreTg();
  }
});

test("8. calendar retry button triggers new fetch", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  let callCount = 0;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () => {
    callCount++;
    if (callCount === 1) {
      return { ok: false, status: 500, json: async () => ({ detail: "Error" }) } as Response;
    }
    return {
      ok: true,
      status: 200,
      json: async () => ({ days: createTestCalendar() }),
    } as Response;
  }) as any;

  try {
    const controller = new ArchiveController();
    await controller.init();
    assert.equal(controller.getState().status, "error");

    // Retry
    await controller.retry();
    assert.equal(controller.getState().status, "ready");
    assert.equal(controller.getState().calendar.length, 4);
    assert.equal(callCount, 2);
  } finally {
    globalThis.fetch = originalFetch;
    restoreTg();
  }
});

test("9. duplicate in-flight loadCalendar calls are ignored (idempotency)", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  let callCount = 0;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () => {
    callCount++;
    await new Promise((r) => setTimeout(r, 20));
    return {
      ok: true,
      status: 200,
      json: async () => ({ days: createTestCalendar() }),
    } as Response;
  }) as any;

  try {
    const controller = new ArchiveController();
    // Call init concurrently twice
    const p1 = controller.init();
    const p2 = controller.init();
    await Promise.all([p1, p2]);

    assert.equal(callCount, 1, "Only one network request should be dispatched");
  } finally {
    globalThis.fetch = originalFetch;
    restoreTg();
  }
});

test("10. stale out-of-order calendar responses are discarded via sequence guard", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const controller = new ArchiveController();

  let resolveFirst: (v: any) => void;
  const firstPromise = new Promise((resolve) => {
    resolveFirst = resolve;
  });

  const originalFetch = globalThis.fetch;
  let reqCount = 0;
  globalThis.fetch = (async () => {
    reqCount++;
    if (reqCount === 1) {
      await firstPromise;
      return {
        ok: true,
        status: 200,
        json: async () => ({ days: [createTestArchiveDay({ number: 1 })] }),
      } as Response;
    }
    // Second request returns immediately with 3 days
    return {
      ok: true,
      status: 200,
      json: async () => ({ days: [createTestArchiveDay({ number: 2 }), createTestArchiveDay({ number: 3 })] }),
    } as Response;
  }) as any;

  try {
    // Start first request
    const p1 = controller.refreshCalendar();
    // Immediately trigger second refresh (increments calendarSeq)
    const p2 = controller.refreshCalendar();

    await p2;
    assert.equal(controller.getState().calendar.length, 2);

    // Now resolve first request late
    resolveFirst!({});
    await p1;

    // State should still have 2 days from the newer request
    assert.equal(controller.getState().calendar.length, 2);
    assert.equal(controller.getState().calendar[0].number, 2);
  } finally {
    globalThis.fetch = originalFetch;
    restoreTg();
  }
});

// ===========================================================================
// CHALLENGE TESTS (11-18)
// ===========================================================================

test("11. clicking a playable day calls POST /app/api/calendar with { day }", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const challengeData = createTestArchiveChallenge({ day: "2026-09-02" });
  const { requests, restore: restoreFetch } = captureFetchRequests(challengeData);

  try {
    const controller = new ArchiveController();
    await controller.openDay("2026-09-02");

    assert.equal(requests.length, 1);
    const req = requests[0];
    assert.equal(req.url, "/app/api/calendar");
    assert.equal(req.method, "POST");
    assert.equal(req.body.day, "2026-09-02");
    assert.ok(req.body.initData);

    const state = controller.getState();
    assert.equal(state.view, "challenge");
    assert.equal(state.status, "challenge_ready");
    assert.equal(state.selectedDay, "2026-09-02");
    assert.equal(state.challenge?.day, "2026-09-02");
  } finally {
    restoreFetch();
    restoreTg();
  }
});

test("12. challenge view renders career path, attempt indicators, and meta info", () => {
  const challenge = createTestArchiveChallenge({
    number: 55,
    label: "15/09/26",
    difficulty_label: "Difficile",
    attempts_used: 2,
    max_attempts: 5,
  });

  const html = renderArchiveViews({
    view: "challenge",
    status: "challenge_ready",
    calendar: [],
    selectedDay: "2026-09-15",
    challenge,
    feedback: null,
    draftAnswer: "",
    challengeFinished: false,
    error: null,
  });

  assert.ok(html.includes("#55 · 15/09/26"));
  assert.ok(html.includes("Difficile"));
  assert.ok(html.includes("archive-attempts-bar"));
  assert.ok(html.includes("Parma"));
  assert.ok(html.includes("Juventus"));
  assert.ok(html.includes('id="archive-answer"'));
  assert.ok(html.includes('id="archive-submit"'));
});

test("13. attempt count dots respect max_attempts dynamically from server", () => {
  const challenge = createTestArchiveChallenge({
    attempts_used: 1,
    max_attempts: 4,
  });

  const html = renderArchiveViews({
    view: "challenge",
    status: "challenge_ready",
    calendar: [],
    selectedDay: "2026-09-02",
    challenge,
    feedback: null,
    draftAnswer: "",
    challengeFinished: false,
    error: null,
  });

  const usedDots = (html.match(/archive-attempt-dot used/g) || []).length;
  const emptyDots = (html.match(/archive-attempt-dot empty/g) || []).length;
  assert.equal(usedDots, 1);
  assert.equal(emptyDots, 3);
});

test("14. unavailable day / 404 response transitions to challenge_error", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const restoreFetch = mockFetchError(404, "Challenge not found");

  try {
    const controller = new ArchiveController();
    await controller.openDay("2026-09-99");

    const state = controller.getState();
    assert.equal(state.status, "challenge_error");
    assert.ok(state.error);

    const html = renderArchiveViews(state);
    assert.ok(html.includes('role="alert"'));
    assert.ok(html.includes('id="archive-challenge-retry"'));
    assert.ok(html.includes('id="archive-back"'));
  } finally {
    restoreFetch();
    restoreTg();
  }
});

test("15. challenge loading state renders accessible spinner", () => {
  const html = renderArchiveViews({
    view: "challenge",
    status: "challenge_loading",
    calendar: [],
    selectedDay: "2026-09-02",
    challenge: null,
    feedback: null,
    draftAnswer: "",
    challengeFinished: false,
    error: null,
  });

  assert.ok(html.includes('role="status"'));
  assert.ok(html.includes("archive-back-btn"));
});

test("16. back button switches view back to calendar without re-fetching if challenge unfinished", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const calendarData = { days: createTestCalendar() };
  let fetchCount = 0;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (_url: string, opts: any) => {
    fetchCount++;
    const body = opts?.body ? JSON.parse(opts.body) : {};
    if (body.day) {
      return { ok: true, status: 200, json: async () => createTestArchiveChallenge({ day: body.day }) } as Response;
    }
    return { ok: true, status: 200, json: async () => calendarData } as Response;
  }) as any;

  try {
    const controller = new ArchiveController();
    await controller.init(); // 1st fetch: calendar
    await controller.openDay("2026-09-02"); // 2nd fetch: challenge

    assert.equal(fetchCount, 2);
    assert.equal(controller.getState().view, "challenge");

    // Click back
    await controller.backToCalendar();

    assert.equal(controller.getState().view, "calendar");
    assert.equal(controller.getState().selectedDay, null);
    assert.equal(controller.getState().challenge, null);
    // Did NOT trigger another calendar fetch because game was not finished
    assert.equal(fetchCount, 2);
  } finally {
    globalThis.fetch = originalFetch;
    restoreTg();
  }
});

test("17. challenge retry button retries openDay", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  let callCount = 0;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () => {
    callCount++;
    if (callCount === 1) {
      return { ok: false, status: 500, json: async () => ({ detail: "Error" }) } as Response;
    }
    return {
      ok: true,
      status: 200,
      json: async () => createTestArchiveChallenge({ day: "2026-09-02" }),
    } as Response;
  }) as any;

  try {
    const controller = new ArchiveController();
    await controller.openDay("2026-09-02");
    assert.equal(controller.getState().status, "challenge_error");

    await controller.retryChallenge();
    assert.equal(controller.getState().status, "challenge_ready");
    assert.equal(controller.getState().challenge?.day, "2026-09-02");
  } finally {
    globalThis.fetch = originalFetch;
    restoreTg();
  }
});

test("18. draft answer can be set and is bound to input", () => {
  const controller = new ArchiveController();
  controller.setDraftAnswer("Del Piero");
  assert.equal(controller.getState().draftAnswer, "Del Piero");
});

// ===========================================================================
// GUESSING TESTS (19-27)
// ===========================================================================

test("19. submitGuess sends POST /app/api/guess with { answer, day, initData }", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const guessResult = createTestArchiveGuessResult({
    status: "wrong",
    attempts_used: 1,
    attempts_left: 4,
  });
  const { requests, restore: restoreFetch } = captureFetchRequests(guessResult);

  try {
    const controller = new ArchiveController();
    // Simulate challenge is already loaded for day
    (controller as any).updateState({
      view: "challenge",
      status: "challenge_ready",
      selectedDay: "2026-09-02",
      challenge: createTestArchiveChallenge({ day: "2026-09-02", attempts_used: 0, attempts_left: 5 }),
    });

    await controller.submitGuess("Pirlo");

    assert.equal(requests.length, 1);
    const req = requests[0];
    assert.equal(req.url, "/app/api/guess");
    assert.equal(req.method, "POST");
    assert.equal(req.body.answer, "Pirlo");
    assert.equal(req.body.day, "2026-09-02");
    assert.ok(req.body.initData);

    const state = controller.getState();
    assert.equal(state.status, "challenge_ready");
    assert.equal(state.feedback?.status, "wrong");
    assert.equal(state.challenge?.attempts_used, 1);
    assert.equal(state.challenge?.attempts_left, 4);
  } finally {
    restoreFetch();
    restoreTg();
  }
});

test("20. wrong guess displays comparison clues and remaining attempts", () => {
  setLanguage("it");
  const feedback = createTestArchiveGuessResult({
    status: "wrong",
    attempts_used: 1,
    attempts_left: 3,
    comparison: {
      name: "Pirlo",
      clues: [
        { key: "feedback.nationality_same", args: {} },
        { key: "feedback.position_diff", args: {} },
      ],
    },
  });

  const html = renderArchiveViews({
    view: "challenge",
    status: "challenge_ready",
    calendar: [],
    selectedDay: "2026-09-02",
    challenge: createTestArchiveChallenge(),
    feedback,
    draftAnswer: "",
    challengeFinished: false,
    error: null,
  });

  assert.ok(html.includes("feedback no"));
  assert.ok(html.includes("Pirlo"));
  assert.ok(html.includes("Tentativi rimasti: 3"));
});

test("21. correct guess displays success feedback, share button, and hides input form", () => {
  setLanguage("it");
  const feedback = createTestArchiveGuessResult({
    status: "correct",
    attempts_used: 2,
    attempts_left: 3,
    share: {
      text: "Ho indovinato la sfida del 02/09!",
      url: "https://t.me/share/url?url=test",
    },
  });

  const html = renderArchiveViews({
    view: "challenge",
    status: "challenge_ready",
    calendar: [],
    selectedDay: "2026-09-02",
    challenge: createTestArchiveChallenge({ solved: true }),
    feedback,
    draftAnswer: "",
    challengeFinished: true,
    error: null,
  });

  assert.ok(html.includes("feedback ok"));
  assert.ok(html.includes("Recuperata! Bel recupero."));
  assert.ok(html.includes('id="archive-share"'));
  // Input form should be hidden on solved
  assert.ok(!html.includes('id="archive-guess-form"'));
});

test("22. final wrong guess (attempts_left === 0) reveals correct answer and hides input", () => {
  setLanguage("it");
  const feedback = createTestArchiveGuessResult({
    status: "wrong",
    attempts_used: 5,
    attempts_left: 0,
    answer: "Alessandro Del Piero",
    share: {
      text: "Ho giocato la sfida del 02/09",
      url: "https://t.me/share/url?url=test",
    },
  });

  const html = renderArchiveViews({
    view: "challenge",
    status: "challenge_ready",
    calendar: [],
    selectedDay: "2026-09-02",
    challenge: createTestArchiveChallenge({ attempts_used: 5, attempts_left: 0 }),
    feedback,
    draftAnswer: "",
    challengeFinished: true,
    error: null,
  });

  assert.ok(html.includes("feedback no"));
  assert.ok(html.includes("Alessandro Del Piero"));
  assert.ok(!html.includes('id="archive-guess-form"'));
});

test("23. refused status (already solved) displays alreadySolved message", () => {
  setLanguage("it");
  const feedback = createTestArchiveGuessResult({
    status: "refused",
    reason: "already_solved",
  });

  const html = renderArchiveViews({
    view: "challenge",
    status: "challenge_ready",
    calendar: [],
    selectedDay: "2026-09-02",
    challenge: createTestArchiveChallenge({ solved: true }),
    feedback,
    draftAnswer: "",
    challengeFinished: true,
    error: null,
  });

  assert.ok(html.includes("Hai già recuperato"));
});

test("24. double-submit blocked while guess submission is in flight", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  let guessCallCount = 0;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () => {
    guessCallCount++;
    await new Promise((r) => setTimeout(r, 40));
    return {
      ok: true,
      status: 200,
      json: async () => createTestArchiveGuessResult({ attempts_used: 1, attempts_left: 4 }),
    } as Response;
  }) as any;

  try {
    const controller = new ArchiveController();
    (controller as any).updateState({
      view: "challenge",
      status: "challenge_ready",
      selectedDay: "2026-09-02",
      challenge: createTestArchiveChallenge({ day: "2026-09-02" }),
    });

    const p1 = controller.submitGuess("Guess 1");
    const p2 = controller.submitGuess("Guess 2"); // Concurrent call while busy
    await Promise.all([p1, p2]);

    assert.equal(guessCallCount, 1, "Second guess must be blocked while first is in flight");
  } finally {
    globalThis.fetch = originalFetch;
    restoreTg();
  }
});

test("25. stale out-of-order guess responses are discarded via sequence guard", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const controller = new ArchiveController();
  (controller as any).updateState({
    view: "challenge",
    status: "challenge_ready",
    selectedDay: "2026-09-02",
    challenge: createTestArchiveChallenge({ day: "2026-09-02" }),
  });

  let resolveFirstGuess: (v: any) => void;
  const firstPromise = new Promise((resolve) => {
    resolveFirstGuess = resolve;
  });

  let reqCount = 0;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () => {
    reqCount++;
    if (reqCount === 1) {
      await firstPromise;
      return {
        ok: true,
        status: 200,
        json: async () => createTestArchiveGuessResult({ status: "wrong", attempts_used: 1 }),
      } as Response;
    }
    return {
      ok: true,
      status: 200,
      json: async () => createTestArchiveGuessResult({ status: "correct", attempts_used: 2 }),
    } as Response;
  }) as any;

  try {
    const p1 = controller.submitGuess("Guess 1");
    // Force status back to ready to simulate second submission
    (controller as any).state.status = "challenge_ready";
    const p2 = controller.submitGuess("Guess 2");

    await p2;
    assert.equal(controller.getState().feedback?.status, "correct");

    // Now resolve the older guess
    resolveFirstGuess!({});
    await p1;

    // Newer result must NOT be overwritten by the stale first response
    assert.equal(controller.getState().feedback?.status, "correct");
  } finally {
    globalThis.fetch = originalFetch;
    restoreTg();
  }
});

test("26. finishing a challenge sets challengeFinished: true", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const restoreFetch = mockFetchResponse(createTestArchiveGuessResult({
    status: "correct",
    attempts_used: 1,
    attempts_left: 4,
  }));

  try {
    const controller = new ArchiveController();
    (controller as any).updateState({
      view: "challenge",
      status: "challenge_ready",
      selectedDay: "2026-09-02",
      challenge: createTestArchiveChallenge({ day: "2026-09-02" }),
      challengeFinished: false,
    });

    await controller.submitGuess("Buffon");
    assert.equal(controller.getState().challengeFinished, true);
  } finally {
    restoreFetch();
    restoreTg();
  }
});

test("27. navigating backToCalendar after finishing challenge automatically triggers calendar refresh", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  let calendarRefreshed = false;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (_url: string, opts: any) => {
    const body = opts?.body ? JSON.parse(opts.body) : {};
    if (!body.day) {
      calendarRefreshed = true;
      return {
        ok: true,
        status: 200,
        json: async () => ({
          days: [
            createTestArchiveDay({ day: "2026-09-02", status: "recovered", playable: false }),
          ],
        }),
      } as Response;
    }
    return { ok: true, status: 200, json: async () => ({}) } as Response;
  }) as any;

  try {
    const controller = new ArchiveController();
    (controller as any).updateState({
      view: "challenge",
      status: "challenge_ready",
      selectedDay: "2026-09-02",
      challengeFinished: true, // finished!
    });

    await controller.backToCalendar();

    assert.equal(calendarRefreshed, true, "Calendar must be automatically refreshed on return");
    assert.equal(controller.getState().view, "calendar");
    assert.equal(controller.getState().calendar[0].status, "recovered");
  } finally {
    globalThis.fetch = originalFetch;
    restoreTg();
  }
});

// ===========================================================================
// i18n & ACCESSIBILITY TESTS (28-32)
// ===========================================================================

test("28. Italian localization renders Italian archive strings", () => {
  setLanguage("it");
  const html = renderArchivePage({
    view: "calendar",
    status: "ready",
    calendar: [createTestArchiveDay({ status: "solved", playable: false })],
    selectedDay: null,
    challenge: null,
    feedback: null,
    draftAnswer: "",
    challengeFinished: false,
    error: null,
  });

  assert.ok(html.includes("ARCHIVIO"));
  assert.ok(html.includes("Sfide passate"));
  assert.ok(html.includes("Indovinata"));
});

test("29. English localization renders English archive strings", () => {
  setLanguage("en");
  const html = renderArchivePage({
    view: "calendar",
    status: "ready",
    calendar: [createTestArchiveDay({ status: "lost", playable: true })],
    selectedDay: null,
    challenge: null,
    feedback: null,
    draftAnswer: "",
    challengeFinished: false,
    error: null,
  });

  assert.ok(html.includes("ARCHIVE"));
  assert.ok(html.includes("Past challenges"));
  assert.ok(html.includes("Lost"));
});

test("30. Spanish localization renders Spanish archive strings", () => {
  setLanguage("es");
  const html = renderArchivePage({
    view: "calendar",
    status: "ready",
    calendar: [createTestArchiveDay({ status: "recovered", playable: false })],
    selectedDay: null,
    challenge: null,
    feedback: null,
    draftAnswer: "",
    challengeFinished: false,
    error: null,
  });

  assert.ok(html.includes("ARCHIVO"));
  assert.ok(html.includes("Retos pasados"));
  assert.ok(html.includes("Recuperado"));
});

test("31. Calendar days have rich aria-label including label, status and attempts", () => {
  setLanguage("it");
  const day = createTestArchiveDay({
    day: "2026-09-01",
    label: "01/09/26",
    status: "solved",
    attempts: 3,
    playable: false,
  });

  const html = renderArchiveViews({
    view: "calendar",
    status: "ready",
    calendar: [day],
    selectedDay: null,
    challenge: null,
    feedback: null,
    draftAnswer: "",
    challengeFinished: false,
    error: null,
  });

  assert.ok(html.includes('aria-label="01/09/26 · Indovinata · 3 tentativi"'));
});

test("32. Status is conveyed via text label and icon (non-color-only cue)", () => {
  setLanguage("it");
  const day = createTestArchiveDay({
    day: "2026-09-02",
    label: "02/09/26",
    status: "lost",
    playable: true,
  });

  const html = renderArchiveViews({
    view: "calendar",
    status: "ready",
    calendar: [day],
    selectedDay: null,
    challenge: null,
    feedback: null,
    draftAnswer: "",
    challengeFinished: false,
    error: null,
  });

  // Icon check
  assert.ok(html.includes("❌"));
  // Screen-reader text check
  assert.ok(html.includes('<span class="archive-day-status-text sr-only">Persa</span>'));
});

// ===========================================================================
// ISOLATION & DOM EVENTS TESTS (33-35)
// ===========================================================================

test("33. Prototype fixtures ('Marco Rossi', fixture days) never appear in real archive runtime", () => {
  const html = renderArchivePage({
    view: "calendar",
    status: "ready",
    calendar: createTestCalendar(),
    selectedDay: null,
    challenge: null,
    feedback: null,
    draftAnswer: "",
    challengeFinished: false,
    error: null,
  });

  assert.ok(!html.includes("Marco Rossi"));
  assert.ok(!html.includes("Carriere indovinate"));
  assert.ok(!html.includes("Il tuo stile"));
});

test("34. No prototype notice is rendered in archive views", () => {
  const html = renderArchivePage({
    view: "calendar",
    status: "ready",
    calendar: createTestCalendar(),
    selectedDay: null,
    challenge: null,
    feedback: null,
    draftAnswer: "",
    challengeFinished: false,
    error: null,
  });

  assert.ok(!html.includes("prototype-notice"));
});

test("35. DOM event wiring: day click opens challenge, back click returns, form submit guesses", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const { window, container, cleanup } = createTestDom();

  const challengeData = createTestArchiveChallenge({ day: "2026-09-02" });
  let openDayCalled = false;
  let backCalled = false;
  let guessSubmitted = "";

  const mockController = {
    getState: () => ({
      view: "calendar",
      status: "ready",
      calendar: [createTestArchiveDay({ day: "2026-09-02", status: "lost", playable: true })],
      selectedDay: null,
      challenge: null,
      feedback: null,
      draftAnswer: "",
      challengeFinished: false,
      error: null,
    }),
    openDay: async (day: string) => {
      openDayCalled = true;
      assert.equal(day, "2026-09-02");
    },
    backToCalendar: async () => {
      backCalled = true;
    },
    submitGuess: async (ans: string) => {
      guessSubmitted = ans;
    },
    setDraftAnswer: () => {},
    retry: async () => {},
    retryChallenge: async () => {},
    openShareUrl: () => {},
  } as unknown as ArchiveController;

  try {
    container.innerHTML = renderArchivePage(mockController.getState() as any);
    attachArchiveEventListeners(container, mockController);

    // Test calendar day click
    const dayBtn = container.querySelector<HTMLButtonElement>("button[data-archive-day='2026-09-02']");
    assert.ok(dayBtn);
    dayBtn.click();
    assert.equal(openDayCalled, true);

    // Now test challenge view wiring
    (mockController as any).getState = () => ({
      view: "challenge",
      status: "challenge_ready",
      calendar: [],
      selectedDay: "2026-09-02",
      challenge: challengeData,
      feedback: null,
      draftAnswer: "Maldini",
      challengeFinished: false,
      error: null,
    });

    container.innerHTML = renderArchivePage(mockController.getState() as any);
    attachArchiveEventListeners(container, mockController);

    // Back button
    const backBtn = container.querySelector<HTMLButtonElement>("[data-archive-back]");
    assert.ok(backBtn);
    backBtn.click();
    assert.equal(backCalled, true);

    // Guess submission via form submit
    const form = container.querySelector<HTMLFormElement>("#archive-guess-form");
    assert.ok(form);
    form.dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }) as unknown as Event);
    assert.equal(guessSubmitted, "Maldini");
  } finally {
    cleanup();
    restoreTg();
  }
});
