/* Game centre. The server owns every puzzle, attempt and result. */
(function (root) {
"use strict";
const TEXT = {
  it: {
    headline: "Il prossimo fischio d’inizio.", intro: "Una sfida al giorno. E tutto un campo da esplorare.",
    training: "Allenamento", trainingTag: "Al tuo ritmo", trainingDesc: "Cinque tentativi, nessuna pressione. Affina il tuo fiuto calcistico.",
    duel: "Sfida un amico", duelTag: "Testa a testa", duelDesc: "Cinque percorsi uguali per entrambi. Giocate quando volete.",
    events: "Eventi settimanali", eventsTag: "La competizione", eventsDesc: "Temi speciali, classifica dedicata e un posto sul podio.",
    back: "Torna a Gioca", start: "Inizia ad allenarti", next: "Prossimo percorso", reveal: "Rivela e termina", create: "Crea un duello",
    rules: "5 percorsi · 3 tentativi per percorso. Vince chi ne indovina di più; a parità, chi usa meno tentativi. Un percorso perso vale 3 tentativi. Nessun punto nella classifica generale. Invito valido 7 giorni.",
    trainRules: "5 tentativi per percorso. Puoi rivelare la soluzione e continuare con un altro calciatore. Nessun punto nella classifica generale.",
    invite: "Invita un amico", inviteText: "Riconosci questi 5 calciatori? Ti sfido su Guess the Player!", join: "Accetta la sfida", joinIntro: "Ti hanno invitato a un duello. Accetta per occupare il secondo posto e giocare gli stessi cinque percorsi.",
    refresh: "Aggiorna", waiting: "In attesa del tuo avversario", waitingEnd: "Hai finito! Il risultato arriva quando anche il tuo avversario completa i percorsi.",
    round: "Percorso {n} di {total}", attempts: "{n} tentativi rimasti", correct: "Indovinato!", wrong: "Risposta non corretta. Riprova.",
    ended: "Percorso concluso", answer: "Era {name}", complete: "Allenamento completato", solved: "Indovinati", spent: "Tentativi", you: "Tu",
    win: "Il duello è tuo!", loss: "Questa volta vince il tuo amico", draw: "Un pareggio perfetto", expires: "Scade il {date}",
    noEvents: "Il campo si sta preparando", noEventsDesc: "Nessun evento attivo. Nel frattempo puoi allenarti o sfidare un amico.",
    playEvent: "Gioca l’evento", eventDone: "Giornata completata", eventWait: "La prossima sfida arriva con la prossima giornata dell’evento.",
    eventEmpty: "La sfida di questa giornata non è ancora disponibile.", eventPoints: "{n} punti in palio", bonus: "+1 al primo che indovina", earned: "+{n} punti evento",
    table: "Classifica dell’evento", eventScore: "I tuoi punti nell’evento: {n}", emptyTable: "Il primo posto aspetta ancora un nome.", careerHint: "Scrivi fino a 5 squadre separate da virgole. Ne servono {n} corrette.", pairHint: "Scrivi i nomi di padre e figlio.",
    answerLabel: "La tua risposta", send: "Conferma risposta", loading: "Prepariamo il campo…", retry: "Riprova", loadError: "Non siamo riusciti ad aggiornare la partita. Riprova.",
    stale: "La partita è cambiata. Aggiorna prima di riprovare.", expired: "Questa sfida è scaduta o non è più disponibile.", full: "Questo duello ha già due giocatori.",
    empty: "Non ci sono ancora abbastanza percorsi disponibili.", invalid_answer: "Inserisci una risposta valida prima di continuare.", max_answers: "Puoi indicare al massimo cinque squadre.",
    finished: "Hai già concluso questa partita. Aggiorna per vedere il risultato.", unavailable: "Gli inviti non sono ancora disponibili.", invalid: "Questa richiesta non è valida.",
    copy: "Copia link", copied: "Link copiato", copyError: "Copia il link dal campo qui sotto.", join_required: "Apri l’invito e accetta per partecipare.",
    matched: "Squadre corrette: {n}", nextRound: "Avanti: un nuovo percorso ti aspetta.", resume: "Riprendi l’ultimo duello", progress: "{n}/{total} percorsi completati", newDuel: "Crea un altro duello", codeLabel: "Link di invito", eventEnd: "Ultima giornata: {date}", recap: "I cinque percorsi: risultati e soluzioni"
  },
  en: {
    headline: "Your next kick-off.", intro: "One daily challenge. A whole pitch to explore.",
    training: "Training", trainingTag: "At your pace", trainingDesc: "Five guesses, no pressure. Sharpen your football instincts.",
    duel: "Challenge a friend", duelTag: "Head to head", duelDesc: "The same five paths for both of you. Play whenever you like.",
    events: "Weekly events", eventsTag: "The competition", eventsDesc: "Special themes, a dedicated leaderboard and a place on the podium.",
    back: "Back to Play", start: "Start training", next: "Next path", reveal: "Reveal and finish", create: "Create a duel",
    rules: "5 paths · 3 guesses per path. Most correct answers wins; ties go to fewer guesses. A failed path counts as 3 guesses. No overall leaderboard points. Invitations last 7 days.",
    trainRules: "5 guesses per path. Reveal the answer whenever you like and move on to another player. No overall leaderboard points.",
    invite: "Invite a friend", inviteText: "Can you recognise these 5 players? Challenge me on Guess the Player!", join: "Accept challenge", joinIntro: "You have been invited to a duel. Accept to take the second spot and play the same five paths.",
    refresh: "Refresh", waiting: "Waiting for your opponent", waitingEnd: "You’re done! The result will appear once your opponent finishes too.",
    round: "Path {n} of {total}", attempts: "{n} guesses left", correct: "You got it!", wrong: "Not quite. Try again.",
    ended: "Path completed", answer: "It was {name}", complete: "Training complete", solved: "Solved", spent: "Guesses", you: "You",
    win: "The duel is yours!", loss: "Your friend wins this time", draw: "A perfect draw", expires: "Expires on {date}",
    noEvents: "Getting the pitch ready", noEventsDesc: "No events are running. Train or challenge a friend in the meantime.",
    playEvent: "Play event", eventDone: "Today’s round completed", eventWait: "The next challenge arrives on the next event day.",
    eventEmpty: "Today’s challenge is not available yet.", eventPoints: "{n} points to play for", bonus: "+1 for the first correct answer", earned: "+{n} event points",
    table: "Event leaderboard", eventScore: "Your event points: {n}", emptyTable: "First place is still waiting for a name.", careerHint: "Enter up to 5 clubs, separated by commas. You need {n} correct answers.", pairHint: "Enter the father’s and son’s names.",
    answerLabel: "Your answer", send: "Submit answer", loading: "Getting the pitch ready…", retry: "Try again", loadError: "We couldn’t update the game. Please try again.",
    stale: "The game has changed. Refresh before trying again.", expired: "This challenge has expired or is no longer available.", full: "This duel already has two players.",
    empty: "There aren’t enough paths available yet.", invalid_answer: "Enter a valid answer to continue.", max_answers: "You can enter at most five clubs.",
    finished: "You’ve already finished this game. Refresh to see the result.", unavailable: "Invitations are not available yet.", invalid: "This request is not valid.",
    copy: "Copy link", copied: "Link copied", copyError: "Copy the link from the field below.", join_required: "Open the invitation and accept to join.",
    matched: "Correct clubs: {n}", nextRound: "Next up: a new path is waiting.", resume: "Resume your last duel", progress: "{n}/{total} paths completed", newDuel: "Create another duel", codeLabel: "Invitation link", eventEnd: "Final day: {date}", recap: "The five paths: results and answers"
  },
  es: {
    headline: "Tu próximo saque inicial.", intro: "Un reto diario. Todo un campo por explorar.",
    training: "Entrenamiento", trainingTag: "A tu ritmo", trainingDesc: "Cinco intentos, sin presión. Afina tu instinto futbolístico.",
    duel: "Reta a un amigo", duelTag: "Cara a cara", duelDesc: "Las mismas cinco trayectorias para ambos. Jugad cuando queráis.",
    events: "Eventos semanales", eventsTag: "La competición", eventsDesc: "Temas especiales, clasificación propia y un lugar en el podio.",
    back: "Volver a Jugar", start: "Empezar a entrenar", next: "Siguiente trayectoria", reveal: "Revelar y terminar", create: "Crear un duelo",
    rules: "5 trayectorias · 3 intentos por trayectoria. Gana quien acierte más; en caso de empate, quien use menos intentos. Una trayectoria fallada cuenta como 3 intentos. Sin puntos para la clasificación general. Invitaciones válidas durante 7 días.",
    trainRules: "5 intentos por trayectoria. Puedes revelar la respuesta y continuar con otro jugador. Sin puntos para la clasificación general.",
    invite: "Invitar a un amigo", inviteText: "¿Reconoces a estos 5 jugadores? ¡Te reto en Guess the Player!", join: "Aceptar el reto", joinIntro: "Te han invitado a un duelo. Acepta para ocupar la segunda plaza y jugar las mismas cinco trayectorias.",
    refresh: "Actualizar", waiting: "Esperando a tu rival", waitingEnd: "¡Has terminado! El resultado aparecerá cuando tu rival complete las trayectorias.",
    round: "Trayectoria {n} de {total}", attempts: "Quedan {n} intentos", correct: "¡Acertaste!", wrong: "Respuesta incorrecta. Inténtalo de nuevo.",
    ended: "Trayectoria completada", answer: "Era {name}", complete: "Entrenamiento completado", solved: "Aciertos", spent: "Intentos", you: "Tú",
    win: "¡El duelo es tuyo!", loss: "Esta vez gana tu amigo", draw: "Un empate perfecto", expires: "Caduca el {date}",
    noEvents: "Preparando el campo", noEventsDesc: "No hay eventos activos. Mientras tanto, puedes entrenar o retar a un amigo.",
    playEvent: "Jugar el evento", eventDone: "Jornada completada", eventWait: "El próximo reto llega en la siguiente jornada del evento.",
    eventEmpty: "El reto de esta jornada aún no está disponible.", eventPoints: "{n} puntos en juego", bonus: "+1 para el primero en acertar", earned: "+{n} puntos del evento",
    table: "Clasificación del evento", eventScore: "Tus puntos en el evento: {n}", emptyTable: "El primer puesto aún espera un nombre.", careerHint: "Escribe hasta 5 equipos separados por comas. Necesitas {n} aciertos.", pairHint: "Escribe los nombres del padre y del hijo.",
    answerLabel: "Tu respuesta", send: "Confirmar respuesta", loading: "Preparando el campo…", retry: "Reintentar", loadError: "No hemos podido actualizar la partida. Inténtalo de nuevo.",
    stale: "La partida ha cambiado. Actualiza antes de volver a intentarlo.", expired: "Este reto ha caducado o ya no está disponible.", full: "Este duelo ya tiene dos jugadores.",
    empty: "Aún no hay suficientes trayectorias disponibles.", invalid_answer: "Introduce una respuesta válida para continuar.", max_answers: "Puedes indicar como máximo cinco equipos.",
    finished: "Ya has terminado esta partida. Actualiza para ver el resultado.", unavailable: "Las invitaciones aún no están disponibles.", invalid: "Esta solicitud no es válida.",
    copy: "Copiar enlace", copied: "Enlace copiado", copyError: "Copia el enlace del campo de abajo.", join_required: "Abre la invitación y acepta para participar.",
    matched: "Equipos correctos: {n}", nextRound: "Siguiente: te espera otra trayectoria.", resume: "Retomar el último duelo", progress: "{n}/{total} trayectorias completadas", newDuel: "Crear otro duelo", codeLabel: "Enlace de invitación", eventEnd: "Última jornada: {date}", recap: "Las cinco trayectorias: resultados y respuestas"
  }
};
let mode = null, data = null, busy = false, error = null, invitation = null, eventCode = null, draft = "", notice = "";
const tr = (key, args = {}) => {
  let value = (TEXT[(state.profile || {}).language] || TEXT.en)[key] || TEXT.en.loadError;
  for (const [k, v] of Object.entries(args)) value = value.replaceAll(`{${k}}`, String(v));
  return value;
};
const esc = value => PlayerClient.escapeHtml(value);
const button = (action, label, ghost = false) => `<button class="btn${ghost ? " ghost" : ""}" data-arena-action="${action}" ${busy ? "disabled" : ""}>${esc(tr(label))}</button>`;
const icon = kind => `<svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true">${{
  training: '<circle cx="16" cy="16" r="11"/><circle cx="16" cy="16" r="5"/><path d="M16 1v7m0 16v7M1 16h7m16 0h7"/>',
  duel: '<path d="m5 4 22 24m0-24L5 28M3 21l8 8m10 0 8-8M5 4l1 8m21-8-1 8"/>',
  events: '<path d="M10 4h12v9a6 6 0 0 1-12 0V4Zm0 3H4v4a6 6 0 0 0 6 6m12-10h6v4a6 6 0 0 1-6 6m-6 2v7m-7 3h14M12 26h8"/>'
}[kind]}</svg>`;

function home() {
  return `<section class="arena-home" aria-label="${esc(L.play)}"><div class="arena-heading"><span class="arena-eyebrow">GUESS THE PLAYER</span><h1>${esc(tr("headline"))}</h1><p>${esc(tr("intro"))}</p></div>
    <div class="arena-modes">${["training", "duel", "events"].map(kind => `<button class="arena-mode arena-${kind}" data-arena-open="${kind}"><span class="arena-icon">${icon(kind)}</span><span class="arena-mode-copy"><span class="arena-eyebrow">${esc(tr(kind + "Tag"))}</span><strong>${esc(tr(kind))}</strong><span>${esc(tr(kind + "Desc"))}</span></span><span class="arena-arrow" aria-hidden="true">↗</span></button>`).join("")}</div></section>`;
}
function date(value) {
  const d = new Date(value.length === 10 ? value + "T12:00:00" : value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleDateString((state.profile || {}).language || "en", {day:"numeric", month:"short"});
}
function form(hint = "") {
  return `<form id="arena-form" class="arena-form"><label for="arena-answer">${esc(tr("answerLabel"))}</label>${hint ? `<p id="arena-answer-help" class="muted">${esc(hint)}</p>` : ""}<input id="arena-answer" ${hint ? 'aria-describedby="arena-answer-help"' : ""} maxlength="220" autocomplete="off" autocorrect="off" value="${esc(draft)}" placeholder="${esc(hint ? tr("answerLabel") : L.placeholder)}" ${busy ? "disabled" : ""}><button class="btn" type="submit" ${busy ? "disabled" : ""}>${esc(tr(busy ? "loading" : "send"))}</button></form>`;
}
function feedback(f) {
  if (!f || !f.status) return "";
  return `<div class="arena-feedback ${f.status === "correct" ? "ok" : ""}" role="status"><strong>${esc(tr(f.status === "correct" ? "correct" : f.done ? "ended" : "wrong"))}</strong>
    ${f.answer ? `<p>${esc(tr("answer", {name:f.answer}))}</p>` : ""}
    ${f.points ? `<p>${esc(tr("earned", {n:f.points}))}</p>` : ""}
    ${f.matched != null ? `<p>${esc(tr("matched", {n:f.matched}))}</p>` : ""}
    ${f.comparison ? comparison(f.comparison) : ""}</div>`;
}
function sessionView(d) {
  const s = d.session;
  if (!s) return `<div class="arena-empty">${icon(mode)}<p>${esc(tr(mode === "training" ? "trainRules" : "rules"))}</p>${button(mode === "training" ? "next" : "create", mode === "training" ? "start" : "create")}</div>`;
  let html = "";
  if (mode === "duel") {
    html += `<div class="arena-versus"><div><span>${esc(tr("you"))}</span><strong>${esc(tr("progress", {n:s.round,total:s.total}))}</strong></div><span class="arena-vs" aria-hidden="true">VS</span><div><span>${esc(d.opponent ? d.opponent.name : tr("waiting"))}</span><strong>${d.opponent ? esc(tr("progress",{n:d.opponent.round,total:s.total})) : "—"}</strong></div></div>
      <div class="arena-actions">${d.invite_url && !d.opponent ? button("invite", "invite") : ""}${button("get", "refresh", true)}</div>
      ${d.invite_url && !d.opponent ? `<label class="arena-link-label" for="arena-link">${esc(tr("codeLabel"))}</label><div class="arena-link"><input id="arena-link" readonly value="${esc(d.invite_url)}">${button("copy", "copy",true)}</div>` : ""}
      <p class="muted arena-small">${esc(tr("expires",{date:date(d.expires_at)}))}</p>`;
  }
  html += feedback(d.feedback);
  if (s.finished) {
    const title = mode === "training" ? "complete" : d.complete ? d.outcome : "waitingEnd";
    html += `<div class="arena-result"><span class="arena-result-mark" aria-hidden="true">${d.outcome === "win" || mode === "training" && s.solved ? "✦" : "✓"}</span><h2>${esc(tr(title))}</h2><div class="arena-score"><div><strong>${s.solved}/${s.total}</strong><span>${esc(tr("solved"))}</span></div><div><strong>${s.spent}</strong><span>${esc(tr("spent"))}</span></div></div>
      ${d.complete ? `<p>${esc(d.opponent.name)} · ${d.opponent.solved}/${s.total} · ${d.opponent.spent} ${esc(tr("spent"))}</p>` : ""}
      ${d.recap && d.recap.length ? `<details class="arena-recap"><summary>${esc(tr("recap"))}</summary>${d.recap.map((row,i)=>`<div><strong>${i+1}. ${esc(row.answer)}</strong><p>${esc(tr("you"))}: ${row.you.solved ? "✓" : "×"} ${row.you.attempts} · ${esc(d.opponent.name)}: ${row.opponent.solved ? "✓" : "×"} ${row.opponent.attempts}</p></div>`).join("")}</details>` : ""}
      ${mode === "training" ? button("next", "next") : d.complete ? button("create", "newDuel") : ""}</div>`;
  } else {
    if (d.feedback && d.feedback.done) html += `<p role="status" class="arena-small">${esc(tr("nextRound"))}</p>`;
    html += `<div class="arena-round"><span class="arena-eyebrow">${esc(tr("round",{n:s.round+1,total:s.total}))}</span><span class="pill">${esc(s.difficulty_label)}</span></div>
      ${mode === "duel" ? `<div class="arena-rounds" aria-label="${esc(tr("progress",{n:s.round,total:s.total}))}">${Array.from({length:s.total},(_,i)=>`<span class="${i<s.round ? "done" : i===s.round ? "current" : ""}">${i<s.round ? s.history[i].solved ? "✓" : "×" : i+1}</span>`).join("")}</div>` : ""}
      <div class="arena-career">${careerPath(s.career_path)}</div><p class="arena-attempts">${esc(tr("attempts",{n:s.max_attempts-s.attempts}))}</p>${form()}
      ${mode === "training" ? `<div class="arena-actions">${button("reveal","reveal",true)}</div>` : ""}`;
  }
  return html;
}
function eventView() {
  const events = data.events || [];
  const active = events.find(e=>e.code===eventCode);
  if (!events.length) return `<div class="arena-empty">${icon("events")}<h2>${esc(tr("noEvents"))}</h2><p>${esc(tr("noEventsDesc"))}</p><button class="btn" data-arena-open="training">${esc(tr("training"))}</button></div>`;
  if (!active) return events.map(e=>`<article class="arena-event-card"><span class="arena-eyebrow">${esc(tr("eventsTag"))}</span><h2>${esc(e.name)}</h2><p>${esc(e.description)}</p><p class="muted">${esc(e.rules)}</p>${e.dates.length ? `<p class="arena-small">${esc(tr("eventEnd",{date:date(e.dates[e.dates.length-1])}))}</p>` : ""}<button class="btn" data-arena-event="${esc(e.code)}">${esc(tr(e.progress.finished ? "eventDone" : "playEvent"))}</button></article>`).join("");
  const p = active.progress;
  const hint = active.type === "career" ? tr("careerHint",{n:active.min_correct}) : active.type === "father_son" ? tr("pairHint") : "";
  const image = typeof active.image_url === "string" && /^https:\/\//i.test(active.image_url) ? `<img class="arena-event-image" src="${esc(active.image_url)}" alt="${esc(active.name)}" referrerpolicy="no-referrer">` : "";
  return `<article><span class="arena-eyebrow">${esc(tr("eventsTag"))}</span><h2 class="arena-event-title">${esc(active.name)}</h2><p class="muted">${esc(active.description)}</p><p>${esc(active.rules)}</p>
    <div class="arena-round"><span class="pill">${esc(tr("eventPoints",{n:active.points}))}</span>${active.bonus_available ? `<span class="arena-small">${esc(tr("bonus"))}</span>` : ""}</div>
    ${feedback(data.feedback)}${active.player_name ? `<h3>${esc(active.player_name)}</h3>` : ""}${careerPath(active.career_path)}${image}
    ${!active.available ? `<p>${esc(tr("eventEmpty"))}</p>` : p.finished ? `<div class="arena-result"><h3>${esc(tr(p.solved ? "correct" : "ended"))}</h3><p>${esc(tr("eventWait"))}</p></div>` : `<p class="arena-attempts">${esc(tr("attempts",{n:3-p.attempts}))}</p>${form(hint)}`}
    <div class="arena-leaderboard"><h3>${esc(tr("table"))}</h3><p class="arena-small">${esc(tr("eventScore",{n:p.points}))}</p>${active.leaderboard.length ? active.leaderboard.map((row,i)=>`<div class="row"><span class="pos">${i+1}</span><span class="name">${esc(row.name)}</span><span class="pts">${row.points}</span></div>`).join("") : `<p class="muted">${esc(tr("emptyTable"))}</p>`}</div>${button("get","refresh",true)}</article>`;
}
function view() {
  return `<section class="arena-shell" aria-busy="${busy}"><button class="arena-back" data-arena-back>← ${esc(tr("back"))}</button><header class="arena-page-head"><span class="arena-icon">${icon(mode)}</span><div><span class="arena-eyebrow">${esc(tr(mode+"Tag"))}</span><h1>${esc(tr(mode))}</h1></div></header>
    ${error ? `<div class="arena-error" role="alert"><p>${esc(tr(error))}</p>${button("get","refresh",true)}</div>` : ""}${notice ? `<p role="status">${esc(notice)}</p>` : ""}
    ${invitation ? `<div class="arena-empty"><p>${esc(tr("joinIntro"))}</p><p class="muted">${esc(tr("rules"))}</p>${button("join","join")}</div>` : !data ? error ? mode === "duel" ? button("create","create") : mode === "training" ? button("next","start") : "" : `<div class="arena-empty" role="status">${esc(tr("loading"))}</div>` : mode === "events" ? eventView() : sessionView(data)}
    </section>`;
}
async function request(action, answer) {
  if (busy) return;
  busy = true; error = null; notice = "";
  const requestedMode = mode;
  const e = mode === "events" && data && (data.events || []).find(e=>e.code===eventCode);
  const body = {mode, action, answer, code: invitation || (e ? e.code : data && data.code), day:e && e.day,
    revision: e ? e.progress.attempts : data && data.session && data.session.revision};
  render();
  try {
    const result = await api("/app/api/arena", body);
    if (mode !== requestedMode) return;
    data = result; invitation = null; draft = "";
    if (action === "guess") haptic(result.feedback && result.feedback.status === "correct" ? "success" : "error");
  } catch (err) {
    if (mode === requestedMode) error = err.detail || "loadError";
  } finally {
    busy = false; render();
    if (action === "guess" && mode === requestedMode && state.tab === "play") {
      if (data && data.feedback && data.feedback.done) window.scrollTo(0,0);
      else { const input=document.getElementById("arena-answer"); if(input) input.focus({preventScroll:true}); }
    }
  }
}
function open(kind, code) {
  if (busy) return;
  mode = kind; data = null; error = null; draft = ""; notice = ""; eventCode = null; invitation = code || null;
  state.tab = "play"; state.publicTarget = null; state.cabinetOpen = false;
  render(); window.scrollTo(0,0);
  if (!invitation) request("get");
}
function wire() {
  document.querySelectorAll("[data-arena-open]").forEach(b=>b.onclick=()=>open(b.dataset.arenaOpen));
  document.querySelectorAll("[data-arena-back]").forEach(b=>b.onclick=()=>{if(busy)return; mode=null; data=null; invitation=null; render();});
  document.querySelectorAll("[data-arena-event]").forEach(b=>b.onclick=()=>{eventCode=b.dataset.arenaEvent; draft=""; data.feedback=null; render();});
  document.querySelectorAll("[data-arena-action]").forEach(b=>b.onclick=async()=>{
    const action=b.dataset.arenaAction;
    if (action === "invite") {
      const url=`https://t.me/share/url?url=${encodeURIComponent(data.invite_url)}&text=${encodeURIComponent(tr("inviteText"))}`;
      if (tg && tg.openTelegramLink) tg.openTelegramLink(url); else window.open(url,"_blank","noopener");
    } else if (action === "copy") {
      try {await navigator.clipboard.writeText(data.invite_url); notice=tr("copied");}
      catch (_) {notice=tr("copyError");} render();
    } else await request(action);
  });
  const input=document.getElementById("arena-answer");
  if(input) input.oninput=()=>{draft=input.value;};
  const f=document.getElementById("arena-form");
  if(f) f.onsubmit=e=>{e.preventDefault(); if(draft.trim())request("guess",draft.trim());};
}
const arena = {TEXT, home, view, wire, open, get mode(){return mode;}};
if(typeof module!=="undefined" && module.exports) module.exports=arena;
else root.PlayerArena=arena;
})(typeof globalThis!=="undefined" ? globalThis : this);
