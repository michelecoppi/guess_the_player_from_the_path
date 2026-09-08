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
| `/archivio` (`/archive`) | rigioca le sfide dei giorni scorsi |
| `/oggi` (`/today`) | esci dall'archivio |
| `/lega` (`/league`) | le tue leghe private |
| `/lega_crea <nome>`, `/lega_entra <codice>`, `/lega_esci <codice>` | crea, entra, esci |
| `/notify`, `/language` | notifiche e lingua |

Il menu "/" di Telegram (`set_my_commands`) viene impostato all'avvio nelle tre lingue.

### Risposte tollerate, ma non regalate

Il confronto passa da `services/matching.py`: accenti, maiuscole, punteggiatura e apostrofi
non contano ("Mbappe" = "Mbappé", "N'Golo" = "Ngolo"), e un refuso vicino alla risposta viene
accettato invece di bruciare un tentativo. La soglia e' alta e c'e' un limite sulla differenza
di lunghezza, perche' il caso da non sbagliare mai e' accettare *ronaldinho* per *ronaldo*:
i test lo verificano su una lista di coppie insidiose. Non viene mai suggerito il nome giusto
("intendevi X?"): sarebbe rivelare la soluzione.

Un messaggio che non ha la forma di un nome (un link, una frase lunga) non consuma tentativi:
il bot risponde con una riga di spiegazione.

### Striscia, condivisione, archivio

- **Striscia** (`services/streak.py`): giorni consecutivi indovinati, con un bonus a soglie
  (3, 7, 30 giorni) e un tetto basso di proposito — deve premiare la costanza, non diventare
  il modo principale di fare punti. Si calcola nella stessa transazione che assegna i punti.
- **Card del risultato** (`services/share.py`): i quadratini stile Wordle (🟥🟩⬜ 2/3) con il
  numero della sfida, da incollare in un gruppo senza rivelare la risposta. Il bottone e' un
  link a `t.me/share/url`, quindi non serve la inline mode del bot.
- **Archivio** (`handlers/archive_handler.py`): rigiocare i giorni passati **senza punti**.
  Aprire un giorno mette l'utente in "modalita' archivio" (`archive_day` sul suo documento,
  non in memoria: su Cloud Run l'istanza puo' sparire fra un messaggio e l'altro), e da li' le
  risposte valgono per quella sfida finche' non la risolve o non fa `/oggi`. A tentativi finiti
  la risposta si puo' dire: quella giornata e' gia' passata.

### Leghe private

Una classifica fra amici (`handlers/league_handler.py`): `/lega_crea` genera un codice di sei
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
services/streak.py           -> regole della striscia di giorni consecutivi
services/share.py            -> card del risultato in quadratini e link di condivisione
services/webapp_auth.py      -> verifica la firma dei dati che manda la mini app Telegram
services/webapp_api.py       -> i dati che la mini app mostra, in una risposta sola
services/daily_generator.py  -> sceglie il calciatore del giorno (con anti-ripetizione) e genera N giorni in anticipo
services/event_generator.py  -> sceglie un template evento a rotazione e lo riempie con giocatori validi
services/manual_event_service.py -> eventi creati a mano dalla chat (coppie padre/figlio)
services/content_admin.py    -> dettaglio e correzione di sfide/eventi gia' programmati (usato dalla dashboard locale)

scripts/generate_content.py  -> entrypoint per generare il buffer a mano (debug/backfill)
scripts/import_players.py    -> importa nuovi calciatori nel dataset con validazione e anti-duplicati
scripts/dataset_report.py    -> report sullo stato del dataset (usato anche dalla CI)
scripts/migrate_firestore.py -> migrazione una tantum dei dati esistenti al modello nuovo
handlers/daily_job.py        -> job di mezzanotte chiamato da Cloud Scheduler: broadcast, reset, e generazione
handlers/guess_handler.py    -> tentativi sulla sfida del giorno (comando e messaggio libero)
handlers/archive_handler.py  -> sfide passate rigiocate senza punti
handlers/league_handler.py   -> leghe private, codici d'invito, classifiche
handlers/keyboards.py        -> tastiera del menu e menu comandi di Telegram
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
| Dataset | report di salute, difficoltà, candidati per template, sfoglia i giocatori con il punteggio di difficoltà, config in uso | — |
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

Il dataset è pensato per crescere nel tempo: oggi contiene **161 calciatori** (144
selezionabili in automatico), cioè più di 140 giorni di sfide senza mai ripetere nessuno,
contro i 60 giorni della finestra anti-ripetizione.

### Il flusso di import

Non si modifica `data/players.json` a mano: si prepara un file di batch e lo si importa.

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
essere confuse), messaggi liberi trattati come tentativo, striscia e relativo bonus, quadratini
della card condivisibile, flusso completo dell'archivio (nessun punto, la giornata di oggi non
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

- **Dataset**: 161 calciatori, 144 selezionabili (oltre 140 giorni senza ripetizioni). 17
  schede sono `verified: false` e aspettano un controllo sulle date (`/admin_review`): sono
  soprattutto carriere lunghissime piene di prestiti (Vieri, Anelka, Crespo, Veron,
  Materazzi, Kvaratskhelia), dove il rischio di sbagliare un anno è alto. Il pool va
  comunque ampliato periodicamente: il segnale è l'avviso di `/admin_pool`.
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
  regole/indici vanno deployati. Restano da fare un export ricorrente di backup e una pulizia
  dei `daily_path` più vecchi di un anno: dettagli in
  [`docs/firebase_review.md`](docs/firebase_review.md).
