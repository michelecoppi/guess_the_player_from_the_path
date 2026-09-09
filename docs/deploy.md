# Deploy

Il bot gira su **Cloud Run** (container, deploy automatico da GitHub Actions dopo i test) e la
generazione giornaliera dei contenuti è affidata a **Cloud Scheduler**, che chiama un endpoint
interno del servizio invece di dipendere da un processo sempre acceso o da un cron esterno tipo
GitHub Actions.

| Componente | Dove | Perché |
|---|---|---|
| Bot (webhook) | **Cloud Run** | Container da [`Dockerfile`](../Dockerfile), scala a zero quando inattivo, HTTPS incluso |
| Generazione giornaliera/eventi | **Cloud Scheduler** → `POST /internal/daily-job` | Non dipende dal fatto che l'istanza Cloud Run sia già sveglia; Cloud Run la avvia al bisogno |
| Database | **Firebase Firestore** | Nessun deploy separato, tranne regole/indici quando cambiano |

Servizio attuale: `https://guess-the-player-595902172561.europe-west1.run.app`

## 1. Cloud Run (bot)

### Deploy automatico (GitHub Actions)

[`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml) fa `gcloud run deploy`
automaticamente ad ogni push su `main` per cui il workflow `CI` è andato a buon fine (parte
con un trigger `workflow_run`, quindi codice che non passa i test non viene mai deployato).
L'autenticazione verso GCP usa **Workload Identity Federation** (WIF): nessuna chiave di
service account salvata come secret GitHub.

Setup una tantum (da fare una volta sola con un account che ha i permessi IAM sul progetto):

```bash
PROJECT_ID="guess-the-player-from-path-bot"
PROJECT_NUMBER="595902172561"
REPO="michelecoppi/guess_the_player_from_the_path"

# 1. Pool e provider OIDC per GitHub Actions
gcloud iam workload-identity-pools create "github-pool" \
  --project="$PROJECT_ID" --location="global" --display-name="GitHub Actions"

gcloud iam workload-identity-pools providers create-oidc "github-provider" \
  --project="$PROJECT_ID" --location="global" --workload-identity-pool="github-pool" \
  --display-name="GitHub" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository=='$REPO'" \
  --issuer-uri="https://token.actions.githubusercontent.com"

# 2. Service account dedicato al deploy, senza chiave scaricata
gcloud iam service-accounts create "github-deployer" \
  --project="$PROJECT_ID" --display-name="GitHub Actions deployer"

# 3. Il provider WIF puo' impersonare il service account, ma solo per questo repo
gcloud iam service-accounts add-iam-policy-binding \
  "github-deployer@$PROJECT_ID.iam.gserviceaccount.com" \
  --project="$PROJECT_ID" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/github-pool/attribute.repository/$REPO"

# 4. Permessi minimi per fare 'gcloud run deploy --source .' (Cloud Build compila
#    l'immagine e la carica su Artifact Registry, poi Cloud Run la esegue)
for ROLE in roles/run.admin roles/iam.serviceAccountUser roles/cloudbuild.builds.editor roles/storage.admin roles/artifactregistry.writer; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:github-deployer@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="$ROLE"
done
```

Poi, su GitHub (Settings → Secrets and variables → Actions), crea due secret nel repository:

| Secret | Valore |
|---|---|
| `WIF_PROVIDER` | `projects/595902172561/locations/global/workloadIdentityPools/github-pool/providers/github-provider` |
| `WIF_SERVICE_ACCOUNT` | `github-deployer@guess-the-player-from-path-bot.iam.gserviceaccount.com` |

Da quel momento in poi ogni push su `main` che supera la CI viene deployato da solo: non serve
più lanciare `gcloud run deploy` a mano.

### Deploy manuale (fallback/debug)

Resta comunque possibile lanciarlo a mano, ad es. per un rollback rapido o per testare una
build locale:

```bash
gcloud run deploy guess-the-player \
  --source . \
  --region europe-west1 \
  --allow-unauthenticated
```

### Variabili d'ambiente / secret sul servizio

| Nome | Cosa |
|---|---|
| `BOT_TOKEN` | Token del bot Telegram (da @BotFather) |
| `WEBHOOK_URL` | URL pubblico completo del webhook, es. `https://guess-the-player-595902172561.europe-west1.run.app/webhook` |
| `ADMIN_TELEGRAM_IDS` | ID Telegram abilitati ai comandi `/admin_*`, separati da virgola |
| `GENERATION_SECRET` | Segreto condiviso con Cloud Scheduler: autorizza le chiamate a `/internal/daily-job` |
| `FIREBASE_CREDENTIALS_PATH` | `firebase-key.json`, montato come secret di Secret Manager |
| `PUBLIC_BASE_URL` | Base pubblica del servizio **senza barra finale**, es. `https://guess-the-player-595902172561.europe-west1.run.app`. Facoltativa: serve alla mini app (`/app`); se manca, il bottone "Apri l'app" non compare |
| `BOT_USERNAME` | Username del bot **senza @**, es. `guess_the_player_bot`. Facoltativa: serve ai link di condivisione del risultato e agli inviti alle leghe; se manca, quei bottoni non compaiono |

Se cambia l'URL del servizio (es. nuova region o nuovo nome), vanno aggiornati `WEBHOOK_URL` e
`PUBLIC_BASE_URL`: il bot rifà `set_webhook` automaticamente al riavvio (`bot.py`, funzione
`lifespan`), non serve nessuna azione manuale su Telegram.

Le variabili si impostano una volta sola sul servizio e **sopravvivono ai deploy**: il workflow
[`deploy.yml`](../.github/workflows/deploy.yml) non passa `--set-env-vars`, quindi non le
sovrascrive. Per aggiungerne senza toccare quelle esistenti serve `--update-env-vars`
(`--set-env-vars` le rimpiazzerebbe tutte):

```bash
gcloud run services update guess-the-player \
  --project guess-the-player-from-path-bot \
  --region europe-west1 \
  --update-env-vars PUBLIC_BASE_URL=https://guess-the-player-595902172561.europe-west1.run.app,BOT_USERNAME=nome_del_bot
```

### Mini app: pulsante nel menu del bot

Con `PUBLIC_BASE_URL` impostata, la pagina risponde su `<PUBLIC_BASE_URL>/app`. Per averla anche
nel pulsante accanto alla graffetta: @BotFather → `/mybots` → il bot → *Bot Settings* → *Menu
Button* → *Edit menu button URL*, e incollare l'URL con `/app` in fondo. Telegram accetta solo
HTTPS, che Cloud Run fornisce già.

### Termini e privacy in BotFather

Servono solo se il negozio in Stelle e' attivo, ma se e' attivo Telegram li considera
obbligatori per la vendita di beni digitali. Le due pagine sono gia' servite dal bot
(`webapp/terms.html` e `webapp/privacy.html`): bastano gli URL, che dipendono da
`PUBLIC_BASE_URL`.

@BotFather -> `/mybots` -> il bot -> *Bot Settings*:

| Voce di BotFather | URL da incollare |
|---|---|
| *Terms of Service* | `<PUBLIC_BASE_URL>/terms` |
| *Privacy Policy* | `<PUBLIC_BASE_URL>/privacy` |

Con il servizio attuale:

```
https://guess-the-player-595902172561.europe-west1.run.app/terms
https://guess-the-player-595902172561.europe-west1.run.app/privacy
```

Le pagine si aprono nel browser (non dentro Telegram) e mostrano italiano, spagnolo o inglese
secondo la lingua del browser; `?lang=it` forza una lingua, ed e' cosi' che le apre il bottone
dentro `/shop`.

**Vanno riviste quando cambia il trattamento dei dati**: elencano i campi salvati su Firestore,
la region e la durata dei backup. Se il codice cambia e loro no, descrivono un servizio che non
esiste - che e' peggio che non avere l'informativa. `tests/test_legal_pages.py` controlla solo
che le tre lingue restino allineate, non che dicano il vero.

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

## 3. Backup settimanale del database

[`.github/workflows/backup.yml`](../.github/workflows/backup.yml) esegue
`scripts/backup_firestore.py` ogni lunedì alle 03:30 UTC e archivia il JSON come artifact del
workflow (365 giorni di conservazione). Si può lanciare anche a mano da GitHub → Actions →
*Backup Firestore* → *Run workflow*, ad esempio prima di una modifica ai dati.

Si autentica con la **stessa Workload Identity Federation del deploy** (`WIF_PROVIDER` /
`WIF_SERVICE_ACCOUNT`): nessuna chiave di service account nei secret. Perché funzioni, al
service account del deploy va aggiunto **una volta sola** il permesso di leggere Firestore —
i ruoli elencati al punto 1 servono a fare il deploy, non a leggere il database:

```bash
gcloud projects add-iam-policy-binding guess-the-player-from-path-bot \
  --member="serviceAccount:github-deployer@guess-the-player-from-path-bot.iam.gserviceaccount.com" \
  --role="roles/datastore.viewer"
```

`roles/datastore.viewer` è **sola lettura**: il workflow non può modificare né cancellare
niente, che è esattamente quello che deve poter fare un backup.

Per verificare quali ruoli ha adesso quel service account:

```bash
gcloud projects get-iam-policy guess-the-player-from-path-bot \
  --flatten="bindings[].members" \
  --filter="bindings.members:github-deployer@guess-the-player-from-path-bot.iam.gserviceaccount.com" \
  --format="table(bindings.role)"
```

Senza questo ruolo il workflow fallisce con un errore di permessi al primo lunedì utile: il
codice è a posto, manca solo l'autorizzazione.

In locale invece lo script usa il `firebase-key.json` come tutto il resto:

```bash
python scripts/backup_firestore.py
```

La pulizia dello storico (`scripts/cleanup_daily_paths.py`) resta **manuale di proposito**: una
cancellazione ricorrente che nessuno guarda, su una collezione che contiene le soluzioni, è il
tipo di automatismo che si scopre rotto tardi.

## 4. Generazione manuale (debug/backfill)

Per generare il buffer senza passare da Cloud Scheduler, in locale con le stesse credenziali
del bot (`.env`, `firebase-key.json`):

```bash
python scripts/generate_content.py
```

Oppure da Telegram, come admin: `/admin_regen` forza subito la generazione del buffer di
sfide/eventi mancanti.

## 5. Dominio personalizzato

Cloud Run supporta domini personalizzati e certificati gestiti gratuitamente tramite
"Custom Domains"; non necessario per il funzionamento del bot.

## Cosa NON serve più

Il progetto in passato usava Render (web service sempre acceso) + un workflow GitHub Actions
(`daily-generation.yml`) come cron esterno per svegliare la generazione dei contenuti. Con
Cloud Run + Cloud Scheduler questi due pezzi non servono più e sono stati rimossi: restano
invece attivi `.github/workflows/ci.yml` (test e lint), `.github/workflows/deploy.yml`
(deploy automatico su Cloud Run dopo che la CI passa su `main`, vedi sopra) e
`.github/workflows/backup.yml` (export settimanale del database, punto 3).
