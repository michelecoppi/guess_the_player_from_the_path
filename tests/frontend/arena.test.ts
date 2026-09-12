import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { App } from "../../webapp/src/app/App";
import { ArenaController } from "../../webapp/src/features/arena/controller";
import { renderArenaPage, attachArenaEventListeners } from "../../webapp/src/pages/ArenaPage";
import { renderTrainingView } from "../../webapp/src/features/training/views";
import { setLanguage, getLanguage, TRANSLATIONS } from "../../webapp/src/i18n";
import {
  setupGlobalDom,
  setupTestTelegram,
  captureFetchRequests,
  createTestDuelData,
  createTestDuelSession,
  createTestOpponentProfile,
  createTestTrainingSession,
  createTestDailyChallenge,
  TEST_DUEL_CODE,
} from "./helpers";

const CODE_A = "000000000000000000000001"; // pragma: allowlist secret
const CODE_B = "000000000000000000000002"; // pragma: allowlist secret
const CODE_C = "000000000000000000000003"; // pragma: allowlist secret
const CODE_D = "000000000000000000000004"; // pragma: allowlist secret

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
  const validCode = CODE_A;
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
  const validCode = CODE_B;
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
    code: CODE_C,
    opponent: null,
    invite_url: `https://t.me/Bot?start=duel_${CODE_C}`,
  });
  const { requests, restore: restoreFetch } = captureFetchRequests(newDuel);

  try {
    const controller = new ArenaController();
    const result = await controller.createNewDuel();

    assert.ok(result);
    assert.equal(result.code, CODE_C);
    const state = controller.getState();
    assert.equal(state.subview, "duel");
    assert.equal(state.activeDuelCode, CODE_C);

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
  const joinCode = CODE_D;
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
  const code = TEST_DUEL_CODE;
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
  const code = TEST_DUEL_CODE;
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
  const code = TEST_DUEL_CODE;
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
  const code = TEST_DUEL_CODE;
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
        invite_url: `https://t.me/GuessThePlayerBot?start=duel_${TEST_DUEL_CODE}`,
      }),
    });

    controller.shareInvite();
    assert.ok(openedUrl.startsWith("https://t.me/share/url?url="));
    assert.ok(openedUrl.includes(`duel_${TEST_DUEL_CODE}`));
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
      activeDuelCode: TEST_DUEL_CODE,
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
      invitationCode: TEST_DUEL_CODE,
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

test("ArenaPage: real Arena rendering contains no prototype or sample-data wording across subviews", () => {
  const { container, cleanup } = setupGlobalDom();
  try {
    const baseState = {
      status: "idle" as const,
      busy: false,
      error: null,
      notice: null,
      confirming: null,
      activeDuelCode: TEST_DUEL_CODE,
      invitationCode: TEST_DUEL_CODE,
      searchQuery: "Matteo",
      searchResults: [createTestOpponentProfile()],
      searchError: null,
      draftAnswer: "",
    };

    const subviews = [
      {
        subview: "hub" as const,
        data: createTestDuelData({
          open: [
            {
              code: TEST_DUEL_CODE,
              opponent: "Andrea",
              complete: false,
              round: 2,
              total: 5,
              expires_at: "2026-09-20T12:00:00Z",
            },
          ],
        }),
      },
      {
        subview: "challenge" as const,
        data: createTestDuelData(),
      },
      {
        subview: "duel" as const,
        data: createTestDuelData({
          session: createTestDuelSession({ round: 2, total: 5 }),
        }),
      },
      {
        subview: "invitation" as const,
        data: null,
      },
    ];

    for (const item of subviews) {
      container.innerHTML = renderArenaPage({ ...baseState, ...item });

      const text = container.textContent?.toLowerCase() || "";
      assert.equal(
        text.includes("dati di esempio"),
        false,
        `Subview ${item.subview} must not contain 'dati di esempio'`,
      );
      assert.equal(
        text.includes("sample data"),
        false,
        `Subview ${item.subview} must not contain 'sample data'`,
      );
      assert.equal(
        container.querySelector(".prototype-notice"),
        null,
        `Subview ${item.subview} must not contain .prototype-notice`,
      );
      assert.equal(
        container.querySelector(".prototype"),
        null,
        `Subview ${item.subview} must not contain .prototype`,
      );
    }
  } finally {
    cleanup();
  }
});

test("ArenaPage: localization is complete across IT, EN, ES with no leaked Italian strings", () => {
  const { cleanup } = setupGlobalDom();
  const initialLang = getLanguage();

  try {
    // 1. Verify translation structure parity across languages
    const itArenaKeys = Object.keys(TRANSLATIONS.it.arena).sort();
    const enArenaKeys = Object.keys(TRANSLATIONS.en.arena).sort();
    const esArenaKeys = Object.keys(TRANSLATIONS.es.arena).sort();

    assert.deepEqual(enArenaKeys, itArenaKeys, "English arena translation keys must match Italian");
    assert.deepEqual(esArenaKeys, itArenaKeys, "Spanish arena translation keys must match Italian");

    // 2. Render subviews in EN and ES and assert Italian-only strings do not leak
    const italianOnlyFragments = [
      "Chi sfidi oggi?",
      "Invita un amico o cerca un altro giocatore.",
      "Gioca con un amico",
      "Crea una nuova sfida e invia il link a chi vuoi tu.",
      "Il tuo duello con",
      "Le tue sfide aperte",
      "Nessuna sfida aperta",
      "In attesa di un amico",
      "Condividi il link per iniziare",
      "TESTA A TESTA",
      "Duelli conclusi",
      "Un avversario",
    ];

    for (const lang of ["en", "es"] as const) {
      setLanguage(lang);

      const challengeHtml = renderArenaPage({
        subview: "challenge",
        status: "idle",
        busy: false,
        error: null,
        notice: null,
        confirming: null,
        data: null,
        activeDuelCode: null,
        invitationCode: null,
        searchQuery: "",
        searchResults: [],
        searchError: null,
        draftAnswer: "",
      });

      const hubHtml = renderArenaPage({
        subview: "hub",
        status: "idle",
        busy: false,
        error: null,
        notice: null,
        confirming: null,
        data: createTestDuelData({
          open: [
            {
              code: TEST_DUEL_CODE,
              opponent: "Friend",
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
      });

      for (const fragment of italianOnlyFragments) {
        assert.equal(
          challengeHtml.includes(fragment),
          false,
          `Challenge view in ${lang} leaked Italian string: "${fragment}"`,
        );
        assert.equal(
          hubHtml.includes(fragment),
          false,
          `Hub view in ${lang} leaked Italian string: "${fragment}"`,
        );
      }

      // Verify specific localized texts render in EN and ES
      if (lang === "en") {
        assert.ok(challengeHtml.includes("Who are you challenging today?"));
        assert.ok(challengeHtml.includes("Play with a friend"));
        assert.ok(hubHtml.includes("Your duel with Friend"));
      } else if (lang === "es") {
        assert.ok(challengeHtml.includes("¿A quién retas hoy?"));
        assert.ok(challengeHtml.includes("Juega con un amigo"));
        assert.ok(hubHtml.includes("Tu duelo con Friend"));
      }
    }
  } finally {
    setLanguage(initialLang);
    cleanup();
  }
});

test("ArenaPage: searched-opponent button creates generic invite and shares link without targeted backend state", async () => {
  const { container, cleanup } = setupGlobalDom();
  const { restore: restoreTg } = setupTestTelegram();

  let shareCalledWithUrl: string | undefined;
  const newDuel = createTestDuelData({
    code: TEST_DUEL_CODE,
    invite_url: `https://t.me/Bot?start=duel_${TEST_DUEL_CODE}`,
    opponent: null,
  });

  const { requests, restore: restoreFetch } = captureFetchRequests(newDuel);

  try {
    const controller = new ArenaController();
    controller.shareInvite = (url?: string) => {
      shareCalledWithUrl = url;
    };

    const targetProfileId = 777;
    const state = {
      subview: "challenge" as const,
      status: "idle" as const,
      busy: false,
      error: null,
      notice: null,
      confirming: null,
      data: null,
      activeDuelCode: null,
      invitationCode: null,
      searchQuery: "Lorenzo",
      searchResults: [
        createTestOpponentProfile({
          profile_id: targetProfileId,
          name: "Lorenzo",
        }),
      ],
      searchError: null,
      draftAnswer: "",
    };

    container.innerHTML = renderArenaPage(state);
    attachArenaEventListeners(container, controller);

    // Verify presence of explanatory note indicating duels are link-based
    const note = container.querySelector(".arena-search-note");
    assert.ok(note);
    assert.ok(note.textContent?.includes("link"));

    // Verify invite button on opponent card
    const inviteBtn = container.querySelector<HTMLButtonElement>(
      `[data-arena-invite-user="${targetProfileId}"]`,
    );
    assert.ok(inviteBtn);
    assert.equal(inviteBtn.textContent?.trim(), "Invita");

    // Click invite button
    inviteBtn.click();

    // Wait for async handler
    await new Promise((r) => setTimeout(r, 20));

    // Verify backend call semantics: action is "create", mode is "duel", and NO target user ID was sent to backend
    const req = requests.find((r) => r.url.includes("/app/api/arena"));
    assert.ok(req);
    assert.equal(req.body.mode, "duel");
    assert.equal(req.body.action, "create");
    assert.equal(req.body.target_user, undefined);
    assert.equal(req.body.opponent_id, undefined);
    assert.equal(req.body.profile_id, undefined);

    // Verify invite URL is shared
    assert.equal(shareCalledWithUrl, `https://t.me/Bot?start=duel_${TEST_DUEL_CODE}`);
  } finally {
    restoreFetch();
    restoreTg();
    cleanup();
  }
});

test("Arena + Training coexistence: 1. Arena hub contains Training entry", () => {
  setLanguage("it");
  const state = {
    subview: "hub" as const,
    status: "idle" as const,
    busy: false,
    error: null,
    notice: null,
    confirming: null,
    data: createTestDuelData(),
    activeDuelCode: null,
    invitationCode: null,
    searchQuery: "",
    searchResults: [],
    searchError: null,
    draftAnswer: "",
  };
  const html = renderArenaPage(state);
  assert.ok(html.includes("training-entry"), "hub must contain .training-entry");
  assert.ok(html.includes('data-arena-nav="training"'), "must have data-arena-nav='training'");
  assert.ok(html.includes("Allenamento"));
});

test("Arena + Training coexistence: 2. Arena hub still contains real 1v1 functionality", () => {
  setLanguage("it");
  const state = {
    subview: "hub" as const,
    status: "idle" as const,
    busy: false,
    error: null,
    notice: null,
    confirming: null,
    data: createTestDuelData(),
    activeDuelCode: null,
    invitationCode: null,
    searchQuery: "",
    searchResults: [],
    searchError: null,
    draftAnswer: "",
  };
  const html = renderArenaPage(state);
  assert.ok(html.includes('data-arena-nav="challenge"'), "hub must contain 1v1 challenge button");
  assert.ok(html.includes("arena-feature"), "hub must contain arena-feature card");
  assert.ok(html.includes("VS"), "hub must contain versus mark");
});

test("Arena + Training coexistence: 3 & 4. Training entry opens Training, Back from Training returns to Arena hub", async () => {
  const { container, cleanup } = setupGlobalDom();
  const { restore: restoreTg } = setupTestTelegram();
  const { requests, restore: restoreFetch } = captureFetchRequests({
    user: { name: "Marco", points: 100 },
    today: createTestDailyChallenge(),
    session: null,
    feedback: null,
    open: [],
  });

  try {
    const app = new App(container);
    app.init();

    // Navigate to Arena tab
    app.setTab("arena");
    assert.ok(container.querySelector(".arena-hub"));
    assert.ok(container.querySelector(".training-entry"));

    // Click Training entry
    const trainingBtn = container.querySelector<HTMLButtonElement>('[data-arena-nav="training"]');
    assert.ok(trainingBtn);
    trainingBtn.click();

    // Verify Training view is displayed
    assert.ok(container.querySelector(".training-view") || container.querySelector("#training-view"));
    const backBtn = container.querySelector<HTMLButtonElement>("[data-training-back]");
    assert.ok(backBtn, "back button must be present in training view");

    // Record requests before clicking back
    const requestsBeforeBack = requests.length;

    // Click back to Arena Hub
    backBtn.click();
    assert.ok(container.querySelector(".arena-hub"), "must return to real Arena hub");
    assert.ok(container.querySelector(".arena-feature"), "Arena hub 1v1 feature card must be present");

    // Single-owner navigation verification: returning to hub dispatches exactly ONE duel-list request
    const duelRequestsAfterBack = requests
      .slice(requestsBeforeBack)
      .filter((r) => r.body && (r.body as any).mode === "duel" && (r.body as any).action === "list");
    assert.equal(duelRequestsAfterBack.length, 1, "exactly one duel-list request should be dispatched on returning to Arena hub");
  } finally {
    restoreFetch();
    restoreTg();
    cleanup();
  }
});

test("Arena + Training coexistence: 5. Duel challenge flow still works", async () => {
  const { container, cleanup } = setupGlobalDom();
  const { restore: restoreTg } = setupTestTelegram();
  const { restore: restoreFetch } = captureFetchRequests({
    user: { name: "Marco", points: 100 },
    open: [],
  });

  try {
    const app = new App(container);
    app.init();
    app.setTab("arena");

    // Click 1v1 challenge banner
    const challengeBtn = container.querySelector<HTMLButtonElement>('[data-arena-nav="challenge"]');
    assert.ok(challengeBtn);
    challengeBtn.click();

    // Verify challenge view
    assert.ok(container.querySelector(".arena-challenge"));
    assert.ok(container.querySelector("#opponent-search"));
  } finally {
    restoreFetch();
    restoreTg();
    cleanup();
  }
});

test("Arena + Training coexistence: 6. Existing duel opens after visiting Training", async () => {
  const { container, cleanup } = setupGlobalDom();
  const { restore: restoreTg } = setupTestTelegram();
  const testDuel = createTestDuelData({ code: CODE_A });
  const { restore: restoreFetch } = captureFetchRequests((_url: string, init?: RequestInit) => {
    const body = JSON.parse(String(init?.body || "{}"));
    if (body.action === "get" && body.mode === "duel") {
      return testDuel;
    }
    if (body.action === "list") {
      return { open: [{ code: CODE_A, opponent: "Andrea", complete: false, round: 1, total: 5 }] };
    }
    if (body.mode === "training") {
      return { session: null, feedback: null };
    }
    return testDuel;
  });

  try {
    const app = new App(container);
    app.init();
    app.setTab("arena");

    // Visit Training
    const trainingBtn = container.querySelector<HTMLButtonElement>('[data-arena-nav="training"]');
    assert.ok(trainingBtn);
    trainingBtn.click();
    assert.ok(container.querySelector("#training-view") || container.querySelector(".training-view"));

    // Return to Hub
    const backBtn = container.querySelector<HTMLButtonElement>("[data-training-back]");
    assert.ok(backBtn);
    backBtn.click();
    await new Promise((r) => setTimeout(r, 40));

    // Click open duel row
    const duelRow = container.querySelector<HTMLButtonElement>(`[data-arena-duel="${CODE_A}"]`);
    assert.ok(duelRow);
    duelRow.click();

    // Verify duel view rendered
    await new Promise((r) => setTimeout(r, 20));
    assert.ok(container.querySelector("#arena-answer") || container.querySelector(".arena-duel"));
  } finally {
    restoreFetch();
    restoreTg();
    cleanup();
  }
});

test("Arena + Training coexistence: 7. duel deep-link (?duel=) still works", async () => {
  const { container, cleanup } = setupGlobalDom();
  const { restore: restoreTg } = setupTestTelegram();
  window.location.search = `?duel=${CODE_A}`;
  const { restore: restoreFetch } = captureFetchRequests(createTestDuelData({ code: CODE_A }));

  try {
    const app = new App(container);
    app.init();

    // Verify invitation subview opened directly
    const acceptBtn = container.querySelector("#arena-accept-invite");
    assert.ok(acceptBtn, "invitation view must render accept button on ?duel deep-link");
  } finally {
    window.location.search = "";
    restoreFetch();
    restoreTg();
    cleanup();
  }
});

test("Arena + Training coexistence: 8. Telegram duel start_param still works", async () => {
  const { container, cleanup } = setupGlobalDom();
  const { restore: restoreTg } = setupTestTelegram({
    initDataUnsafe: {
      user: { id: 42, first_name: "Marco" },
      start_param: `duel_${CODE_B}`,
    },
  });
  const { restore: restoreFetch } = captureFetchRequests(createTestDuelData({ code: CODE_B }));

  try {
    const app = new App(container);
    app.init();

    const acceptBtn = container.querySelector("#arena-accept-invite");
    assert.ok(acceptBtn, "invitation view must render accept button on Telegram start_param");
  } finally {
    restoreFetch();
    restoreTg();
    cleanup();
  }
});

test("Arena + Training coexistence: 9 & 10. Training state survives navigation and does not create new challenge on re-entry", async () => {
  const { container, cleanup } = setupGlobalDom();
  const { restore: restoreTg } = setupTestTelegram({
    initDataUnsafe: {
      user: { id: 42, first_name: "Marco", language_code: "it" },
    },
  });
  const activeSession = createTestTrainingSession({ attempts: 3, revision: 4 });
  const { requests, restore: restoreFetch } = captureFetchRequests((_url: string, init?: RequestInit) => {
    const body = JSON.parse(String(init?.body || "{}"));
    if (body.mode === "training" && body.action === "get") {
      return { session: activeSession, feedback: null };
    }
    return createTestDuelData();
  });

  try {
    setLanguage("it");
    const app = new App(container);
    app.init();
    app.setTab("arena");

    // 1. Enter Training
    const trainingBtn = container.querySelector<HTMLButtonElement>('[data-arena-nav="training"]');
    assert.ok(trainingBtn);
    trainingBtn.click();
    await new Promise((r) => setTimeout(r, 50));

    // Verify attempts left
    assert.ok(container.textContent?.includes("2 tentativi rimasti"));

    // 2. Return to Hub
    const backBtn = container.querySelector<HTMLButtonElement>("[data-training-back]");
    assert.ok(backBtn);
    backBtn.click();
    assert.ok(container.querySelector(".arena-hub"));

    // 3. Re-enter Training
    const trainingBtn2 = container.querySelector<HTMLButtonElement>('[data-arena-nav="training"]');
    assert.ok(trainingBtn2);
    trainingBtn2.click();

    // Verify state survived
    assert.ok(container.textContent?.includes("2 tentativi rimasti"));

    // Verify NO "next" action was dispatched on re-entry!
    const nextRequests = requests.filter((r) => r.body?.mode === "training" && r.body?.action === "next");
    assert.equal(nextRequests.length, 0, "must NOT dispatch action: next on re-entry");
  } finally {
    restoreFetch();
    restoreTg();
    cleanup();
  }
});

test("Arena + Training coexistence: 11 & 12. Real Arena and Real Training contain no prototype or sample data", () => {
  const hubHtml = renderArenaPage({ subview: "hub", data: createTestDuelData() } as any);
  assert.ok(!hubHtml.includes("dati di esempio") && !hubHtml.includes("sample data") && !hubHtml.includes("prototype-banner"));

  const duelHtml = renderArenaPage({ subview: "duel", data: createTestDuelData() } as any);
  assert.ok(!duelHtml.includes("dati di esempio") && !duelHtml.includes("sample data"));

  const trainingHtml = renderTrainingView({
    status: "idle",
    busy: false,
    error: null,
    notice: null,
    confirming: null,
    data: { session: createTestTrainingSession(), feedback: null },
    draftAnswer: "",
  });
  assert.ok(!trainingHtml.includes("dati di esempio") && !trainingHtml.includes("sample data"));
});

test("Arena + Training coexistence: 13. IT/EN/ES work for both Arena and Training", () => {
  const initialLang = getLanguage();
  try {
    for (const lang of ["it", "en", "es"] as const) {
      setLanguage(lang);
      const hubHtml = renderArenaPage({ subview: "hub" });
      const trainingHtml = renderTrainingView({
        status: "idle",
        busy: false,
        error: null,
        notice: null,
        confirming: null,
        data: { session: createTestTrainingSession(), feedback: null },
        draftAnswer: "",
      });

      if (lang === "it") {
        assert.ok(hubHtml.includes("Arena Duelli"));
        assert.ok(hubHtml.includes("Allenamento"));
        assert.ok(trainingHtml.includes("Al tuo ritmo"));
      } else if (lang === "en") {
        assert.ok(hubHtml.includes("Duels Arena"));
        assert.ok(hubHtml.includes("Training"));
        assert.ok(trainingHtml.includes("At your pace"));
      } else if (lang === "es") {
        assert.ok(hubHtml.includes("Arena de Duelos"));
        assert.ok(hubHtml.includes("Entrenamiento"));
        assert.ok(trainingHtml.includes("A tu ritmo"));
      }
    }
  } finally {
    setLanguage(initialLang);
  }
});

test("Arena + Training coexistence: 14. no duplicate event submission after navigating repeatedly between Arena/Training/Duel", async () => {
  const { container, cleanup } = setupGlobalDom();
  const { restore: restoreTg } = setupTestTelegram();
  const activeSession = createTestTrainingSession({ attempts: 0, revision: 1 });
  const { requests, restore: restoreFetch } = captureFetchRequests((_url: string, init?: RequestInit) => {
    const body = JSON.parse(String(init?.body || "{}"));
    if (body.mode === "training" && body.action === "get") {
      return { session: activeSession, feedback: null };
    }
    if (body.mode === "training" && body.action === "guess") {
      return { session: { ...activeSession, attempts: 1 }, feedback: { status: "wrong" } };
    }
    return createTestDuelData({ code: CODE_A });
  });

  try {
    const app = new App(container);
    app.init();
    app.setTab("arena");

    // Navigate Hub -> Training -> Hub -> Duel -> Hub -> Training
    for (let i = 0; i < 3; i++) {
      const trainBtn = container.querySelector<HTMLButtonElement>('[data-arena-nav="training"]');
      trainBtn?.click();
      await new Promise((r) => setTimeout(r, 10));

      const backBtn = container.querySelector<HTMLButtonElement>("[data-training-back]");
      backBtn?.click();
      await new Promise((r) => setTimeout(r, 10));
    }

    // Now in Training
    const trainBtn = container.querySelector<HTMLButtonElement>('[data-arena-nav="training"]');
    trainBtn?.click();
    await new Promise((r) => setTimeout(r, 10));

    // Clear previous requests
    requests.length = 0;

    // Submit guess
    const input = container.querySelector<HTMLInputElement>("#training-answer");
    assert.ok(input);
    input.value = "Del Piero";
    const submitBtn = container.querySelector<HTMLButtonElement>("#training-submit");
    assert.ok(submitBtn);
    submitBtn.click();
    await new Promise((r) => setTimeout(r, 20));

    // Verify exactly ONE guess request was submitted
    const guessRequests = requests.filter((r) => r.body?.mode === "training" && r.body?.action === "guess");
    assert.equal(guessRequests.length, 1, "must submit exactly one guess request despite repeated navigation");
  } finally {
    restoreFetch();
    restoreTg();
    cleanup();
  }
});

test("Arena + Training coexistence: 15. legacy /app unchanged", () => {
  const legacyArenaPath = path.resolve(process.cwd(), "webapp/arena.js");
  const legacyClientPath = path.resolve(process.cwd(), "webapp/client.js");

  assert.ok(fs.existsSync(legacyArenaPath), "webapp/arena.js must exist");
  assert.ok(fs.existsSync(legacyClientPath), "webapp/client.js must exist");

  const arenaContent = fs.readFileSync(legacyArenaPath, "utf-8");
  assert.ok(arenaContent.includes("PlayerArena"), "arena.js must export PlayerArena");
});

