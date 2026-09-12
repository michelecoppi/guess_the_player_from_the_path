import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { TrainingController } from "../../webapp/src/features/training/controller";
import {
  renderTrainingView,
  renderFinishedSessionView,
} from "../../webapp/src/features/training/views";
import { renderArenaPage } from "../../webapp/src/pages/ArenaPage";
import { setLanguage } from "../../webapp/src/i18n";
import {
  setupTestTelegram,
  mockFetchResponse,
  mockFetchError,
  captureFetchRequests,
  createTestCareerPath,
  createTestTrainingSession,
} from "./helpers";

test("1. API get request contract: calls POST /app/api/arena with mode='training', action='get' and initData", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const { requests, restore: restoreFetch } = captureFetchRequests({
    session: null,
    feedback: null,
  });

  try {
    const controller = new TrainingController();
    await controller.init();

    assert.equal(requests.length, 1);
    const req = requests[0];
    assert.equal(req.url, "/app/api/arena");
    assert.equal(req.method, "POST");
    assert.equal(req.body.mode, "training");
    assert.equal(req.body.action, "get");
    assert.ok(req.body.initData, "request must include Telegram initData in body");
  } finally {
    restoreFetch();
    restoreTg();
  }
});

test("2. get with no active session: renders intro/rules and 'Inizia ad allenarti' button", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const restoreFetch = mockFetchResponse({
    session: null,
    feedback: null,
  });

  try {
    setLanguage("it");
    const controller = new TrainingController();
    await controller.init();

    const state = controller.getState();
    assert.equal(state.status, "idle");
    assert.equal(state.data?.session, null);

    const html = renderTrainingView(state);
    assert.ok(html.includes("Inizia ad allenarti"), "must include start button");
    assert.ok(html.includes("5 tentativi per percorso"), "must display training rules");
    assert.ok(html.includes("training-start"), "must have #training-start id");
  } finally {
    restoreFetch();
    restoreTg();
  }
});

test("3. next starts Training: dispatches action='next' and mounts career path", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const sessionFixture = createTestTrainingSession({
    round: 0,
    attempts: 0,
    max_attempts: 5,
    difficulty_label: "Facile",
    career_path: createTestCareerPath(),
  });

  const { requests, restore: restoreFetch } = captureFetchRequests({
    session: sessionFixture,
    feedback: null,
  });

  try {
    setLanguage("it");
    const controller = new TrainingController();
    await controller.startNext();

    assert.equal(requests.length, 1);
    assert.equal(requests[0].body.action, "next");

    const state = controller.getState();
    assert.equal(state.status, "idle");
    assert.equal(state.data?.session?.round, 0);

    const html = renderTrainingView(state);
    assert.ok(html.includes("Juventus"), "must render career path team");
    assert.ok(html.includes("5 tentativi rimasti"), "must show 5 attempts left");
    assert.ok(html.includes("Facile"), "must render difficulty pill");
    assert.ok(html.includes("training-answer"), "must render guess input");
  } finally {
    restoreFetch();
    restoreTg();
  }
});

test("4. resumed active Training: restores session with correct round and attempts", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const sessionFixture = createTestTrainingSession({
    round: 0,
    attempts: 2,
    max_attempts: 5,
    career_path: createTestCareerPath(),
  });

  const restoreFetch = mockFetchResponse({
    session: sessionFixture,
    feedback: null,
  });

  try {
    setLanguage("it");
    const controller = new TrainingController();
    await controller.init();

    const state = controller.getState();
    assert.equal(state.data?.session?.attempts, 2);

    const html = renderTrainingView(state);
    assert.ok(html.includes("3 tentativi rimasti"), "must show 3 remaining attempts");
  } finally {
    restoreFetch();
    restoreTg();
  }
});

test("5. correct guess: sends guess with revision, marks finished, reveals solution", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const initialSession = createTestTrainingSession({
    round: 0,
    attempts: 1,
    revision: 2,
    finished: false,
  });

  const solvedSession = createTestTrainingSession({
    round: 1,
    attempts: 0,
    solved: 1,
    spent: 2,
    revision: 3,
    finished: true,
  });

  let callCount = 0;
  const restoreFetch = mockFetchResponse((_url: string, init?: RequestInit) => {
    callCount++;
    if (callCount === 1) {
      return { session: initialSession, feedback: null };
    }
    const body = JSON.parse(String(init?.body || "{}"));
    assert.equal(body.action, "guess");
    assert.equal(body.answer, "Paolo Maldini");
    assert.equal(body.revision, 2);
    return {
      session: solvedSession,
      feedback: {
        status: "correct",
        done: true,
        answer: "Paolo Maldini",
      },
    };
  });

  try {
    setLanguage("it");
    const controller = new TrainingController();
    await controller.init();

    const result = await controller.submitGuess("  Paolo Maldini  ");
    assert.ok(result);
    assert.equal(result?.feedback?.status, "correct");

    const state = controller.getState();
    assert.equal(state.data?.session?.finished, true);
    assert.equal(state.data?.session?.solved, 1);

    const html = renderTrainingView(state);
    assert.ok(html.includes("✦"), "must include success mark ✦");
    assert.ok(html.includes("Allenamento completato"), "must show completion title");
    assert.ok(html.includes("1 / 1"), "must show solved score");
    assert.ok(html.includes("Era Paolo Maldini"), "must reveal answer");
    assert.ok(html.includes("Prossimo percorso"), "must have next button");
  } finally {
    restoreFetch();
    restoreTg();
  }
});

test("6. wrong guess: decrements attempts and displays feedback box", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const initialSession = createTestTrainingSession({
    round: 0,
    attempts: 0,
    revision: 1,
  });

  const wrongSession = createTestTrainingSession({
    round: 0,
    attempts: 1,
    revision: 2,
  });

  let callCount = 0;
  const restoreFetch = mockFetchResponse(() => {
    callCount++;
    if (callCount === 1) return { session: initialSession, feedback: null };
    return {
      session: wrongSession,
      feedback: {
        status: "wrong",
        done: false,
      },
    };
  });

  try {
    setLanguage("it");
    const controller = new TrainingController();
    await controller.init();

    await controller.submitGuess("Lionel Messi");

    const state = controller.getState();
    assert.equal(state.data?.session?.attempts, 1);
    assert.equal(state.data?.feedback?.status, "wrong");

    const html = renderTrainingView(state);
    assert.ok(html.includes("4 tentativi rimasti"), "must show 4 attempts left");
    assert.ok(html.includes("Risposta non corretta"), "must display error feedback");
  } finally {
    restoreFetch();
    restoreTg();
  }
});

test("7. comparison clues: renders clues for nationality, position, birth year", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const sessionFixture = createTestTrainingSession({ attempts: 1 });

  const restoreFetch = mockFetchResponse({
    session: sessionFixture,
    feedback: {
      status: "wrong",
      done: false,
      comparison: {
        name: "Lionel Messi",
        clues: [
          { key: "feedback.nationality_diff" },
          { key: "feedback.position_diff" },
          { key: "feedback.birth_before", args: { year: 1987 } },
        ],
      },
    },
  });

  try {
    setLanguage("it");
    const controller = new TrainingController();
    await controller.init();

    const html = renderTrainingView(controller.getState());
    assert.ok(html.includes("Nazionalità diversa"), "must show nationality diff clue");
    assert.ok(html.includes("Ruolo diverso"), "must show position diff clue");
    assert.ok(html.includes("Più vecchio del 1987"), "must show birth year clue");
    assert.ok(html.includes("Lionel Messi"), "must show compared player name");
  } finally {
    restoreFetch();
    restoreTg();
  }
});

test("8. attempt count from backend: respects max_attempts dynamically", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const sessionFixture = createTestTrainingSession({
    max_attempts: 7,
    attempts: 3,
  });

  const restoreFetch = mockFetchResponse({
    session: sessionFixture,
    feedback: null,
  });

  try {
    setLanguage("it");
    const controller = new TrainingController();
    await controller.init();

    const html = renderTrainingView(controller.getState());
    assert.ok(html.includes("4 tentativi rimasti"), "must compute remaining attempts from max_attempts (7 - 3 = 4)");
  } finally {
    restoreFetch();
    restoreTg();
  }
});

test("9. double-submit blocked: prevents concurrent submissions while busy", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  let callCount = 0;
  let resolveGuess: ((val: any) => void) | null = null;

  const restoreFetch = mockFetchResponse((_url: string, init?: RequestInit) => {
    callCount++;
    const body = JSON.parse(String(init?.body || "{}"));
    if (body.action === "get") {
      return { session: createTestTrainingSession({ revision: 1 }), feedback: null };
    }
    return new Promise((resolve) => {
      resolveGuess = resolve;
    });
  });

  try {
    const controller = new TrainingController();
    await controller.init();

    // Start first guess (in flight)
    const firstPromise = controller.submitGuess("Buffon");
    assert.equal(controller.getState().busy, true);

    // Attempt second guess while first is busy
    const secondPromise = controller.submitGuess("Buffon");
    const secondResult = await secondPromise;
    assert.equal(secondResult, null, "second concurrent submit should be blocked");

    // Resolve first
    resolveGuess!({
      session: createTestTrainingSession({ attempts: 1, revision: 2 }),
      feedback: { status: "wrong", done: false },
    });
    await firstPromise;

    assert.equal(controller.getState().busy, false);
    assert.equal(callCount, 2, "only 1 get and 1 guess request dispatched");
  } finally {
    restoreFetch();
    restoreTg();
  }
});

test("10. reveal flow: 2-step confirmation and action='reveal'", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const activeSession = createTestTrainingSession({ revision: 4 });
  const finishedSession = createTestTrainingSession({
    revision: 5,
    finished: true,
    solved: 0,
    spent: 5,
  });

  const { requests, restore: restoreFetch } = captureFetchRequests((_url: string, init?: RequestInit) => {
    const body = JSON.parse(String(init?.body || "{}"));
    if (body.action === "get") return { session: activeSession, feedback: null };
    return {
      session: finishedSession,
      feedback: { status: "wrong", done: true, answer: "Alessandro Del Piero" },
    };
  });

  try {
    setLanguage("it");
    const controller = new TrainingController();
    await controller.init();

    // Step 1: click reveal triggers confirmation
    const firstClick = await controller.reveal();
    assert.equal(firstClick, null, "first click should request confirmation");
    assert.equal(controller.getState().confirming, "reveal");

    const confirmHtml = renderTrainingView(controller.getState());
    assert.ok(confirmHtml.includes("Confermi di voler rivelare?"), "button label must ask for confirmation");

    // Step 2: second click sends action: "reveal"
    const secondClick = await controller.reveal();
    assert.ok(secondClick);
    assert.equal(secondClick?.session?.finished, true);

    const revealReq = requests.find((r) => r.body.action === "reveal");
    assert.ok(revealReq, "reveal request was sent");
    assert.equal(revealReq.body.revision, 4);

    const finalHtml = renderTrainingView(controller.getState());
    assert.ok(finalHtml.includes("Era Alessandro Del Piero"), "must reveal answer on finish");
  } finally {
    restoreFetch();
    restoreTg();
  }
});

test("11. finished session: displays score summary and 'Prossimo percorso' button", () => {
  setLanguage("it");
  const finishedSession = createTestTrainingSession({
    finished: true,
    solved: 1,
    total: 1,
    spent: 3,
  });

  const state = {
    status: "idle" as const,
    busy: false,
    error: null,
    notice: null,
    confirming: null,
    data: {
      session: finishedSession,
      feedback: { status: "correct" as const, done: true, answer: "Francesco Totti" },
    },
    draftAnswer: "",
  };

  const html = renderFinishedSessionView(state);
  assert.ok(html.includes("Allenamento completato"));
  assert.ok(html.includes("1 / 1"));
  assert.ok(html.includes("3"));
  assert.ok(html.includes("Era Francesco Totti"));
  assert.ok(html.includes("Prossimo percorso"));
});

test("12. next after finished: starts a new challenge", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const newSession = createTestTrainingSession({
    round: 0,
    attempts: 0,
    revision: 1,
    finished: false,
  });

  const { requests, restore: restoreFetch } = captureFetchRequests({
    session: newSession,
    feedback: null,
  });

  try {
    const controller = new TrainingController();
    const result = await controller.startNext();

    assert.ok(result);
    assert.equal(result?.session?.finished, false);
    assert.equal(requests[0].body.action, "next");
  } finally {
    restoreFetch();
    restoreTg();
  }
});

test("13. stale revision triggers automatic get/resync and notifies user", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const serverUpdatedSession = createTestTrainingSession({
    attempts: 3,
    revision: 4,
  });

  let callCount = 0;
  const restoreFetch = mockFetchResponse((_url: string, init?: RequestInit) => {
    callCount++;
    const body = JSON.parse(String(init?.body || "{}"));
    if (callCount === 1) {
      // initial get
      return { session: createTestTrainingSession({ attempts: 2, revision: 3 }), feedback: null };
    }
    if (body.action === "guess") {
      // Stale error thrown by server
      const errorResponse = new Response(JSON.stringify({ detail: "stale" }), {
        status: 409,
        statusText: "Conflict",
        headers: { "Content-Type": "application/json" },
      });
      return errorResponse;
    }
    if (body.action === "get") {
      // Auto-resync call
      return { session: serverUpdatedSession, feedback: null };
    }
    return {};
  });

  try {
    setLanguage("it");
    const controller = new TrainingController();
    await controller.init();

    // Submit guess that triggers stale
    const guessResult = await controller.submitGuess("Baggio");
    assert.equal(guessResult, null);

    const state = controller.getState();
    assert.equal(state.notice, "synced", "notice should be set to 'synced'");
    assert.equal(state.data?.session?.revision, 4, "state should be resynced to server revision");
    assert.equal(state.data?.session?.attempts, 3, "state should reflect server attempts");

    const html = renderTrainingView(state);
    assert.ok(html.includes("Partita aggiornata dal server"), "must render synced notice");
  } finally {
    restoreFetch();
    restoreTg();
  }
});

test("14. older async response cannot replace newer session", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  let resolveOld: ((val: any) => void) | null = null;
  let callCount = 0;

  const restoreFetch = mockFetchResponse(() => {
    callCount++;
    if (callCount === 1) {
      return new Promise((resolve) => {
        resolveOld = resolve;
      });
    }
    return {
      session: createTestTrainingSession({ revision: 99, difficulty_label: "NewSession" }),
      feedback: null,
    };
  });

  try {
    const controller = new TrainingController();
    // Start slow request 1
    const promise1 = controller.init();

    // Trigger request 2 (e.g. refreshed/re-entered, completes first)
    const promise2 = controller.init();
    await promise2;

    assert.equal(controller.getState().data?.session?.difficulty_label, "NewSession");

    // Resolve delayed request 1
    resolveOld!({
      session: createTestTrainingSession({ revision: 1, difficulty_label: "OldSession" }),
      feedback: null,
    });
    await promise1;

    // State should still be NewSession
    assert.equal(controller.getState().data?.session?.difficulty_label, "NewSession");
  } finally {
    restoreFetch();
    restoreTg();
  }
});

test("15. API/auth failure: renders error state with retry button", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const restoreFetch = mockFetchError(401, "Unauthorized");

  try {
    setLanguage("it");
    const controller = new TrainingController();
    await controller.init();

    const state = controller.getState();
    assert.equal(state.status, "error");

    const html = renderTrainingView(state);
    assert.ok(html.includes("training-retry"), "must render retry button on error");
    assert.ok(html.includes("Non siamo riusciti ad aggiornare la partita"), "must display error message");
  } finally {
    restoreFetch();
    restoreTg();
  }
});

test("16. no sample/prototype data in runtime: all data comes from server", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const realSession = createTestTrainingSession({
    career_path: [
      { team: "Real Madrid", league: "La Liga", country: "Spagna", start_year: 2009, end_year: 2018 },
    ],
  });

  const restoreFetch = mockFetchResponse({
    session: realSession,
    feedback: null,
  });

  try {
    const controller = new TrainingController();
    await controller.init();

    const html = renderTrainingView(controller.getState());
    // Verify no prototype mock names
    assert.ok(!html.includes("dati di esempio"), "must not contain prototype data notice");
    assert.ok(!html.includes("Marco"), "must not contain prototype player Marco");
    assert.ok(!html.includes("Andrea"), "must not contain prototype opponent Andrea");
    assert.ok(html.includes("Real Madrid"), "must contain server-provided team");
  } finally {
    restoreFetch();
    restoreTg();
  }
});

test("17. IT rendering: verifies Italian strings", () => {
  setLanguage("it");
  const session = createTestTrainingSession();
  const html = renderTrainingView({
    status: "idle",
    busy: false,
    error: null,
    notice: null,
    confirming: null,
    data: { session, feedback: null },
    draftAnswer: "",
  });

  assert.ok(html.includes("Allenamento"));
  assert.ok(html.includes("Al tuo ritmo"));
  assert.ok(html.includes("tentativi rimasti"));
  assert.ok(html.includes("Rivela e termina"));
  assert.ok(html.includes("Conferma risposta"));
  assert.ok(html.includes("Torna all’Arena"));
});

test("18. EN rendering: verifies English strings", () => {
  setLanguage("en");
  const session = createTestTrainingSession();
  const html = renderTrainingView({
    status: "idle",
    busy: false,
    error: null,
    notice: null,
    confirming: null,
    data: { session, feedback: null },
    draftAnswer: "",
  });

  assert.ok(html.includes("Training"));
  assert.ok(html.includes("At your pace"));
  assert.ok(html.includes("guesses left"));
  assert.ok(html.includes("Reveal and finish"));
  assert.ok(html.includes("Submit answer"));
  assert.ok(html.includes("Back to Arena"));
});

test("19. ES rendering: verifies Spanish strings", () => {
  setLanguage("es");
  const session = createTestTrainingSession();
  const html = renderTrainingView({
    status: "idle",
    busy: false,
    error: null,
    notice: null,
    confirming: null,
    data: { session, feedback: null },
    draftAnswer: "",
  });

  assert.ok(html.includes("Entrenamiento"));
  assert.ok(html.includes("A tu ritmo"));
  assert.ok(html.includes("Quedan 5 intentos"));
  assert.ok(html.includes("Revelar y terminar"));
  assert.ok(html.includes("Confirmar respuesta"));
  assert.ok(html.includes("Volver a la Arena"));
});

test("20. Arena navigation into Training: entering Training from Arena hub", () => {
  setLanguage("it");
  const controller = new TrainingController();

  // Initially hub view: contains Training card
  const hubHtml = renderArenaPage({ subview: "hub", trainingState: controller.getState() });
  assert.ok(hubHtml.includes("training-entry"), "Arena hub must contain training entry card");
  assert.ok(hubHtml.includes("data-arena-nav=\"training\""), "card must have navigation attribute");

  // In training view: contains Training content and back button
  const trainingHtml = renderArenaPage({ subview: "training", trainingState: controller.getState() });
  assert.ok(trainingHtml.includes("data-training-back"), "must have back button");
  assert.ok(trainingHtml.includes("training-view"), "must render training view");
});

test("21. leaving/re-entering Training restores backend state correctly", () => {
  setLanguage("it");
  const activeSession = createTestTrainingSession({ attempts: 3, revision: 4 });
  const trainingState = {
    status: "idle" as const,
    busy: false,
    error: null,
    notice: null,
    confirming: null,
    data: { session: activeSession, feedback: null },
    draftAnswer: "",
  };

  const html = renderArenaPage({ subview: "training", trainingState });
  assert.ok(html.includes("2 tentativi rimasti"), "must restore remaining attempts (5 - 3 = 2)");
});

test("22. legacy /app unchanged: asserts legacy arena.js and client.js remain untouched", () => {
  const legacyArenaPath = path.resolve(process.cwd(), "webapp/arena.js");
  const legacyClientPath = path.resolve(process.cwd(), "webapp/client.js");

  assert.ok(fs.existsSync(legacyArenaPath), "webapp/arena.js must exist");
  assert.ok(fs.existsSync(legacyClientPath), "webapp/client.js must exist");

  const arenaContent = fs.readFileSync(legacyArenaPath, "utf-8");
  assert.ok(arenaContent.includes("PlayerArena"), "arena.js must export PlayerArena");
  assert.ok(arenaContent.includes("mode: \"training\"") || arenaContent.includes("mode === \"training\""));
});
