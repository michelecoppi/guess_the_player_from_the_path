import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
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
// ARCHIVE REGRESSION SUITE (STEP 8: 1-35)
// ===========================================================================

test("1. real calendar request: calls POST /app/api/calendar with initData and transitions to ready", async () => {
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
    assert.equal(req.body.day, undefined, "day should NOT be present when fetching calendar");

    const state = controller.getState();
    assert.equal(state.status, "ready");
    assert.equal(state.calendar.length, 4);
    assert.equal(state.view, "calendar");
  } finally {
    restoreFetch();
    restoreTg();
  }
});

test("2. calendar empty: renders empty message when calendar has 0 days", () => {
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

test("3. solved: solved day renders as non-interactive card with checkmark and status label", () => {
  setLanguage("it");
  const daySolved = createTestArchiveDay({
    day: "2026-09-01",
    status: "solved",
    playable: false,
    number: 10,
    attempts: 2,
  });

  const html = renderArchiveViews({
    view: "calendar",
    status: "ready",
    calendar: [daySolved],
    selectedDay: null,
    challenge: null,
    feedback: null,
    draftAnswer: "",
    challengeFinished: false,
    error: null,
  });

  assert.ok(!html.includes('button class="archive-day-card solved"'), "Solved day must not be a button");
  assert.ok(html.includes('div class="archive-day-card solved"'), "Solved day must be a div card");
  assert.ok(html.includes("✅"), "Solved day must display checkmark icon");
  assert.ok(html.includes("Indovinata"), "Solved day must display Indovinata status");
});

test("4. lost: lost day renders as playable button with cross icon", () => {
  setLanguage("it");
  const dayLost = createTestArchiveDay({
    day: "2026-09-02",
    status: "lost",
    playable: true,
    number: 20,
    attempts: 3,
  });

  const html = renderArchiveViews({
    view: "calendar",
    status: "ready",
    calendar: [dayLost],
    selectedDay: null,
    challenge: null,
    feedback: null,
    draftAnswer: "",
    challengeFinished: false,
    error: null,
  });

  assert.ok(html.includes('button class="archive-day-card lost"'), "Playable lost day must be a button");
  assert.ok(html.includes('data-archive-day="2026-09-02"'), "Must have data-archive-day attribute");
  assert.ok(html.includes("❌"), "Lost day must display cross icon");
  assert.ok(html.includes("Persa"), "Lost day must display Persa status");
});

test("5. recovered: recovered day renders as non-interactive card with recovered icon", () => {
  setLanguage("it");
  const dayRecovered = createTestArchiveDay({
    day: "2026-09-03",
    status: "recovered",
    playable: false,
    number: 21,
    attempts: 1,
  });

  const html = renderArchiveViews({
    view: "calendar",
    status: "ready",
    calendar: [dayRecovered],
    selectedDay: null,
    challenge: null,
    feedback: null,
    draftAnswer: "",
    challengeFinished: false,
    error: null,
  });

  assert.ok(!html.includes('button class="archive-day-card recovered"'), "Recovered day must not be a button");
  assert.ok(html.includes('div class="archive-day-card recovered"'), "Recovered day must be a div card");
  assert.ok(html.includes("🔄"), "Recovered day must display recycle icon");
  assert.ok(html.includes("Recuperata"), "Recovered day must display Recuperata status");
});

test("6. missed: missed day renders as playable button with missed icon", () => {
  setLanguage("it");
  const dayMissed = createTestArchiveDay({
    day: "2026-09-04",
    status: "missed",
    playable: true,
    number: 22,
  });

  const html = renderArchiveViews({
    view: "calendar",
    status: "ready",
    calendar: [dayMissed],
    selectedDay: null,
    challenge: null,
    feedback: null,
    draftAnswer: "",
    challengeFinished: false,
    error: null,
  });

  assert.ok(html.includes('button class="archive-day-card missed"'), "Playable missed day must be a button");
  assert.ok(html.includes('data-archive-day="2026-09-04"'), "Must have data-archive-day attribute");
  assert.ok(html.includes("⬜"), "Missed day must display square icon");
  assert.ok(html.includes("Non giocata"), "Missed day must display Non giocata status");
});

test("7. server playable authoritative: server playable=false creates div even if status is lost", () => {
  const nonPlayableLost = createTestArchiveDay({
    day: "2026-09-05",
    status: "lost",
    playable: false,
    number: 30,
  });

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

  assert.ok(!html.includes('button class="archive-day-card lost"'), "Non-playable day must never be a button");
  assert.ok(html.includes('div class="archive-day-card lost"'), "Non-playable day must render as div");
});

test("8. real challenge request: clicking a playable day calls POST /app/api/calendar with { day }", async () => {
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
    assert.ok(req.body.initData, "Must include Telegram initData");

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

test("9. career path: challenge view renders career path stops, loan styling, appearances, and metadata", () => {
  const challenge = createTestArchiveChallenge({
    number: 55,
    label: "15/09/26",
    difficulty_label: "Difficile",
    career_path: [
      { team: "Parma", league: "Serie A", country: "Italia", start_year: 1995, end_year: 2001, apps: 168, goals: 0, loan: false },
      { team: "Juventus", league: "Serie A", country: "Italia", start_year: 2001, end_year: 2018, apps: 509, goals: 0, loan: false },
      { team: "Paris SG", league: "Ligue 1", country: "Francia", start_year: 2018, end_year: 2019, apps: 17, goals: 0, loan: true },
    ],
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

  assert.ok(html.includes("#55 · 15/09/26"));
  assert.ok(html.includes("Difficile"));
  assert.ok(html.includes("archive-attempts-bar"));
  assert.ok(html.includes("Parma"));
  assert.ok(html.includes("Juventus"));
  assert.ok(html.includes("Paris SG"));
  assert.ok(html.includes("loan"), "Loan styling must be displayed");
  assert.ok(html.includes('id="archive-answer"'));
  assert.ok(html.includes('id="archive-submit"'));
});

test("10. max attempts from backend: attempt count dots respect max_attempts dynamically from server", () => {
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
  assert.equal(usedDots + emptyDots, 4, "Total dots must dynamically match server max_attempts (4)");
});

test("11. canonical production max = 3: default fixtures and challenge views model exactly 3 attempts", () => {
  const defaultChallenge = createTestArchiveChallenge();
  assert.equal(defaultChallenge.max_attempts, 3, "Production max_attempts must be 3");
  assert.equal(defaultChallenge.attempts_left, 3, "Initial attempts_left must be 3");
  assert.equal(defaultChallenge.attempts_used, 0, "Initial attempts_used must be 0");

  const html = renderArchiveViews({
    view: "challenge",
    status: "challenge_ready",
    calendar: [],
    selectedDay: "2026-09-02",
    challenge: defaultChallenge,
    feedback: null,
    draftAnswer: "",
    challengeFinished: false,
    error: null,
  });

  const dots = (html.match(/archive-attempt-dot/g) || []).length;
  assert.equal(dots, 3, "Standard challenge view must render exactly 3 dots");
});

test("12. wrong guess: displays comparison clues and decrements attempts", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const guessResult = createTestArchiveGuessResult({
    status: "wrong",
    attempts_used: 1,
    attempts_left: 2,
    comparison: {
      name: "Pirlo",
      clues: [
        { key: "feedback.nationality_same", args: {} },
        { key: "feedback.position_diff", args: {} },
      ],
    },
  });
  const { restore: restoreFetch } = captureFetchRequests(guessResult);

  try {
    const controller = new ArchiveController();
    (controller as any).updateState({
      view: "challenge",
      status: "challenge_ready",
      selectedDay: "2026-09-02",
      challenge: createTestArchiveChallenge({ day: "2026-09-02", attempts_used: 0, attempts_left: 3 }),
    });

    const result = await controller.submitGuess("Pirlo");
    assert.ok(result);
    assert.equal(result.status, "wrong");

    const state = controller.getState();
    assert.equal(state.challenge?.attempts_used, 1);
    assert.equal(state.challenge?.attempts_left, 2);
    assert.equal(state.challengeFinished, false, "Game is still active with attempts left");

    const html = renderArchiveViews(state);
    assert.ok(html.includes("feedback no"));
    assert.ok(html.includes("Tentativi rimasti: 2"));
    assert.ok(html.includes('id="archive-guess-form"'), "Input form must remain visible while active");
  } finally {
    restoreFetch();
    restoreTg();
  }
});

test("13. correct guess: displays success feedback, share button, and hides input form", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const guessResult = createTestArchiveGuessResult({
    status: "correct",
    attempts_used: 1,
    attempts_left: 2,
    share: {
      text: "Ho recuperato la sfida del 02/09",
      url: "https://t.me/share/url?url=test",
    },
  });
  const { restore: restoreFetch } = captureFetchRequests(guessResult);

  try {
    const controller = new ArchiveController();
    (controller as any).updateState({
      view: "challenge",
      status: "challenge_ready",
      selectedDay: "2026-09-02",
      challenge: createTestArchiveChallenge({ day: "2026-09-02", attempts_used: 0, attempts_left: 3 }),
    });

    const result = await controller.submitGuess("Buffon");
    assert.ok(result);
    assert.equal(result.status, "correct");

    const state = controller.getState();
    assert.equal(state.challengeFinished, true);
    assert.equal(state.challenge?.solved, true);

    const html = renderArchiveViews(state);
    assert.ok(html.includes("feedback ok"));
    assert.ok(html.includes("Recuperata! Bel recupero."));
    assert.ok(html.includes('id="archive-share"'), "Share button must be rendered on correct guess");
    assert.ok(!html.includes('id="archive-guess-form"'), "Input form must be hidden when solved");
  } finally {
    restoreFetch();
    restoreTg();
  }
});

test("14. final wrong guess: reveals correct answer, share card, and hides input form when attempts_left === 0", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const guessResult = createTestArchiveGuessResult({
    status: "wrong",
    attempts_used: 3,
    attempts_left: 0,
    answer: "Alessandro Del Piero",
    share: {
      text: "Ho giocato la sfida del 02/09",
      url: "https://t.me/share/url?url=test",
    },
  });
  const { restore: restoreFetch } = captureFetchRequests(guessResult);

  try {
    const controller = new ArchiveController();
    (controller as any).updateState({
      view: "challenge",
      status: "challenge_ready",
      selectedDay: "2026-09-02",
      challenge: createTestArchiveChallenge({ day: "2026-09-02", attempts_used: 2, attempts_left: 1 }),
    });

    const result = await controller.submitGuess("Zidane");
    assert.ok(result);
    assert.equal(result.status, "wrong");

    const state = controller.getState();
    assert.equal(state.challengeFinished, true, "Terminal state reached on final wrong guess");
    assert.equal(state.challenge?.attempts_left, 0);

    const html = renderArchiveViews(state);
    assert.ok(html.includes("feedback no"));
    assert.ok(html.includes("Alessandro Del Piero"), "Answer must be revealed on 0 attempts left");
    assert.ok(html.includes('id="archive-share"'), "Share button must be present on game over");
    assert.ok(!html.includes('id="archive-guess-form"'), "Input form must be hidden when exhausted");
  } finally {
    restoreFetch();
    restoreTg();
  }
});

test("15. refused/already_solved: displays localized already_solved refusal message", () => {
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

  assert.ok(html.includes("Hai già recuperato questa giornata."));
  assert.ok(!html.includes('id="archive-guess-form"'), "Guess form must be hidden on refused/already_solved");
  assert.ok(html.includes('id="archive-back"'), "Back button must be available");
});

test("16. refused/no_attempts: displays localized no_attempts refusal message", () => {
  setLanguage("it");
  const feedback = createTestArchiveGuessResult({
    status: "refused",
    reason: "no_attempts",
  });

  const html = renderArchiveViews({
    view: "challenge",
    status: "challenge_ready",
    calendar: [],
    selectedDay: "2026-09-02",
    challenge: createTestArchiveChallenge({ attempts_used: 3, attempts_left: 0 }),
    feedback,
    draftAnswer: "",
    challengeFinished: true,
    error: null,
  });

  assert.ok(html.includes("Hai esaurito i tentativi per questa giornata."));
  assert.ok(!html.includes("Hai già recuperato"), "Must NOT display already_solved message for no_attempts");
  assert.ok(!html.includes('id="archive-guess-form"'), "Guess form must be hidden on refused/no_attempts");
  assert.ok(html.includes('id="archive-back"'), "Back button must be available");
});

test("17. unknown refused reason: displays generic localized refusal message", () => {
  setLanguage("it");
  const feedback = createTestArchiveGuessResult({
    status: "refused",
    reason: "rate_limited_or_future_reason",
  });

  const html = renderArchiveViews({
    view: "challenge",
    status: "challenge_ready",
    calendar: [],
    selectedDay: "2026-09-02",
    challenge: createTestArchiveChallenge(),
    feedback,
    draftAnswer: "",
    challengeFinished: true,
    error: null,
  });

  assert.ok(html.includes("Non è possibile giocare questa giornata."));
  assert.ok(!html.includes('id="archive-guess-form"'));
  assert.ok(html.includes('id="archive-back"'));
});

test("18. refused payload without counters: handles response containing only status and reason without throwing", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const restoreFetch = mockFetchResponse({
    status: "refused",
    reason: "already_solved",
  });

  try {
    const controller = new ArchiveController();
    (controller as any).updateState({
      view: "challenge",
      status: "challenge_ready",
      selectedDay: "2026-09-02",
      challenge: createTestArchiveChallenge({ attempts_used: 1, attempts_left: 2 }),
    });

    const result = await controller.submitGuess("Del Piero");
    assert.ok(result);
    assert.equal(result.status, "refused");
    assert.equal((result as any).attempts_left, undefined);
  } finally {
    restoreFetch();
    restoreTg();
  }
});

test("19. counters survive refused response: loaded challenge attempts_used and attempts_left are never overwritten with undefined", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const restoreFetch = mockFetchResponse({
    status: "refused",
    reason: "no_attempts",
  });

  try {
    const controller = new ArchiveController();
    (controller as any).updateState({
      view: "challenge",
      status: "challenge_ready",
      selectedDay: "2026-09-02",
      challenge: createTestArchiveChallenge({ attempts_used: 3, attempts_left: 0 }),
    });

    await controller.submitGuess("Pirlo");

    const state = controller.getState();
    assert.equal(state.challenge?.attempts_used, 3, "attempts_used must survive intact");
    assert.equal(state.challenge?.attempts_left, 0, "attempts_left must survive intact");
    assert.notEqual(state.challenge?.attempts_used, undefined);
    assert.notEqual(state.challenge?.attempts_left, undefined);
  } finally {
    restoreFetch();
    restoreTg();
  }
});

test("20. no_challenge payload without counters: handles response containing only status without throwing", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const restoreFetch = mockFetchResponse({
    status: "no_challenge",
  });

  try {
    const controller = new ArchiveController();
    (controller as any).updateState({
      view: "challenge",
      status: "challenge_ready",
      selectedDay: "2026-09-02",
      challenge: createTestArchiveChallenge({ attempts_used: 1, attempts_left: 2 }),
    });

    const result = await controller.submitGuess("Pirlo");
    assert.ok(result);
    assert.equal(result.status, "no_challenge");
    assert.equal((result as any).attempts_left, undefined);
  } finally {
    restoreFetch();
    restoreTg();
  }
});

test("21. no_challenge disables gameplay: hides guess input, shows dayUnavailable message, and provides Back to Archive", () => {
  setLanguage("it");
  const feedback = createTestArchiveGuessResult({
    status: "no_challenge",
  });

  const html = renderArchiveViews({
    view: "challenge",
    status: "challenge_ready",
    calendar: [],
    selectedDay: "2026-09-02",
    challenge: createTestArchiveChallenge(),
    feedback,
    draftAnswer: "",
    challengeFinished: true,
    error: null,
  });

  assert.ok(html.includes("Questa giornata non è più disponibile."));
  assert.ok(!html.includes('id="archive-guess-form"'), "Guess form must be hidden on no_challenge");
  assert.ok(html.includes('id="archive-back"'), "Back to Calendar button must be present");
});

test("22. challenge initially loaded with attempts_left = 0: displays exhausted message, hides input form, and keeps Back button", async () => {
  setLanguage("it");
  const { restore: restoreTg } = setupTestTelegram();
  const exhaustedChallenge = createTestArchiveChallenge({
    solved: false,
    attempts_used: 3,
    attempts_left: 0,
    max_attempts: 3,
  });
  const { requests, restore: restoreFetch } = captureFetchRequests(exhaustedChallenge);

  try {
    const controller = new ArchiveController();
    await controller.openDay("2026-09-02");

    const state = controller.getState();
    assert.equal(state.challenge?.attempts_left, 0);
    assert.equal(state.challengeFinished, true, "Exhausted challenge must be flagged as challengeFinished");

    const html = renderArchiveViews(state);
    assert.ok(html.includes("Hai esaurito i tentativi per questa giornata."), "Must show exhausted message");
    assert.ok(html.includes('role="status" aria-live="polite"'), "Exhausted alert must have accessible live region");
    assert.ok(!html.includes('id="archive-guess-form"'), "Input form must NOT be rendered");
    assert.ok(html.includes('id="archive-back"'), "Back button must be available");

    // Submitting a guess must be completely blocked
    const submitResult = await controller.submitGuess("Pirlo");
    assert.equal(submitResult, null);
    // No guess request dispatched
    assert.equal(requests.filter((r) => r.url.includes("/app/api/guess")).length, 0);
  } finally {
    restoreFetch();
    restoreTg();
  }
});

test("23. double submit: second guess is blocked while submission is in flight", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  let guessCallCount = 0;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () => {
    guessCallCount++;
    await new Promise((r) => setTimeout(r, 40));
    return {
      ok: true,
      status: 200,
      json: async () => createTestArchiveGuessResult({ attempts_used: 1, attempts_left: 2 }),
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

test("24. stale guess response: older out-of-order guess response cannot overwrite newer response", async () => {
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

test("25. stale Day A response cannot overwrite Day B: guess response for prior day is discarded after day switch", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const controller = new ArchiveController();

  let resolveDayAGuess: (v: any) => void;
  const dayAPromise = new Promise((resolve) => {
    resolveDayAGuess = resolve;
  });

  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (url: string, opts: any) => {
    const body = opts?.body ? JSON.parse(opts.body) : {};
    if (body.day === "2026-09-01" && url.includes("/app/api/guess")) {
      await dayAPromise;
      return {
        ok: true,
        status: 200,
        json: async () => createTestArchiveGuessResult({ status: "correct", attempts_used: 1 }),
      } as Response;
    }
    if (body.day === "2026-09-02" && url.includes("/app/api/calendar")) {
      return {
        ok: true,
        status: 200,
        json: async () => createTestArchiveChallenge({ day: "2026-09-02", solved: false }),
      } as Response;
    }
    return { ok: true, status: 200, json: async () => ({}) } as Response;
  }) as any;

  try {
    // Open Day A
    (controller as any).updateState({
      view: "challenge",
      status: "challenge_ready",
      selectedDay: "2026-09-01",
      challenge: createTestArchiveChallenge({ day: "2026-09-01" }),
    });

    // Start guess on Day A
    const p1 = controller.submitGuess("Buffon");

    // Navigate to Day B while guess on Day A is still in flight
    await controller.openDay("2026-09-02");
    assert.equal(controller.getState().selectedDay, "2026-09-02");
    assert.equal(controller.getState().challenge?.solved, false);

    // Resolve Day A's guess
    resolveDayAGuess!({});
    const guessRes = await p1;
    assert.equal(guessRes, null, "Stale guess response for Day A must be discarded");

    // State on Day B must NOT be corrupted with Day A's correct feedback or solved status
    const finalState = controller.getState();
    assert.equal(finalState.selectedDay, "2026-09-02");
    assert.equal(finalState.feedback, null);
    assert.equal(finalState.challenge?.solved, false);
  } finally {
    globalThis.fetch = originalFetch;
    restoreTg();
  }
});

test("26. back before finish: switches view back to calendar without re-fetching if challenge was unfinished", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  let fetchCount = 0;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () => {
    fetchCount++;
    return { ok: true, status: 200, json: async () => ({}) } as Response;
  }) as any;

  try {
    const controller = new ArchiveController();
    (controller as any).updateState({
      view: "challenge",
      status: "challenge_ready",
      selectedDay: "2026-09-02",
      challengeFinished: false, // NOT finished!
      calendar: createTestCalendar(),
    });

    await controller.backToCalendar();

    assert.equal(controller.getState().view, "calendar");
    assert.equal(controller.getState().selectedDay, null);
    assert.equal(fetchCount, 0, "No network request should be made when returning before finish");
  } finally {
    globalThis.fetch = originalFetch;
    restoreTg();
  }
});

test("27. back after terminal result: triggers automatic calendar refresh when returning from finished challenge", async () => {
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
  } finally {
    globalThis.fetch = originalFetch;
    restoreTg();
  }
});

test("28. backend calendar refresh after recovery: refreshed calendar shows updated day status from server", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () => {
    return {
      ok: true,
      status: 200,
      json: async () => ({
        days: [
          createTestArchiveDay({ day: "2026-09-02", status: "recovered", playable: false, number: 41 }),
        ],
      }),
    } as Response;
  }) as any;

  try {
    const controller = new ArchiveController();
    (controller as any).updateState({
      view: "challenge",
      status: "challenge_ready",
      selectedDay: "2026-09-02",
      challengeFinished: true,
    });

    await controller.backToCalendar();

    const state = controller.getState();
    assert.equal(state.calendar.length, 1);
    assert.equal(state.calendar[0].status, "recovered", "Status must update authoritatively to recovered from backend");
    assert.equal(state.calendar[0].playable, false);
  } finally {
    globalThis.fetch = originalFetch;
    restoreTg();
  }
});

test("29. IT: Italian localization renders Italian archive strings", () => {
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

test("30. EN: English localization renders English archive strings", () => {
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

test("31. ES: Spanish localization renders Spanish archive strings", () => {
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

test("32. localized accessibility labels: calendar days have rich aria-label and non-color cues", () => {
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

  assert.ok(html.includes('aria-label="01/09/26 · Indovinata · 3 tentativi"'), "Rich aria-label must include status and attempts");
  assert.ok(html.includes('<span class="archive-day-status-text sr-only">Indovinata</span>'), "Screen reader text must be included");
  assert.ok(html.includes("✅"), "Visual icon cue must accompany color");
});

test("33. no prototype data: prototype fixtures and notice never appear in real archive runtime", () => {
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
  assert.ok(!html.includes("prototype-notice"));
});

test("34. no authenticated renderPrototype('archive'): verified across app navigation and page rendering", () => {
  const pageHtml = renderArchivePage({
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

  assert.ok(!pageHtml.includes("prototype-banner"));
  assert.ok(!pageHtml.includes("PROTOTYPE"));
  assert.ok(pageHtml.includes("archive-calendar"));
});

test("35. legacy /app unchanged: legacy index.html, client.js, and arena.js remain untouched", () => {
  const legacyHtmlPath = path.resolve(process.cwd(), "webapp/index.html");
  const legacyClientPath = path.resolve(process.cwd(), "webapp/client.js");
  const legacyArenaPath = path.resolve(process.cwd(), "webapp/arena.js");

  assert.ok(fs.existsSync(legacyHtmlPath), "webapp/index.html must exist");
  assert.ok(fs.existsSync(legacyClientPath), "webapp/client.js must exist");
  assert.ok(fs.existsSync(legacyArenaPath), "webapp/arena.js must exist");

  const legacyHtml = fs.readFileSync(legacyHtmlPath, "utf-8");
  assert.ok(legacyHtml.includes("function statsTab()"), "Legacy statsTab must be present");
  assert.ok(legacyHtml.includes("function leaguesTab()"), "Legacy leaguesTab must be present");
  assert.ok(legacyHtml.includes("client.js"), "Legacy client.js script tag must be present");
});

// ===========================================================================
// ADDITIONAL ARCHIVE INTEGRATION & RESILIENCE TESTS
// ===========================================================================

test("36. calendar API error renders accessible error state with retry button", async () => {
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

test("37. calendar retry button triggers new fetch", async () => {
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

test("38. duplicate in-flight loadCalendar calls are ignored (idempotency)", async () => {
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
    const p1 = controller.init();
    const p2 = controller.init();
    await Promise.all([p1, p2]);

    assert.equal(callCount, 1, "Only one network request should be dispatched");
  } finally {
    globalThis.fetch = originalFetch;
    restoreTg();
  }
});

test("39. stale out-of-order calendar responses are discarded via sequence guard", async () => {
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
    return {
      ok: true,
      status: 200,
      json: async () => ({ days: [createTestArchiveDay({ number: 2 }), createTestArchiveDay({ number: 3 })] }),
    } as Response;
  }) as any;

  try {
    const p1 = controller.refreshCalendar();
    const p2 = controller.refreshCalendar();

    await p2;
    assert.equal(controller.getState().calendar.length, 2);

    resolveFirst!({});
    await p1;

    assert.equal(controller.getState().calendar.length, 2);
    assert.equal(controller.getState().calendar[0].number, 2);
  } finally {
    globalThis.fetch = originalFetch;
    restoreTg();
  }
});

test("40. unavailable day / 404 response transitions to challenge_error with retry", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const restoreFetch = mockFetchError(404, "Not Found");

  try {
    const controller = new ArchiveController();
    await controller.openDay("2026-09-02");

    const state = controller.getState();
    assert.equal(state.status, "challenge_error");

    const html = renderArchiveViews(state);
    assert.ok(html.includes('id="archive-challenge-retry"'));
    assert.ok(html.includes('id="archive-back"'));
  } finally {
    restoreFetch();
    restoreTg();
  }
});

test("41. challenge loading state renders accessible spinner", () => {
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

  assert.ok(html.includes("loading-state"));
  assert.ok(html.includes("spinner"));
  assert.ok(html.includes('role="status"'));
});

test("42. DOM event wiring: day click opens challenge, back click returns, form submit guesses", async () => {
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
