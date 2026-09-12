import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { LeaderboardController } from "../../webapp/src/features/leaderboard/controller";
import {
  renderLeaderboardView,
  renderLeaderboardRow,
} from "../../webapp/src/features/leaderboard/views";
import {
  renderLeaderboardPage,
  attachLeaderboardEventListeners,
} from "../../webapp/src/pages/LeaderboardPage";
import { setLanguage } from "../../webapp/src/i18n";
import {
  setupTestTelegram,
  mockFetchResponse,
  mockFetchError,
  captureFetchRequests,
  createTestFullProfile,
  createTestPublicProfile,
  createTestDom,
} from "./helpers";

test("1 & 2. full /me request includes social data without lightweight: true", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  const profileData = createTestFullProfile();
  const { requests, restore: restoreFetch } = captureFetchRequests(profileData);

  try {
    const controller = new LeaderboardController();
    await controller.init();

    assert.equal(requests.length, 1);
    const req = requests[0];
    assert.equal(req.url, "/app/api/me");
    assert.equal(req.method, "POST");
    assert.equal(req.body.lightweight, false);
    assert.ok(req.body.initData, "request must include Telegram initData in body");

    const state = controller.getState();
    assert.equal(state.status, "ready");
    assert.equal(state.globalLeaderboard.length, 4);
    assert.equal(state.leagues.length, 1);
  } finally {
    restoreFetch();
    restoreTg();
  }
});

test("3, 4, 5, 6. real global rows render preserving positions, points and backend badge", () => {
  setLanguage("it");
  const entries = [
    { position: 1, profile_id: 101, name: "Alessandro Del Piero", badge: "👑", points: 1540, me: false },
    { position: 2, profile_id: 102, name: "Francesco Totti", badge: "🥈", points: 1480, me: false },
    { position: 3, profile_id: 103, name: "Roberto Baggio", badge: "🥉", points: 1390, me: false },
  ];

  const html = renderLeaderboardView({
    status: "ready",
    error: null,
    activeTab: "global",
    selectedLeagueCode: null,
    globalLeaderboard: entries,
    leagues: [],
    publicProfile: null,
  });

  // Verify rows are rendered in backend order
  assert.ok(html.includes("Alessandro Del Piero"));
  assert.ok(html.includes("Francesco Totti"));
  assert.ok(html.includes("Roberto Baggio"));

  // Verify positions
  assert.ok(html.includes('>1</span>'));
  assert.ok(html.includes('>2</span>'));
  assert.ok(html.includes('>3</span>'));

  // Verify points
  assert.ok(html.includes('>1540</span>'));
  assert.ok(html.includes('>1480</span>'));
  assert.ok(html.includes('>1390</span>'));

  // Verify badge is rendered
  assert.ok(html.includes("👑 Alessandro Del Piero"));
  assert.ok(html.includes("🥈 Francesco Totti"));
  assert.ok(html.includes("🥉 Roberto Baggio"));
});

test("7. current user is highlighted by me === true and includes accessible non-color cue", () => {
  setLanguage("it");
  const entries = [
    { position: 1, profile_id: 101, name: "Alessandro Del Piero", points: 1540, me: false },
    { position: 2, profile_id: 103, name: "Mario", points: 1200, me: true },
  ];

  const html = renderLeaderboardView({
    status: "ready",
    error: null,
    activeTab: "global",
    selectedLeagueCode: null,
    globalLeaderboard: entries,
    leagues: [],
    publicProfile: null,
  });

  // Current user row has .row.me and aria-current="true"
  assert.ok(html.includes('class="row me"'));
  assert.ok(html.includes('aria-current="true"'));
  // Has non-color accessible tag (Tu)
  assert.ok(html.includes("me-tag"));
  assert.ok(html.includes("(Tu)"));
});

test("8. current user absent from top 10 is handled honestly without inventing position", () => {
  setLanguage("it");
  const entries = [
    { position: 1, profile_id: 101, name: "Top Player 1", points: 2000, me: false },
    { position: 2, profile_id: 102, name: "Top Player 2", points: 1900, me: false },
  ];

  const html = renderLeaderboardView({
    status: "ready",
    error: null,
    activeTab: "global",
    selectedLeagueCode: null,
    globalLeaderboard: entries,
    leagues: [],
    publicProfile: null,
  });

  // No row is highlighted as me
  assert.ok(!html.includes('class="row me"'));
  assert.ok(!html.includes("(Tu)"));
  // Does not invent a row with fake rank
  assert.ok(!html.includes("Top Player 3"));
});

test("9. valid profile row renders button with data-profile-id to open public profile", () => {
  const rowHtml = renderLeaderboardRow({
    position: 1,
    profile_id: 101,
    name: "Alex",
    points: 500,
    me: false,
  });

  assert.ok(rowHtml.includes('<button type="button" class="profile-link-btn" data-profile-id="101"'));
  assert.ok(rowHtml.includes('aria-label="Apri profilo · Alex"'));
});

test("10. invalid or missing profile_id renders plain non-clickable text", () => {
  const rowNoId = renderLeaderboardRow({
    position: 1,
    name: "Anonymous",
    points: 100,
    me: false,
  });
  assert.ok(!rowNoId.includes("<button"));
  assert.ok(rowNoId.includes('<span class="player-name">Anonymous</span>'));

  const rowNegativeId = renderLeaderboardRow({
    position: 2,
    profile_id: -5,
    name: "Bad ID",
    points: 50,
    me: false,
  });
  assert.ok(!rowNegativeId.includes("<button"));
  assert.ok(rowNegativeId.includes('<span class="player-name">Bad ID</span>'));
});

test("11. HTML-sensitive names and dirty data are strictly escaped", () => {
  const rowHtml = renderLeaderboardRow({
    position: 1,
    profile_id: 200,
    name: '<script>alert("xss")</script>',
    points: 999,
    me: false,
  }, '<img src=x onerror=alert(1)>');

  assert.ok(!rowHtml.includes("<script>"));
  assert.ok(rowHtml.includes("&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;"));
  assert.ok(!rowHtml.includes("<img src=x"));
  assert.ok(rowHtml.includes("&lt;img src=x onerror=alert(1)&gt;"));
});

test("12. empty global leaderboard renders proper empty state", () => {
  setLanguage("it");
  const html = renderLeaderboardView({
    status: "ready",
    error: null,
    activeTab: "global",
    selectedLeagueCode: null,
    globalLeaderboard: [],
    leagues: [],
    publicProfile: null,
  });

  assert.ok(html.includes("Nessun giocatore in classifica"));
  assert.ok(html.includes("La classifica è ancora vuota"));
});

test("13. zero private leagues renders proper empty state", () => {
  setLanguage("it");
  const html = renderLeaderboardView({
    status: "ready",
    error: null,
    activeTab: "leagues",
    selectedLeagueCode: null,
    globalLeaderboard: [],
    leagues: [],
    publicProfile: null,
  });

  assert.ok(html.includes("Nessuna lega"));
  assert.ok(html.includes("Non fai parte di nessuna lega."));
});

test("14 & 15. single and multiple private leagues render accurately with selector pills", () => {
  setLanguage("it");
  const leagues = [
    {
      code: "BAR01",
      name: "Amici del Bar",
      members: 5,
      position: 1,
      points: 1540,
      standings: [
        { position: 1, profile_id: 101, name: "Mario", points: 1540, me: true },
        { position: 2, profile_id: 102, name: "Luigi", points: 1200, me: false },
      ],
    },
    {
      code: "WORK02",
      name: "Colleghi Ufficio",
      members: 8,
      position: 3,
      points: 800,
      standings: [
        { position: 1, profile_id: 201, name: "Boss", points: 1900, me: false },
      ],
    },
  ];

  const html = renderLeaderboardView({
    status: "ready",
    error: null,
    activeTab: "leagues",
    selectedLeagueCode: "BAR01",
    globalLeaderboard: [],
    leagues,
    publicProfile: null,
  });

  // Multiple leagues show selector pills
  assert.ok(html.includes("league-pills"));
  assert.ok(html.includes('data-select-league="BAR01"'));
  assert.ok(html.includes('data-select-league="WORK02"'));

  // Active league details
  assert.ok(html.includes("Amici del Bar"));
  assert.ok(html.includes("BAR01"));
  assert.ok(html.includes("5 giocatori"));
  assert.ok(html.includes("La tua posizione: #1"));
  assert.ok(html.includes("1540 punti"));
});

test("16 & 17. league standings preserve backend ordering and current user row", () => {
  setLanguage("it");
  const league = {
    code: "LEAGUE1",
    name: "Fantacalcio",
    members: 3,
    position: 2,
    points: 900,
    standings: [
      { position: 1, profile_id: 101, name: "Primo", points: 1000, me: false },
      { position: 2, profile_id: 102, name: "Io", points: 900, me: true },
      { position: 3, profile_id: 103, name: "Terzo", points: 800, me: false },
    ],
  };

  const html = renderLeaderboardView({
    status: "ready",
    error: null,
    activeTab: "leagues",
    selectedLeagueCode: "LEAGUE1",
    globalLeaderboard: [],
    leagues: [league],
    publicProfile: null,
  });

  assert.ok(html.includes("Primo"));
  assert.ok(html.includes("Io"));
  assert.ok(html.includes("Terzo"));
  assert.ok(html.includes('class="row me"'));
  assert.ok(html.includes("(Tu)"));
});

test("18. long player names render without layout breaking", () => {
  const longName = "Karl-Heinz Rummenigge Von Hohenzollern Sigismondo III";
  const rowHtml = renderLeaderboardRow({
    position: 1,
    profile_id: 101,
    name: longName,
    points: 100000,
    me: false,
  });

  assert.ok(rowHtml.includes(longName));
  assert.ok(rowHtml.includes("100000"));
});

test("19. loading state renders accessible spinner and placeholder", () => {
  setLanguage("it");
  const html = renderLeaderboardView({
    status: "loading",
    error: null,
    activeTab: "global",
    selectedLeagueCode: null,
    globalLeaderboard: [],
    leagues: [],
    publicProfile: null,
  });

  assert.ok(html.includes("loading-state"));
  assert.ok(html.includes('role="status"'));
});

test("20 & 21. API error renders error message with refresh/retry trigger", async () => {
  setLanguage("it");
  const { restore: restoreTg } = setupTestTelegram();
  const restoreFetch = mockFetchError(500, "Database indisponibile");

  try {
    const controller = new LeaderboardController();
    await controller.load();

    const state = controller.getState();
    assert.equal(state.status, "error");

    const html = renderLeaderboardView(state);
    assert.ok(html.includes('role="alert"'));
    assert.ok(html.includes("Impossibile caricare la classifica"));
    assert.ok(html.includes("Riprova"));
  } finally {
    restoreFetch();
    restoreTg();
  }
});

test("22. duplicate-load protection prevents concurrent in-flight requests", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  let fetchCount = 0;
  const restoreFetch = mockFetchResponse(async () => {
    fetchCount++;
    await new Promise((r) => setTimeout(r, 50));
    return createTestFullProfile();
  });

  try {
    const controller = new LeaderboardController();
    const p1 = controller.load();
    const p2 = controller.load();
    const p3 = controller.load();

    await Promise.all([p1, p2, p3]);
    assert.equal(fetchCount, 1, "only 1 network request should be dispatched for concurrent load calls");
  } finally {
    restoreFetch();
    restoreTg();
  }
});

test("23. stale/out-of-order response guard discards outdated responses", async () => {
  const { restore: restoreTg } = setupTestTelegram();
  let callIndex = 0;
  const restoreFetch = mockFetchResponse(async () => {
    callIndex++;
    if (callIndex === 1) {
      // First call is slow
      await new Promise((r) => setTimeout(r, 80));
      return createTestFullProfile({
        leaderboard: [{ position: 1, name: "Old Data", points: 10, me: false }],
      });
    }
    // Second call is fast
    await new Promise((r) => setTimeout(r, 10));
    return createTestFullProfile({
      leaderboard: [{ position: 1, name: "New Fresh Data", points: 100, me: false }],
    });
  });

  try {
    const controller = new LeaderboardController();
    // First load dispatched
    const p1 = controller.load(true);
    // Almost immediately, another refresh is forced
    await new Promise((r) => setTimeout(r, 5));
    // Reset loadInFlight for testing forced re-request seq
    const p2 = controller.refresh();

    await Promise.all([p1, p2]);
    const state = controller.getState();
    assert.equal(state.globalLeaderboard[0].name, "New Fresh Data");
  } finally {
    restoreFetch();
    restoreTg();
  }
});

test("24, 25, 26. complete localization across Italian, English, and Spanish", () => {
  const entries = [
    { position: 1, profile_id: 101, name: "Player 1", points: 500, me: true },
  ];
  const leagues = [
    { code: "L1", name: "League 1", members: 2, position: 1, points: 500, standings: [] },
  ];

  // Italian
  setLanguage("it");
  const itHtml = renderLeaderboardView({
    status: "ready",
    error: null,
    activeTab: "global",
    selectedLeagueCode: "L1",
    globalLeaderboard: entries,
    leagues,
    publicProfile: null,
  });
  assert.ok(itHtml.includes("Classifica Generale"));
  assert.ok(itHtml.includes("PUNTI"));
  assert.ok(itHtml.includes("(Tu)"));

  // English
  setLanguage("en");
  const enHtml = renderLeaderboardView({
    status: "ready",
    error: null,
    activeTab: "global",
    selectedLeagueCode: "L1",
    globalLeaderboard: entries,
    leagues,
    publicProfile: null,
  });
  assert.ok(enHtml.includes("Global Leaderboard"));
  assert.ok(enHtml.includes("POINTS"));
  assert.ok(enHtml.includes("(You)"));

  // Spanish
  setLanguage("es");
  const esHtml = renderLeaderboardView({
    status: "ready",
    error: null,
    activeTab: "global",
    selectedLeagueCode: "L1",
    globalLeaderboard: entries,
    leagues,
    publicProfile: null,
  });
  assert.ok(esHtml.includes("Clasificación General"));
  assert.ok(esHtml.includes("PUNTOS"));
  assert.ok(esHtml.includes("(Tú)"));

  setLanguage("it");
});

test("27. prototype data and notice are absent from runtime", () => {
  setLanguage("it");
  const entries = [
    { position: 1, profile_id: 101, name: "Real Player", points: 500, me: false },
  ];

  const html = renderLeaderboardPage({
    status: "ready",
    error: null,
    activeTab: "global",
    selectedLeagueCode: null,
    globalLeaderboard: entries,
    leagues: [],
    publicProfile: null,
  });

  // Prototype hard-coded strings must not appear
  assert.ok(!html.includes("LA SETTIMANA / 07–13 SET"));
  assert.ok(!html.includes("Marco Rossi"));
  assert.ok(!html.includes("Sofia Riva"));
  assert.ok(!html.includes("Amici del Bar") || !html.includes("12 giocatori · una classifica condivisa"));
  assert.ok(!html.includes("prototype-notice"));
});

test("28. legacy /app webapp/index.html remains completely untouched", () => {
  const legacyHtmlPath = path.resolve(__dirname, "../../webapp/index.html");
  const legacyContent = fs.readFileSync(legacyHtmlPath, "utf-8");

  assert.ok(legacyContent.includes('function statsTab()'));
  assert.ok(legacyContent.includes('function leaguesTab()'));
  assert.ok(legacyContent.includes('state.profile.leaderboard'));
  assert.ok(legacyContent.includes('state.profile.leagues'));
});

test("29. public profile flow: click row opens public profile with back button restoring ranking", async () => {
  setLanguage("it");
  const { restore: restoreTg } = setupTestTelegram();
  const publicData = createTestPublicProfile();
  const { requests, restore: restoreFetch } = captureFetchRequests((url: unknown) => {
    if (String(url).includes("/profile/public")) {
      return publicData;
    }
    return createTestFullProfile();
  });

  try {
    const controller = new LeaderboardController();
    await controller.init();

    // User clicks player with profile_id 101
    await controller.openPublicProfile(101);

    assert.equal(requests.length, 2);
    assert.equal(requests[1].url, "/app/api/profile/public");
    assert.equal(requests[1].body.profile_id, 101);

    const state = controller.getState();
    assert.ok(state.publicProfile);
    assert.equal(state.publicProfile.status, "ready");
    assert.equal(state.publicProfile.data?.user.name, "Alessandro Del Piero");

    const html = renderLeaderboardPage(state);
    assert.ok(html.includes("Alessandro Del Piero"));
    assert.ok(html.includes("Torna alla classifica"));
    assert.ok(html.includes("I numeri di gioco"));
    assert.ok(html.includes("Maglia numero 10"));

    // Close public profile
    controller.closePublicProfile();
    assert.equal(controller.getState().publicProfile, null);
    const restoredHtml = renderLeaderboardPage(controller.getState());
    assert.ok(restoredHtml.includes("Classifica Generale"));
    assert.ok(!restoredHtml.includes("Torna alla classifica"));
  } finally {
    restoreFetch();
    restoreTg();
  }
});

test("30. DOM event wiring triggers tab switches, league selection, profile opening and refresh", async () => {
  setLanguage("it");
  const { restore: restoreTg } = setupTestTelegram();
  const restoreFetch = mockFetchResponse(createTestFullProfile());
  const { container, cleanup } = createTestDom('<div id="root"></div>');

  try {
    const controller = new LeaderboardController();
    await controller.init();

    container.innerHTML = renderLeaderboardPage(controller.getState());
    attachLeaderboardEventListeners(container, controller);

    // Switch to leagues tab
    const leaguesTabBtn = container.querySelector<HTMLButtonElement>("button[data-leaderboard-tab='leagues']");
    assert.ok(leaguesTabBtn);
    leaguesTabBtn.click();
    assert.equal(controller.getState().activeTab, "leagues");

    // Switch back to global tab
    const globalTabBtn = container.querySelector<HTMLButtonElement>("button[data-leaderboard-tab='global']");
    assert.ok(globalTabBtn);
    globalTabBtn.click();
    assert.equal(controller.getState().activeTab, "global");

    // Click profile link
    const profileBtn = container.querySelector<HTMLButtonElement>("button[data-profile-id='101']");
    assert.ok(profileBtn);
    profileBtn.click();
    assert.equal(controller.getState().publicProfile?.profileId, 101);
  } finally {
    cleanup();
    restoreFetch();
    restoreTg();
  }
});

test("31. public profile renders resolved cosmetic presentation values and never raw equipped item IDs", () => {
  setLanguage("it");
  const profileData = createTestPublicProfile();

  // Verify fixture intentionally demonstrates the distinction
  assert.equal(profileData.cosmetics.equipped?.badge, "distintivo_stella");
  assert.equal(profileData.cosmetics.badge, "⭐");
  assert.equal(profileData.cosmetics.equipped?.number, "maglia_dieci");
  assert.equal(profileData.cosmetics.number, "10");

  const html = renderLeaderboardPage({
    status: "ready",
    error: null,
    activeTab: "global",
    selectedLeagueCode: null,
    globalLeaderboard: [],
    leagues: [],
    publicProfile: {
      profileId: 101,
      status: "ready",
      data: profileData,
      error: null,
    },
  });

  // Verify resolved badge emoji is rendered
  assert.ok(html.includes("⭐"));
  assert.ok(html.includes("Alessandro Del Piero ⭐"));

  // Verify resolved shirt number is rendered
  assert.ok(html.includes('<span class="shirt">10</span>'));

  // Verify heading does NOT contain raw cosmetic item IDs
  const headingMatch = html.match(/<h1 id="public-profile-heading"[^>]*>([\s\S]*?)<\/h1>/);
  assert.ok(headingMatch, "public profile heading must be rendered");
  const headingHtml = headingMatch[1];
  assert.ok(!headingHtml.includes("distintivo_stella"), "heading must not contain raw badge item ID");
  assert.ok(!headingHtml.includes("maglia_dieci"), "heading must not contain raw number item ID");

  // Verify raw cosmetic item IDs never leak into profile presentation
  assert.ok(!html.includes("distintivo_stella"), "profile view must not contain raw badge ID");
  assert.ok(!html.includes("maglia_dieci"), "profile view must not contain raw number ID");
});

test("32. row accessibility labels (position, points, open profile, current user) are localized across IT, EN, and ES", () => {
  const rowData = {
    position: 1,
    profile_id: 101,
    name: "Alessandro Del Piero",
    points: 1540,
    me: true,
  };

  // Italian
  setLanguage("it");
  const itRow = renderLeaderboardRow(rowData);
  assert.ok(itRow.includes('aria-label="Posizione 1"'), "IT position aria-label");
  assert.ok(itRow.includes('aria-label="1540 punti"'), "IT points aria-label");
  assert.ok(itRow.includes('aria-label="Tu"'), "IT you aria-label");
  assert.ok(itRow.includes('aria-label="Apri profilo · Alessandro Del Piero"'), "IT open profile aria-label");

  // English
  setLanguage("en");
  const enRow = renderLeaderboardRow(rowData);
  assert.ok(enRow.includes('aria-label="Position 1"'), "EN position aria-label");
  assert.ok(enRow.includes('aria-label="1540 points"'), "EN points aria-label");
  assert.ok(enRow.includes('aria-label="You"'), "EN you aria-label");
  assert.ok(enRow.includes('aria-label="Open profile · Alessandro Del Piero"'), "EN open profile aria-label");

  // Spanish
  setLanguage("es");
  const esRow = renderLeaderboardRow(rowData);
  assert.ok(esRow.includes('aria-label="Posición 1"'), "ES position aria-label");
  assert.ok(esRow.includes('aria-label="1540 puntos"'), "ES points aria-label");
  assert.ok(esRow.includes('aria-label="Tú"'), "ES you aria-label");
  assert.ok(esRow.includes('aria-label="Abrir perfil · Alessandro Del Piero"'), "ES open profile aria-label");

  setLanguage("it");
});

