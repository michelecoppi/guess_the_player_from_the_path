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
  switch (id) {
    case "arena":
      title = "Arena";
      kicker = "DUELLI / 1 CONTRO 1";
      body = `<div class="scoreboard"><div class="score-teams"><span>MARCO</span><span>Round ${duel.current_round} / ${duel.total_rounds}</span><span>${e(duel.opponent?.name).toUpperCase()}</span></div><div class="score">${duel.user_score} : ${duel.opponent_score}</div><div class="flex justify-between text-secondary text-xs"><span>2 carriere indovinate</span><span>1 carriera indovinata</span></div></div>${section("Il prossimo round", `<p class="muted mb-4">Cinque carriere. Un avversario. Ogni risposta conta.</p>${disabled("Continua il duello")}`)}${section("Un’altra partita", disabled("Sfida un amico"))}`;
      break;
    case "profile":
      title = "La tua carriera";
      kicker = "PROFILO GIOCATORE";
      body = `<div class="profile-pass">${renderAvatar({ name: profile.name, size: "large" })}<div><p class="eyebrow">PLAYER / 001</p><h3>${e(profile.name)}</h3><p class="muted text-xs">Sette giornate di fila</p></div></div><div class="stat-grid three-cols">${renderStatTile({ value: profile.points, label: "Punti totali" })}${renderStatTile({ value: profile.current_streak, label: "Serie attuale" })}${renderStatTile({ value: profile.best_streak, label: "Serie record" })}</div>${section("Bacheca", `<div class="row">${icon("ranking")}<div class="name">Secondo classificato<p class="muted text-xs">Settembre · classifica mensile</p></div><span class="pts">02</span></div>`)}${section("Il tuo stile", disabled("Personalizza il profilo"))}`;
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
  return `<aside class="prototype-notice"><b>${v("preview")}</b><p>${v("previewNote")}</p></aside><article class="prototype" data-prototype="${id}"><p class="eyebrow">${kicker}</p><h2 class="page-title">${title}</h2>${body}</article>`;
}
