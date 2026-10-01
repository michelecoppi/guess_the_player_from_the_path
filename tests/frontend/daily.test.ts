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

test("first Daily load is lightweight and the one-time guide is dismissible", async () => {
  const { cleanup } = setupGlobalDom();
  const { restore: restoreTg } = setupTestTelegram();
  const { requests, restore: restoreFetch } = captureFetchRequests({
    language: "it",
    user: { name: "Nuovo", players_guessed: 0 },
    today: createTestDailyChallenge({ attempts_used: 0, attempts_left: 3 }),
  });
  try {
    const controller = new DailyController();
    await controller.init();
    assert.equal(requests[0].body.lightweight, true);
    assert.equal(controller.getState().introVisible, true);
    assert.match(renderDailyPage(controller.getState()), /daily-intro-dismiss/);
    controller.dismissIntro();
    assert.equal(controller.getState().introVisible, false);
    const reopened = new DailyController();
    await reopened.init();
    assert.equal(reopened.getState().introVisible, false);
  } finally {
    restoreFetch();
    restoreTg();
    cleanup();
  }
});

test("Daily 409 reloads the new day and reports that no attempt was spent", async () => {
  const { cleanup } = setupGlobalDom();
  const { restore: restoreTg } = setupTestTelegram();
  const originalFetch = globalThis.fetch;
  let day = "2026-09-26";
  const sent: Record<string, unknown>[] = [];
  globalThis.fetch = (async (url: string, options: RequestInit) => {
    const body = JSON.parse(String(options.body));
    if (String(url).endsWith("/guess")) {
      sent.push(body);
      day = "2026-09-27";
      return new Response(JSON.stringify({ detail: "daily_changed" }), { status: 409 });
    }
    return new Response(JSON.stringify({
      user: { name: "Marco", players_guessed: 2 },
      today: createTestDailyChallenge({ day }),
    }), { status: 200 });
  }) as typeof fetch;
  try {
    const controller = new DailyController();
    await controller.init();
    assert.equal(await controller.submitGuess("Buffon"), null);
    assert.equal(sent[0].expected_day, "2026-09-26");
    assert.equal(controller.getState().challenge?.day, "2026-09-27");
    assert.equal(controller.getState().status, "ready");
    assert.match(controller.getState().errorMessage || "", /nuova giornata/);
  } finally {
    globalThis.fetch = originalFetch;
    restoreTg();
    cleanup();
  }
});

test("a wrong answer that carries today's Daily needs no second /me (#259)", async () => {
  const { cleanup } = setupGlobalDom();
  const { restore: restoreTg } = setupTestTelegram();
  const originalFetch = globalThis.fetch;
  const urls: string[] = [];
  const day = "2026-09-26";
  globalThis.fetch = (async (url: string) => {
    urls.push(String(url));
    if (String(url).endsWith("/guess")) {
      return new Response(JSON.stringify({
        status: "wrong", attempts_used: 1, attempts_left: 2, hints_used: 0,
        today: createTestDailyChallenge({ day, attempts_used: 1, attempts_left: 2 }),
      }), { status: 200 });
    }
    return new Response(JSON.stringify({
      user: { name: "Marco", players_guessed: 2 },
      today: createTestDailyChallenge({ day, attempts_used: 0, attempts_left: 3 }),
    }), { status: 200 });
  }) as typeof fetch;
  try {
    const controller = new DailyController();
    await controller.init();
    const result = await controller.submitGuess("Buffon");
    assert.equal(result?.status, "wrong");
    assert.deepEqual(urls.map((u) => u.split("/").pop()), ["me", "guess"]);
    assert.equal(controller.getState().challenge?.attempts_left, 2);
    assert.equal(controller.getState().status, "incorrect");
    assert.equal(controller.getState().user?.name, "Marco");
  } finally {
    globalThis.fetch = originalFetch;
    restoreTg();
    cleanup();
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
    assert.equal(guessReq.body.expected_day, createTestDailyChallenge().day);

    // Hint request
    await controller.takeHint();
    const hintReq = requests.find((r) => r.url === "/app/api/hint");
    assert.ok(hintReq, "hint request was sent");
    assert.ok(hintReq.body.initData, "hint request must include initData in body");
    assert.equal(hintReq.body.expected_day, createTestDailyChallenge().day);

    // Card request
    await controller.loadResultCard();
    const cardReq = requests.find((r) => r.url === "/app/api/card");
    assert.ok(cardReq, "card request was sent");
    assert.ok(cardReq.body.initData, "card request must include initData in body");
    assert.deepEqual(Object.keys(cardReq.body), ["initData"], "card result must come from server state");
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
      // Two misses, one hint used: the second hint is available.
      challenge: createTestDailyChallenge({ attempts_used: 2, attempts_left: 3 }),
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
    shareResult: () => {
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

test("DailyController: a FEATURE_DISABLED refusal shows a localized notice instead of the raw code", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  setLanguage("en");
  let restoreFetch = mockFetchResponse({
    user: { name: "Marco" },
    today: createTestDailyChallenge(),
    features: { daily_ui: false, hints: false },
  });

  try {
    const controller = new DailyController();
    await controller.init();
    restoreFetch();

    restoreFetch = mockFetchResponse(
      { detail: "feature_disabled", code: "FEATURE_DISABLED", feature: "daily_ui" },
      403,
    );
    assert.equal(await controller.submitGuess("Buffon"), null);
    assert.equal(controller.getState().errorMessage, "This feature is temporarily unavailable. Please try again later.");

    controller.getState().errorMessage = undefined;
    await controller.takeHint();
    assert.equal(controller.getState().errorMessage, "This feature is temporarily unavailable. Please try again later.");
    assert.ok(!renderDailyPage(controller.getState()).includes("feature_disabled"));
  } finally {
    restoreFetch();
    restoreTg();
    setLanguage("it");
  }
});

test("DailyPage: the hint stays locked until the first wrong guess (#277)", () => {
  setLanguage("it");
  const base = { status: "ready" as const, squaresSymbols: { correct: "🟩", wrong: "🟥", unused: "⬜" }, inputValue: "" };
  const fresh = renderDailyPage({ ...base, challenge: createTestDailyChallenge({ attempts_used: 0, attempts_left: 3, hints: { total: 2, used: 0, taken: [] } }) } as any);
  assert.match(fresh, /<button[^>]*id="hint"[^>]* disabled/);
  assert.ok(fresh.includes("Gli indizi si sbloccano dopo il primo tentativo sbagliato"));

  const afterMiss = renderDailyPage({ ...base, challenge: createTestDailyChallenge({ attempts_used: 1, attempts_left: 2, hints: { total: 2, used: 0, taken: [] } }) } as any);
  assert.doesNotMatch(afterMiss, /<button[^>]*id="hint"[^>]* disabled/);
  assert.ok(afterMiss.includes("2 indizi rimasti"));

  // One hint per wrong guess: after one miss and one hint, the next waits for another miss.
  const oneEach = renderDailyPage({ ...base, challenge: createTestDailyChallenge({ attempts_used: 1, attempts_left: 2, hints: { total: 2, used: 1, taken: ["Nazionalità: Italia"] } }) } as any);
  assert.match(oneEach, /<button[^>]*id="hint"[^>]* disabled/);
  assert.ok(oneEach.includes("Il prossimo indizio si sblocca dopo un altro tentativo sbagliato"));

  const easy = renderDailyPage({ ...base, challenge: createTestDailyChallenge({ difficulty: "easy", attempts_used: 1, attempts_left: 2, hints: { total: 0, used: 0, taken: [] } }) } as any);
  assert.ok(!easy.includes('id="hint"'));
  assert.ok(easy.includes("Le sfide facili non hanno indizi"));
});

test("DailyController: a refused hint resyncs and tells the player why (#277)", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  setLanguage("it");
  const today = createTestDailyChallenge({ attempts_used: 0, attempts_left: 3, hints: { total: 2, used: 0, taken: [] } });
  const calls: string[] = [];
  const restoreFetch = mockFetchResponse((input: RequestInfo | URL) => {
    const url = String(input);
    calls.push(url);
    if (url.endsWith("/hint")) return { status: "refused", reason: "needs_attempt", total: 2 };
    return { language: "it", user: { name: "Marco" }, today };
  });

  try {
    const controller = new DailyController();
    await controller.init();
    await controller.takeHint();
    const state = controller.getState();
    assert.equal(state.errorMessage, "Gli indizi si sbloccano dopo il primo tentativo sbagliato");
    assert.equal(state.hintLoading, false);
    assert.equal(calls.filter((u) => u.endsWith("/me")).length, 2, "refusal reloads today's state");
  } finally {
    restoreFetch();
    restoreTg();
  }
});

test("DailyController: a revealed hint shows up after reloading today (#277)", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  setLanguage("it");
  let hintTaken = false;
  const restoreFetch = mockFetchResponse((input: RequestInfo | URL) => {
    if (String(input).endsWith("/hint")) {
      hintTaken = true;
      return { status: "ok", index: 1, total: 2, text: "Nazionalità: Italia" };
    }
    return {
      language: "it",
      user: { name: "Marco" },
      today: createTestDailyChallenge({
        attempts_used: 1, attempts_left: 2,
        hints: hintTaken ? { total: 2, used: 1, taken: ["Nazionalità: Italia"] } : { total: 2, used: 0, taken: [] },
      }),
    };
  });

  try {
    const controller = new DailyController();
    await controller.init();
    await controller.takeHint();
    const state = controller.getState();
    assert.equal(state.errorMessage, undefined);
    assert.ok(renderDailyPage(state).includes("Nazionalità: Italia"));
    // One miss, one hint: the second waits for another wrong guess.
    assert.ok(renderDailyPage(state).includes("Il prossimo indizio si sblocca dopo un altro tentativo sbagliato"));
  } finally {
    restoreFetch();
    restoreTg();
  }
});

function withClipboard(writeText: (text: string) => Promise<void>): () => void {
  const previous = Object.getOwnPropertyDescriptor(globalThis, "navigator");
  Object.defineProperty(globalThis, "navigator", {
    value: { clipboard: { writeText } },
    configurable: true,
    writable: true,
  });
  return () => {
    if (previous) Object.defineProperty(globalThis, "navigator", previous);
    else delete (globalThis as any).navigator;
  };
}

function finishedController(share?: { text: string; url: string }): DailyController {
  const controller = new DailyController();
  (controller as any).state.feedback = { status: "correct", attempts_used: 2, share };
  return controller;
}

test("DailyController: copying the result puts the shared text on the clipboard (#150)", async () => {
  setLanguage("it");
  const copied: string[] = [];
  const restore = withClipboard(async (text) => {
    copied.push(text);
  });
  try {
    const text = "⚽ Guess the Player #214\n🟥🟩⬜ 2/3\nRiesci a fare meglio? 👉 https://t.me/bot?start=ref_1_x";
    const controller = finishedController({ text, url: "https://t.me/share/url" });

    assert.equal(await controller.copyShareText(), true);
    assert.deepEqual(copied, [text]);
    assert.equal(controller.getState().copyNotice, "Risultato copiato: incollalo dove vuoi.");
  } finally {
    restore();
  }
});

test("DailyController: a refused clipboard shows how to copy by hand (#150)", async () => {
  setLanguage("en");
  const restore = withClipboard(async () => {
    throw new Error("denied");
  });
  try {
    const controller = finishedController({ text: "x", url: "https://t.me/share/url" });

    assert.equal(await controller.copyShareText(), false);
    assert.equal(controller.getState().copyNotice, "Couldn't copy: long-press the text to copy it.");
    assert.equal(await finishedController(undefined).copyShareText(), false);
  } finally {
    restore();
    setLanguage("it");
  }
});

test("DailyPage: the copy button sits next to share and shows its outcome (#150)", () => {
  setLanguage("it");
  const { container, cleanup } = setupGlobalDom();
  let copyCalls = 0;
  const state = {
    status: "correct" as const,
    challenge: createTestDailyChallenge({ solved: true, attempts_used: 2 }),
    squaresSymbols: { correct: "🟩", wrong: "🟥", unused: "⬜" },
    inputValue: "",
    copyNotice: "Risultato copiato: incollalo dove vuoi.",
    feedback: { status: "correct" as const, attempts_used: 2, share: { text: "t", url: "https://t.me/share" } },
  };
  const mockController = {
    getState: () => state,
    copyShareText: async () => {
      copyCalls++;
      return true;
    },
  } as unknown as DailyController;
  try {
    container.innerHTML = renderDailyPage(state as any);
    attachDailyEventListeners(container, mockController);

    const copy = container.querySelector<HTMLButtonElement>("#share-copy");
    assert.ok(container.querySelector("#share"));
    assert.ok(copy);
    // An icon button since #254: its name is the accessible label.
    assert.equal(copy.getAttribute("aria-label"), "Copia il risultato");
    assert.match(container.querySelector(".share-copy-notice")?.textContent ?? "", /Risultato copiato/);

    copy.click();
    assert.equal(copyCalls, 1);
  } finally {
    cleanup();
  }
});

// ---------------------------------------------------------------------------
// #254: compact end of the Daily
// ---------------------------------------------------------------------------

function finishedState(overrides: Record<string, unknown> = {}) {
  return {
    status: "correct" as const,
    challenge: createTestDailyChallenge({ solved: true, attempts_used: 2, attempts_left: 3 }),
    squaresSymbols: { correct: "🟩", wrong: "🟥", unused: "⬜" },
    inputValue: "",
    feedback: { status: "correct" as const, attempts_used: 2, points_awarded: 4, answer: "Shinji Kagawa",
      share: { text: "t", url: "https://t.me/share" } },
    ...overrides,
  };
}

test("#254 a finished Daily shows the result first and folds the career", () => {
  setLanguage("it");
  const html = renderDailyPage(finishedState() as any);
  const report = html.indexOf("match-report");
  const fold = html.indexOf('class="career-fold"');
  assert.ok(report > 0 && fold > report, "the report comes before the folded career");
  assert.match(html, /<details class="career-fold"><summary>[\s\S]*Mostra la carriera/);
  assert.match(html, /<details class="career-fold">[\s\S]*id="daily-career-card"/);
  assert.doesNotMatch(html, /<details class="career-fold" open/);
  // Still playing: the career stays open, first.
  const playing = renderDailyPage({ ...finishedState(), status: "idle", feedback: null,
    challenge: createTestDailyChallenge() } as any);
  assert.doesNotMatch(playing, /career-fold/);
  assert.ok(playing.indexOf('id="daily-career-card"') < playing.indexOf('id="daily-interaction-card"'));
});

test("#254 share, copy and card sit in one row; the card previews and enlarges in place", () => {
  setLanguage("it");
  const { container, cleanup } = setupGlobalDom();
  let cardLoads = 0;
  const controller = { loadResultCard: () => { cardLoads++; } } as unknown as DailyController;
  try {
    const row = renderDailyPage(finishedState() as any);
    assert.match(row, /class="report-actions">[\s\S]*id="share"[\s\S]*id="share-copy"[\s\S]*id="show-card"/);
    assert.doesNotMatch(row, /Vedi la figurina/, "no separate card button after a game");

    // Loading: a placeholder where the preview will be.
    assert.match(renderDailyPage(finishedState({ cardLoading: true }) as any), /report-card is-loading/);

    // Ready: a small preview; tapping it (or the card icon) enlarges it.
    container.innerHTML = renderDailyPage(finishedState({ cardImage: "data:image/png;base64,AAAA" }) as any);
    attachDailyEventListeners(container, controller);
    const card = container.querySelector<HTMLElement>(".report-card");
    const preview = container.querySelector<HTMLButtonElement>("#card-preview");
    assert.ok(card && preview);
    assert.equal(card.classList.contains("is-open"), false);
    preview.click();
    assert.equal(card.classList.contains("is-open"), true);
    assert.equal(preview.getAttribute("aria-expanded"), "true");
    container.querySelector<HTMLButtonElement>("#show-card")!.click();
    assert.equal(card.classList.contains("is-open"), false);
    assert.equal(cardLoads, 0);

    // Card not there (failed load): the icon asks for it.
    container.innerHTML = renderDailyPage(finishedState() as any);
    attachDailyEventListeners(container, controller);
    container.querySelector<HTMLButtonElement>("#show-card")!.click();
    assert.equal(cardLoads, 1);
  } finally {
    cleanup();
  }
});

test("#254 reopening a finished Daily keeps the card on request, no automatic render", () => {
  setLanguage("it");
  const html = renderDailyPage(finishedState({ feedback: null }) as any);
  assert.match(html, /id="show-card"[\s\S]*Vedi la figurina/);
  assert.doesNotMatch(html, /report-actions/);
});

// ---------------------------------------------------------------------------
// #271: the solution turns over like a football sticker
// ---------------------------------------------------------------------------

test("#271 a won Daily flips the sticker once, then shows it already turned", () => {
  setLanguage("it");
  const flipping = renderDailyPage(finishedState({ revealPending: true }) as any);
  assert.match(flipping, /class="reveal-card won flipping"/);
  assert.match(flipping, /reveal-back[\s\S]*\?[\s\S]*reveal-front[\s\S]*Nº 42[\s\S]*Era proprio lui[\s\S]*Shinji Kagawa/);

  const turned = renderDailyPage(finishedState({ revealPending: false }) as any);
  assert.match(turned, /class="reveal-card won"/);
  assert.match(turned, /class="report-player">Shinji Kagawa</);
});

test("#271 a lost Daily keeps the sticker face down until midnight", () => {
  setLanguage("it");
  const lost = finishedState({
    status: "completed",
    challenge: createTestDailyChallenge({ solved: false, attempts_used: 3, attempts_left: 0 }),
    feedback: { status: "wrong" as const, attempts_used: 3, attempts_left: 0, share: { text: "t", url: "https://t.me/share" } },
  });
  const html = renderDailyPage(lost as any);
  assert.match(html, /class="reveal-card sealed"[\s\S]*Nº 42 · si gira a mezzanotte/);
  assert.doesNotMatch(html, /reveal-front|report-player/, "today's name is never shown after a loss");

  setLanguage("en");
  assert.match(renderDailyPage(lost as any), /turns over at midnight/);
  setLanguage("it");
});

test("#271 drawing the flip consumes it and buzzes when the name shows", async (t) => {
  setLanguage("it");
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const { container, cleanup } = setupGlobalDom();
  const impacts: string[] = [];
  const { restore: restoreTg } = setupTestTelegram({
    HapticFeedback: {
      impactOccurred: (style: string) => { impacts.push(style); return undefined as any; },
      notificationOccurred: () => undefined as any,
      selectionChanged: () => undefined as any,
    },
  } as any);
  try {
    const controller = new DailyController();
    (controller as any).state = { ...controller.getState(), ...finishedState({ revealPending: true }) };
    container.innerHTML = renderDailyPage(controller.getState());
    attachDailyEventListeners(container, controller);
    assert.equal(controller.getState().revealPending, false);
    assert.deepEqual(impacts, []);
    t.mock.timers.tick(1000);
    assert.deepEqual(impacts, ["heavy"]);

    // A later render (card, copy notice) does not flip or buzz again.
    container.innerHTML = renderDailyPage(controller.getState());
    attachDailyEventListeners(container, controller);
    t.mock.timers.tick(1000);
    assert.doesNotMatch(container.innerHTML, /flipping/);
    assert.deepEqual(impacts, ["heavy"]);
  } finally {
    restoreTg();
    cleanup();
  }
});

test("#271 only a final answer that names the player starts the reveal", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const replies = [
    { status: "wrong", attempts_used: 1, attempts_left: 2 },
    { status: "correct", attempts_used: 2, attempts_left: 1, points_awarded: 4, answer: "Shinji Kagawa" },
  ];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (url: string) => {
    const body = String(url).endsWith("/guess")
      ? replies.shift()
      : { user: { name: "Marco" }, today: createTestDailyChallenge({ attempts_used: 0, attempts_left: 3 }) };
    return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as any;
  try {
    const controller = new DailyController();
    await controller.init();
    await controller.submitGuess("Nakata");
    assert.equal(controller.getState().revealPending, false);
    await controller.submitGuess("Kagawa");
    assert.equal(controller.getState().revealPending, true);
  } finally {
    globalThis.fetch = originalFetch;
    restoreTg();
  }
});
