/*
  La logica della mini app che non tocca ne' il DOM ne' la rete: sta qui perche' e' l'unica
  parte del client che si puo' provare senza un browser. `index.html` la carica come
  <script> e i test la caricano con require(), senza bundler e senza passaggio di build.

  La regola per decidere cosa entra: una funzione sta qui se, dandole gli stessi argomenti,
  torna sempre la stessa cosa. Tutto quello che legge `state`, disegna HTML o chiama le API
  resta in index.html - portarlo qui vorrebbe dire portarci anche mezza pagina.
*/
(function (root) {
"use strict";
function escapeHtml(value) {
  return String(value == null ? "" : value).replace(/[&<>"']/g, c => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

function initials(name) {
  return (name || "?").split(" ").filter(Boolean).slice(0, 2).map(w => w[0].toUpperCase()).join("") || "?";
}

function mergeProfile(previous, incoming, lightweight) {
  return lightweight ? Object.assign({}, previous, incoming) : incoming;
}

/*
  I quadretti del risultato, gli stessi che finiscono nel testo da condividere: uno rosso
  per ogni tentativo sbagliato, il verde solo se ha indovinato, i restanti vuoti.

  Il conto e' meno ovvio di quanto sembra: `used` comprende anche il tentativo giusto,
  quindi chi indovina al primo colpo ha zero quadretti rossi e non uno. I simboli arrivano
  da fuori perche' si possono comprare in negozio (services/shop.py): un set diverso non
  cambia il conteggio.
*/
function squares(used, max, solved, symbols) {
  const wrong = solved ? Math.max(used - 1, 0) : used;
  return symbols.wrong.repeat(wrong)
    + (solved ? symbols.correct : "")
    + symbols.unused.repeat(Math.max(max - wrong - (solved ? 1 : 0), 0));
}

/*
  L'istogramma "in quanti tentativi risolvi di solito", alla Wordle.

  La barra piu' lunga e' quella del valore massimo, non del totale: interessa il confronto
  fra le colonne, non la percentuale. Il minimo dell'8% serve a far vedere che una colonna
  c'e' anche quando vale 1 su 300, e `played` a zero e' il caso di chi non ha ancora
  giocato, che merita una frase e non un grafico piatto.
*/
function histogram(distribution) {
  const rows = distribution || [];
  const played = rows.reduce((sum, row) => sum + (row.count || 0), 0);
  const max = Math.max(1, ...rows.map(row => row.count || 0));
  return {
    played,
    rows: rows.map(row => ({
      attempts: row.attempts,
      count: row.count || 0,
      best: row.count > 0 && row.count === max,
      width: Math.max(8, Math.round(100 * (row.count || 0) / max)),
    })),
  };
}

/* Quanti trofei per ogni posizione del podio (primo, secondo, terzo). */
function cabinetCounts(all) {
  return [1, 2, 3].map(position => (all || []).filter(tag => tag.position === position).length);
}

/*
  La lingua del client Telegram ridotta a quella del gioco: 'es-MX' e' spagnolo, 'pt-BR' non
  e' fra le tre e diventa inglese. E' la stessa regola del server
  (services/i18n.resolve_language) con lo stesso ripiego, cosi' chi apre la mini app prima
  di aver scelto una lingua nel bot non vede due lingue diverse nei due posti.
*/
function languageFromCode(code, supported) {
  const languages = supported || ["it", "es", "en"];
  const short = String(code || "").toLowerCase().split("-")[0];
  return languages.indexOf(short) === -1 ? "en" : short;
}

/* Il numero di settimana dentro un identificativo ISO tipo "2026-W37". */
function weekNumber(week) {
  return String(week || "").split("W")[1] || "";
}

/*
  Quanto ci ha messo la mini app a diventare usabile, letto dalla timeline di Performance nel
  momento in cui i dati sono a schermo (#32). Solo numeri: il server tiene un insieme chiuso
  di metriche e le registra senza id. La stessa misura della V2 (webapp/src/telemetry/startup.ts).
*/
function startupMetrics(perf, firstDataAt) {
  const round = value => Math.round(value * 10) / 10;
  const metrics = { first_data_ms: round(firstDataAt) };
  const navigation = (perf.getEntriesByType("navigation") || [])[0];
  let transfer = 0;
  if (navigation) {
    if (navigation.responseStart > 0) metrics.ttfb_ms = round(navigation.responseStart);
    if (navigation.domContentLoadedEventEnd > 0) metrics.dom_ready_ms = round(navigation.domContentLoadedEventEnd);
    transfer += navigation.transferSize || 0;
  }
  const resources = perf.getEntriesByType("resource") || [];
  resources.forEach(entry => { transfer += entry.transferSize || 0; });
  const me = resources.filter(entry => /\/app\/api\/me$/.test(entry.name))[0];
  if (me) {
    metrics.api_me_ms = round(me.duration);
    const server = (me.serverTiming || []).filter(timing => timing.name === "app")[0];
    if (server) metrics.api_me_server_ms = round(server.duration);
  }
  if (transfer > 0) metrics.transfer_kb = round(transfer / 1024);
  return metrics;
}

const api = { escapeHtml, initials, mergeProfile, squares, histogram, cabinetCounts, languageFromCode, weekNumber, startupMetrics };
if (typeof module !== "undefined" && module.exports) module.exports = api;
else root.PlayerClient = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
