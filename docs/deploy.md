# Deploy

Il bot gira su **Cloud Run** (container, deploy manuale) e la generazione giornaliera dei
contenuti è affidata a **Cloud Scheduler**, che chiama un endpoint interno del servizio invece
di dipendere da un processo sempre acceso o da un cron esterno tipo GitHub Actions.

| Componente | Dove | Perché |
|---|---|---|
| Bot (webhook) | **Cloud Run** | Container da [`Dockerfile`](../Dockerfile), scala a zero quando inattivo, HTTPS incluso |
| Generazione giornaliera/eventi | **Cloud Scheduler** → `POST /internal/daily-job` | Non dipende dal fatto che l'istanza Cloud Run sia già sveglia; Cloud Run la avvia al bisogno |
| Database | **Firebase Firestore** | Nessun deploy separato, tranne regole/indici quando cambiano |

Servizio attuale: `https://guess-the-player-595902172561.europe-west1.run.app`

## 1. Cloud Run (bot)

Build e deploy manuale dell'immagine da [`Dockerfile`](../Dockerfile):

```bash
gcloud run deploy guess-the-player \
  --source . \
  --region europe-west1 \
  --allow-unauthenticated
```

Da ripetere ogni volta che c'è codice nuovo da rilasciare: non c'è nessun trigger automatico
collegato al push su GitHub, il deploy parte solo lanciando questo comando.

### Variabili d'ambiente / secret sul servizio

| Nome | Cosa |
|---|---|
| `BOT_TOKEN` | Token del bot Telegram (da @BotFather) |
| `WEBHOOK_URL` | URL pubblico completo del webhook, es. `https://guess-the-player-595902172561.europe-west1.run.app/webhook` |
| `ADMIN_TELEGRAM_IDS` | ID Telegram abilitati ai comandi `/admin_*`, separati da virgola |
| `GENERATION_SECRET` | Segreto condiviso con Cloud Scheduler: autorizza le chiamate a `/internal/daily-job` |
| `FIREBASE_CREDENTIALS_PATH` | `firebase-key.json`, montato come secret di Secret Manager |

Se cambia l'URL del servizio (es. nuova region o nuovo nome), va aggiornato `WEBHOOK_URL`: il
bot rifà `set_webhook` automaticamente al riavvio (`bot.py`, funzione `lifespan`), non serve
nessuna azione manuale su Telegram.

## 2. Cloud Scheduler (generazione contenuti)

Un job HTTP chiama ogni notte l'endpoint interno con l'header di autorizzazione:

```bash
gcloud scheduler jobs create http daily-generation \
  --schedule="15 23 * * *" \
  --uri="https://guess-the-player-595902172561.europe-west1.run.app/internal/daily-job" \
  --http-method=POST \
  --headers="x-cron-secret=<GENERATION_SECRET>" \
  --time-zone="UTC"
```

L'orario (23:15 UTC) è poco dopo mezzanotte a Roma sia in ora solare che legale.

Cosa fa la chiamata (`bot.py` → `@app.post("/internal/daily-job")` → `handlers/daily_job.py`,
`update_daily_challenge()`):

1. verifica l'header `x-cron-secret` contro `GENERATION_SECRET`, rifiuta con `403` se manca o
   è sbagliato;
2. genera i prossimi `buffer_days_ahead` giorni mancanti (default 3, vedi `data/config.json`)
   e, se le regole di rotazione lo consentono, un nuovo evento tematico;
3. invia il broadcast agli utenti iscritti, assegna i trofei degli eventi conclusi e - il
   primo del mese - chiude la stagione mensile;
4. **non azzera nessun contatore**: i tentativi giornalieri si azzerano da soli perché ogni
   documento utente porta il giorno a cui si riferisce (`last_played_day`).

Se Cloud Scheduler non dovesse partire per qualche motivo, `/show` e `/guess` generano
comunque la sfida del giorno al primo utilizzo (fallback "esecuzione alla prima richiesta" in
`services/daily_generator.py`), quindi il gioco non si blocca.

## 3. Generazione manuale (debug/backfill)

Per generare il buffer senza passare da Cloud Scheduler, in locale con le stesse credenziali
del bot (`.env`, `firebase-key.json`):

```bash
python scripts/generate_content.py
```

Oppure da Telegram, come admin: `/admin_regen` forza subito la generazione del buffer di
sfide/eventi mancanti.

## 4. Dominio personalizzato

Cloud Run supporta domini personalizzati e certificati gestiti gratuitamente tramite
"Custom Domains"; non necessario per il funzionamento del bot.

## Cosa NON serve più

Il progetto in passato usava Render (web service sempre acceso) + un workflow GitHub Actions
(`daily-generation.yml`) come cron esterno per svegliare la generazione dei contenuti. Con
Cloud Run + Cloud Scheduler questi due pezzi non servono più e sono stati rimossi: il workflow
CI (`.github/workflows/ci.yml`) resta invece attivo, ma serve solo per test e lint, non per il
deploy.
