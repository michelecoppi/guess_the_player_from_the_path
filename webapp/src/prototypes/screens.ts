import { escapeHtml as e } from "@/utils/format";
import {
  renderAvatar,
  renderStatTile,
  renderListRow,
  renderButton,
} from "@/components";
import { icon } from "@/components/Icon";
import { v } from "@/i18n/visual";
import type { NavTabId } from "@/components/NavBar";
import {
  duel,
  profile,
  rankings,
  days,
  items,
  referral,
  event,
} from "./fixtures";
export type PrototypeId = Exclude<NavTabId, "play">;
const disabled = (label: string) =>
  renderButton({ label, disabled: true, fullWidth: true });
const section = (title: string, html: string) =>
  `<section class="prototype-section"><h3>${title}</h3>${html}</section>`;
export function renderPrototype(id: PrototypeId): string {
  let title = "",
    kicker = "",
    body = "";
  if (["reports", "refunds", "privacy"].includes(id))
    return renderSupport(id as "reports" | "refunds" | "privacy");
  switch (id) {
    case "arena":
      title = "Arena";
      kicker = "SCEGLI LA TUA PROSSIMA SFIDA";
      body = `<button class="arena-feature" data-tab="challenge"><div class="arena-feature-copy"><span class="mode-label">1 CONTRO 1</span><h3>Sfida un giocatore</h3><p>Stessa carriera. Vince chi la riconosce prima.</p><span class="feature-action">Scegli l’avversario ${icon("arrow")}</span></div><div class="versus-mark" aria-hidden="true"><span>M</span><b>VS</b><span>?</span></div></button>
      <button class="active-duel" data-tab="duels"><span class="duel-indicator">${icon("arena")}</span><span><b>Il tuo duello con Andrea</b><small>Round ${duel.current_round} di ${duel.total_rounds} · dati di esempio</small></span><strong>${duel.user_score} : ${duel.opponent_score}</strong>${icon("arrow")}</button>
      <section class="extra-modes"><h3>Altre modalità</h3><button class="mode-entry archive-entry" data-tab="archive"><span class="mode-icon">${icon("archive")}</span><span><b>Archivio</b><small>Recupera le Daily che hai perso</small></span>${icon("arrow")}</button><button class="mode-entry events-entry" data-tab="events"><span class="mode-icon">${icon("events")}</span><span><b>Eventi</b><small>Carriere speciali, nuove competizioni</small></span>${icon("arrow")}</button></section>`;
      break;
    case "challenge":
      title = "Sfida un giocatore";
      kicker = "ARENA / 1 CONTRO 1";
      body = `<div class="challenge-intro"><span class="mode-icon">${icon("referral")}</span><h3>Chi sfidi oggi?</h3><p>Invita un amico o cerca un altro giocatore.</p></div><label class="guess-label" for="opponent-search">Nome o username Telegram</label><input class="guess-input" id="opponent-search" placeholder="Cerca un giocatore" disabled><p class="prototype-explanation">La ricerca dei giocatori sarà disponibile con l’attivazione dei duelli.</p>${section("Gioca con un amico", disabled("Crea un invito al duello"))}`;
      break;
    case "duels":
      title = "Il tuo duello";
      kicker = "ARENA / PARTITA IN CORSO";
      body = `<div class="scoreboard"><div class="score-teams"><span>MARCO</span><span>Round ${duel.current_round} / ${duel.total_rounds}</span><span>${e(duel.opponent?.name).toUpperCase()}</span></div><div class="score">${duel.user_score} : ${duel.opponent_score}</div><div class="flex justify-between text-secondary text-xs"><span>2 carriere indovinate</span><span>1 carriera indovinata</span></div></div>${section("Il prossimo round", `<p class="muted mb-4">Cinque carriere. Un avversario. Ogni risposta conta.</p>${disabled("Continua il duello")}`)}${section("Un’altra partita", disabled("Sfida un amico"))}`;
      break;
    case "profile":
      title = "La tua carriera";
      kicker = "PROFILO GIOCATORE";
      body = `<div class="profile-pass">${renderAvatar({ name: profile.name, size: "large" })}<div><p class="eyebrow">PLAYER / 001</p><h3>${e(profile.name)}</h3><p class="muted text-xs">Sette giornate di fila</p></div></div><div class="stat-grid three-cols">${renderStatTile({ value: profile.points, label: "Punti totali" })}${renderStatTile({ value: profile.current_streak, label: "Serie attuale" })}${renderStatTile({ value: profile.best_streak, label: "Serie record" })}</div>${section("Bacheca", `<div class="row">${icon("ranking")}<div class="name">Secondo classificato<p class="muted text-xs">Settembre · classifica mensile</p></div><span class="pts">02</span></div>`)}${section("Il tuo stile", disabled("Personalizza il profilo"))}<button class="mode-entry" data-tab="referral"><span class="mode-icon">${icon("referral")}</span><span><b>Invita amici</b><small>Fai crescere la tua squadra</small></span>${icon("arrow")}</button>`;
      break;
    case "leaderboard":
      title = "Classifica";
      kicker = "LA SETTIMANA / 07–13 SET";
      body = `<div class="flex justify-between text-secondary text-xs border-b pb-3"><span>POS. / GIOCATORE</span><span>PUNTI</span></div><div role="list">${rankings.map((r) => renderListRow({ position: String(r.rank).padStart(2, "0"), title: r.name, subtitle: `${r.best_streak} giornate di fila`, value: r.points, isCurrent: r.user_id === 1 })).join("")}</div>${section("La tua lega", `<div class="ticket"><p class="eyebrow">LEGA PRIVATA</p><h3>Amici del Bar</h3><p>12 giocatori · una classifica condivisa</p>${disabled("Apri la lega")}</div>`)}`;
      break;
    case "archive":
      title = "Settembre 2026";
      kicker = "ARCHIVIO / DAILY CHALLENGE";
      body = `<div class="calendar-grid">${["L", "M", "M", "G", "V", "S", "D"].map((x) => `<span>${x}</span>`).join("")}<div></div>${days.map((d, i) => `<div class="calendar-day ${d.solved ? "solved" : d.available ? "" : "future"} ${i === 11 ? "today" : ""}" aria-label="${e(d.date)} · ${d.solved ? "Indovinata" : d.available ? "Disponibile" : "In arrivo"}"><b>${i + 1}</b>${d.solved ? icon("check") : "<span>·</span>"}</div>`).join("")}</div>${section("Il tuo mese", `<div class="stat-grid">${renderStatTile({ value: 9, label: "Carriere indovinate" })}${renderStatTile({ value: 2, label: "Da recuperare" })}</div>`)}${section("Giornata 08", `<p class="muted mb-4">Una carriera ancora da scoprire.</p>${disabled("Gioca questa giornata")}`)}`;
      break;
    case "shop":
      title = "Lo spogliatoio";
      kicker = "SHOP / IL TUO STILE";
      body = items
        .map(
          (item) =>
            `<article class="shop-item"><div class="shop-swatch">${icon(item.type === "frame" ? "profile" : "career")}</div><div><h3>${e(item.name)}</h3><p>${e(item.description)}</p>${disabled(item.equipped ? "Equipaggiato" : `${item.price_stars} Stelle`)}</div></article>`,
        )
        .join("");
      break;
    case "referral":
      title = "Porta un amico";
      kicker = "INVITI / LA TUA SQUADRA";
      body = `<div class="ticket"><p class="eyebrow">PASS PER UN AMICO</p><h3>Il calcio si gioca<br>in compagnia.</h3><p>Invita un amico a indovinare la prossima carriera.</p>${disabled("Condividi l’invito")}<div class="ticket-code">${referral.qualified_count} / ${referral.max_rewards}</div><span class="muted text-xs">Amici qualificati / premi disponibili</span></div>${section("La tua squadra", `<div role="list">${referral.friends.map((f) => renderListRow({ title: f.name, subtitle: `${f.days_completed} giornate completate`, value: f.qualified ? "Qualificato" : "In gioco" })).join("")}</div>`)}`;
      break;
    case "events":
      title = "Eventi";
      kicker = "IL CALENDARIO / EDIZIONI SPECIALI";
      body = `<div class="event-banner">${icon("events")}<p class="eyebrow">15–22 SETTEMBRE</p><h3>${e(event.title)}</h3><p class="muted mt-4">${e(event.theme)}</p></div>${section("Una settimana europea", `<p class="muted mb-4">Percorsi tra i club che hanno scritto la storia delle coppe.</p>${disabled("In arrivo")}`)}`;
  }
  const parent = ["archive", "events", "duels", "challenge"].includes(id)
    ? "arena"
    : id === "referral"
      ? "profile"
      : null;
  const back = parent
    ? `<button class="back-link" data-tab="${parent}">${icon("back")}${v(parent === "arena" ? "backArena" : "backProfile")}</button>`
    : "";
  return `${back}<aside class="prototype-notice"><b>${v("preview")}</b><p>${v("previewNote")}</p></aside><article class="prototype" data-prototype="${id}"><p class="eyebrow">${kicker}</p><h2 class="page-title">${title}</h2>${body}</article>`;
}

function renderSupport(id: "reports" | "refunds" | "privacy"): string {
  const content = {
    reports: `<p>Hai trovato un errore in una carriera o un problema nella Mini App?</p><div class="support-block"><h3>Cosa indicare</h3><p>Numero della Daily, club o stagione coinvolti e una breve descrizione. Se puoi, aggiungi uno screenshot.</p></div><p class="prototype-explanation">L’invio delle segnalazioni dal menu è in preparazione. Questa anteprima non invia messaggi al bot.</p>`,
    refunds: `<p>Per un acquisto in Stelle, contatta l’assistenza nella chat privata del bot.</p><div class="support-block"><h3>Richiedi assistenza</h3><code>/paysupport</code><p>Aggiungi la descrizione del problema e l’identificativo dell’acquisto. Il bot inoltrerà la richiesta all’assistenza.</p></div><p>La richiesta viene valutata dall’assistenza; aprire questa pagina non esegue un rimborso.</p>`,
    privacy: `<p>Puoi richiedere la cancellazione dei tuoi dati di gioco dalla chat privata del bot.</p><div class="support-block"><h3>Gestisci i tuoi dati</h3><code>/forgetme</code><p>Il bot ti mostrerà la richiesta di conferma prima di cancellare i dati.</p></div><p>Questa pagina è informativa e non avvia la cancellazione.</p>`,
  };
  return `<button class="back-link" data-tab="play">${icon("back")}${v("backDaily")}</button><article class="support-page" data-support="${id}"><span class="support-symbol">${icon(id)}</span><h2 class="page-title">${v(id)}</h2>${content[id]}</article>`;
}
