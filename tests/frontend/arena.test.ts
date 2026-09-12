import { test } from "node:test";
import assert from "node:assert/strict";
import { ArenaController } from "../../webapp/src/features/arena/controller";
import { renderArenaPage, attachArenaEventListeners } from "../../webapp/src/pages/ArenaPage";
import {
  setupGlobalDom,
  setupTestTelegram,
  captureFetchRequests,
  createTestDuelData,
  createTestDuelSession,
  createTestOpponentProfile,
} from "./helpers";

test("ArenaController: loads open duels list on init when no deep link", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const testData = createTestDuelData();
  const { requests, restore: restoreFetch } = captureFetchRequests(testData);

  try {
    const controller = new ArenaController();
    await controller.init();

    const state = controller.getState();
    assert.equal(state.subview, "hub");
    assert.equal(state.status, "idle");
    assert.equal(state.data?.open?.length, 1);
    assert.equal(state.data?.open?.[0].opponent, "Andrea");

    const req = requests.find((r) => r.url.includes("/app/api/arena"));
    assert.ok(req);
    assert.equal(req.body.mode, "duel");
    assert.equal(req.body.action, "list");
  } finally {
    restoreFetch();
    restoreTg();
  }
});

test("ArenaController: detects invitation deep-link via location.search ?duel=", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const { cleanup: cleanupDom } = setupGlobalDom();
  const validCode = "abcdef0123456789abcdef01";
  window.location.search = `?duel=${validCode}`;

  try {
    const controller = new ArenaController();
    await controller.init();

    const state = controller.getState();
    assert.equal(state.subview, "invitation");
    assert.equal(state.invitationCode, validCode);
  } finally {
    window.location.search = "";
    cleanupDom();
    restoreTg();
  }
});

test("ArenaController: detects invitation deep-link via Telegram start_param duel_", async () => {
  const validCode = "1234567890abcdef12345678";
  const { restore: restoreTg } = setupTestTelegram({
    initDataUnsafe: {
      user: { id: 42, first_name: "Marco" },
      start_param: `duel_${validCode}`,
    },
  });

  try {
    const controller = new ArenaController();
    await controller.init();

    const state = controller.getState();
    assert.equal(state.subview, "invitation");
    assert.equal(state.invitationCode, validCode);
  } finally {
    restoreTg();
  }
});

test("ArenaController: createNewDuel calls API with action:create and updates subview to duel", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const newDuel = createTestDuelData({
    code: "feedface0123456789abcdef",
    opponent: null,
    invite_url: "https://t.me/Bot?start=duel_feedface0123456789abcdef",
  });
  const { requests, restore: restoreFetch } = captureFetchRequests(newDuel);

  try {
    const controller = new ArenaController();
    const result = await controller.createNewDuel();

    assert.ok(result);
    assert.equal(result.code, "feedface0123456789abcdef");
    const state = controller.getState();
    assert.equal(state.subview, "duel");
    assert.equal(state.activeDuelCode, "feedface0123456789abcdef");

    const req = requests.find((r) => r.url.includes("/app/api/arena"));
    assert.ok(req);
    assert.equal(req.body.mode, "duel");
    assert.equal(req.body.action, "create");
  } finally {
    restoreFetch();
    restoreTg();
  }
});

test("ArenaController: acceptInvitation calls action:join and enters active duel", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const joinCode = "9876543210fedcba98765432";
  const joinedDuel = createTestDuelData({
    code: joinCode,
    opponent: { name: "Creator", round: 0, finished: false },
  });
  const { requests, restore: restoreFetch } = captureFetchRequests(joinedDuel);

  try {
    const controller = new ArenaController();
    controller.setSubview("invitation", joinCode);
    await controller.acceptInvitation();

    const state = controller.getState();
    assert.equal(state.subview, "duel");
    assert.equal(state.activeDuelCode, joinCode);
    assert.equal(state.invitationCode, null);

    const req = requests.find((r) => r.url.includes("/app/api/arena"));
    assert.ok(req);
    assert.equal(req.body.mode, "duel");
    assert.equal(req.body.action, "join");
    assert.equal(req.body.code, joinCode);
  } finally {
    restoreFetch();
    restoreTg();
  }
});

test("ArenaController: submitGuess sends trimmed answer and revision, handles correct feedback", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const code = "0123456789abcdef01234567";
  const initialDuel = createTestDuelData({
    code,
    session: createTestDuelSession({ revision: 3, round: 1 }),
  });
  const guessResponse = createTestDuelData({
    code,
    session: createTestDuelSession({ revision: 4, round: 2, solved: 1 }),
    feedback: {
      status: "correct",
      done: true,
      answer: "Paulo Dybala",
    },
  });

  const { requests, restore: restoreFetch } = captureFetchRequests(guessResponse);

  try {
    const controller = new ArenaController();
    // Pre-populate duel state
    (controller as any).updateState({
      data: initialDuel,
      activeDuelCode: code,
      subview: "duel",
    });

    await controller.submitGuess("  Paulo Dybala  ");

    const state = controller.getState();
    assert.equal(state.draftAnswer, "");
    assert.equal(state.data?.feedback?.status, "correct");

    const req = requests.find((r) => r.url.includes("/app/api/arena"));
    assert.ok(req);
    assert.equal(req.body.action, "guess");
    assert.equal(req.body.answer, "Paulo Dybala");
    assert.equal(req.body.revision, 3);
    assert.equal(req.body.code, code);
  } finally {
    restoreFetch();
    restoreTg();
  }
});

test("ArenaController: server stale error triggers automatic resync with action:get", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const code = "0123456789abcdef01234567";
  const initialDuel = createTestDuelData({
    code,
    session: createTestDuelSession({ revision: 1 }),
  });

  const originalFetch = globalThis.fetch;
  let callCount = 0;
  globalThis.fetch = (async (_input: RequestInfo | URL, _init?: RequestInit): Promise<Response> => {
    callCount++;
    if (callCount === 1) {
      return new Response(JSON.stringify({ detail: "stale" }), {
        status: 409,
        headers: { "Content-Type": "application/json" },
      });
    }
    return new Response(
      JSON.stringify(
        createTestDuelData({
          code,
          session: createTestDuelSession({ revision: 2 }),
        }),
      ),
      {
        status: 200,
        headers: { "Content-Type": "application/json" },
      },
    );
  }) as any;
  const restoreFetch = () => {
    globalThis.fetch = originalFetch;
  };

  try {
    const controller = new ArenaController();
    (controller as any).updateState({
      data: initialDuel,
      activeDuelCode: code,
      subview: "duel",
    });

    await controller.submitGuess("Cavani");

    const state = controller.getState();
    assert.equal(state.notice, "Partita aggiornata dal server: controlla i tentativi rimasti.");
    assert.equal(state.data?.session?.revision, 2);
  } finally {
    restoreFetch();
    restoreTg();
  }
});

test("ArenaController: skipRound requires 2 clicks and reveals current round", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const code = "0123456789abcdef01234567";
  const initialDuel = createTestDuelData({
    code,
    session: createTestDuelSession({ revision: 2 }),
  });
  const skippedDuel = createTestDuelData({
    code,
    session: createTestDuelSession({ revision: 3, round: 1, spent: 3 }),
  });

  const { requests, restore: restoreFetch } = captureFetchRequests(skippedDuel);

  try {
    const controller = new ArenaController();
    (controller as any).updateState({
      data: initialDuel,
      activeDuelCode: code,
      subview: "duel",
    });

    // First click: prompts for confirmation
    await controller.skipRound();
    assert.equal(controller.getState().confirming, "skip");
    assert.equal(requests.length, 0);

    // Second click: performs reveal
    await controller.skipRound();
    assert.equal(controller.getState().confirming, null);

    const req = requests.find((r) => r.url.includes("/app/api/arena"));
    assert.ok(req);
    assert.equal(req.body.action, "reveal");
    assert.equal(req.body.revision, 2);
    assert.equal(req.body.code, code);
  } finally {
    restoreFetch();
    restoreTg();
  }
});

test("ArenaController: deleteDuel requires 2 clicks, deletes unjoined duel and refreshes list", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const code = "0123456789abcdef01234567";
  const openList = createTestDuelData({ open: [] });

  const originalFetch = globalThis.fetch;
  let deleteCalled = false;
  globalThis.fetch = (async (_input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const body = JSON.parse(String(init?.body || "{}"));
    if (body.action === "delete") {
      deleteCalled = true;
      return new Response(JSON.stringify({ deleted: code }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    return new Response(JSON.stringify(openList), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }) as any;
  const restoreFetch = () => {
    globalThis.fetch = originalFetch;
  };

  try {
    const controller = new ArenaController();
    (controller as any).updateState({
      data: createTestDuelData(),
      subview: "hub",
    });

    // 1st click: confirming set
    await controller.deleteDuel(code);
    assert.equal(controller.getState().confirming, `delete:${code}`);
    assert.equal(deleteCalled, false);

    // 2nd click: execute delete
    await controller.deleteDuel(code);
    assert.equal(controller.getState().confirming, null);
    assert.equal(deleteCalled, true);
    assert.equal(controller.getState().notice, "Sfida eliminata");
  } finally {
    restoreFetch();
    restoreTg();
  }
});

test("ArenaController: searchOpponents debounces 300ms and filters current user", async () => {
  const currentUserId = 12345;
  const { restore: restoreTg } = setupTestTelegram({
    initDataUnsafe: {
      user: { id: currentUserId, first_name: "Self" },
    },
  });

  const searchPayload = {
    profiles: [
      createTestOpponentProfile({ profile_id: currentUserId, name: "Self" }),
      createTestOpponentProfile({ profile_id: 67890, name: "Opponent" }),
    ],
  };

  const { requests, restore: restoreFetch } = captureFetchRequests(searchPayload);

  try {
    const controller = new ArenaController();
    controller.searchOpponents("Op");

    // Before debounce timer fires
    assert.equal(controller.getState().status, "searching");
    assert.equal(requests.length, 0);

    // Wait for 350ms to let timer fire
    await new Promise((r) => setTimeout(r, 350));

    const state = controller.getState();
    assert.equal(state.status, "idle");
    assert.equal(state.searchResults.length, 1);
    assert.equal(state.searchResults[0].profile_id, 67890);
    assert.equal(state.searchResults[0].name, "Opponent");

    const req = requests.find((r) => r.url.includes("/app/api/profile/search"));
    assert.ok(req);
    assert.equal(req.body.query, "Op");
  } finally {
    restoreFetch();
    restoreTg();
  }
});

test("ArenaController: shareInvite opens Telegram link", async () => {
  let openedUrl = "";
  const { restore: restoreTg } = setupTestTelegram({
    openTelegramLink: (url: string) => {
      openedUrl = url;
    },
  });

  try {
    const controller = new ArenaController();
    (controller as any).updateState({
      data: createTestDuelData({
        invite_url: "https://t.me/GuessThePlayerBot?start=duel_0123456789abcdef01234567",
      }),
    });

    controller.shareInvite();
    assert.ok(openedUrl.startsWith("https://t.me/share/url?url="));
    assert.ok(openedUrl.includes("duel_0123456789abcdef01234567"));
  } finally {
    restoreTg();
  }
});

test("ArenaController: copyInvite writes to clipboard and sets notice", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const { cleanup: cleanupDom } = setupGlobalDom();

  let clipboardContent = "";
  Object.assign(navigator, {
    clipboard: {
      writeText: async (text: string) => {
        clipboardContent = text;
      },
    },
  });

  try {
    const controller = new ArenaController();
    const inviteUrl = "https://t.me/GuessThePlayerBot?start=duel_test";
    (controller as any).updateState({
      data: createTestDuelData({ invite_url: inviteUrl }),
    });

    const success = await controller.copyInvite();
    assert.equal(success, true);
    assert.equal(clipboardContent, inviteUrl);
    assert.equal(controller.getState().notice, "Link copiato");
  } finally {
    cleanupDom();
    restoreTg();
  }
});

test("ArenaPage: renders Hub view with 1v1 feature banner, open duels list and H2H ledger", () => {
  const { container, cleanup } = setupGlobalDom();
  try {
    const state = {
      subview: "hub" as const,
      status: "idle" as const,
      busy: false,
      error: null,
      notice: null,
      confirming: null,
      data: createTestDuelData({
        open: [
          {
            code: "abc",
            opponent: "Luca",
            complete: false,
            round: 2,
            total: 5,
            expires_at: "2026-09-20T12:00:00Z",
          },
        ],
      }),
      activeDuelCode: null,
      invitationCode: null,
      searchQuery: "",
      searchResults: [],
      searchError: null,
      draftAnswer: "",
    };

    container.innerHTML = renderArenaPage(state);

    // Verify 1v1 banner
    assert.ok(container.querySelector(".arena-feature"));
    assert.ok(container.querySelector(".mode-label")?.textContent?.includes("1 CONTRO 1"));

    // Verify open duels list
    assert.ok(container.querySelector(".arena-open-list"));
    assert.ok(container.textContent?.includes("Luca"));

    // Verify H2H ledger
    assert.ok(container.querySelector(".arena-h2h"));
    assert.ok(container.textContent?.includes("3–2"));

    // Verify page title
    assert.ok(container.querySelector(".page-title")?.textContent?.includes("Arena"));
  } finally {
    cleanup();
  }
});

test("ArenaPage: DOM event wiring triggers controller navigation and duel loading", () => {
  const { container, cleanup } = setupGlobalDom();
  try {
    const controller = new ArenaController();
    let navigatedTo = "";
    let loadedDuelCode = "";

    controller.setSubview = (subview) => {
      navigatedTo = subview;
    };
    controller.loadDuel = async (code) => {
      loadedDuelCode = code;
    };

    const state = {
      subview: "hub" as const,
      status: "idle" as const,
      busy: false,
      error: null,
      notice: null,
      confirming: null,
      data: createTestDuelData({
        open: [
          {
            code: "duel123",
            opponent: "Marco",
            complete: false,
            round: 1,
            total: 5,
            expires_at: "2026-09-20T12:00:00Z",
          },
        ],
      }),
      activeDuelCode: null,
      invitationCode: null,
      searchQuery: "",
      searchResults: [],
      searchError: null,
      draftAnswer: "",
    };

    container.innerHTML = renderArenaPage(state);
    attachArenaEventListeners(container, controller);

    // Click on 1v1 banner -> challenge
    const banner = container.querySelector<HTMLButtonElement>("[data-arena-nav='challenge']");
    assert.ok(banner);
    banner.click();
    assert.equal(navigatedTo, "challenge");

    // Click on duel row -> loadDuel
    const duelRow = container.querySelector<HTMLButtonElement>("[data-arena-duel='duel123']");
    assert.ok(duelRow);
    duelRow.click();
    assert.equal(loadedDuelCode, "duel123");
  } finally {
    cleanup();
  }
});

test("ArenaPage: renders active duel gameplay with CareerPath, guess form, and submit", () => {
  const { container, cleanup } = setupGlobalDom();
  try {
    const controller = new ArenaController();
    let submittedAnswer = "";
    controller.submitGuess = async (ans) => {
      submittedAnswer = ans;
    };

    const state = {
      subview: "duel" as const,
      status: "idle" as const,
      busy: false,
      error: null,
      notice: null,
      confirming: null,
      data: createTestDuelData({
        opponent: { name: "Matteo", round: 1, finished: false },
        session: createTestDuelSession({ round: 0, total: 5 }),
      }),
      activeDuelCode: "0123456789abcdef01234567",
      invitationCode: null,
      searchQuery: "",
      searchResults: [],
      searchError: null,
      draftAnswer: "Dybala",
    };

    container.innerHTML = renderArenaPage(state);
    attachArenaEventListeners(container, controller);

    // Check CareerPath is rendered
    assert.ok(container.querySelector(".path"));
    assert.ok(container.textContent?.includes("Palermo"));

    // Check input has draft value
    const input = container.querySelector<HTMLInputElement>("#arena-answer");
    assert.ok(input);
    assert.equal(input.value, "Dybala");

    // Submit form
    const submitBtn = container.querySelector<HTMLButtonElement>("#arena-submit");
    assert.ok(submitBtn);
    submitBtn.click();
    assert.equal(submittedAnswer, "Dybala");
  } finally {
    cleanup();
  }
});

test("ArenaPage: renders invitation view with accept button and triggers acceptInvitation", () => {
  const { container, cleanup } = setupGlobalDom();
  try {
    const controller = new ArenaController();
    let acceptCalled = false;
    controller.acceptInvitation = async () => {
      acceptCalled = true;
    };

    const state = {
      subview: "invitation" as const,
      status: "idle" as const,
      busy: false,
      error: null,
      notice: null,
      confirming: null,
      data: null,
      activeDuelCode: null,
      invitationCode: "0123456789abcdef01234567",
      searchQuery: "",
      searchResults: [],
      searchError: null,
      draftAnswer: "",
    };

    container.innerHTML = renderArenaPage(state);
    attachArenaEventListeners(container, controller);

    const joinBtn = container.querySelector<HTMLButtonElement>("#arena-accept-invite");
    assert.ok(joinBtn);
    joinBtn.click();
    assert.equal(acceptCalled, true);
  } finally {
    cleanup();
  }
});
