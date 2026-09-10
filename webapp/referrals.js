/* Private referral progress and the exclusive tactics cosmetics. */
const PlayerReferrals = (() => {
  const COPY = {
    it: {title:"La tua formazione",eyebrow:"IL GIOCO È PIÙ BELLO INSIEME",intro:"Porta gli amici in campo. Costruisci qualcosa di tuo.",exclusive:"SOLO CON GLI INVITI",rules:"Un amico conta dopo 5 daily completate in 5 giorni diversi, anche non consecutivi. Valgono vittorie e tentativi esauriti; archivio, allenamento e duelli sono esclusi. L’invito vale solo per nuovi giocatori registrati dal tuo link.",invite:"Invita un amico",copy:"Copia link",copied:"Link copiato",share:"Entra nella mia formazione! Gioca 5 sfide daily: mi aiuterai a sbloccare una collezione esclusiva.",qualified:"amici qualificati",next:"amici qualificati al prossimo premio",done:"Formazione completa. Tutti i premi sono tuoi.",friends:"Chi sta entrando in campo",empty:"Il primo posto è per un tuo amico. Mandagli il link e inizia la formazione.",complete:"Invito completato",daily:"daily completate",refresh:"Aggiorna progressi",more:"Altri amici",back:"Torna al profilo",retry:"Riprova",unavailable:"Non riesco a caricare i progressi. Riprova tra poco.",noLink:"Gli inviti non sono ancora disponibili.",preview:"Guarda il premio",close:"Chiudi anteprima",wear:"Equipaggia",worn:"Equipaggiato",unlock:"Premio sbloccato",locked:"Si sblocca con",people:"amici qualificati",you:"TU",numbers:"punti",best:"serie migliore",names:["L’intesa","La squadra","Il tuo undici"],descs:["Tre nodi, un pallone. La tua prima connessione.","La lavagna del mister diventa la tua card personale.","Tu e dieci amici. Una formazione, un’identità completa."],manual:"Il tuo link personale",progress:"Progressi degli inviti",view:"Scopri i premi esclusivi →"},
    en: {title:"Your starting eleven",eyebrow:"BETTER TOGETHER",intro:"Bring your friends onto the pitch. Build something of your own.",exclusive:"REFERRAL EXCLUSIVE",rules:"A friend qualifies after completing 5 daily challenges on 5 different days, not necessarily consecutive. Wins and exhausted attempts count; archive, training and duels do not. Only new players registering through your link qualify.",invite:"Invite a friend",copy:"Copy link",copied:"Link copied",share:"Join my team! Complete 5 daily challenges and help me unlock an exclusive collection.",qualified:"qualified friends",next:"qualified friends to the next reward",done:"Team complete. All rewards are yours.",friends:"Who's joining the team",empty:"The first spot is for a friend. Send your link to start building your team.",complete:"Referral complete",daily:"daily challenges completed",refresh:"Refresh progress",more:"More friends",back:"Back to profile",retry:"Retry",unavailable:"Progress could not be loaded. Please try again.",noLink:"Invites are not available yet.",preview:"Preview reward",close:"Close preview",wear:"Equip",worn:"Equipped",unlock:"Reward unlocked",locked:"Unlocks with",people:"qualified friends",you:"YOU",numbers:"points",best:"best streak",names:["The connection","The team","Your starting eleven"],descs:["Three nodes, one ball. Your first connection.","The tactics board becomes your personal card.","You and ten friends. One team, a complete identity."],manual:"Your personal link",progress:"Referral progress",view:"Discover exclusive rewards →"},
    es: {title:"Tu once inicial",eyebrow:"MEJOR JUNTOS",intro:"Trae a tus amigos al campo. Construye algo tuyo.",exclusive:"SOLO CON INVITACIONES",rules:"Un amigo cuenta tras completar 5 retos diarios en 5 días distintos, no necesariamente consecutivos. Cuentan victorias e intentos agotados; no archivo, entrenamiento ni duelos. Solo cuentan nuevos jugadores registrados desde tu enlace.",invite:"Invita a un amigo",copy:"Copiar enlace",copied:"Enlace copiado",share:"¡Únete a mi equipo! Completa 5 retos diarios y ayúdame a desbloquear una colección exclusiva.",qualified:"amigos clasificados",next:"amigos clasificados para el próximo premio",done:"Equipo completo. Todos los premios son tuyos.",friends:"Quién está entrando al campo",empty:"El primer puesto es para un amigo. Envía tu enlace para formar el equipo.",complete:"Invitación completada",daily:"retos diarios completados",refresh:"Actualizar progreso",more:"Más amigos",back:"Volver al perfil",retry:"Reintentar",unavailable:"No se pudo cargar el progreso. Inténtalo de nuevo.",noLink:"Las invitaciones aún no están disponibles.",preview:"Ver recompensa",close:"Cerrar vista previa",wear:"Equipar",worn:"Equipado",unlock:"Recompensa desbloqueada",locked:"Se desbloquea con",people:"amigos clasificados",you:"TÚ",numbers:"puntos",best:"mejor racha",names:["La conexión","El equipo","Tu once inicial"],descs:["Tres nodos, un balón. Tu primera conexión.","La pizarra del míster se convierte en tu tarjeta personal.","Tú y diez amigos. Un equipo, una identidad completa."],manual:"Tu enlace personal",progress:"Progreso de invitaciones",view:"Descubre las recompensas exclusivas →"}
  };
  // Senza offset-path (iOS < 16) la pallina resterebbe a 0 0: un puntino bianco nell'angolo
  // del campo. cx/cy la parcheggiano sulla partenza del tracciato, ma vanno emessi *solo*
  // li': misurato, insieme a offset-path non fanno da riserva, si sommano e la portano fuori.
  const MOTION = typeof CSS !== "undefined" && !!CSS.supports && CSS.supports("offset-path", "path('M0 0')");
  const ball = (radius, d, [x, y]) =>
    `<circle class="rf-ball" r="${radius}"${MOTION ? "" : ` cx="${x}" cy="${y}"`} style="offset-path:path('${d}')"/>`;
  let data = null, error = false, busy = false, selected = null, watcher = null;
  const text = () => COPY[state.profile?.language] || COPY.en;
  const esc = value => escapeHtml(String(value ?? ""));
  const POS = [[50,86],[18,66],[39,68],[61,68],[82,66],[25,45],[50,49],[75,45],[22,23],[50,17],[78,23]];

  function pitch(count=11, labels=[], active=count) {
    const points = count === 3 ? [[50,20],[22,74],[78,74]] : count === 5 ? [[50,78],[20,53],[80,53],[30,23],[70,23]] : POS;
    const d = `${points.map(([x,y],i) => `${i?'L':'M'}${x} ${y}`).join(' ')} Z`;
    return `<svg class="rf-pitch" viewBox="0 0 100 100" aria-hidden="true"><rect class="rf-field" x="6" y="6" width="88" height="88" rx="2"/><path class="rf-lines" d="M6 50H94 M30 6V21H70V6 M30 94V79H70V94"/><circle class="rf-lines" cx="50" cy="50" r="13"/><path class="rf-pass" d="${d}"/>${points.map(([x,y],i)=>`<g class="rf-player ${i>=active?'rf-vacant':''}" style="--i:${i}" transform="translate(${x} ${y})"><circle r="4.2"/><text y="1.35">${esc(labels[i] || (i===0 ? '★' : String(i)))}</text></g>`).join('')}${ball(1.5, d, points[0])}</svg>`;
  }

  function frame(style) {
    if (!style?.tactics) return "";
    const count=style.tactics===3?3:11;
    const points=Array.from({length:count},(_,i)=>{const a=-Math.PI/2+i*2*Math.PI/count;return [50+43*Math.cos(a),50+43*Math.sin(a)];});
    return `<span class="rf-avatar-frame rf-frame-${count}"><svg class="rf-pitch" viewBox="0 0 100 100" aria-hidden="true"><circle class="rf-pass" cx="50" cy="50" r="43"/>${points.map(([x,y])=>`<circle cx="${x}" cy="${y}" r="${count===3?4:2.5}" fill="#102925" stroke="#c8f48b" stroke-width="1.2"/>`).join('')}${ball(2.2, "M50 7 A43 43 0 1 1 50 93 A43 43 0 1 1 50 7", [50, 7])}</svg></span>`;
  }

  function identity(user, worn) {
    const finish = worn?.card?.finish;
    const eleven = worn?.theme?.formation || finish === "eleven";
    if (!eleven && finish !== "tactics") return "";
    const t=text();
    return `<section class="rf-identity ${eleven?'rf-eleven':''}" aria-label="${esc(t.title)}"><div class="rf-identity-top"><span>${esc(t.exclusive)}</span><b>${eleven?'XI':'V'}</b></div>${pitch(eleven?11:5)}<div class="rf-identity-info"><h2>${esc(user.name)}</h2><span>${esc(user.points)} ${esc(t.numbers)} · ${esc(user.best_streak)} ${esc(t.best)}</span></div></section>`;
  }

  function entry() {
    const t=text();
    return `<button class="rf-entry" id="open-referrals"><span class="rf-entry-icon" aria-hidden="true">↗</span><span><strong>${esc(t.title)}</strong><small>${esc(t.view)}</small></span><b aria-hidden="true">XI</b></button>`;
  }

  async function load(more=false) {
    if (busy) return;
    busy=true; error=false; render();
    try {
      const result=await api('/app/api/referrals', more ? {cursor:data?.next_cursor} : {});
      data = more && data ? {...result,friends:[...data.friends,...result.friends]} : result;
    } catch { error=true; }
    finally { busy=false; render(); }
  }

  function rewardArt(target) {
    if (target===3) return `<div class="rf-frame-art">${avatar(state.profile.user.name,{tactics:3})}</div>`;
    return identity(state.profile.user, {card:{finish:target===5?'tactics':'eleven'}});
  }

  function view() {
    const t=text(), count=data?.qualified || 0, next=[3,5,10].find(n=>n>count);
    const back=`<button class="btn ghost small" id="close-referrals">← ${esc(t.back)}</button>`;
    if (!data) return back+`<div class="card" role="status"><p>${esc(error?t.unavailable:L.loading)}</p>${!busy?`<button class="btn" id="rf-refresh">${esc(t.retry)}</button>`:''}</div>`;
    const reward=(data.rewards || []).find(r=>r.target===selected);
    if (reward) return back+`<section class="rf-reveal"><button class="btn ghost small" id="rf-close-preview">← ${esc(t.close)}</button><p class="rf-kicker">${esc(count>=selected?t.unlock:t.exclusive)}</p><h1>${esc(t.names[[3,5,10].indexOf(selected)])}</h1>${rewardArt(selected)}<p>${esc(t.descs[[3,5,10].indexOf(selected)])}</p>${reward.items.map(item=>`<div class="rf-prize-piece"><div><strong>${esc(item.name)}</strong><small>${esc(item.description)}</small></div>${item.owned?`<button class="btn small" data-rf-equip="${esc(item.id)}" ${item.equipped?'disabled':''}>${esc(item.equipped?t.worn:t.wear)}</button>`:`<span class="rf-exclusive">${selected} ${esc(t.people)}</span>`}</div>`).join('')}</section>`;
    return back+`<section class="rf-hero"><p class="rf-kicker">${esc(t.eyebrow)}</p><h1>${esc(t.title)}</h1><p class="rf-intro">${esc(t.intro)}</p><div class="rf-hero-field">${pitch(11,[],Math.min(count+1,11))}<span class="rf-field-caption">${esc(t.you)} + 10</span></div><div class="rf-score"><strong>${count}<span>/10</span></strong><div>${esc(t.qualified)}<small>${esc(next?`${next-count} ${t.next}`:t.done)}</small></div></div><div class="rf-milestones">${[3,5,10].map(n=>`<span class="${count>=n?'is-done':''}">${count>=n?'✓':n}</span>`).join('')}</div>${data.link?`<button class="btn" id="rf-invite">${esc(t.invite)} ↗</button><button class="btn ghost small" id="rf-copy">${esc(t.copy)}</button><details class="rf-link"><summary>${esc(t.manual)}</summary><input readonly value="${esc(data.link)}" aria-label="${esc(t.manual)}"></details>`:`<p>${esc(t.noLink)}</p>`}</section>
      <div class="rf-rewards">${[3,5,10].map((n,i)=>`<button class="rf-reward ${count>=n?'is-unlocked':''}" data-rf-preview="${n}" aria-label="${esc(t.preview+' · '+t.names[i])}"><span class="rf-reward-top"><span>${esc(t.exclusive)}</span><b>${count>=n?'✓':n}</b></span><div class="rf-reward-art">${n===3?rewardArt(3):pitch(n===5?5:11)}</div><strong>${esc(t.names[i])}</strong><small>${esc(t.descs[i])}</small><span class="rf-reward-status">${esc(count>=n?t.unlock:`${Math.min(count,n)} / ${n} · ${t.people}`)} →</span></button>`).join('')}</div>
      <section class="card rf-friends"><div class="rf-friends-heading"><h2>${esc(t.friends)}</h2><button class="btn ghost small" id="rf-refresh" ${busy?'disabled':''}>${esc(busy?L.loading:t.refresh)}</button></div>${error?`<p role="alert">${esc(t.unavailable)}</p>`:''}${data.friends.length?data.friends.map(friend=>`<div class="rf-friend"><span class="rf-friend-avatar">${esc(initials(friend.name))}</span><div><strong>${esc(friend.name)}</strong><small>${friend.status==='qualified'?'✓ '+esc(t.complete):`${friend.days}/5 · ${esc(t.daily)}`}</small><progress value="${friend.days}" max="5" aria-label="${esc(friend.name+' · '+t.progress)}"></progress></div></div>`).join(''):`<p class="muted">${esc(t.empty)}</p>`}${data.next_cursor?`<button class="btn ghost" id="rf-more" ${busy?'disabled':''}>${esc(t.more)}</button>`:''}</section><p class="rf-rules">${esc(t.rules)}</p>`;
  }

  function watchMotion() {
    // Un campo fuori dallo schermo continuerebbe a ridipingersi sotto al pollice: la card
    // indossata sta nel profilo, non solo qui, e l'utente scorre via ma l'animazione resta.
    if (!window.IntersectionObserver) return;
    watcher = watcher || new IntersectionObserver(
      seen => seen.forEach(entry => entry.target.classList.toggle("rf-paused", !entry.isIntersecting)),
      {rootMargin: "60px"});
    watcher.disconnect();
    document.querySelectorAll(".rf-pitch").forEach(pitch => watcher.observe(pitch));
  }

  function wire() {
    watchMotion();
    const bind=(id,fn)=>{const el=document.getElementById(id); if(el)el.onclick=fn;};
    bind('open-referrals',()=>{state.referralsOpen=true;selected=null;load();window.scrollTo(0,0);});
    bind('close-referrals',()=>{state.referralsOpen=false;selected=null;render();});
    bind('rf-refresh',()=>load()); bind('rf-more',()=>load(true));
    bind('rf-close-preview',()=>{selected=null;render();});
    bind('rf-invite',()=>{if(!data?.link)return; const url='https://t.me/share/url?url='+encodeURIComponent(data.link)+'&text='+encodeURIComponent(text().share); if(tg?.openTelegramLink)tg.openTelegramLink(url);else window.open(url,'_blank','noopener');});
    bind('rf-copy',async()=>{try{await navigator.clipboard.writeText(data.link);toast(text().copied);}catch{document.querySelector('.rf-link').open=true;document.querySelector('.rf-link input').select();}});
    document.querySelectorAll('[data-rf-preview]').forEach(el=>el.onclick=()=>{selected=Number(el.dataset.rfPreview);render();window.scrollTo(0,0);});
    document.querySelectorAll('[data-rf-equip]').forEach(el=>el.onclick=async()=>{el.disabled=true;await wear(el.dataset.rfEquip);await load();});
  }
  return {view,wire,entry,frame,identity,pitch,COPY};
})();
