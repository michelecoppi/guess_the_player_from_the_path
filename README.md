# Guess the Player from the Path

Bot Telegram che ogni giorno propone il percorso professionale (misterioso) di un calciatore
da indovinare, con classifiche, statistiche personali, eventi tematici a tempo e trofei.

## Stack

- **Bot**: [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) su webhook, servito da **FastAPI** (`bot.py`)
- **Dati di gioco**: **Firebase Firestore** (collection `users`, `daily_path`, `events`, `seasons`)
- **Scheduler**: APScheduler in-process (mezzanotte Europe/Rome) + **GitHub Actions** come cron esterno affidabile
- **Immagini del percorso**: generate a runtime con **Pillow** (`services/path_image.py`), nessun hosting immagini esterno necessario
- **Dataset calciatori**: JSON locale versionato in `data/players.json`

## Architettura dell'automazione

```
data/players.json          -> pool di calciatori curato (carriera, nazionalità, popolarità, verified)
data/event_templates.json  -> regole configurabili per generare gli eventi a rotazione
data/config.json           -> parametri di gioco (difficoltà, buffer giorni, anti-ripetizione, ecc.)

services/player_pool.py      -> carica e valida il dataset, filtra per le regole di un evento
services/difficulty.py       -> calcola la difficoltà di un percorso (facile/normale/difficile/esperto)
services/path_image.py       -> disegna l'immagine del percorso (Pillow), nessuna immagine caricata a mano
services/daily_generator.py  -> sceglie il calciatore del giorno (con anti-ripetizione) e genera N giorni in anticipo
services/event_generator.py  -> sceglie un template evento a rotazione e lo riempie con giocatori validi

scripts/generate_content.py  -> entrypoint eseguito da GitHub Actions ogni notte
handlers/daily_job.py        -> job di mezzanotte in-process: broadcast, reset, e fallback di generazione
handlers/admin_handler.py    -> comandi Telegram /admin_status, /admin_regen, /admin_review
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
   controllo di generazione, invia il broadcast agli utenti iscritti e resetta i tentativi.

### Come vengono generati gli eventi tematici

- Ogni "tipo" di evento è descritto come **template** in `data/event_templates.json`: nome,
  descrizione, tipo di gameplay (`path`/`career`/`transfer_guess`/`father_son`), regole di
  filtro sul pool di giocatori (es. minimo 6 squadre, solo big-5, solo nazionalità sudamericane),
  durata e punti giornalieri.
- `services/event_generator.py` sceglie un template **non usato di recente** (vedi
  `event_history_no_repeat_templates`), rispetta un intervallo minimo tra un evento e l'altro
  (`event_min_gap_days`) e — se il template lo richiede — solo nel weekend (`weekend_only`).
- Un template può essere marcato `manual_only: true` (es. "Coppie leggendarie" padre/figlio, che
  richiede un dataset di immagini non ancora presente): non verrà mai generato in automatico,
  va creato a mano su Firestore finché non si aggiunge il dataset dedicato.
- Per il tipo `career` (indovina le squadre di un giocatore noto) **non** viene mai salvata
  un'immagine del percorso nei dati giornalieri, per non rivelare la risposta.

### Difficoltà

Calcolata in `services/difficulty.py` da: numero di squadre, numero di paesi diversi, tappe in
campionati non fra i "top 5" europei, popolarità del giocatore (1-5). Più alto il punteggio,
più alta la difficoltà (`easy` < `medium` < `hard` < `impossible`), con soglie configurabili in
`data/config.json`. I punti assegnati per difficoltà sono invariati rispetto al gioco esistente
(1/2/3/4).

## Comandi amministrativi

Riservati agli ID Telegram elencati in `ADMIN_TELEGRAM_IDS` (env var, separati da virgola):

- `/admin_status` — evento attivo, quanti giocatori sono esclusi dalla selezione automatica
- `/admin_regen` — forza subito la generazione del buffer di sfide/eventi mancanti
- `/admin_review` — elenco dei giocatori del dataset esclusi (dati incompleti o `verified: false`) e il motivo

## Estendere il dataset dei calciatori

Aggiungi una voce a `data/players.json` seguendo lo schema esistente. Imposta `"verified": false`
finché non hai controllato le date; un giocatore non verificato **non** entra nella selezione
automatica (vedi `/admin_review` per la lista di quelli in attesa di revisione) a meno di
impostare `auto_include_unverified_players: true` in `data/config.json`.

## Test

```bash
pip install -r requirements-dev.txt
pytest -q
```

I test coprono: selezione deterministica e anti-ripetizione del giocatore del giorno,
validazione del dataset (percorsi corti/incompleti), calcolo difficoltà, generazione eventi
(rotazione, cooldown, weekend-only, nessuna fuga di risposta per gli eventi "career"),
generazione dell'immagine del percorso, cambio di giorno/fuso orario, permessi dei comandi admin.

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

- **Dataset**: ~45 calciatori curati manualmente (dati da conoscenza pubblica, alcuni marcati
  `verified: false` da controllare). Va ampliato periodicamente per non esaurire il pool e
  ridurre le ripetizioni forzate nel lungo periodo.
- **Eventi "coppie padre/figlio"**: nessun dataset di immagini disponibile, restano da creare a
  mano finché non si aggiunge una fonte dati dedicata.
- **Render free tier**: il servizio va in sleep se inattivo; il ping opzionale da GitHub Actions
  lo risveglia una volta al giorno, ma un utente che scrive al bot durante un lungo periodo di
  inattività può avere qualche secondo di latenza sulla prima risposta.
- **Nessuna interfaccia web di amministrazione**: la gestione è tramite comandi Telegram
  (`/admin_*`), sufficiente per l'uso attuale ma senza vista storica/grafici.
