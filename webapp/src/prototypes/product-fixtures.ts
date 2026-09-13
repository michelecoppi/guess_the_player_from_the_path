/** Development-only snapshots passed to the real V2 renderers. No API writes. */
import { dailyFixture } from './daily-fixtures';
import { appearanceFixtures } from './appearance-fixtures';
import type { ArenaState } from '@/features/arena/types';
import type { TrainingState } from '@/features/training/types';
import type { ProfileState } from '@/features/profile/types';
import type { LeaderboardState } from '@/features/leaderboard/types';
import type { ArchiveState } from '@/features/archive/types';
import type { ShopState, ShopCosmeticItem } from '@/features/shop/types';
import type { ReferralState } from '@/features/referral/types';
import type { EventsState } from '@/features/events/types';

const career = dailyFixture('ready').challenge!.career_path!;
export function arenaFixture(): ArenaState {
  return { subview:'hub', status:'idle', busy:false, error:null, notice:null, confirming:null,
    activeDuelCode:null, invitationCode:null, searchQuery:'', searchResults:[], searchError:null, draftAnswer:'',
    data:{code:'review-duel', opponent:{name:'Luca',round:1,finished:false},
      session:{round:1,attempts:0,solved:1,spent:1,revision:1,finished:false,history:[],total:5,max_attempts:3,
        career_path:career.map(s=>({year:`${s.start_year}–${s.end_year}`,team:s.team,apps:s.apps ?? undefined})),difficulty_label:'Media'},
      open:[{code:'review-duel',opponent:'Luca',complete:false,round:1,total:5,expires_at:'2026-09-20T12:00:00Z'}],
      ledger:{record:{name:'Luca',won:3,lost:2,drawn:1},matches:[{code:'review-past',outcome:'win',ended_at:'2026-09-12T18:00:00Z',name:'Luca',you:{solved:4,spent:7},them:{solved:3,spent:9},rounds:[{answer:'Andrea Pirlo',you:{solved:true,attempts:1},them:{solved:true,attempts:2}}]}]}} };
}
export function trainingFixture(): TrainingState {
  return {status:'idle',busy:false,error:null,notice:null,confirming:null,draftAnswer:'',data:{session:{
    round:0,attempts:0,solved:0,spent:0,revision:1,finished:false,history:[],total:1,max_attempts:5,career_path:career,difficulty_label:'Media'}}};
}
export function profileFixture(): ProfileState {
  const trophy={code:'review-monthly',kind:'monthly',position:1,medal:'',color:'#d8ba78',label:'Agosto',detail:'Classifica mensile · 2026',year:'2026'};
  return {view:'profile',status:'ready',error:null,cabinetFilter:'all',pendingPinCodes:null,isPinning:false,pinError:null,pinSuccess:false,
    profile:{language:'it',user:{name:'Marco',points:1284,monthly_points:146,players_guessed:92,bonus_first_guessed:8,streak:12,best_streak:21,archive_solved:18,trophies:1},
      cosmetics:appearanceFixtures.identity,trophies:{pinned:[trophy],all:[trophy],max:3},distribution:[5,18,32,24,13].map((count,i)=>({attempts:i+1,count}))}};
}
export function leaderboardFixture(): LeaderboardState {
  return {status:'ready',error:null,activeTab:'global',selectedLeagueCode:null,leagues:['Amici del calcetto','Curva Nord'].map((name,i)=>({code:`DEMO${i+1}`,name,members:3,position:2,points:1284,standings:[{position:1,profile_id:i+1,name:i?'Luca':'Giulia',points:1450,me:false},{position:2,profile_id:3,name:'Marco',points:1284,me:true},{position:3,profile_id:4,name:'Andrea',points:1201,me:false}]})),publicProfile:null,
    globalLeaderboard:['Giulia','Luca','Marco','Andrea','Sara','Alessandro','Francesca','Davide'].map((name,i)=>({position:i+1,profile_id:i+1,name,points:1450-i*83,me:i===2}))};
}
export function archiveFixture(): ArchiveState {
  return {view:'calendar',status:'ready',error:null,selectedDay:null,feedback:null,draftAnswer:'',challengeFinished:false,
    calendar:Array.from({length:12},(_,i)=>({day:`2026-09-${String(i+1).padStart(2,'0')}`,label:`${i+1}/09/26`,number:235+i,difficulty:'medium',difficulty_label:'Media',status:i%3===0?'missed':'solved',attempts:i%3===0?null:2,hints:0,playable:i%3===0})),
    challenge:{day:'2026-09-01',label:'01/09/26',number:235,difficulty:'medium',difficulty_label:'Media',solved:false,attempts_used:0,attempts_left:3,max_attempts:3,career_path:career}};
}
function item(kind:ShopCosmeticItem['kind'],name:string,style:Record<string,unknown>,owned=false):ShopCosmeticItem {
  return {id:`review-${kind}`,kind,name,description:'Un dettaglio per la tua identità in campo.',price:25,full_price:25,missing:[],achievement:null,progress:0,style,grants:[],owned,equipped:false,free:false,featured:true,equippable:true,rarity:'rare',completes:[],trophy:null,welcome:false};
}
export function shopFixture(): ShopState {
  const items=[item('frame','Fascia da capitano',appearanceFixtures.identity.frame,true),item('number','Il numero dieci',{number:'10'},true),item('card','La figurina',appearanceFixtures.card.card),item('theme','Notte d’inverno',appearanceFixtures.collection.theme),item('title','Regista',{label:'Regista',color:'#d8ba78'},true),item('badge','Stella del club',{emoji:'★'}),item('squares','Tabellino',{correct:'●',wrong:'×',unused:'○'}),item('celebration','Il traguardo',{effect:'none'})];
  return {view:'catalog',status:'ready',kindFilter:'all',priceFilter:'all',hideOwned:false,preview:null,buying:false,deliveryStatus:'idle',buyingItemId:null,equippingItemId:null,lookMutation:null,historyStatus:'ready',
    history:{purchases:[{name:'Fascia da capitano',day:'10/09/2026',stars:25,refunded:false,charge_id:'review-example'}],support_url:''},
    catalogue:{sections:items.map(i=>({kind:i.kind as 'frame',items:[i]})),bundles:[],showcase:{week:'2026-W37',items:items.slice(0,3)},equipped:{},owned:items.filter(i=>i.owned).map(i=>i.id),looks:[{name:'La domenica',equipped:{}}]}};
}
export function referralFixture(): ReferralState {
  return {status:'ready',loadingMore:false,refreshing:false,selectedRewardTarget:null,equippingItemId:null,toast:null,errorNotice:null,
    data:{qualified:3,required_days:5,link:'https://example.invalid/invito-demo',next_cursor:null,friends:[{name:'Giulia',days:5,status:'qualified'},{name:'Luca',days:5,status:'qualified'},{name:'Sara',days:5,status:'qualified'},{name:'Andrea',days:3,status:'pending'}],rewards:[3,5,10].map(target=>({target,items:[item('card',target===3?"L’intesa":target===5?'La lavagna':'Il tuo undici',{finish:'tactics'},target===3)]}))}};
}
export function eventsFixture(): EventsState {
  return {status:'ready',selectedCode:null,feedback:null,draftAnswer:'',error:null,events:['path','career','father_son','transfer_guess'].map((type,i)=>({
    code:`review-event-${i}`,day:'2026-09-13',type,name:['Il regista','Una carriera, tanti club','Di padre in figlio','L’ultimo trasferimento'][i]!,description:'Una nuova sfida nella storia del calcio.',dates:['2026-09-13','2026-09-20'],available:true,rules:'Tre tentativi. Un punto bonus alla prima risposta corretta.',player_name:type==='career'?'Andrea Pirlo':'',min_correct:3,career_path:type==='path'?career:[],image_url:null,points:5,bonus_available:true,progress:{attempts:0,finished:false,solved:false,points:0},leaderboard:[{name:'Giulia',points:16},{name:'Luca',points:12}] }))};
}
