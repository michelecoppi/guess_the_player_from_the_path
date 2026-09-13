/** DEV-only review: real renderers, sample states, no API writes. */
import { appearanceFixtures, type AppearanceFixtureName } from './appearance-fixtures';
import { applyResolvedAppearance, appearanceSquares, type ResolvedAppearance } from '@/appearance';
import { renderHeader } from '@/components/Header';
import { renderNavBar, type NavTabId } from '@/components/NavBar';
import { renderDailyPage } from '@/pages/DailyPage';
import { renderArenaPage } from '@/pages/ArenaPage';
import { renderProfilePage } from '@/pages/ProfilePage';
import { renderLeaderboardPage } from '@/pages/LeaderboardPage';
import { renderArchivePage } from '@/pages/ArchivePage';
import { renderShopPage } from '@/pages/ShopPage';
import { renderReferralPage } from '@/pages/ReferralPage';
import { renderEventsPage } from '@/pages/EventsPage';
import { EventsController } from '@/features/events/controller';
import { dailyFixture, REVIEW_STATES, type ReviewState } from './daily-fixtures';
import * as fixtures from './product-fixtures';
import { createPreviewAppearance } from '@/features/shop/preview';
import { watchReferralMotion, disconnectReferralMotion } from '@/features/referral/views';
import type { PublicProfileState } from '@/features/leaderboard/types';
import { setLanguage } from '@/i18n';
import { renderPrototype, type PrototypeId } from './screens';

export const REVIEW_PAGES=['Daily','Arena','Duelli','Cerca utenti','Duello','Allenamento','Profilo','Trofei','Classifica','Archivio','Sfida archivio','Shop','Guardaroba','Traguardi','Acquisti','Referral','Eventi','Dettaglio evento'] as const;
export function startReview(root:HTMLElement):void {
  let page:string='Daily', state:ReviewState='ready', outfit:AppearanceFixtureName='default', language:'it'|'en'|'es'='it', eventIndex=0;
  const eventController=new EventsController();
  const shop=fixtures.shopFixture();
  let worn:ResolvedAppearance=appearanceFixtures.default;
  let publicProfile:PublicProfileState|null=null;
  let leaderboardTab:'global'|'leagues'='global';
  let leagueCode:string|null=null;
  let searchQuery='';
  let opponentName='Luca';
  let rewardTarget:number|null=null;
  let referralNotice:string|null=null;
  const items=shop.catalogue!.sections.flatMap(section=>section.items);
  const equip=(id:string)=>{
    const item=items.find(item=>item.id===id);
    if(!item?.owned)return;
    worn=createPreviewAppearance(worn,item,language);
    items.filter(other=>other.kind===item.kind).forEach(other=>other.equipped=other.id===id);
    if(item.kind!=='bundle')shop.catalogue!.equipped[item.kind]=id;
    shop.preview=null;
    shop.toast='Indossato nella demo. Apri Profilo per vedere il risultato.';
  };
  function render() {
    const controlsOpen=root.querySelector<HTMLDetailsElement>('.product-review')?.open ?? false;
    setLanguage(language);document.documentElement.lang=language;document.documentElement.dataset.theme='dark';
    disconnectReferralMotion();
    const appearance=applyResolvedAppearance(shop.preview?.appearance ?? worn);
    const daily=dailyFixture(state);daily.squaresSymbols=appearanceSquares(appearance);
    const arena=fixtures.arenaFixture(),training=fixtures.trainingFixture(),profile=fixtures.profileFixture(),leaderboard=fixtures.leaderboardFixture(),archive=fixtures.archiveFixture(),referral=fixtures.referralFixture();
    let active:NavTabId='play',html='';
    if(['reports','refunds','privacy'].includes(page))html=renderPrototype(page as PrototypeId);
    else if(page==='Daily')html=renderDailyPage(daily);
    else if(['Arena','Duelli','Cerca utenti','Duello','Allenamento'].includes(page)) {
      active='arena';arena.subview=page==='Duelli'?'duels':page==='Cerca utenti'?'challenge':page==='Duello'?'duel':page==='Allenamento'?'training':'hub';
      arena.searchQuery=searchQuery;
      arena.searchResults=searchQuery.trim().length<2?[]:fixtures.leaderboardFixture().globalLeaderboard
        .filter(user=>!user.me && user.name.toLowerCase().includes(searchQuery.trim().toLowerCase()))
        .map(user=>({profile_id:user.profile_id!,name:user.name,points:user.points,badge:'',trophies:1}));
      arena.data!.opponent!.name=opponentName;
      if(state==='loading'){arena.status='loading';training.status='loading';arena.data=null;training.data=null;}
      if(state==='completed'){arena.data!.session!.finished=true;training.data!.session!.finished=true;}
      html=renderArenaPage(arena,training);
    } else if(['Profilo','Trofei'].includes(page)) {
      active='profile';profile.view=page==='Trofei'?'cabinet':'profile';profile.profile!.cosmetics=appearance;
      if(state==='loading'||state==='error'){profile.status=state;profile.profile=null;}
      html=renderProfilePage(profile);
    } else if(page==='Classifica') {
      active='leaderboard';leaderboard.activeTab=leaderboardTab;leaderboard.selectedLeagueCode=leagueCode;leaderboard.publicProfile=publicProfile;if(state==='unavailable')leaderboard.globalLeaderboard=[];
      if(state==='loading'||state==='error')leaderboard.status=state;
      html=renderLeaderboardPage(leaderboard);
    } else if(page.includes('archivio')||page==='Archivio') {
      active='arena';if(page==='Sfida archivio'){archive.view='challenge';archive.status='challenge_ready';archive.selectedDay=archive.challenge!.day;}
      if(state==='loading')archive.status='loading';html=renderArchivePage(archive);
    } else if(['Shop','Guardaroba','Traguardi','Acquisti'].includes(page)) {
      active='shop';shop.view=page==='Guardaroba'?'wardrobe':page==='Traguardi'?'achievements':page==='Acquisti'?'history':'catalog';
      if(state==='loading'||state==='error'){html=renderShopPage({...shop,status:state,catalogue:null});}else html=renderShopPage(shop);
    } else if(page==='Referral') {
      active='profile';if(state==='loading'||state==='error'){referral.status=state;referral.data=null;}referral.selectedRewardTarget=rewardTarget;referral.toast=referralNotice;html=renderReferralPage(referral);
    } else {
      active='arena';const events=fixtures.eventsFixture();if(page==='Dettaglio evento')events.selectedCode=events.events[eventIndex]!.code;
      if(state==='loading'||state==='error'){events.status=state;events.events=[];}
      if(state==='unavailable')events.events=[];
      if(state==='completed')events.events[eventIndex]!.progress={attempts:1,finished:true,solved:true,points:5};
      Object.assign(eventController.getState(),events);html=renderEventsPage(eventController);
    }
    root.innerHTML=`${renderHeader({user:{id:1,first_name:'Marco'},activeTab:active})}<p class="product-review-notice">Demo interattiva · nessuna spesa o invio reale</p><main id="app-content">${html}</main>${renderNavBar({activeTab:active})}
      <details class="product-review" ${controlsOpen?'open':''}><summary>Revisione grafica · dati di esempio</summary><div class="product-review-fields">
      <label>Schermata<select id="review-page">${REVIEW_PAGES.map(p=>`<option ${p===page?'selected':''}>${p}</option>`).join('')}</select></label>
      <label>Stato<select id="review-state">${REVIEW_STATES.map(s=>`<option ${s===state?'selected':''}>${s}</option>`).join('')}</select></label>
      <label>Cosmetici<select id="review-appearance">${Object.keys(appearanceFixtures).map(s=>`<option ${s===outfit?'selected':''}>${s}</option>`).join('')}</select></label>
      <label>Lingua<select id="review-language">${['it','en','es'].map(s=>`<option ${s===language?'selected':''}>${s}</option>`).join('')}</select></label>
      </div><p>Demo interattiva con dati locali: acquisti e inviti simulati, nessuna spesa o invio reale. Gli oggetti indossati restano fino al ricaricamento. Gli stati si applicano alle schermate che li supportano.</p></details>`;
    const change=(id:string,fn:(value:string)=>void)=>{root.querySelector<HTMLSelectElement>(id)!.onchange=e=>{fn((e.target as HTMLSelectElement).value);render();};};
    change('#review-page',v=>{page=v;state='ready';publicProfile=null;shop.preview=null;});change('#review-state',v=>state=v as ReviewState);change('#review-appearance',v=>{outfit=v as AppearanceFixtureName;worn=appearanceFixtures[outfit];shop.preview=null;items.forEach(item=>item.equipped=false);});change('#review-language',v=>language=v as typeof language);
    root.querySelectorAll<HTMLButtonElement>('[data-tab]').forEach(b=>b.onclick=()=>{page=({play:'Daily',arena:'Arena',profile:'Profilo',leaderboard:'Classifica',shop:'Shop',archive:'Archivio',events:'Eventi',referral:'Referral',duels:'Duello',challenge:'Cerca utenti'} as Record<string,string>)[b.dataset.tab!]||b.dataset.tab!;state='ready';publicProfile=null;shop.preview=null;render();window.scrollTo(0,0);});
    const bind=(selector:string,fn:()=>void)=>root.querySelectorAll<HTMLElement>(selector).forEach(el=>el.onclick=e=>{e.preventDefault();fn();render();});
    bind('#submit',()=>state=root.querySelector<HTMLInputElement>('#answer')?.value.toLowerCase().includes('pirlo')?'correct':'wrong');bind('#hint',()=>state='hint');bind('#daily-retry',()=>state='ready');bind('#open-cabinet',()=>page='Trofei');
    bind('[data-arena-nav="challenge"]',()=>page='Cerca utenti');
    const search=root.querySelector<HTMLInputElement>('#opponent-search');
    if(search)search.oninput=()=>{
      searchQuery=search.value;const cursor=search.selectionStart;render();
      const next=root.querySelector<HTMLInputElement>('#opponent-search');next?.focus({preventScroll:true});
      if(cursor!==null)next?.setSelectionRange(cursor,cursor);
    };
    root.querySelectorAll<HTMLElement>('[data-arena-challenge-user]').forEach(button=>button.onclick=()=>{
      opponentName=arena.searchResults.find(user=>user.profile_id===Number(button.dataset.arenaChallengeUser))!.name;
      page='Duello';render();
    });
    root.querySelectorAll<HTMLElement>('[data-profile-id]').forEach(button=>button.onclick=()=>{
      const user=leaderboard.globalLeaderboard.find(user=>user.profile_id===Number(button.dataset.profileId));
      if(!user)return;
      const sample=fixtures.profileFixture().profile!;
      publicProfile={profileId:user.profile_id!,status:'ready',data:{user:{...sample.user,name:user.name,points:user.points},cosmetics:user.me?worn:appearanceFixtures.identity,trophies:sample.trophies.all,wearing:[]}};
      render();root.querySelector<HTMLElement>('#public-profile-heading')?.focus();
    });
    root.querySelectorAll<HTMLElement>('[data-leaderboard-tab]').forEach(button=>button.onclick=()=>{leaderboardTab=button.dataset.leaderboardTab as typeof leaderboardTab;publicProfile=null;render();});
    root.querySelectorAll<HTMLElement>('[data-select-league]').forEach(button=>button.onclick=()=>{leagueCode=button.dataset.selectLeague!;render();});
    bind('[data-arena-nav="duels"]',()=>page='Duelli');
    bind('[data-action="close-profile"]',()=>publicProfile=null);
    root.querySelectorAll<HTMLElement>('[data-try]').forEach(button=>button.onclick=()=>{
      const item=items.find(item=>item.id===button.dataset.try);if(!item)return;
      shop.preview={item,appearance:createPreviewAppearance(worn,item,language)};render();root.querySelector('.preview-bar')?.scrollIntoView?.({block:'nearest'});
    });
    root.querySelectorAll<HTMLElement>('[data-equip]').forEach(button=>button.onclick=()=>{equip(button.dataset.equip!);render();});
    root.querySelectorAll<HTMLElement>('[data-buy]').forEach(button=>button.onclick=()=>{
      const item=items.find(item=>item.id===button.dataset.buy);if(!item)return;
      item.owned=true;if(!shop.catalogue!.owned.includes(item.id))shop.catalogue!.owned.push(item.id);
      shop.toast='Oggetto aggiunto alla demo, senza spendere Stars. Ora puoi indossarlo.';render();
      root.querySelector('.toast')?.scrollIntoView?.({block:'nearest'});
    });
    const kind=root.querySelector<HTMLSelectElement>('#shop-kind');if(kind)kind.onchange=()=>{shop.kindFilter=kind.value as typeof shop.kindFilter;render();};
    const price=root.querySelector<HTMLSelectElement>('#shop-price');if(price)price.onchange=()=>{shop.priceFilter=price.value as typeof shop.priceFilter;render();};
    const hideOwned=root.querySelector<HTMLInputElement>('#shop-hide-owned');if(hideOwned)hideOwned.onchange=()=>{shop.hideOwned=hideOwned.checked;render();};
    bind('#shop-stop-preview',()=>shop.preview=null);
    root.querySelectorAll<HTMLElement>('[data-rf-preview]').forEach(button=>button.onclick=()=>{rewardTarget=Number(button.dataset.rfPreview);render();});
    bind('#rf-close-preview',()=>rewardTarget=null);
    bind('#rf-invite, #rf-copy',()=>referralNotice='Invito dimostrativo: nessun messaggio inviato e nessun link reale copiato.');
    bind('#rf-refresh',()=>referralNotice='Progressi di esempio aggiornati.');
    if(page==='Referral')watchReferralMotion(root);
    bind('[data-arena-duel]',()=>page='Duello');bind('[data-arena-nav="training"]',()=>page='Allenamento');bind('[data-arena-nav="hub"]',()=>page='Arena');
    root.querySelectorAll<HTMLElement>('[data-shop-view]').forEach(b=>b.onclick=()=>{page=({catalog:'Shop',wardrobe:'Guardaroba',achievements:'Traguardi',history:'Acquisti'} as Record<string,string>)[b.dataset.shopView!]!;render();});
    root.querySelectorAll<HTMLElement>('[data-event-open]').forEach((b,i)=>b.onclick=()=>{eventIndex=i;page='Dettaglio evento';render();});bind('#events-back',()=>page='Eventi');bind('#events-open-training',()=>page='Allenamento');
  }
  render();
}
