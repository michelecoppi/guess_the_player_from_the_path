import { test } from "node:test";
import assert from "node:assert/strict";
import { DailyController } from "../../webapp/src/features/daily/controller";
import { renderDailyPage, attachDailyEventListeners } from "../../webapp/src/pages/DailyPage";
import {

  setupGlobalDom,
  setupTestTelegram,
  mockFetchResponse,
  mockFetchError,
  captureFetchRequests,
  createTestDailyChallenge,
} from "./helpers";
import { setLanguage } from "../../webapp/src/i18n";

test("DailyController: initial loading and successful challenge load", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const challengeFixture = createTestDailyChallenge({
    number: 42,
    difficulty_label: "Difficile",
    points: 150,
    attempts_used: 1,
    attempts_left: 4,
    solved: false,
  });

  const restoreFetch = mockFetchResponse({
    language: "it",
    user: { name: "Marco", points: 200, streak: 5 },
    today: challengeFixture,
  });

  try {
    const controller = new DailyController();
    assert.equal(controller.getState().status, "loading");

    await controller.init();

    const state = controller.getState();
    assert.equal(state.status, "ready");
    assert.equal(state.challenge?.number, 42);
    assert.equal(state.challenge?.points, 150);
    assert.equal(state.user?.name, "Marco");
    assert.equal(state.user?.streak, 5);
  } finally {
    restoreFetch();
    restoreTg();
  }
});

test("DailyController: API contract sends initData in JSON body for me, guess, hint, card", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const { requests, restore: restoreFetch } = captureFetchRequests({
    status: "ok",
    user: { name: "Marco" },
    today: createTestDailyChallenge(),
    attempts_used: 1,
    attempts_left: 4,
    hints_used: 0,
    image: "data:image/png;base64,fake",
  });

  try {
    const controller = new DailyController();
    await controller.init();

    // Verify /app/api/me payload
    assert.ok(requests.length >= 1);
    const meReq = requests[0];
    assert.equal(meReq.url, "/app/api/me");
    assert.equal(meReq.method, "POST");
    assert.ok(meReq.body.initData, "me request must include initData in body");

    // Guess submission
    await controller.submitGuess("Buffon");
    const guessReq = requests.find((r) => r.url === "/app/api/guess");
    assert.ok(guessReq, "guess request was sent");
    assert.equal(guessReq.body.answer, "Buffon");
    assert.ok(guessReq.body.initData, "guess request must include initData in body");

    // Hint request
    await controller.takeHint();
    const hintReq = requests.find((r) => r.url === "/app/api/hint");
    assert.ok(hintReq, "hint request was sent");
    assert.ok(hintReq.body.initData, "hint request must include initData in body");

    // Card request
    await controller.loadResultCard();
    const cardReq = requests.find((r) => r.url === "/app/api/card");
    assert.ok(cardReq, "card request was sent");
    assert.ok(cardReq.body.initData, "card request must include initData in body");
    assert.equal(typeof cardReq.body.attempts, "number");
    assert.equal(typeof cardReq.body.max_attempts, "number");
  } finally {
    restoreFetch();
    restoreTg();
  }
});

test("DailyController: correct guess transitions state to correct and awards points", async () => {
  const { restore: restoreTg } = setupTestTelegram();

  let callCount = 0;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (url: string) => {
    callCount++;
    if (String(url).endsWith("/me")) {
      return new Response(
        JSON.stringify({
          user: { name: "Marco", streak: 4 },
          today: createTestDailyChallenge({ solved: callCount > 1, attempts_used: 2 }),
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }
    if (String(url).endsWith("/guess")) {
      return new Response(
        JSON.stringify({
          status: "correct",
          attempts_used: 2,
          attempts_left: 3,
          points_awarded: 100,
          bonus: 1,
          streak: 4,
          share: { text: "Guess the Player #42 2/5", url: "https://t.me/share/url?text=foo" },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }
    return new Response(JSON.stringify({}), { status: 200 });
  }) as any;

  try {
    const controller = new DailyController();
    await controller.init();

    assert.equal(controller.getState().status, "ready");

    const result = await controller.submitGuess("Gianluigi Buffon");
    assert.ok(result);
    assert.equal(result.status, "correct");
    assert.equal(result.points_awarded, 100);

    const state = controller.getState();
    assert.equal(state.status, "correct");
    assert.ok(state.feedback);
    assert.equal(state.feedback.status, "correct");
    assert.ok(state.feedback.share);
  } finally {
    globalThis.fetch = originalFetch;
    restoreTg();
  }
});

test("DailyController: incorrect guess updates attempts and renders comparison clues", async () => {
  const { restore: restoreTg } = setupTestTelegram();

  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (url: string) => {
    if (String(url).endsWith("/me")) {
      return new Response(
        JSON.stringify({
          user: { name: "Marco" },
          today: createTestDailyChallenge({ solved: false, attempts_used: 2, attempts_left: 3 }),
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }
    if (String(url).endsWith("/guess")) {
      return new Response(
        JSON.stringify({
          status: "wrong",
          attempts_used: 2,
          attempts_left: 3,
          hints_used: 0,
          comparison: {
            name: "Cannavaro",
            clues: [
              { key: "feedback.nationality_same" },
              { key: "feedback.position_diff" },
              { key: "feedback.birth_before", args: { year: 1973 } },
            ],
          },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }
    return new Response(JSON.stringify({}), { status: 200 });
  }) as any;

  try {
    const controller = new DailyController();
    await controller.init();

    const result = await controller.submitGuess("Cannavaro");
    assert.ok(result);
    assert.equal(result.status, "wrong");
    assert.equal(result.attempts_left, 3);

    const state = controller.getState();
    assert.equal(state.status, "incorrect");
    assert.equal(state.feedback?.comparison?.name, "Cannavaro");
    assert.equal(state.feedback?.comparison?.clues.length, 3);

    const html = renderDailyPage(state);
    assert.ok(html.includes("Sbagliato."));
    assert.ok(html.includes("Tentativi rimasti: 3."));
    assert.ok(html.includes("Cannavaro"));
    assert.ok(html.includes("Stessa nazionalità"));
    assert.ok(html.includes("Ruolo diverso"));
    assert.ok(html.includes("Più vecchio del 1973"));
  } finally {
    globalThis.fetch = originalFetch;
    restoreTg();
  }
});

test("DailyController: prevents double submit while request is in flight", async () => {
  const { restore: restoreTg } = setupTestTelegram();

  let guessRequests = 0;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (url: string) => {
    if (String(url).endsWith("/me")) {
      return new Response(
        JSON.stringify({
          user: { name: "Marco" },
          today: createTestDailyChallenge(),
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }
    if (String(url).endsWith("/guess")) {
      guessRequests++;
      // simulate network latency
      await new Promise((resolve) => setTimeout(resolve, 50));
      return new Response(
        JSON.stringify({
          status: "wrong",
          attempts_used: 2,
          attempts_left: 3,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }
    return new Response(JSON.stringify({}), { status: 200 });
  }) as any;

  try {
    const controller = new DailyController();
    await controller.init();

    // Fire first guess
    const p1 = controller.submitGuess("Player 1");
    assert.equal(controller.getState().status, "submitting");

    // Attempt second guess concurrently
    const p2 = controller.submitGuess("Player 2");
    assert.equal(await p2, null, "Concurrent second guess must be blocked");

    await p1;
    assert.equal(guessRequests, 1, "Only one guess network request should have been dispatched");
  } finally {
    globalThis.fetch = originalFetch;
    restoreTg();
  }
});

test("DailyController: handles completed Daily and already-played state", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const restoreFetch = mockFetchResponse({
    user: { name: "Marco" },
    today: createTestDailyChallenge({
      solved: true,
      attempts_used: 1,
      attempts_left: 4,
    }),
  });

  try {
    const controller = new DailyController();
    await controller.init();

    const state = controller.getState();
    assert.equal(state.status, "completed");

    const html = renderDailyPage(state);
    assert.ok(html.includes("Indovinata"), "Status pill should show Indovinata");
    assert.ok(!html.includes('id="submit"'), "Submit button must not be present when already completed");
    assert.ok(!html.includes('id="hint"'), "Hint button must not be present when already completed");
  } finally {
    restoreFetch();
    restoreTg();
  }
});

test("DailyController: handles unavailable challenge and error with retry", async () => {
  const { restore: restoreTg } = setupTestTelegram();

  // 1. Unavailable challenge
  let restoreFetch = mockFetchResponse({
    user: { name: "Marco" },
    today: { available: false, solved: false },
  });

  try {
    const controller = new DailyController();
    await controller.init();
    assert.equal(controller.getState().status, "unavailable");
    const html = renderDailyPage(controller.getState());
    assert.ok(html.includes("Nessuna sfida disponibile"));
    restoreFetch();

    // 2. Error state
    restoreFetch = mockFetchError(500, "Server non raggiungibile");
    await controller.loadDailyData();
    assert.equal(controller.getState().status, "error");
    const errorHtml = renderDailyPage(controller.getState());
    assert.ok(errorHtml.includes("Server non raggiungibile"));
    assert.ok(errorHtml.includes("daily-retry"));
    restoreFetch();

    // 3. Retry recovery
    restoreFetch = mockFetchResponse({
      user: { name: "Marco" },
      today: createTestDailyChallenge(),
    });
    controller.retry();
    await controller.loadDailyData();
    assert.equal(controller.getState().status, "ready");
  } finally {
    restoreFetch();
    restoreTg();
  }
});

test("DailyPage: renders exact clues across Italian, English, and Spanish", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const { cleanup } = setupGlobalDom();

  const feedback = {
    status: "wrong" as const,
    attempts_used: 2,
    attempts_left: 3,
    comparison: {
      name: "Zidane",
      clues: [
        { key: "feedback.nationality_diff" },
        { key: "feedback.position_same" },
        { key: "feedback.birth_same", args: { year: 1972 } },
      ],
    },
  };

  try {
    // 1. Italian
    setLanguage("it");
    let html = renderDailyPage({
      status: "incorrect",
      challenge: createTestDailyChallenge({ solved: false }),
      feedback,
      squaresSymbols: { correct: "🟩", wrong: "🟥", unused: "⬜" },
      inputValue: "",
    });
    assert.ok(html.includes("Rispetto a <b>Zidane</b>:"));
    assert.ok(html.includes("Nazionalità diversa"));
    assert.ok(html.includes("Stesso ruolo"));
    assert.ok(html.includes("Stesso anno: 1972"));

    // 2. English
    setLanguage("en");
    html = renderDailyPage({
      status: "incorrect",
      challenge: createTestDailyChallenge({ solved: false }),
      feedback,
      squaresSymbols: { correct: "🟩", wrong: "🟥", unused: "⬜" },
      inputValue: "",
    });
    assert.ok(html.includes("Compared with <b>Zidane</b>:"));
    assert.ok(html.includes("Different nationality"));
    assert.ok(html.includes("Same position"));
    assert.ok(html.includes("Same year: 1972"));

    // 3. Spanish
    setLanguage("es");
    html = renderDailyPage({
      status: "incorrect",
      challenge: createTestDailyChallenge({ solved: false }),
      feedback,
      squaresSymbols: { correct: "🟩", wrong: "🟥", unused: "⬜" },
      inputValue: "",
    });
    assert.ok(html.includes("Respecto a <b>Zidane</b>:"));
    assert.ok(html.includes("Nacionalidad distinta"));
    assert.ok(html.includes("Misma posición"));
    assert.ok(html.includes("Mismo año: 1972"));
  } finally {
    setLanguage("it");
    cleanup();
    restoreTg();
  }
});

test("DailyPage: DOM event wiring triggers controller guess, enter key, hint, and share", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const { container, cleanup } = setupGlobalDom();

  let submittedGuess: string | null = null;
  let hintRequested = false;
  let shareOpened = false;

  const mockController = {
    getState: () => ({
      status: "ready" as const,
      challenge: createTestDailyChallenge(),
      squaresSymbols: { correct: "🟩", wrong: "🟥", unused: "⬜" },
      inputValue: "",
      feedback: {
        status: "wrong" as const,
        attempts_left: 3,
        share: { text: "share text", url: "https://t.me/share" },
      },
    }),
    setInputValue: (_v: string) => {},
    submitGuess: async (val: string) => {
      submittedGuess = val;
      return null;
    },
    takeHint: async () => {
      hintRequested = true;
    },
    loadResultCard: async () => {},
    openShareUrl: () => {
      shareOpened = true;
    },
    retry: () => {},
  } as unknown as DailyController;

  try {
    container.innerHTML = renderDailyPage(mockController.getState() as any);
    attachDailyEventListeners(container, mockController);

    const input = container.querySelector<HTMLInputElement>("#answer");
    const submitBtn = container.querySelector<HTMLButtonElement>("#submit");
    const hintBtn = container.querySelector<HTMLButtonElement>("#hint");
    const shareBtn = container.querySelector<HTMLButtonElement>("#share");

    assert.ok(input);
    assert.ok(submitBtn);
    assert.ok(hintBtn);
    assert.ok(shareBtn);

    // Test click on submit
    input.value = "Totti";
    submitBtn.click();
    assert.equal(submittedGuess, "Totti");

    // Test enter key
    input.value = "Baggio";
    input.dispatchEvent(new (window as any).KeyboardEvent("keydown", { key: "Enter" }));
    assert.equal(submittedGuess, "Baggio");

    // Test hint click
    hintBtn.click();
    assert.equal(hintRequested, true);

    // Test share click
    shareBtn.click();
    assert.equal(shareOpened, true);
  } finally {
    cleanup();
    restoreTg();
  }
});
