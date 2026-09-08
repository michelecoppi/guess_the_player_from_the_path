# Guess the Player from the Path

Bot Telegram che ogni giorno propone il percorso professionale (misterioso) di un calciatore
da indovinare, con classifiche, statistiche personali, eventi tematici a tempo e trofei.

## Come si gioca

Ogni giorno il bot pubblica il percorso di carriera di un calciatore, senza il nome. In chat
privata **basta scrivere il nome**: non serve nessun comando (`/guess <nome>` continua a
funzionare). Tre tentativi al giorno, i punti dipendono dalla difficolta', chi indovina per
primo prende un punto in piu'.

| Comando | Cosa fa |
|---|---|
| `/start` | registrazione e menu; apre anche i link d'invito alle leghe |
| `/menu` | la tastiera con tutto quello che si puo' fare |
| `/show` | la sfida di oggi |
| `/guess <risposta>` | il modo classico di rispondere |
| `/stats` | punti, striscia, trofei |
| `/top` | classifica generale e mensile |
| `/events` | centro eventi |
| `/archive` (`/archivio`) | rigioca le sfide dei giorni scorsi |
| `/training` (`/allenamento`) | sfide a raffica, senza punti |
| `/round` (`/sfida`) | **in un gruppo**: apre un round per tutti |
| `/standings` (`/classifica`) | **in un gruppo**: la classifica di quel gruppo |
| `/today` (`/oggi`) | esci dall'archivio o dall'allenamento |
| `/league` (`/lega`) | le tue leghe private |
| `/league_create <nome>`, `/league_join <codice>`, `/league_leave <codice>` | crea, entra, esci |
| `/legend` (`/legenda`) | come si legge l'immagine del percorso |
| `/notify`, `/language` | notifiche e lingua |

Il menu "/" di Telegram (`set_my_commands`) viene impostato all'avvio nelle tre lingue: le
**descrizioni** sono tradotte, i **nomi dei comandi** no — sono in inglese per tutti. Un bot
trilingue con tre serie di comandi diversi obbligherebbe a scrivere ogni messaggio in tre
versioni ("torna a oggi con /oggi" per un italiano, "con /today" per un inglese), e chi cambia
lingua si ritroverebbe i comandi che ha imparato a non funzionare più. Gli alias italiani della
prima versione (`/archivio`, `/oggi`, `/lega`, `/lega_crea`, `/allenamento`, `/sfida`,
`/classifica`, `/legenda`) restano registrati e funzionanti: semplicemente non sono più quelli
che il bot suggerisce.

### Risposte tollerate, ma non regalate

Il confronto passa da `services/matching.py`: accenti, maiuscole, punteggiatura e apostrofi
non contano ("Mbappe" = "Mbappé", "N'Golo" = "Ngolo"), e un refuso vicino alla risposta viene
accettato invece di bruciare un tentativo. La soglia e' alta e c'e' un limite sulla differenza
di lunghezza, perche' il caso da non sbagliare mai e' accettare *ronaldinho* per *ronaldo*:
i test lo verificano su una lista di coppie insidiose. Non viene mai suggerito il nome giusto
("intendevi X?"): sarebbe rivelare la soluzione.

Un messaggio che non ha la forma di un nome (un link, una frase lunga) non consuma tentativi:
il bot risponde con una riga di spiegazione.

### Cosa lascia un tentativo sbagliato

Prima non lasciava niente ("sbagliato, te ne restano due"): su una giornata difficile
l'unica strategia possibile era sparare nomi. Adesso, se il calciatore scritto e' nel
dataset, `services/guess_feedback.py` lo confronta con la soluzione e risponde come Wordle:

```
❌ Risposta sbagliata, riprova! Hai 2 tentativi rimasti.

🔎 Rispetto a Alessandro Del Piero:
🌍 Nazionalità: diversa
🎽 Ruolo: stesso
⬇️ Più giovane: nato dopo il 1974
```

Il confronto e' **relativo al nome scritto dall'utente**, e questo decide due cose. La
prima: non c'e' niente da tradurre (chi ha scritto "Del Piero" sa gia' di che nazionalita'
e ruolo sia), quindi il blocco funziona uguale nelle tre lingue senza tradurre 53 paesi. La
seconda: le squadre **non** si confrontano mai. Sono gia' tutte nell'immagine — dirle
sarebbe ripetere quello che si vede — e le informazioni che l'immagine non da' sono
esattamente nazionalita', ruolo ed eta'.

Il nome tentato viene risolto sul dataset con la stessa tolleranza ai refusi delle risposte,
e il blocco riporta in testa la scheda che il bot ha capito: e' l'unico modo che ha l'utente
di accorgersi che "Ronaldo" e' stato inteso come un altro Ronaldo. Se il nome non e' nel
dataset — o se la sfida e' cosi' vecchia da non avere `player_id` — il confronto non c'e' e
il messaggio resta quello di prima. Chi volesse usarlo come oracolo ("questo calciatore e'
nel dataset?") ha tre tentativi al giorno per farlo, che e' un prezzo abbastanza alto da
rendere la cosa inutile.

Lo stesso confronto vale nell'archivio: recuperare una sfida passata non deve essere piu'
difficile del gioco vero.

### Striscia, condivisione, archivio

- **Striscia** (`services/streak.py`): giorni consecutivi indovinati, con un bonus a soglie
  (3, 7, 30 giorni) e un tetto basso di proposito — deve premiare la costanza, non diventare
  il modo principale di fare punti. Si calcola nella stessa transazione che assegna i punti.
- **Card del risultato** (`services/share.py`): i quadratini stile Wordle (🟥🟩⬜ 2/3) con il
  numero della sfida, da incollare in un gruppo senza rivelare la risposta. Il bottone e' un
  link a `t.me/share/url`, quindi non serve la inline mode del bot. C'e' anche per chi **non**
  ci e' arrivato (🟥🟥🟥 X/3): la giornata persa e' meta' di quello che si incolla in un
  gruppo, ed e' l'unica riga che non puo' spoilerare niente. Le sfide recuperate
  dall'archivio si condividono marcate come tali, cosi' in un gruppo dove quella di oggi e'
  ancora aperta non sembrano il risultato di oggi.
- **Archivio** (`handlers/archive_handler.py`): rigiocare i giorni passati **senza punti**.
  Aprire un giorno mette l'utente in "modalita' archivio" (`archive_day` sul suo documento,
  non in memoria: su Cloud Run l'istanza puo' sparire fra un messaggio e l'altro), e da li' le
  risposte valgono per quella sfida finche' non la risolve o non fa `/today`. A tentativi finiti
  la risposta si puo' dire: quella giornata e' gia' passata.

### Allenamento e partite di gruppo

Due modalità con lo stesso motore (`services/practice_content.py`) e la stessa regola: si
gioca solo su materiale che **non può spoilerare la sfida del giorno**, e non si tocca la
classifica generale.

Il problema da risolvere è questo: pescare un giocatore qualsiasi dal dataset mostrerebbe il
percorso di carriera di qualcuno che non è ancora uscito, e chi lo ha visto — il giorno in cui
esce — lo riconosce in due secondi e si prende pure il bonus del primo. È un danno diretto
alla classifica. Le due sorgenti ammesse lo evitano in due modi diversi:

1. **il pool riservato** — i calciatori con `"practice_only": true` in `data/players.json`
   (80 sui 323 di oggi, bilanciati fra le quattro fasce di difficoltà) **non escono mai** come
   sfida del giorno né dentro un evento. Allenarsi su di loro non dà nessun vantaggio, per
   costruzione. È materiale disponibile subito e non costa **nessuna lettura**: le schede sono
   nel file, dentro il container. `python scripts/reserve_practice_players.py` è ciò che ha
   assegnato la fetta, e la scelta sta nel dataset — non calcolata a runtime, perché se la
   regola cambiasse un giocatore passerebbe da una parte all'altra e lo spoiler tornerebbe.
   Per lo stesso motivo `scripts/import_players.py` non perde il flag reimportando una scheda.
   I nomi da copertina (`popularity` 5) non si riservano mai: sono quelli che fanno venire
   voglia di rispondere a chi apre il bot la prima volta, e toglierli per sempre dalla sfida
   del giorno costerebbe piu' di quanto renda averli in allenamento;
2. **le sfide già passate** — pubbliche per costruzione: l'archivio le mostra, il broadcast di
   mezzanotte dice la risposta di ieri. Entrano una volta su quattro
   (`practice_past_challenge_ratio` in `data/config.json`), perché sono le partite vere e
   ritrovarne una ha un sapore diverso da un esercizio.

Anche la seconda sorgente costa **una lettura**: l'id del documento *è* la data, quindi si
estrae una data a caso e si legge quel documento. Scaricare l'elenco dei giorni passati per
sceglierne uno costerebbe fino a trecento letture a partita. Se il giorno estratto è vuoto (il
bot non c'era ancora, o la pulizia ha tolto quel documento) si riprova, e dopo qualche
tentativo a vuoto si ripiega su una query sola sui giorni recenti.

Le due sorgenti escono dal servizio con la stessa forma, chiave compresa (`pool:maldini`,
`day:2026-09-07`): chi le usa non sa da dove vengono, e la chiave è quello che si salva sul
documento utente o sul round per riprendere la partita dopo che l'istanza Cloud Run è sparita.

**Allenamento** (`/training`, `handlers/training_handler.py`): chi installa il bot oggi
gioca *una* partita e poi aspetta ventiquattro ore, ed è il minuto in cui si decide se
restare. Qui invece si preme un bottone e arriva un'altra sfida, per sempre. Nessun punto, il
confronto dopo ogni errore, cinque tentativi e poi la risposta — che si può anche chiedere
subito con "👀 Rivela", visto che quella giornata è passata. I tentativi sono cinque e non
infiniti anche per una ragione meno ovvia: un campo che accetta nomi all'infinito e risponde
"stessa nazionalità, ruolo diverso" sarebbe un modo comodo per sondare il dataset.

**Partita di gruppo** (`/round`, `handlers/group_handler.py`): un round alla volta nel
gruppo, vince chi risponde per primo, punti per difficoltà come nel gioco vero. **Non** è la
sfida di oggi ripubblicata — la risposta comparirebbe in chiaro davanti a chi non ha ancora
giocato, bruciando la giornata anche a chi non stava guardando. Le altre tre conseguenze della stessa scelta:

- **i punti restano nel gruppo** (`group_rounds/{chat}/players/{utente}`, `/standings`) e non
  toccano né la classifica generale né quella del mese: un gruppo creato con un account
  secondario non sposta niente di quello che conta;
- **si risponde con `/guess`**, non a messaggio libero: leggere i messaggi liberi di un gruppo
  vorrebbe dire spegnere la privacy mode in BotFather, cioè ricevere *tutti* i messaggi di
  *tutti* i gruppi in cui il bot è dentro. I comandi arrivano lo stesso;
- **non serve essersi registrati**: in gruppo non c'è niente da salvare sull'utente, e
  chiedere `/start` prima di poter rispondere toglierebbe alla modalità l'unica cosa che la
  rende utile.

Tre tentativi a testa per round, contati su un documento per giocatore (come i partecipanti a
un evento, e per lo stesso motivo: in un gruppo che risponde a raffica una mappa sola dentro
il round sarebbe un punto di contesa in scrittura). Si azzerano da soli quando comincia un
round nuovo, perché il documento porta il numero del round a cui si riferisce — lo stesso
meccanismo dei contatori giornalieri con `last_played_day`. Il round lo vince una persona
sola anche se in due rispondono nello stesso istante: è la stessa transazione del bonus del
primo.

### Leghe private

Una classifica fra amici (`handlers/league_handler.py`): `/league_create` genera un codice di sei
caratteri senza `0/O` e `1/I` (si detta a voce) e un link d'invito `t.me/<bot>?start=lega_CODICE`
che iscrive chi lo apre. I punti di una lega stanno sul documento del membro e vengono sommati
quando l'utente indovina — la classifica e' quindi una query ordinata invece di una lettura per
ogni iscritto — e contano solo **da quando si entra**, cosi' entrare in una lega vecchia non
condanna a restare ultimi.

### Mini app Telegram

`webapp/index.html` e' una pagina servita dallo stesso servizio FastAPI su `/app`: profilo,
striscia, classifica e leghe in una schermata sola. Chi sia l'utente lo stabilisce **solo** la
firma di `initData` (`services/webapp_auth.py`, HMAC-SHA256 con il token del bot piu' controllo
sull'eta' dei dati): il client non manda mai un id, altrimenti chiunque potrebbe chiedere i dati
di chiunque. Il bottone "Apri l'app" compare solo se `PUBLIC_BASE_URL` e' configurata.

## Stack

- **Bot**: [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) su webhook, servito da **FastAPI** (`bot.py`)
- **Dati di gioco**: **Firebase Firestore** (`users`, `daily_path`, `events` con la sotto-collection `participants`, `seasons`). Le date sul database sono ISO `YYYY-MM-DD`; agli utenti si mostrano come `gg/mm/aa`
- **Scheduler**: **Cloud Scheduler** chiama `POST /internal/daily-job` a mezzanotte italiana (nessun processo interno da tenere sveglio)
- **Immagini**: percorso, banner evento, palmarès e avatar sono generati a runtime con **Pillow** (`services/path_image.py`), con un font TrueType di sistema (`fonts-dejavu-core` nel Dockerfile). Nessuna immagine ospitata fuori dal progetto
- **Dataset calciatori**: JSON locale versionato in `data/players.json`
- **Mini app**: pagina statica servita da FastAPI su `/app`, autenticata con la firma `initData` di Telegram

## Architettura dell'automazione

```
data/players.json          -> pool di calciatori curato (carriera, nazionalità, popolarità, verified)
data/event_templates.json  -> regole configurabili per generare gli eventi a rotazione
data/config.json           -> parametri di gioco (difficoltà, buffer giorni, anti-ripetizione, ecc.)
docs/difficolta.md         -> come si assegnano notorietà e difficoltà (da leggere prima di ampliare il dataset)

services/dates.py            -> un solo posto in cui si decide come si scrive una data (ISO sul db, gg/mm/aa a schermo)
services/firebase_service.py -> tutti gli accessi a Firestore (transazioni comprese)
services/daily_challenge.py  -> sfida del giorno, con cache in memoria della sola parte immutabile
services/player_pool.py      -> carica e valida il dataset, filtra per le regole di un evento
services/difficulty.py       -> calcola la difficoltà di un percorso (facile/normale/difficile/esperto)
services/dataset_health.py   -> salute del pool: autonomia, difficoltà scoperte, eventi senza candidati
services/path_image.py       -> disegna le immagini (Pillow): percorso, banner evento, palmarès, avatar
services/fonts.py            -> trova un TrueType di sistema per le immagini (fallback compreso)
services/matching.py         -> confronto tollerante fra risposta scritta e risposte accettate
services/guess_feedback.py   -> confronto fra il calciatore tentato e la soluzione (nazionalità, ruolo, età)
services/past_challenges.py  -> sceglie una sfida già passata, a una lettura invece che con una query
services/practice_content.py -> il materiale di allenamento e gruppo: pool riservato + sfide passate, una forma sola
services/streak.py           -> regole della striscia di giorni consecutivi
services/share.py            -> card del risultato in quadratini e link di condivisione
services/webapp_auth.py      -> verifica la firma dei dati che manda la mini app Telegram
services/webapp_api.py       -> i dati che la mini app mostra, in una risposta sola
services/daily_generator.py  -> sceglie il calciatore del giorno (con anti-ripetizione) e genera N giorni in anticipo
services/event_generator.py  -> sceglie un template evento a rotazione e lo riempie con giocatori validi
services/manual_event_service.py -> eventi creati a mano dalla chat (coppie padre/figlio)
services/content_admin.py    -> dettaglio e correzione di sfide/eventi gia' programmati (usato dalla dashboard locale)
services/dataset_editor.py   -> modifiche al dataset e alla taratura della difficolta' (usato dalla dashboard locale)

scripts/generate_content.py  -> entrypoint per generare il buffer a mano (debug/backfill)
scripts/import_players.py    -> importa nuovi calciatori nel dataset con validazione e anti-duplicati
scripts/reserve_practice_players.py -> riserva all'allenamento una fetta del dataset, bilanciata per difficoltà
scripts/dataset_report.py    -> report sullo stato del dataset (usato anche dalla CI)
scripts/migrate_firestore.py -> migrazione una tantum dei dati esistenti al modello nuovo
scripts/backup_firestore.py  -> export JSON del database, sotto-collezioni comprese (usato dal workflow settimanale)
scripts/cleanup_daily_paths.py -> cancella le sfide oltre l'anno e i documenti pre-migrazione
handlers/daily_job.py        -> job di mezzanotte chiamato da Cloud Scheduler: broadcast, reset, e generazione
handlers/guess_handler.py    -> tentativi sulla sfida del giorno (comando e messaggio libero)
handlers/archive_handler.py  -> sfide passate rigiocate senza punti
handlers/training_handler.py -> allenamento: sfide passate a raffica, in privato
handlers/group_handler.py    -> partite di gruppo: un round alla volta, punti solo dentro il gruppo
handlers/league_handler.py   -> leghe private, codici d'invito, classifiche
handlers/keyboards.py        -> tastiera del menu e menu comandi di Telegram
handlers/legend_handler.py   -> la legenda dell'immagine (bottone sotto la sfida e /legend)
handlers/menu_handler.py     -> i bottoni del menu, collegati agli handler dei comandi
handlers/admin_handler.py    -> tutti i comandi Telegram /admin_* (al posto di una dashboard web)
webapp/index.html            -> la mini app Telegram (servita da FastAPI su /app)
admin_ui.py                  -> dashboard locale Streamlit: stato dettagliato e modifiche ai dati
```

### Come viene scelto il calciatore del giorno

1. Ogni notte (23:15 UTC) **Cloud Scheduler** chiama `POST /internal/daily-job` sul servizio
   Cloud Run, che scrive direttamente su Firestore i prossimi `buffer_days_ahead` giorni
   mancanti (default 3), invia il broadcast agli utenti iscritti, assegna i trofei degli eventi
   conclusi e - il primo del mese - chiude la stagione mensile. **Non azzera nessun contatore**:
   i tentativi giornalieri si azzerano da soli (vedi [Database](#database)).
2. Il calciatore viene scelto **escludendo** quelli usati negli ultimi `history_days_no_repeat`
   giorni (default 60), tra i soli giocatori con `verified: true` e un percorso di almeno
   `min_teams_in_career` squadre (default 2) — niente percorsi banali o dati incompleti.
3. La difficoltà ruota secondo `difficulty_rotation` in `data/config.json`; se per quella
   difficoltà non ci sono candidati liberi, si prova la difficoltà più vicina.
4. La scelta è **deterministica per data** (seed = data): se la generazione va rieseguita per
   errore, il giocatore scelto per un giorno già passato resta lo stesso.
5. Se anche Cloud Scheduler non dovesse partire, `/show` e `/guess` generano la sfida del
   giorno al primo utilizzo (fallback "esecuzione alla prima richiesta").

### Come vengono generati gli eventi tematici

- Ogni "tipo" di evento è descritto come **template** in `data/event_templates.json`: nome,
  descrizione, tipo di gameplay (`path`/`career`/`transfer_guess`/`father_son`), regole di
  filtro sul pool di giocatori (es. minimo 6 squadre, solo big-5, solo nazionalità sudamericane),
  durata e punti giornalieri.
- **Nome e descrizione sono tradotti** (`name_i18n`, `description_i18n`): erano gli ultimi testi
  che restavano in italiano per tutti, perché sono contenuto e non passavano da
  `services/i18n.py` — quindi nemmeno dal test che tiene allineate le tre lingue. Ora c'è un
  test apposta ([`tests/test_event_translations.py`](tests/test_event_translations.py)) che
  fallisce se un template nuovo arriva senza traduzioni. `name` e `description` restano il
  testo italiano: sono il ripiego per gli eventi generati prima, ed è quello che legge
  l'amministrazione. Le traduzioni vengono **copiate sul documento dell'evento** al momento
  della generazione, come il nome: un evento già partito resta quello che era anche se il
  template cambia sotto.
- `services/event_generator.py` sceglie un template **non usato di recente** (vedi
  `event_history_no_repeat_templates`), rispetta un intervallo minimo tra un evento e l'altro
  (`event_min_gap_days`) e — se il template lo richiede — solo nel weekend (`weekend_only`).
- Un template può essere marcato `manual_only: true` (es. "Coppie leggendarie" padre/figlio, che
  richiede una foto e non una carriera): non verrà mai generato in automatico, si crea dalla
  chat con `/admin_fs_add` + `/admin_event_create` (vedi
  [Eventi "coppie padre/figlio"](#eventi-coppie-padrefiglio-manuali)).
- Per il tipo `career` (indovina le squadre di un giocatore noto) **non** viene mai salvata
  un'immagine del percorso nei dati giornalieri, per non rivelare la risposta.

### Difficoltà

**Come si assegnano notorietà e difficoltà è definito in
[`docs/difficolta.md`](docs/difficolta.md)**: è il riferimento da leggere prima di aggiungere
un giocatore o di ritarare i pesi, e contiene la scala `popularity` 1-5 con gli esempi.

In breve: la difficoltà è calcolata in `services/difficulty.py` e non è un campo del dataset.
La **notorietà** (`popularity` 1-5) fissa la fascia a passi di 4 punti; il percorso (quota di
tappe fuori dai campionati noti, paesi, squadre) pesa come modificatore per un massimo di 5.5
punti, cioè **può spostare un giocatore di una fascia, mai di due**. È il vincolo che evita i
due errori tipici: il campione girovago che risulta "impossibile" e lo sconosciuto con
carriera lineare che risulta "facile".

I campionati valgono su tre livelli — `top_leagues` (i top 5), `known_leagues` (Eredivisie,
Primeira Liga, Brasileirão, MLS...) e tutto il resto — così l'Ajax non pesa come una seconda
divisione asiatica. Pesi, soglie e liste sono in `data/config.json` e si ritarano senza
toccare il codice: `python scripts/dataset_report.py` mostra come si distribuisce il dataset
fra le quattro fasce, e `explain_difficulty(player)` scompone il punteggio di una singola
scheda. I punti assegnati per difficoltà sono invariati rispetto al gioco esistente (1/2/3/4).

Quando una fascia non convince, la sezione *Dataset* della
[dashboard locale](#dashboard-locale-streamlit) fa le stesse cose senza aprire il file:
elenca tutte le schede con il punteggio già scomposto in "da notorietà" e "dal percorso",
permette di correggere notorietà e campionato di una tappa, e mostra **chi cambia fascia
prima** di salvare. La logica sta in `services/dataset_editor.py`, che scrive
`data/players.json` con una copia di sicurezza in `backup/` e rifiuta le modifiche che
renderebbero il dataset incoerente.

## Comandi amministrativi

Riservati agli ID Telegram elencati in `ADMIN_TELEGRAM_IDS` (env var, separati da virgola).
Non c'è (e non serve) una dashboard **web** esposta pubblicamente: si amministra dalla chat,
oppure dalla [dashboard locale](#dashboard-locale-streamlit) quando serve vedere i dettagli o
correggere qualcosa a mano.

| Comando | Cosa fa |
|---|---|
| `/admin_help` | elenco dei comandi amministrativi |
| `/admin_status` | evento attivo, stato del dataset, sfide già in buffer |
| `/admin_stats` | utenti registrati, con notifiche attive, che hanno indovinato oggi |
| `/admin_pool` | salute del dataset: autonomia senza ripetizioni, difficoltà, eventi senza candidati |
| `/admin_review` | giocatori esclusi dalla selezione automatica e il motivo |
| `/admin_next [n]` | le prossime sfide già generate (**contiene le soluzioni**) |
| `/admin_events [n]` | ultimi eventi generati, con periodo e numero di partecipanti |
| `/admin_regen` | forza subito la generazione del buffer di sfide/eventi mancanti |
| `/admin_block <id>` | sospende un giocatore dalla selezione automatica (es. dato sbagliato segnalato) |
| `/admin_unblock <id>` | riammette un giocatore sospeso |
| `/admin_blocked` | elenco dei giocatori sospesi |
| `/admin_fs_add <risposte>` | salva una coppia padre/figlio (in didascalia a una foto) |
| `/admin_fs_list` | coppie padre/figlio salvate |
| `/admin_fs_del <id>` | elimina una coppia padre/figlio |
| `/admin_event_create <template> [gg/mm/aa] [giorni]` | crea a mano un evento |

`/admin_block` scrive su Firestore (`admin_settings/dataset_overrides`), quindi ha effetto
**subito**, senza redeploy: utile quando un utente segnala una carriera sbagliata. Le sfide
già presenti nel buffer non cambiano, si controllano con `/admin_next`.

## Dashboard locale (Streamlit)

```bash
pip install -r requirements-dev.txt
streamlit run admin_ui.py
```

Gira **sul proprio PC** con le stesse credenziali del bot (`.env` + `firebase-key.json`) e
non viene mai esposta: non ha login perché non è raggiungibile da fuori. Usa gli stessi
servizi dei comandi Telegram — nessuna logica duplicata — e in più permette le correzioni che
in chat sarebbero scomode. **Scrive sul database di produzione.**

| Sezione | Cosa mostra | Cosa permette di modificare |
|---|---|---|
| Stato generale | sfida di oggi con la soluzione, giorni coperti dal buffer, evento in corso, salute del dataset, utenti | genera subito sfide/eventi mancanti |
| Sfide giornaliere | ogni giorno della finestra scelta **buchi compresi**: numero della sfida, soluzione, difficoltà e punti, tappe di carriera, origine (auto/manuale), stato del bonus del primo, anteprima dell'immagine inviata agli utenti | sostituisci il giocatore, rigenera con le regole automatiche, correggi le risposte accettate, cambia la difficoltà, riapri/chiudi il bonus, elimina o programma una sfida in una data qualsiasi |
| Eventi | stato (programmato/in corso/concluso), giorno corrente su totale, giorno per giorno con risposte, punti e bonus, elenco dei giorni **senza contenuto**, classifica dei partecipanti | attiva/disattiva, sposta le date (rimappa anche i contenuti e il giorno dei trofei), correggi le risposte di un giorno, riapri/chiudi il bonus di giornata, elimina, crea un evento manuale |
| Utenti | classifiche, ricerca per id o per nome, scheda completa con striscia, trofei, leghe e archivio | punti totali e del mese, striscia, lingua, notifiche, azzeramento dei tentativi di oggi |
| Leghe | leghe private con numero di membri e classifica interna | — |
| Dataset | quattro schede: salute del pool, **elenco completo** dei giocatori con difficoltà e punteggio scomposto, scheda singola con le tappe e il peso di ogni campionato, taratura della formula | notorietà (`popularity`), *verificato*, *solo allenamento*, campionato di una tappa; pesi e soglie della difficoltà, con anteprima di chi cambia fascia |
| Giocatori sospesi | chi è escluso dalla selezione automatica | sospendi / riammetti |
| Coppie padre/figlio | coppie salvate e in quali eventi sono state usate | aggiungi (foto via bot) / elimina |

Le regole del gioco valgono anche qui, e stanno in `services/content_admin.py`, non
nell'interfaccia: la sfida di oggi non si elimina (è in gioco), un evento in corso si
disattiva invece di essere cancellato, sostituire il giocatore di una giornata già vinta non
rimette in palio il bonus del primo, e spostare un evento sposta insieme date, contenuti e
giorno dei trofei. Le letture stanno dietro una cache di 45 secondi (le letture Firestore si
pagano); ogni modifica la svuota.

## Eventi "coppie padre/figlio" (manuali)

Questo evento non si può generare dal dataset dei percorsi: serve una foto, e un dataset di
immagini di coppie padre/figlio non esiste. Resta quindi **manuale**, ma si crea interamente
da Telegram, senza scrivere documenti a mano su Firestore:

1. manda al bot la foto della coppia con didascalia
   `/admin_fs_add Maldini, Paolo e Cesare Maldini` (le risposte accettate separate da
   virgola). La foto **non viene ospitata da nessuna parte**: si salva il `file_id` di
   Telegram, che il bot può rimandare come immagine. In alternativa si può rispondere con lo
   stesso comando a una foto già inviata;
2. ripeti per tutte le coppie che vuoi (`/admin_fs_list` le elenca, `/admin_fs_del <id>` ne
   toglie una);
3. quando ce ne sono abbastanza: `/admin_event_create coppie_leggendarie [gg/mm/aa]`.
   L'evento dura **un giorno per coppia** (mai due volte la stessa coppia nello stesso
   evento) e le coppie già usate non vengono ripescate negli eventi successivi.

Lo stesso comando serve anche a **forzare a mano un evento automatico**, quando si vuole
decidere quando parte invece di aspettare la rotazione:
`/admin_event_create giramondo 01/12/26`.

## Ampliare il dataset dei calciatori

Il dataset è pensato per crescere nel tempo: oggi contiene **323 calciatori**, tutti
verificati. 243 alimentano il gioco vero — 243 giorni di sfide senza mai ripetere nessuno,
contro i 60 giorni della finestra anti-ripetizione — e 80 sono riservati all'allenamento e ai
round di gruppo, dove non possono spoilerare niente.

### Il flusso di import

Per **aggiungere** calciatori non si modifica `data/players.json` a mano: si prepara un file
di batch e lo si importa. Per **correggere** una scheda già dentro (notorietà sbagliata,
campionato scritto male) c'è la sezione *Dataset* della
[dashboard locale](#dashboard-locale-streamlit), che scrive lo stesso file con gli stessi
controlli.

```bash
# 1. prepara il batch (stesso schema di data/players.json, vedi gli esempi in data/incoming/)
# 2. prova senza scrivere
python scripts/import_players.py data/incoming/nuovo_batch.json --dry-run
# 3. importa davvero
python scripts/import_players.py data/incoming/nuovo_batch.json
# 4. controlla come sta il pool dopo l'aggiunta
python scripts/dataset_report.py
```

Lo script fa quello che a mano si dimentica sempre: normalizza id e alias, salta i giocatori
già presenti (`--update` per aggiornarli), rifiuta chi ha dati incoerenti spiegando il
motivo, e soprattutto intercetta gli **alias ambigui** — la stessa risposta valida per due
calciatori diversi, il bug più fastidioso per chi gioca, perché scrive la risposta giusta e
il bot gliela rifiuta. I nuovi arrivi restano `"verified": false` (e quindi fuori dalla
selezione automatica) finché qualcuno non ha controllato le date: `--verified` salta questo
passaggio, `/admin_review` elenca chi è in attesa di revisione.

Per **rivedere davvero** le schede in attesa serve vederne la carriera, non solo il nome:

```bash
python scripts/dataset_report.py --pending   # schede da approvare, tappa per tappa
```

Quando le date tornano, si approva reimportando lo stesso batch:

```bash
python scripts/import_players.py data/incoming/<batch>.json --update --verified
```

### Schema di una scheda

```json
{
  "id": "maldini",
  "full_name": "Paolo Maldini",
  "aliases": ["maldini", "paolo maldini"],
  "nationality": "Italia",
  "position": "Difensore",
  "birth_year": 1968,
  "popularity": 5,
  "verified": true,
  "one_club_career": true,
  "career": [
    {"team": "Milan", "country": "Italia", "league": "Serie A", "start_year": 1985, "end_year": 2009,
     "apps": 647, "goals": 29}
  ]
}
```

Ogni tappa ha tre campi facoltativi: `loan` (prestito), `apps` (presenze) e `goals` (gol).
Presenze e gol sono quelli di **campionato**, come li conta Wikipedia: alla Juventus Del
Piero risulta con ~478 presenze, non con le ~700 di tutte le competizioni.

`practice_only: true` toglie un calciatore dal gioco quotidiano e lo mette fra il materiale
di allenamento (vedi [Allenamento e partite di gruppo](#allenamento-e-partite-di-gruppo)). Non
si mette a mano: lo assegna `scripts/reserve_practice_players.py`, che tiene la fetta
bilanciata fra le fasce di difficoltà. Una volta riservato, un giocatore resta riservato — è
la ragione per cui il flag sopravvive a un reimport.

`one_club_career: true` serve a distinguere una **bandiera** (Totti, Maldini, Puyol: una sola
squadra e i dati sono completi) da una **scheda incompleta**: senza questo flag un percorso
di una squadra sola viene scartato come dato mancante. È anche ciò che rende possibile
l'evento "Un amore, una maglia".

`popularity` è l'unico campo che decide la difficoltà, quindi è anche l'unico che si può
sbagliare in modo silenzioso: **la scala con gli esempi è in
[`docs/difficolta.md`](docs/difficolta.md)**, che contiene anche la checklist da seguire
prima di scrivere una scheda nuova. La difficoltà, invece, non è un campo: è calcolata.

### Cosa si vede nell'immagine

Il percorso è disegnato da `services/path_image.py` **senza una parola**, perché la stessa
PNG viene inviata a utenti italiani, inglesi e spagnoli. Quindi ogni informazione ha un
segno, non un'etichetta:

| Informazione | Come appare |
|---|---|
| Prestito | barretta laterale **tratteggiata** e freccia `→` davanti agli anni |
| Tappa ancora in corso | `2016 – …` |
| Presenze e gol | `33 (22)`, la convenzione di Wikipedia; per i portieri le sole presenze |
| Durata della tappa | barra proporzionale, mostrata solo quando mancano presenze e gol |

Che questi segni vogliano dire qualcosa, pero', bisogna dirlo: sotto ogni sfida (e sotto
ogni sfida d'archivio) c'e' il bottone **"Come si legge"**, e c'e' il comando `/legend`
(`handlers/legend_handler.py`). Prima la notazione non era scritta da nessuna parte, nemmeno
in `/help`: chi apriva la sfida stava indovinando anche quella.

Il layout si adatta al numero di tappe: fino a 12 righe larghe, da 13 in su righe compatte.
Una carriera da 20 tappe sta in 900×1952 px — sopra le ~2000 px Telegram rimpicciolisce
l'immagine al punto da renderla illeggibile in chat, ed è il motivo per cui esiste la
soglia.

### Controlli automatici

`validate_dataset()` gira nei test e in CI (`python scripts/dataset_report.py --strict`) e
blocca la pipeline se il dataset ha: id duplicati, alias condivisi fra due giocatori, tappe
non in ordine cronologico, anni di fine precedenti all'inizio, esordi incompatibili con
l'anno di nascita, popolarità fuori dalla scala 1-5.

### Quando ampliarlo

`/admin_pool` (o `python scripts/dataset_report.py`) risponde alla domanda "il pool basta
ancora?": quanti giorni si va avanti senza ripetizioni, quante fasce di difficoltà sono
scoperte e quali eventi tematici hanno meno candidati dei giorni che durano. È il momento di
aggiungere calciatori quando compare un avviso: i giocatori selezionabili sono meno di 1,5
volte la finestra anti-ripetizione, oppure una fascia di difficoltà è quasi vuota.

## Database

Il modello dati Firestore è documentato in
[`docs/firebase_review.md`](docs/firebase_review.md), insieme al perché di ogni scelta.
In breve:

- `users/{telegram_id}` — l'id Telegram **è** l'id del documento: letture dirette, creazione
  atomica (niente utenti duplicati), transazioni possibili.
- **Nessun reset notturno dei contatori**: ogni documento porta `last_played_day`, quindi i
  tentativi di ieri valgono zero oggi senza che nessuno li abbia azzerati. Il costo del reset
  passa da "una scrittura per utente ogni notte" a zero.
- Il **bonus al primo che indovina** si assegna in transazione: due risposte simultanee non
  possono più prenderlo entrambe.
- I **partecipanti a un evento** sono documenti separati
  (`events/{code}/participants/{telegram_id}`), non una mappa dentro l'evento: niente limite
  di 1 MB e niente contesa in scrittura.
- Le **classifiche** si leggono con `order_by(...).limit(10)` più un `count()` per la
  posizione personale, invece di scaricare tutti gli utenti.
- `group_rounds/{chat_id}` — il round in corso di un gruppo, con la sotto-collection
  `players` (un documento per partecipante: punti del gruppo, round vinti, tentativi del
  round corrente). Sul round si copiano risposte accettate, difficoltà e `player_id`, così
  ogni tentativo costa **una** lettura invece di due; il percorso di carriera no, si
  ridisegna al momento.

### Migrazione dei dati esistenti

A bot fermo:

```bash
python scripts/migrate_firestore.py --dry-run   # mostra cosa farebbe
python scripts/migrate_firestore.py             # esegue, con export JSON preliminare
firebase deploy --only firestore:rules,firestore:indexes
```

Lo script è idempotente: esporta prima tutto in JSON, poi sposta gli utenti sul nuovo id
(fondendo gli eventuali duplicati), converte le date in ISO e trasforma la classifica degli
eventi in sotto-collection.

[`firestore.rules`](firestore.rules) nega ogni accesso dai client (il bot usa solo l'Admin
SDK, che le ignora) e [`firestore.indexes.json`](firestore.indexes.json) contiene i due
indici compositi necessari.

### Backup e pulizia

L'export gestito di Firestore richiede il piano Blaze e un bucket; il database qui è piccolo
(utenti, un documento per giorno di gioco, qualche evento), quindi il backup è un JSON alla
settimana, archiviato come artifact di GitHub Actions
([`.github/workflows/backup.yml`](.github/workflows/backup.yml), lunedì alle 03:30 UTC, o a
mano con *Run workflow*). Si autentica con la stessa Workload Identity Federation del deploy:
nessuna chiave di servizio nei secret.

```bash
python scripts/backup_firestore.py            # copia in backup/, sotto-collezioni comprese
```

L'export segue le **sotto-collezioni** (`participants`, `members`, `archive`): sono metà dei
dati del gioco, e un backup che si ferma al primo livello sarebbe un backup finto.

`daily_path` cresce di 365 documenti l'anno e non si guarda indietro — l'archivio mostra dieci
giorni, l'anti-ripetizione sessanta, il numero della sfida è calcolato dalla data:

```bash
python scripts/cleanup_daily_paths.py --dry-run       # cosa cancellerebbe
python scripts/cleanup_daily_paths.py                 # sfide oltre l'anno
python scripts/cleanup_daily_paths.py --drop-legacy   # anche i documenti pre-migrazione
```

Lo script distingue due cose: le sfide **vecchie** (oltre la finestra da conservare, un anno
di default) e i documenti **inservibili** — id non in ISO, oppure senza percorso di carriera
o senza risposte accettate. Sono quelli che nell'archivio danno "sfida non più disponibile", e
si cancellano solo chiedendolo esplicitamente. La sfida di oggi e i giorni futuri già generati
non si toccano mai, e prima di cancellare viene scritto un JSON con tutto quello che sta per
sparire.

## Test

```bash
pip install -r requirements-dev.txt
pytest -q
```

I test coprono: selezione deterministica e anti-ripetizione del giocatore del giorno,
integrità del dataset (id duplicati, alias ambigui, cronologia delle carriere, bandiere),
import di nuovi calciatori, calcolo difficoltà, generazione eventi (rotazione, cooldown,
weekend-only, nessuna fuga di risposta per gli eventi "career"), creazione manuale
dell'evento padre/figlio, generazione dell'immagine del percorso, cambio di giorno/fuso
orario, permessi di **tutti** i comandi admin, e - dopo la revisione del database - il
flusso completo di `/guess` e `/events` (tentativi, bonus del primo assegnato una volta
sola, limiti giornalieri), il reset "pigro" dei contatori, il reset mensile, il broadcast di
mezzanotte, le classifiche e le trasformazioni della migrazione Firestore.

Sulle funzioni aggiunte dopo: tolleranza ai refusi (con la lista di coppie che **non** devono
essere confuse), messaggi liberi trattati come tentativo, confronto dopo un tentativo sbagliato
(compresi i casi in cui **non** deve uscire: nome fuori dal dataset, sfida senza `player_id`),
striscia e relativo bonus, quadratini della card condivisibile — vinta e persa —, backup con
le sotto-collezioni e regole di cancellazione dei `daily_path`, scelta di una sfida passata
(mai dal futuro, mai un documento senza percorso, e il ripiego quando le date estratte sono
vuote), allenamento (nessun punto, risposta svelata all'ultimo tentativo) e round di gruppo
(un solo vincitore, punti che non entrano nella classifica generale, nome con HTML dentro),
flusso completo dell'archivio (nessun punto, la giornata di oggi non
viene toccata, la risposta rivelata solo a tentativi finiti), leghe private (codici, limiti,
classifica, link d'invito che iscrive da `/start`), firma `initData` della mini app (dato
manomesso, token sbagliato, dati scaduti) e allineamento delle tre lingue: se una chiave o un
segnaposto manca in una traduzione, la CI se ne accorge.

## Deploy

Il bot gira su **Cloud Run** (container, deploy automatico da GitHub Actions dopo i test — vedi
[`docs/deploy.md`](docs/deploy.md)) e la generazione giornaliera dei contenuti è affidata a
**Cloud Scheduler**, che chiama un endpoint interno del servizio invece di dipendere da un
processo sempre acceso. Il ciclo completo test → deploy, con le scelte di qualità del codice e
gestione delle dipendenze, è documentato in [`docs/ci_cd_pipeline.md`](docs/ci_cd_pipeline.md).

| Componente | Dove | Perché |
|---|---|---|
| Bot (webhook) | **Cloud Run** | Container da [`Dockerfile`](Dockerfile), scala a zero quando inattivo, HTTPS incluso |
| Generazione giornaliera/eventi | **Cloud Scheduler** → `POST /internal/daily-job` | Non dipende dal fatto che l'istanza Cloud Run sia già sveglia; Cloud Run la avvia al bisogno |
| Database | **Firebase Firestore** | Già in uso, nessuna migrazione necessaria |

### 1. Cloud Run (bot)

Deploy automatico da GitHub Actions ad ogni push su `main` che supera la CI (setup di Workload
Identity Federation, comandi manuali di fallback e variabili d'ambiente del servizio: vedi
[`docs/deploy.md`](docs/deploy.md)).

Se cambia l'URL del servizio va aggiornato `WEBHOOK_URL` e il bot deve rieseguire `set_webhook`
(avviene automaticamente all'avvio, vedi `bot.py`).

Due variabili d'ambiente in piu' (facoltative, vedi [`.env.example`](.env.example)) accendono le
funzioni che hanno bisogno di sapere dove sta il bot:

| Variabile | Serve a | Se manca |
|---|---|---|
| `PUBLIC_BASE_URL` | mini app Telegram (`/app`) | il bottone "Apri l'app" non compare |
| `BOT_USERNAME` | link di condivisione del risultato e inviti alle leghe | i bottoni di condivisione/invito non compaiono, il resto funziona |

### 2. Cloud Scheduler (generazione contenuti)

Un job di Cloud Scheduler chiama ogni notte l'endpoint interno con l'header di autorizzazione:

```bash
gcloud scheduler jobs create http daily-generation \
  --schedule="15 23 * * *" \
  --uri="https://guess-the-player-595902172561.europe-west1.run.app/internal/daily-job" \
  --http-method=POST \
  --headers="x-cron-secret=<GENERATION_SECRET>" \
  --time-zone="UTC"
```

L'orario (23:15 UTC) è poco dopo mezzanotte a Roma sia in ora solare che legale. L'endpoint
(`bot.py`, `@app.post("/internal/daily-job")`) verifica l'header `x-cron-secret` contro
`GENERATION_SECRET` e rifiuta le chiamate non autorizzate con `403`.

### 3. Dominio personalizzato

Cloud Run supporta domini personalizzati e certificati gestiti gratuitamente tramite
"Custom Domains"; non necessario per il funzionamento del bot.

## Limiti noti / cosa resta da fare

- **Dataset**: 323 calciatori, tutti verificati e selezionabili (323 giorni senza
  ripetizioni). Il pool va comunque ampliato periodicamente: il segnale è l'avviso di
  `/admin_pool`, non il calendario.
- **Eventi "coppie padre/figlio"**: restano manuali per scelta, perché non esiste un dataset
  di immagini di coppie. La creazione però non richiede più di scrivere documenti su
  Firestore a mano: si fa da Telegram con `/admin_fs_add` + `/admin_event_create`.
- **Interfaccia di amministrazione**: oltre ai comandi Telegram `/admin_*`, c'è una
  [dashboard locale](#dashboard-locale-streamlit) (`streamlit run admin_ui.py`) che riusa gli
  stessi servizi e permette di correggere sfide ed eventi già programmati; va lanciata sulla
  propria macchina con le credenziali del bot, non è esposta pubblicamente. Non ha
  autenticazione propria: chi ha accesso al PC e al `firebase-key.json` ha accesso al
  database, quindi non va aperta su una macchina condivisa.
- **Font delle immagini**: sul container arrivano da `fonts-dejavu-core` (Dockerfile). Se il
  pacchetto sparisce, Pillow ripiega sul font bitmap di default: le immagini escono comunque,
  ma brutte. `services/fonts.py` accetta anche un font messo in `assets/fonts/` o indicato con
  `FONT_REGULAR_PATH` / `FONT_BOLD_PATH`.
- **Leghe private**: la classifica di una lega somma i punti fatti da quando si è entrati, e i
  limiti (50 membri, 5 leghe a testa) sono costanti in `handlers/league_handler.py`. Chi lascia
  una lega perde i punti accumulati lì dentro: rientrando riparte da zero.
- **Cloud Run scale-to-zero**: il servizio può andare a zero istanze se inattivo; la prima
  richiesta dopo un periodo di inattività (webhook Telegram o chiamata di Cloud Scheduler) ha
  qualche secondo di latenza in più per il cold start.
- **Database**: gli interventi della revisione sono stati applicati al codice, ma la
  **migrazione dei dati esistenti va eseguita a mano** (`scripts/migrate_firestore.py`) e le
  regole/indici vanno deployati. Backup ricorrente e pulizia dello storico invece ci sono
  ora, vedi [Backup e pulizia](#backup-e-pulizia).
- **Materiale per allenamento e gruppo**: il grosso è il pool riservato (80 calciatori, fissi
  finché non se ne riservano altri); le sfide passate sono la parte che cresce, e oggi ce n'è
  **una sola**. I 111 documenti scritti dalla versione precedente del bot (dal 26/04/25 al
  14/08/25) non erano utilizzabili — hanno le risposte ma non il percorso di carriera, solo un
  `image_url` su un hosting esterno — e sono stati rimossi con
  `scripts/cleanup_daily_paths.py`: comparivano anche nell'archivio, come giornate che si
  aprivano senza immagine e senza modo di giocarle. Il pool riservato si allarga rieseguendo
  `scripts/reserve_practice_players.py --ratio`, al prezzo di altrettanti giorni di autonomia
  del gioco quotidiano.
- **Confronto dopo un tentativo sbagliato**: vale sulla sfida del giorno, sull'archivio,
  sull'allenamento e sui round di gruppo, non sugli eventi tematici. Gli eventi `career` e `transfer_guess` non chiedono un calciatore
  ma una squadra, quindi il confronto per nazionalità/ruolo/età non avrebbe senso così com'è.
