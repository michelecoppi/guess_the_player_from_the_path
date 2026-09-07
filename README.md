# Guess the Player from the Path

Bot Telegram che ogni giorno propone il percorso professionale (misterioso) di un calciatore
da indovinare, con classifiche, statistiche personali, eventi tematici a tempo e trofei.

## Stack

- **Bot**: [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) su webhook, servito da **FastAPI** (`bot.py`)
- **Dati di gioco**: **Firebase Firestore** (`users`, `daily_path`, `events` con la sotto-collection `participants`, `seasons`). Le date sul database sono ISO `YYYY-MM-DD`; agli utenti si mostrano come `gg/mm/aa`
- **Scheduler**: APScheduler in-process (mezzanotte Europe/Rome) + **GitHub Actions** come cron esterno affidabile
- **Immagini del percorso**: generate a runtime con **Pillow** (`services/path_image.py`), nessun hosting immagini esterno necessario
- **Dataset calciatori**: JSON locale versionato in `data/players.json`

## Architettura dell'automazione

```
data/players.json          -> pool di calciatori curato (carriera, nazionalità, popolarità, verified)
data/event_templates.json  -> regole configurabili per generare gli eventi a rotazione
data/config.json           -> parametri di gioco (difficoltà, buffer giorni, anti-ripetizione, ecc.)

services/dates.py            -> un solo posto in cui si decide come si scrive una data (ISO sul db, gg/mm/aa a schermo)
services/firebase_service.py -> tutti gli accessi a Firestore (transazioni comprese)
services/daily_challenge.py  -> sfida del giorno, con cache in memoria della sola parte immutabile
services/player_pool.py      -> carica e valida il dataset, filtra per le regole di un evento
services/difficulty.py       -> calcola la difficoltà di un percorso (facile/normale/difficile/esperto)
services/dataset_health.py   -> salute del pool: autonomia, difficoltà scoperte, eventi senza candidati
services/path_image.py       -> disegna l'immagine del percorso (Pillow), nessuna immagine caricata a mano
services/daily_generator.py  -> sceglie il calciatore del giorno (con anti-ripetizione) e genera N giorni in anticipo
services/event_generator.py  -> sceglie un template evento a rotazione e lo riempie con giocatori validi
services/manual_event_service.py -> eventi creati a mano dalla chat (coppie padre/figlio)

scripts/generate_content.py  -> entrypoint eseguito da GitHub Actions ogni notte
scripts/import_players.py    -> importa nuovi calciatori nel dataset con validazione e anti-duplicati
scripts/dataset_report.py    -> report sullo stato del dataset (usato anche dalla CI)
scripts/migrate_firestore.py -> migrazione una tantum dei dati esistenti al modello nuovo
handlers/daily_job.py        -> job di mezzanotte in-process: broadcast, reset, e fallback di generazione
handlers/admin_handler.py    -> tutti i comandi Telegram /admin_* (al posto di una dashboard web)
```

### Come viene scelto il calciatore del giorno

1. Ogni notte (23:15 UTC) **GitHub Actions** esegue `scripts/generate_content.py`, che scrive
   direttamente su Firestore i prossimi `buffer_days_ahead` giorni mancanti (default 3): così la
   sfida di oggi non dipende dal fatto che il server Render sia sveglio esattamente a mezzanotte.
2. Il calciatore viene scelto **escludendo** quelli usati negli ultimi `history_days_no_repeat`
   giorni (default 60), tra i soli giocatori con `verified: true` e un percorso di almeno
   `min_teams_in_career` squadre (default 2) — niente percorsi banali o dati incompleti.
3. La difficoltà ruota secondo `difficulty_rotation` in `data/config.json`; se per quella
   difficoltà non ci sono candidati liberi, si prova la difficoltà più vicina.
4. La scelta è **deterministica per data** (seed = data): se la generazione va rieseguita per
   errore, il giocatore scelto per un giorno già passato resta lo stesso.
5. Se anche GitHub Actions non fosse eseguita, `/show` e `/guess` generano la sfida del giorno
   al primo utilizzo (fallback "esecuzione alla prima richiesta").
6. Alla mezzanotte italiana, lo scheduler interno (`handlers/daily_job.py`) fa comunque un
   controllo di generazione, invia il broadcast agli utenti iscritti, assegna i trofei degli
   eventi conclusi e - il primo del mese - chiude la stagione mensile. **Non azzera nessun
   contatore**: i tentativi giornalieri si azzerano da soli (vedi [Database](#database)).

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

Calcolata in `services/difficulty.py`. Il fattore dominante è la **notorietà** del calciatore
(`popularity` 1-5): un percorso lungo di un giocatore famosissimo resta facile da indovinare,
mentre poche tappe in campionati poco seguiti sono difficili. Gli altri fattori pesano come
modificatori e sono normalizzati sulla lunghezza della carriera (quota di tappe fuori dai
"top 5" europei, numero di paesi oltre i primi due, squadre oltre le prime quattro), così il
punteggio non cresce solo perché un calciatore ha cambiato molte squadre.

Pesi e soglie sono in `data/config.json` (`difficulty_weights`, `difficulty_thresholds`) e si
possono ritarare senza toccare il codice: `python scripts/dataset_report.py` mostra come si
distribuisce il dataset fra le quattro fasce. I punti assegnati per difficoltà sono invariati
rispetto al gioco esistente (1/2/3/4).

## Comandi amministrativi

Riservati agli ID Telegram elencati in `ADMIN_TELEGRAM_IDS` (env var, separati da virgola).
Non c'è (e non serve) una dashboard web: tutto passa dalla chat.

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

### Schema di una scheda

```json
{
  "id": "maldini",
  "full_name": "Paolo Maldini",
  "aliases": ["maldini", "paolo maldini"],
  "nationality": "Italia",
  "position": "Difensore",
  "birth_year": 1968,
  "popularity": 4,
  "verified": true,
  "one_club_career": true,
  "career": [
    {"team": "Milan", "country": "Italia", "league": "Serie A", "start_year": 1985, "end_year": 2009}
  ]
}
```

`one_club_career: true` serve a distinguere una **bandiera** (Totti, Maldini, Puyol: una sola
squadra e i dati sono completi) da una **scheda incompleta**: senza questo flag un percorso
di una squadra sola viene scartato come dato mancante. È anche ciò che rende possibile
l'evento "Un amore, una maglia".

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

## Deploy gratuito

**Perché questa combinazione**: il bot è un servizio Python a webhook con scheduler interno,
non un frontend statico — GitHub Pages/Cloudflare Pages non si applicano. Serve un host che
tenga vivo un processo Python; la generazione dei contenuti però *non* richiede che quel
processo sia sveglio, quindi la spostiamo su un cron esterno gratuito e affidabile.

| Componente | Dove | Perché |
|---|---|---|
| Bot (webhook + scheduler) | **Render** (free web service) | Gira FastAPI/uvicorn così com'è, HTTPS incluso, deploy automatico da GitHub |
| Generazione giornaliera/eventi | **GitHub Actions** (cron) | Gratuito, non dipende dal fatto che Render sia "sveglio", esegue lo script direttamente su Firestore |
| Database | **Firebase Firestore** | Già in uso, nessuna migrazione necessaria |

### 1. Render (bot)

1. Crea un nuovo *Web Service* da questo repository GitHub.
2. Build command: `pip install -r requirements.txt`
3. Start command: `uvicorn bot:app --host 0.0.0.0 --port $PORT`
4. Variabili d'ambiente da impostare su Render:
   - `BOT_TOKEN`
   - `WEBHOOK_URL` (es. `https://<nome-servizio>.onrender.com/webhook`)
   - `ADMIN_TELEGRAM_IDS`
   - `FIREBASE_CREDENTIALS_PATH=firebase-key.json`
   - Carica il contenuto del service account Firebase come *Secret File* chiamato `firebase-key.json` (Render → Environment → Secret Files)
5. Il piano free di Render va in sleep dopo ~15 minuti di inattività: la prima richiesta dopo lo
   sleep sarà più lenta, ma **la scelta del giocatore del giorno non ne risente** perché è già
   stata generata in anticipo da GitHub Actions.

### 2. GitHub Actions (generazione contenuti)

Aggiungi questi *repository secrets* (Settings → Secrets and variables → Actions):

- `FIREBASE_CREDENTIALS_JSON` — l'intero contenuto del file JSON del service account Firebase
- `BOT_PING_URL` *(opzionale)* — es. `https://<nome-servizio>.onrender.com/ping`, per svegliare
  il servizio Render subito dopo la generazione

Il workflow [`daily-generation.yml`](.github/workflows/daily-generation.yml) gira ogni notte
alle 23:15 UTC (dopo la mezzanotte italiana sia in ora solare che legale) e può anche essere
lanciato a mano da GitHub → Actions → "Generazione automatica giornaliera" → Run workflow.

### 3. Dominio personalizzato

Sia Render che Cloudflare (come proxy DNS gratuito davanti a Render) supportano domini
personalizzati gratuitamente; non necessario per il funzionamento del bot.

## Limiti noti / cosa resta da fare

- **Dataset**: 161 calciatori, 144 selezionabili (oltre 140 giorni senza ripetizioni). 17
  schede sono `verified: false` e aspettano un controllo sulle date (`/admin_review`): sono
  soprattutto carriere lunghissime piene di prestiti (Vieri, Anelka, Crespo, Veron,
  Materazzi, Kvaratskhelia), dove il rischio di sbagliare un anno è alto. Il pool va
  comunque ampliato periodicamente: il segnale è l'avviso di `/admin_pool`.
- **Eventi "coppie padre/figlio"**: restano manuali per scelta, perché non esiste un dataset
  di immagini di coppie. La creazione però non richiede più di scrivere documenti su
  Firestore a mano: si fa da Telegram con `/admin_fs_add` + `/admin_event_create`.
- **Nessuna interfaccia web di amministrazione**: la gestione è tramite comandi Telegram
  (`/admin_*`), che ora coprono anche statistiche utenti, salute del dataset, anteprima delle
  sfide generate e creazione manuale degli eventi. Restano fuori le viste storiche e i
  grafici, che avrebbero senso solo con una dashboard vera.
- **Render free tier**: il servizio va in sleep se inattivo; il ping opzionale da GitHub
  Actions lo risveglia una volta al giorno, ma un utente che scrive al bot durante un lungo
  periodo di inattività può avere qualche secondo di latenza sulla prima risposta.
- **Database**: gli interventi della revisione sono stati applicati al codice, ma la
  **migrazione dei dati esistenti va eseguita a mano** (`scripts/migrate_firestore.py`) e le
  regole/indici vanno deployati. Restano da fare un export ricorrente di backup e una pulizia
  dei `daily_path` più vecchi di un anno: dettagli in
  [`docs/firebase_review.md`](docs/firebase_review.md).
