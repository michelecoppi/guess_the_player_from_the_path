# Webhook, code e retry

## Configurazione prima del deploy

Il nuovo processo rifiuta l'avvio se mancano `WEBHOOK_SECRET`, `TASK_SECRET`,
`TASKS_QUEUE`, `BROADCAST_QUEUE` o `PUBLIC_BASE_URL`. È intenzionale: non c'è un
ripiego su webhook aperto o su una coda volatile. Configurare l'infrastruttura prima
di pubblicare questa revisione. Non sono state modificate risorse cloud dal codice locale.

Generare due segreti distinti una sola volta con
`python -c "import secrets; print(secrets.token_urlsafe(48))"`, salvarli in Secret Manager
e montarli come variabili `WEBHOOK_SECRET` e `TASK_SECRET` su Cloud Run. Devono restare
identici tra repliche. Non salvarli nel repository. `GENERATION_SECRET` continua a
proteggere esclusivamente il trigger Cloud Scheduler.

Creare le due code nella stessa regione del servizio (esempio bash):

```bash
PROJECT_ID="guess-the-player-from-path-bot"
REGION="europe-west1"
gcloud services enable cloudtasks.googleapis.com --project="$PROJECT_ID"
gcloud tasks queues create telegram-updates --project="$PROJECT_ID" --location="$REGION" \
  --max-concurrent-dispatches=16 --max-dispatches-per-second=20 \
  --min-backoff=2s --max-backoff=300s --max-attempts=100
gcloud tasks queues create daily-broadcast --project="$PROJECT_ID" --location="$REGION" \
  --max-concurrent-dispatches=1 --max-dispatches-per-second=1 \
  --min-backoff=30s --max-backoff=300s --max-attempts=100
```

Se le code esistono già, usare `gcloud tasks queues update` con gli stessi parametri.
La concorrenza 1 sulla coda broadcast mantiene gli invii a circa 20/s (pausa 0,05s
più latenza Telegram), lasciando margine per le risposte del bot.

Autorizzare l'identità ADC del container con `roles/cloudtasks.enqueuer` sulle due
code. Cloud Tasks usa ADC; può essere un'identità diversa dalla chiave Firebase
montata in `FIREBASE_CREDENTIALS_PATH`. Il worker richiede `X-Task-Secret`, non si
fida degli header dichiarativi `X-CloudTasks-*`.

Impostare:

```text
TASKS_QUEUE=projects/guess-the-player-from-path-bot/locations/europe-west1/queues/telegram-updates
BROADCAST_QUEUE=projects/guess-the-player-from-path-bot/locations/europe-west1/queues/daily-broadcast
PUBLIC_BASE_URL=https://guess-the-player-595902172561.europe-west1.run.app
```

Il servizio resta pubblicamente raggiungibile per Telegram e la mini app. Gli endpoint
worker sono protetti dal loro segreto. Impostare il timeout Cloud Run almeno a 180s e
un numero massimo di istanze adeguato al budget. Non è necessario abilitare CPU sempre
assegnata: il lavoro rimane dentro le richieste worker. I task hanno deadline 180s;
il worker Telegram limita l'elaborazione a 150s e i lease durano 240s.

Il webhook restituisce 403 prima di leggere il JSON per un segreto assente/errato,
400 per un update malformato e 200 solo dopo che Cloud Tasks ha accettato il task
(o riconosciuto il suo nome già esistente). Errori di accodamento restano errori HTTP,
così Telegram può ritentare. Il nome è un hash deterministico di `update_id`.

## Stato e recupero

- `work_receipts/telegram-{update_id}` conserva l'esito dell'elaborazione.
- `update_locks/{user_id}` serializza gli update dello stesso utente tra repliche.
- `daily_jobs/{YYYY-MM-DD}` conserva il payload immutabile del broadcast.
- `monthly_closures/{YYYY-MM}` conserva il podio prima di modificare i contatori.
- `work_receipts/notify-{giorno}-{utente}` protegge ciascun invio; dopo il successo
  viene aggiornato anche `users/{id}.last_notification_day`.
- `daily_jobs/{YYYY-MM-DD}.sent_total` conta gli invii con un `Increment` per pagina.

Le pagine dei destinatari filtrano `notifications_enabled` **nella query**: chi ha le
notifiche spente non costa una lettura. L'indice a campo singolo automatico copre
"uguaglianza + ordine per `__name__`", quindi non serve un indice composito.

Il riepilogo agli admin lo manda l'ultima pagina del broadcast, non il trigger di
mezzanotte: fra i due ci sono N richieste separate, e il totale viene dal contatore sul
documento del giorno perche' chi chiude non ha visto le pagine precedenti. Una pagina che
fallisce conta comunque quello che e' partito (al retry le ricevute saltano quegli utenti)
e non manda nessun riepilogo.

Il retry di una pagina salta gli invii completati. Un errore Telegram `Forbidden`
disabilita le notifiche; `RetryAfter` rilascia la ricevuta e riprova tramite la coda.
Un errore di rete ambiguo lascia la ricevuta in elaborazione: dopo 240s diventa
`uncertain` e non reinvia automaticamente. Questo evita duplicati a costo di poter
saltare un messaggio quando non è possibile sapere se Telegram l'ha ricevuto.
La stessa scelta protegge i tentativi dopo un crash del worker. Non cancellare una
ricevuta incerta senza aver prima verificato lo storico e gli effetti dell'operazione.

Configurare alert Cloud Logging per `uncertain`, `manual reconciliation required`,
errori worker e task che esauriscono i retry. L'error handler PTB informa l'utente
senza promettere che il tentativo sia stato annullato e invia agli admin un riferimento.
Il messaggio all'utente e' tradotto nelle tre lingue e prende `language_code` dall'update:
una lettura a Firestore dentro il gestore che gira dopo un guasto sarebbe un secondo modo
di fallire proprio dove non si puo'.
Le eccezioni note al gestore non vengono riprodotte automaticamente.

Le ricevute hanno `delete_after` a 30 giorni: abilitare opzionalmente una policy TTL
Firestore su questo campo della collection group `work_receipts`. Senza TTL restano
valide ma crescono nel tempo. Payload giornalieri e chiusure sono documenti di audit.

Per ruotare i segreti, sospendere le code e drenare le richieste; aggiornare tutte le
revisioni serventi e la registrazione Telegram. I task già accodati contengono il
vecchio header: completarli prima della rotazione oppure ricrearli in modo controllato.
Non distribuire contemporaneamente revisioni con segreti diversi.

## Struttura del codice e verifiche

`services/repos/` separa utenti, sfide, archivio, gruppi, eventi, leghe, shop, stagioni
e amministrazione. `firebase_service` mantiene client, schema e re-export: gli import
esistenti e i punti di sostituzione usati dai test restano validi. I repository risolvono
la facciata dentro le funzioni per consentire anche import diretti senza cicli all'avvio.
`admin_pages/` separa le otto pagine e i widget condivisi; `admin_ui.py` mantiene avvio
e navigazione.

`webapp/client.js` raccoglie le funzioni della mini app che non toccano ne' il DOM ne' la
rete - quadretti del risultato, istogramma dei tentativi, conteggio del podio,
normalizzazione della lingua - ed e' l'unica parte del client che si prova senza browser
(`tests/client.test.cjs`, in CI). Il criterio per spostare qualcosa qui: stessi argomenti,
stesso risultato. Non richiede bundler: `index.html` lo carica come `<script>` e i test con
`require()`. La rotta `/app/client.js` esiste sia in `bot.py` sia in
`scripts/preview_webapp.py`: senza, la pagina si carica a meta'.

```bash
pytest -q --cov=services --cov=handlers --cov-report=term-missing --cov-fail-under=70
node --test tests/client.test.cjs
ruff check .
mypy services/
```

I test non usano il database reale. Verificare in staging la configurazione IAM,
il drain delle code e i limiti di latenza: i test locali non misurano Firestore o Telegram.

Riferimenti: [task HTTP Cloud Tasks](https://docs.cloud.google.com/tasks/docs/samples/cloud-tasks-create-http-task)
e [deduplicazione dei nomi dei task](https://docs.cloud.google.com/tasks/docs/create-tasks).
