import { test } from "node:test";
import assert from "node:assert/strict";
import {
  renderButton,
  renderCard,
  renderPageContainer,
  renderBadge,
  renderCareerPath,
  renderGuessInput,
  renderHintPanel,
  renderFeedbackBox,
  renderLoadingState,
  renderSkeleton,
  renderErrorState,
  renderEmptyState,
  renderStatTile,
  renderAvatar,
  renderListRow,
  renderModal,
} from "../../webapp/src/components";
import { renderToDom, createTestCareerPath } from "./helpers";

test("renderButton renders accessible primary, ghost, and destructive buttons", () => {
  const { element: primaryBtn, cleanup: c1 } = renderToDom<HTMLButtonElement>(
    renderButton({ label: "Gioca", variant: "primary", id: "play-btn" })
  );
  assert.equal(primaryBtn.tagName, "BUTTON");
  assert.equal(primaryBtn.id, "play-btn");
  assert.ok(primaryBtn.classList.contains("btn"));
  assert.equal(primaryBtn.textContent?.trim(), "Gioca");
  assert.equal(primaryBtn.disabled, false);
  c1();

  const { element: ghostBtn, cleanup: c2 } = renderToDom<HTMLButtonElement>(
    renderButton({ label: "Indizio", variant: "ghost", size: "small" })
  );
  assert.ok(ghostBtn.classList.contains("ghost"));
  assert.ok(ghostBtn.classList.contains("small"));
  c2();

  const { element: destructiveBtn, cleanup: c3 } = renderToDom<HTMLButtonElement>(
    renderButton({ label: "Elimina", variant: "destructive" })
  );
  assert.ok(destructiveBtn.classList.contains("destructive"));
  c3();
});

test("renderButton handles loading and disabled states with accessibility attributes", () => {
  const { element, cleanup } = renderToDom<HTMLButtonElement>(
    renderButton({
      label: "Caricamento...",
      loading: true,
      ariaLabel: "Invio risposta in corso",
    })
  );
  assert.equal(element.disabled, true);
  assert.equal(element.getAttribute("aria-busy"), "true");
  assert.equal(element.getAttribute("aria-label"), "Invio risposta in corso");
  assert.ok(element.querySelector(".spinner"));
  cleanup();
});

test("renderCard renders header kicker, title, top-right action, and body content", () => {
  const { element, cleanup } = renderToDom<HTMLElement>(
    renderCard({
      id: "daily-card",
      kicker: "Sfida del giorno",
      title: "Calciatore misterioso",
      actionHtml: '<span class="pill">#42</span>',
      bodyHtml: "<p>Dati della carriera</p>",
      as: "section",
    })
  );

  assert.equal(element.tagName, "SECTION");
  assert.equal(element.id, "daily-card");
  assert.equal(element.querySelector(".card-kicker")?.textContent, "Sfida del giorno");
  assert.equal(element.querySelector(".card-title")?.textContent, "Calciatore misterioso");
  assert.ok(element.querySelector(".card-action .pill"));
  assert.equal(element.querySelector(".card-body")?.innerHTML.trim(), "<p>Dati della carriera</p>");
  cleanup();
});

test("renderPageContainer standardizes screen layout with title and header actions", () => {
  const { element, cleanup } = renderToDom<HTMLElement>(
    renderPageContainer({
      id: "screen-daily",
      kicker: "Modalità",
      title: "Daily Challenge",
      headerActionHtml: '<button id="rules-btn">Regole</button>',
      contentHtml: '<div class="content-block">Contenuto</div>',
    })
  );

  assert.equal(element.id, "screen-daily");
  assert.ok(element.classList.contains("page-container"));
  assert.equal(element.querySelector(".page-title")?.textContent, "Daily Challenge");
  assert.ok(element.querySelector("#rules-btn"));
  assert.ok(element.querySelector(".content-block"));
  cleanup();
});

test("renderBadge supports all status variants with escaping", () => {
  for (const variant of ["success", "danger", "warning", "info", "neutral"] as const) {
    const { element, cleanup } = renderToDom<HTMLElement>(
      renderBadge({ label: `<${variant}>`, variant, icon: "⚽" })
    );
    assert.ok(element.classList.contains("pill"));
    assert.ok(element.classList.contains(variant));
    assert.equal(element.textContent?.includes(`<${variant}>`), true);
    assert.equal(element.querySelector(".badge-icon")?.textContent, "⚽");
    cleanup();
  }
});

test("renderCareerPath correctly formats stops, loan styling, apps, and metadata", () => {
  const stops = createTestCareerPath();
  const { element, cleanup } = renderToDom<HTMLElement>(
    renderCareerPath({ stops, id: "career-timeline" })
  );

  assert.equal(element.id, "career-timeline");
  assert.equal(element.getAttribute("role"), "list");
  const items = element.querySelectorAll(".stop");
  assert.equal(items.length, 3);

  // Stop 1: Parma
  assert.equal(items[0].querySelector(".team")?.textContent, "Parma");
  assert.equal(items[0].querySelector(".meta")?.textContent, "Serie A · Italia");
  assert.equal(items[0].querySelector(".years")?.textContent, "1995 – 2001");
  assert.equal(items[0].classList.contains("loan"), false);

  // Stop 3: Paris Saint-Germain (loan)
  assert.equal(items[2].querySelector(".team")?.textContent, "Paris Saint-Germain");
  assert.ok(items[2].classList.contains("loan"));
  assert.ok(items[2].querySelector(".years")?.textContent?.startsWith("→ "));

  cleanup();
});

test("renderCareerPath handles empty list gracefully", () => {
  const emptyHtml = renderCareerPath({ stops: [], emptyText: "Nessuna informazione" });
  const { element, cleanup } = renderToDom<HTMLElement>(emptyHtml);
  assert.ok(element.classList.contains("path-empty"));
  assert.equal(element.textContent, "Nessuna informazione");
  cleanup();

  assert.equal(renderCareerPath({ stops: null }), "");
});

test("renderGuessInput renders accessible input form with submit button", () => {
  const { element, cleanup } = renderToDom<HTMLFormElement>(
    renderGuessInput({
      id: "guess-form",
      inputId: "player-guess-input",
      submitButtonId: "guess-submit-btn",
      placeholder: "Nome calciatore...",
      buttonLabel: "Invia",
      helperText: "Scrivi nome e cognome",
    })
  );

  assert.equal(element.tagName, "FORM");
  assert.equal(element.getAttribute("role"), "search");

  const input = element.querySelector<HTMLInputElement>("#player-guess-input");
  assert.ok(input);
  assert.equal(input.placeholder, "Nome calciatore...");
  assert.equal(input.autocomplete, "off");

  const button = element.querySelector<HTMLButtonElement>("#guess-submit-btn");
  assert.ok(button);
  assert.equal(button.type, "submit");
  assert.equal(button.textContent?.trim(), "Invia");

  const helper = element.querySelector("#player-guess-input-helper");
  assert.ok(helper);
  assert.equal(helper.textContent, "Scrivi nome e cognome");

  cleanup();
});

test("renderHintPanel renders revealed hints, remaining counter, and unlock button", () => {
  const { element, cleanup } = renderToDom<HTMLElement>(
    renderHintPanel({
      hintsTaken: ["Ha giocato nel Real Madrid", "Ruolo: Centrocampista"],
      hintsTotal: 3,
      hintsUsed: 2,
      unlockButtonId: "get-hint-btn",
      unlockButtonLabel: "Prendi un indizio",
      hintsLeftLabel: "indizi rimanenti",
    })
  );

  const hints = element.querySelectorAll(".hint-taken-item");
  assert.equal(hints.length, 2);
  assert.equal(hints[0].textContent, "Ha giocato nel Real Madrid");
  assert.equal(hints[1].textContent, "Ruolo: Centrocampista");

  const unlockBtn = element.querySelector("#get-hint-btn");
  assert.ok(unlockBtn);
  assert.equal(unlockBtn.textContent?.trim(), "Prendi un indizio");

  const counter = element.querySelector(".hints-remaining");
  assert.ok(counter);
  assert.equal(counter.textContent, "1 indizi rimanenti");

  cleanup();
});

test("renderHintPanel hides unlock button when all hints are exhausted", () => {
  const { element, cleanup } = renderToDom<HTMLElement>(
    renderHintPanel({
      hintsTaken: ["Indizio 1", "Indizio 2"],
      hintsTotal: 2,
      hintsUsed: 2,
    })
  );
  assert.equal(element.querySelector("#hint"), null);
  assert.equal(element.querySelector(".hints-remaining"), null);
  cleanup();
});

test("renderFeedbackBox renders correct and wrong states with comparison clues", () => {
  const { element: correctBox, cleanup: c1 } = renderToDom<HTMLElement>(
    renderFeedbackBox({
      status: "correct",
      title: "Esatto!",
      message: "100 punti assegnati.",
      shareLabel: "Condividi risultato",
      onShare: true,
    })
  );
  assert.ok(correctBox.classList.contains("ok"));
  assert.ok(correctBox.textContent?.includes("Esatto!"));
  assert.ok(correctBox.querySelector("#share"));
  c1();

  const { element: wrongBox, cleanup: c2 } = renderToDom<HTMLElement>(
    renderFeedbackBox({
      status: "wrong",
      title: "Sbagliato!",
      message: "Rimangono 2 tentativi.",
      comparedName: "Zinédine Zidane",
      clues: ["Stessa nazionalità", "Più anziano del 1985"],
    })
  );
  assert.ok(wrongBox.classList.contains("no"));
  assert.ok(wrongBox.textContent?.includes("Zinédine Zidane"));
  const clueItems = wrongBox.querySelectorAll("li");
  assert.equal(clueItems.length, 2);
  assert.equal(clueItems[0].textContent, "Stessa nazionalità");
  c2();
});

test("renderLoadingState and renderSkeleton output accessible loading placeholders", () => {
  const { element: loadingEl, cleanup: c1 } = renderToDom<HTMLElement>(
    renderLoadingState({ message: "Caricamento statistiche...", id: "loading-stats" })
  );
  assert.equal(loadingEl.getAttribute("role"), "status");
  assert.equal(loadingEl.getAttribute("aria-live"), "polite");
  assert.ok(loadingEl.querySelector(".spinner"));
  assert.equal(loadingEl.textContent?.trim(), "Caricamento statistiche...");
  c1();

  const skeletonHtml = renderSkeleton({ variant: "card", count: 2 });
  const { element: container, cleanup: c2 } = renderToDom<HTMLElement>(`<div>${skeletonHtml}</div>`);
  const skeletons = container.querySelectorAll(".skeleton.skeleton-card");
  assert.equal(skeletons.length, 2);
  c2();
});

test("renderErrorState outputs accessible error alert with retry button", () => {
  const { element, cleanup } = renderToDom<HTMLElement>(
    renderErrorState({
      id: "net-error",
      title: "Errore di connessione",
      message: "Impossibile contattare il server.",
      retryLabel: "Riprova",
      retryButtonId: "retry-api-btn",
    })
  );

  assert.equal(element.id, "net-error");
  assert.equal(element.getAttribute("role"), "alert");
  assert.equal(element.querySelector(".error-state-title")?.textContent, "Errore di connessione");
  assert.equal(element.querySelector(".error-state-message")?.textContent, "Impossibile contattare il server.");
  assert.ok(element.querySelector("#retry-api-btn"));
  cleanup();
});

test("renderEmptyState outputs empty view with icon and action", () => {
  const { element, cleanup } = renderToDom<HTMLElement>(
    renderEmptyState({
      title: "Archivio vuoto",
      description: "Non ci sono giornate precedenti disponibili.",
      actionLabel: "Torna alla sfida di oggi",
      actionButtonId: "go-today-btn",
    })
  );

  assert.equal(element.querySelector(".empty-state-title")?.textContent, "Archivio vuoto");
  assert.equal(element.querySelector(".empty-state-description")?.textContent, "Non ci sono giornate precedenti disponibili.");
  assert.ok(element.querySelector("#go-today-btn"));
  cleanup();
});

test("renderStatTile formats KPIs and labels", () => {
  const { element, cleanup } = renderToDom<HTMLElement>(
    renderStatTile({
      value: "1.450",
      label: "Punteggio totale",
      subtext: "+150 questa settimana",
      icon: "⭐",
    })
  );

  assert.ok(element.classList.contains("tile"));
  assert.ok(element.querySelector(".tile-value")?.textContent?.includes("1.450"));
  assert.equal(element.querySelector(".tile-label")?.textContent, "Punteggio totale");
  assert.equal(element.querySelector(".tile-sub")?.textContent, "+150 questa settimana");
  cleanup();
});

test("renderAvatar renders initials fallback, sizes, and cosmetic rings", () => {
  const { element: standardAvatar, cleanup: c1 } = renderToDom<HTMLElement>(
    renderAvatar({ name: "Gianluigi Buffon", size: "normal" })
  );
  assert.equal(standardAvatar.querySelector(".avatar")?.textContent?.trim(), "GB");
  c1();

  const { element: cosmeticAvatar, cleanup: c2 } = renderToDom<HTMLElement>(
    renderAvatar({
      name: "Paolo Maldini",
      ringStyle: "border: 2px solid gold;",
      spinRing: true,
      size: "large",
    })
  );
  assert.ok(cosmeticAvatar.classList.contains("large"));
  const ring = cosmeticAvatar.querySelector(".ring");
  assert.ok(ring);
  assert.ok(ring.classList.contains("spin"));
  c2();
});

test("renderListRow renders position, title, subtitle, points, and current user styling", () => {
  const { element, cleanup } = renderToDom<HTMLElement>(
    renderListRow({
      position: 1,
      title: "Marco Azzurri",
      subtitle: "Serie A Master",
      value: "2.400 pts",
      isCurrent: true,
      actionHtml: '<button class="view-btn">Vedi</button>',
    })
  );

  assert.ok(element.classList.contains("row"));
  assert.ok(element.classList.contains("me"));
  assert.equal(element.querySelector(".pos")?.textContent, "1");
  assert.ok(element.querySelector(".name")?.textContent?.includes("Marco Azzurri"));
  assert.equal(element.querySelector(".pts")?.textContent, "2.400 pts");
  assert.ok(element.querySelector(".view-btn"));
  cleanup();
});

test("renderModal renders accessible dialog semantics and close button", () => {
  const { element, cleanup } = renderToDom<HTMLElement>(
    renderModal({
      id: "purchase-dialog",
      title: "Conferma acquisto",
      bodyHtml: "<p>Vuoi acquistare la cornice d'oro per 100 Stelle?</p>",
      footerHtml: '<button id="confirm-buy">Conferma</button>',
      closeButtonId: "cancel-buy",
    })
  );

  assert.equal(element.getAttribute("role"), "presentation");
  const dialog = element.querySelector('[role="dialog"]');
  assert.ok(dialog);
  assert.equal(dialog.getAttribute("aria-modal"), "true");
  assert.equal(dialog.getAttribute("aria-labelledby"), "purchase-dialog-title");
  assert.equal(element.querySelector(".modal-title")?.textContent, "Conferma acquisto");
  assert.ok(element.querySelector("#cancel-buy"));
  assert.ok(element.querySelector("#confirm-buy"));
  cleanup();
});
