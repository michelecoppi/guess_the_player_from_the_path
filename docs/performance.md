# Prestazioni

Documento primario per le prestazioni del servizio: cosa si misura, la baseline di
produzione, i budget, come si riproduce il report e quali ottimizzazioni sono state fatte
(o scartate) **sulla base di quali dati**. Introdotto da
[#32](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/32); i log su cui
poggia sono quelli di [observability.md](observability.md) (#18).

La regola del progetto: prima si misura, poi si ottimizza. Un'ottimizzazione entra solo se
la sezione [Decisioni](#decisioni-di-ottimizzazione) può citare il dato che la giustifica.

## Cosa si misura

Tutto finisce in record strutturati su Cloud Logging (nessun sistema di metriche in più);
il codice sta in [`services/performance.py`](../services/performance.py).

| Misura | Dove nasce | Record / campo |
| --- | --- | --- |
| Latenza di ogni richiesta API/interna | middleware in `apps/api/observe.py` | `api.request.completed`: `route`, `status_code`, `duration_ms` |
| Cold start | prima richiesta servita da un processo | `cold_start: true` sullo stesso record (assente sulle richieste calde) |
| Fasi di avvio del container | lifespan FastAPI | `app.startup.completed`: `before_lifespan_ms` (età del processo quando parte il lifespan: interprete, import, setup a livello di modulo; da `/proc`, quindi solo su Linux), `lifespan_ms` (inizializzazione Telegram, webhook, comandi), `startup_ms` |
| Letture/scritture Firestore per richiesta | wrapper sui metodi GAPIC del client Firestore | `firestore_reads`, `firestore_gets`, `firestore_queries`, `firestore_writes`, `firestore_ms` su `api.request.completed`; header `Server-Timing: app;dur=…, fs;dur=…;desc="reads=N"` |
| Query lente | stesso wrapper | `firestore.query.slow` (WARNING) oltre 500 ms: `kind`, `collection` (solo il nome della collection, mai un path con id), `documents`, `duration_ms` |
| Durata degli handler Telegram | worker `/internal/telegram-update` | `telegram.update.completed`: `duration_ms` del solo `process_update`, con `command`/`update_type`/`handler` già legati e l'uso di Firestore dell'update |
| Avvio della Mini App sul telefono | legacy `webapp/index.html` + `webapp/client.js`, V2 `webapp/src/telemetry/startup.ts` | `POST /app/api/perf` → `miniapp.startup.measured`: `app` (`legacy`/`v2`), `outcome`, `ttfb_ms`, `dom_ready_ms`, `first_data_ms`, `api_me_ms`, `api_me_server_ms`, `transfer_kb` |
| Superamento dei budget | middleware | `performance.budget.exceeded` (WARNING): `route`, `metric` (`latency_ms` \| `firestore_reads`), `value`, `budget` |

Note sul conteggio Firestore:

- Le letture seguono la fatturazione abbastanza da confrontare richieste fra loro: una per
  documento restituito da una get o da una query, almeno una per query o aggregazione anche
  se vuota. È una stima, non una fattura.
- Si conta solo dentro un blocco `performance.track()` (una richiesta HTTP). Admin, script e
  test senza blocco non contano niente. Il lavoro spostato in thread (`run_in_threadpool`,
  `asyncio.to_thread`) si somma alla stessa richiesta perché il contesto viene copiato.
- `tests/test_performance.py` verifica i contatori sia su un client finto sia sull'SDK vero
  contro l'emulatore: se un aggiornamento della libreria smettesse di passare dai metodi
  avvolti, il test fallirebbe invece di riportare zero.

Il beacon della Mini App (`/app/api/perf`) richiede la firma di `initData` e passa dal token
bucket, ma **non legge il documento utente**: una misura non costa letture. Il server tiene
solo le chiavi numeriche note, limitate a 0–120 000; qualunque altro campo inviato dal client
viene scartato, e nel log non finiscono id né testo. Il client lo invia una volta per
apertura, dopo il primo caricamento dei dati, senza bloccare l'interfaccia; nella V2 non
parte con il mock di sviluppo.

## Baseline

Baseline di produzione del **2026-09-07 → 2026-09-16** (tutto il traffico disponibile nei
log al momento della misura), salvata in
[`performance-baselines/2026-09-16.json`](performance-baselines/2026-09-16.json) e
riproducibile con il [report](#report-baseline-e-trend). Il traffico è basso: i percentili
alti di rotte con pochi campioni vanno letti come ordini di grandezza.

**Latenza all'edge di Cloud Run** (log `run.googleapis.com/requests`, include il cold start;
"cold" è la prima richiesta vista per ogni istanza):

| Richiesta | n | p50 ms | p95 ms | cold | p95 caldo ms |
| --- | --- | --- | --- | --- | --- |
| `POST /webhook` | 229 | 200 | 6681 | 37 (16%) | 625 |
| `POST /app/api/arena` | 151 | 158 | 385 | 0 | 385 |
| `POST /internal/telegram-update` | 124 | 662 | 1290 | 0 | 1290 |
| `GET /app` (apertura Mini App) | 112 | 6 | 6357 | 35 (31%) | 16 |
| `POST /app/api/me` | 110 | 288 | 763 | 0 | 763 |
| `POST /app/api/calendar` | 60 | 141 | 379 | 1 | 379 |
| `POST /app/api/shop` | 43 | 96 | 150 | 0 | 150 |
| `POST /app/api/guess` | 16 | 287 | 838 | 0 | 838 |
| `POST /internal/daily-job` | 10 | 4844 | 8285 | 7 | 1280 |
| `POST /internal/broadcast` | 7 | 2715 | 2863 | 0 | 2863 |

Nel periodo: 95 istanze avviate su 1449 richieste; la prima richiesta di un'istanza ha p50
**5,3 s** e p95 7,5 s, le richieste calde p50 102 ms e p95 764 ms, e **nessuna** richiesta
calda ha superato i 3 s.

**Cold start del container** (righe di sistema `Starting new instance` e di uvicorn
`Waiting for application startup.` / `Application startup complete.`, 30 avvii):

| Fase | p50 ms | p95 ms |
| --- | --- | --- |
| Avvio istanza → applicazione importata | 4516 | 6596 |
| Lifespan (Telegram `initialize`, `setWebhook`, comandi, pulsante menu) | 300 | 811 |
| Totale | 4836 | 7039 |

**Import di `bot.py` in locale** (`python -X importtime`, Windows, CPU desktop): 1,45 s in
totale; il corpo di `bot.py` pesa 329 ms, di cui ~300 ms in `ApplicationBuilder().build()`,
che crea due client HTTP e carica due volte il bundle dei certificati CA (~150 ms ciascuno).
Firestore/gRPC ~290 ms, `telegram` ~270 ms, `fastapi` ~220 ms.

**Letture Firestore misurate** (emulatore, caso peggiore consentito dal prodotto):
`/app/api/me` completo = **118** letture (utente, feature flags, sfida del giorno, top 10,
5 leghe × (lega + 20 membri)); refresh leggero = **3**. Le letture di produzione per rotta
arriveranno con i nuovi campi `firestore_*` e aggiorneranno la baseline.

Cosa ancora non c'è nella baseline, perché i record che la producono nascono con #32:
letture Firestore di produzione, durata per comando Telegram, fasi di avvio lato
applicazione e avvio della Mini App sul telefono. Il prossimo report dopo il deploy le
conterrà.

## Budget

Soglie in [`services/performance.py`](../services/performance.py). Una richiesta **calda** che
supera il budget di latenza, o una richiesta qualsiasi che supera il budget di letture, genera
`performance.budget.exceeded`. Il cold start non viene giudicato sulla latenza: si misura a
parte.

| Rotta | Latenza (ms) | Letture |
| --- | --- | --- |
| `/webhook` | 1000 | – |
| `/internal/telegram-update` | 2500 | – |
| `/app/api/me` | 1200 | 120 |
| `/app/api/guess` | 1500 | – |
| `/app/api/hint` | 1000 | – |
| `/app/api/card` | 2000 | – |
| `/app/api/shop/buy` | 1500 | – |
| `/app/api/perf` | 300 | 0 |
| altre `/app/api/*` | 1000 | – |
| `/internal/daily-job` | 20000 | – |
| `/internal/broadcast`, `/internal/monthly-close` | 10000 | – |

- Le latenze partono dal p95 caldo della baseline con margine: superarle vuol dire "più lento
  di quanto sia mai stato normalmente", non "lento".
- I budget di letture esistono **solo per rotte misurate**: le letture sono deterministiche
  per un percorso di codice e una forma dei dati, quindi un budget indovinato o grida al lupo
  o nasconde una regressione. `/app/api/me` è fissato sul caso peggiore misurato, e
  `test_profile_read_cost_stays_within_its_budget` fallisce se il costo cambia. Per aggiungere
  una rotta: misurarne il caso peggiore sull'emulatore con lo stesso schema, poi il budget.

## Report: baseline e trend

[`tools/perf_report.py`](../tools/perf_report.py) legge Cloud Logging (sola lettura, serve
`roles/logging.viewer`) e produce le tabelle sopra: latenza all'edge con cold start separati,
fasi del container, rotte applicative con budget e letture Firestore, handler Telegram, avvio
della Mini App, budget superati.

```bash
# ultimi 7 giorni, direttamente da Cloud Logging
python -m tools.dev perf-report --fetch --days 7

# salvare un'istantanea (nuova baseline) e confrontare una misura successiva (trend)
python -m tools.dev perf-report --fetch --days 30 --save docs/performance-baselines/AAAA-MM-GG.json
python -m tools.dev perf-report --fetch --days 7 --compare docs/performance-baselines/2026-09-16.json

# da un export già scaricato, o per vedere il filtro usato
python -m tools.dev perf-report --input logs.json
python -m tools.dev perf-report --print-filter
```

Il trend si legge confrontando istantanee: la sezione `Trend vs …` riporta p50/p95 prima,
adesso e variazione percentuale per ogni metrica presente in entrambe. Salvare una nuova
istantanea in `docs/performance-baselines/` dopo un'ottimizzazione o un cambio di traffico
significativo, citandola nella decisione corrispondente.

Per grafici continui in Cloud Monitoring si possono creare metriche basate sui log (non sono
definite in questo repository; crearle è un'operazione sul progetto GCP):

```yaml
# gtp_request_latency.yaml
name: gtp_request_latency
description: Warm request latency by route (#32)
filter: jsonPayload.event="api.request.completed" AND NOT jsonPayload.cold_start=true
valueExtractor: EXTRACT(jsonPayload.duration_ms)
labelExtractors:
  route: EXTRACT(jsonPayload.route)
metricDescriptor:
  metricKind: DELTA
  valueType: DISTRIBUTION
  unit: ms
  labels:
    - key: route
      valueType: STRING
bucketOptions:
  exponentialBuckets: {numFiniteBuckets: 30, growthFactor: 1.4, scale: 5}
```

```bash
gcloud logging metrics create gtp_request_latency --project guess-the-player-from-path-bot --config-from-file=gtp_request_latency.yaml
gcloud logging metrics create gtp_budget_exceeded --project guess-the-player-from-path-bot --description="Performance budget exceeded (#32)" --log-filter='jsonPayload.event="performance.budget.exceeded"'
```

Query utili in Logs Explorer:

```text
jsonPayload.event="api.request.completed" AND jsonPayload.cold_start=true
jsonPayload.event="performance.budget.exceeded"
jsonPayload.event="telegram.update.completed" AND jsonPayload.duration_ms>1500
jsonPayload.event="api.request.completed" AND jsonPayload.firestore_reads>50
jsonPayload.event="miniapp.startup.measured"
jsonPayload.event="app.startup.completed"
```

## Decisioni di ottimizzazione

Registro delle ottimizzazioni valutate: il dato, la decisione, e cosa servirebbe per
riaprirla. Aggiungere una riga per ogni nuova valutazione.

| # | Candidato | Dato | Decisione |
| --- | --- | --- | --- |
| 1 | **Cold start** | Primo accesso a un'istanza p50 5,3 s / p95 7,5 s contro p95 caldo 764 ms; colpisce il 31% delle aperture della Mini App e il 16% dei webhook. 4,5 s su ~4,8 s sono prima che l'applicazione sia importata | È il collo di bottiglia principale. Misurato, affrontato con le righe 2–3 e 4 |
| 2 | Secondo client HTTP di PTB (`get_updates_request`) | `ApplicationBuilder().build()` 298 ms → 149 ms (tre misure identiche): il bot usa il webhook e non chiama mai `getUpdates`, ma PTB costruiva comunque un secondo `httpx.AsyncClient` e ricaricava i certificati CA | **Fatto** (#32): un solo `HTTPXRequest` per entrambi. `test_telegram_client_is_shared_between_api_calls_and_get_updates` lo verifica. L'effetto in produzione si leggerà in `before_lifespan_ms` |
| 3 | Rimandare `setWebhook`/comandi/pulsante menu dopo l'avvio | Lifespan p50 300 ms, p95 811 ms (6% del cold start) | **Non fatto**: guadagno piccolo, e rimandare la registrazione del webhook introduce una finestra in cui l'istanza risponde prima di essere configurata. Riaprire se `lifespan_ms` supera stabilmente 1 s |
| 4 | Istanza minima sempre calda (`--min-instances 1`) | Eliminerebbe quasi tutti i 95 cold start del periodo (restano quelli oltre la prima istanza e dei deploy). Costo stimato: un'istanza inattiva da 1 vCPU/512 MiB fatturata a tariffa idle, nell'ordine di 10 $/mese in europe-west1 | **Decisione del maintainer** (è un costo ricorrente, non codice): è l'intervento con l'effetto più grande sul p95 percepito. Si applica con `gcloud run services update guess-the-player --min-instances 1` (sopravvive ai deploy, vedi [deploy.md](deploy.md)). `startup-cpu-boost` è già attivo |
| 5 | Lazy import dei moduli pesanti (Firestore/gRPC, Pillow, handler admin) | Import locale 1,45 s; quanto pesi su Cloud Run non è ancora noto | **Rimandato**: serve `before_lifespan_ms` di produzione per sapere quanto dei 4,5 s è import Python e quanto avvio della sandbox. Cambierebbe l'ordine di import di tutto `bot.py` |
| 6 | Letture di `/app/api/me` (leghe lette in sequenza, 2 RPC per lega) | Caso peggiore 118 letture / 6 query; p50 di produzione 288 ms, p95 763 ms, sotto budget | **Non fatto**: nessuna evidenza che le leghe siano la parte lenta. Riaprire se `firestore_ms` di `/app/api/me` supera metà di `duration_ms` al p95 |
| 7 | Cache, snapshot della classifica, payload daily precomputato, compressione asset | Richieste calde tutte sotto 3 s; asset statici p95 ≤ 36 ms con ETag/304; broadcast e daily job sono batch fuori dal percorso utente | **Non fatto**: nessun dato li giustifica oggi |

## Scelte di progetto già in essere

Gli handler Telegram spostano le operazioni Firestore sincrone e i servizi che le
incapsulano in `asyncio.to_thread`, inclusa la generazione delle immagini. Il webhook
autenticato accoda su Cloud Tasks e conferma 200 dopo la scrittura durabile; il worker
elabora l'update durante una propria richiesta HTTP. Questo funziona anche con CPU
Cloud Run assegnata solo durante le richieste e istanze che si spengono.

Le ricevute Firestore impediscono il replay di update conclusi e serializzano il lavoro
per utente tra istanze. Un'interruzione dopo l'inizio può aver già consumato il tentativo:
alla scadenza del lease viene registrato `uncertain`, senza riesecuzione automatica.
Questi casi richiedono riconciliazione dai log e dallo storico. Non è una garanzia di
consegna esattamente una volta: Firestore e Telegram non condividono una transazione.

Il job giornaliero salva il payload prima di accodare il broadcast. Reset mensile e
broadcast procedono a pagine di 100 documenti: nessuna richiesta invia a tutti gli utenti.
Il podio mensile viene congelato prima del primo reset; ogni reset utente è transazionale
e conserva i punti maturati nel nuovo mese. La lettura iniziale del podio scorre ancora
gli utenti con punti mensili, quindi il costo di preparazione resta O(N).

Le API applicano un token bucket in memoria dopo la firma e prima di Firestore:
30 token iniziali, ricarica di 1 token ogni 2 secondi; card costa 6, ricerca 2, le altre
richieste 1. Il rifiuto restituisce 429 e `Retry-After`. Il bucket è protetto da lock e
mantiene al massimo 10.000 utenti con espulsione LRU. I limiti valgono per processo:
repliche, riavvii ed espulsioni rinnovano il budget. Per un tetto globale servirebbe
uno store condiviso; impostare anche un massimo di istanze Cloud Run.

HTML, CSS legale e modulo client hanno ETag SHA-256 e
`Cache-Control: public, max-age=0, must-revalidate`: l'apertura successiva rivalida e
riceve 304 senza corpo quando il contenuto è invariato. Gli asset della V2 hanno nomi con
hash e `Cache-Control: public, max-age=31536000, immutable`. `webapp/client.js` contiene
escape HTML, iniziali, merge del profilo e il calcolo delle metriche di avvio, verificati con
`node --test` anche in CI.

Gli endpoint che usano Firestore sincrono sono funzioni `def`: FastAPI li esegue
nel pool di thread, lasciando libero il ciclo asincrono per le altre richieste.
La creazione della fattura resta asincrona per Telegram, ma sposta la lettura
dell'utente nel pool. L'inizializzazione condivisa di Firestore usa un lock per
evitare due inizializzazioni alla prima coppia di richieste concorrenti.

`/app/api/me` riusa il documento utente appena letto per l'autenticazione.
Con `lightweight: true` restituisce profilo e sfida senza interrogare classifica
e leghe (3 letture invece di fino a 118). Il client unisce la risposta al profilo precedente
dopo errori e indizi; alla prima apertura, dopo una risposta corretta e dopo modifiche alle
leghe richiede il profilo completo. Non viene introdotta una cache dei tentativi.
Gli altri utenti possono comunque modificare le classifiche nel frattempo:
il refresh leggero conserva quelle dell'ultimo caricamento completo.

`duration_ms` e `Server-Timing` comprendono l'attesa dei worker e del database; non
comprendono la rete del telefono né l'avvio del container precedente all'arrivo
nell'applicazione, che si leggono rispettivamente in `miniapp.startup.measured` e nei cold
start qui sopra.

## Test

- [`tests/test_performance.py`](../tests/test_performance.py): contatori Firestore (client
  finto e SDK vero sull'emulatore, thread, idempotenza), query lente senza id, budget (caldo,
  cold start, rotte non misurate), fasi di avvio, beacon Mini App (firma, nessuna lettura,
  campi ammessi), campi e `Server-Timing` sulle richieste, `telegram.update.completed`,
  client HTTP condiviso, costo in letture di `/app/api/me` nel caso peggiore.
- [`tests/test_perf_report.py`](../tests/test_perf_report.py): percentili, separazione dei
  cold start, fasi del container, budget e confronto fra istantanee.
- [`tests/test_webapp_performance.py`](../tests/test_webapp_performance.py): una lettura
  Firestore bloccata non blocca `/ping`, `/me` legge l'utente una volta sola.
- `tests/frontend/startup-timing.test.ts` e `tests/client.test.cjs`: metriche di avvio
  derivate dalla timeline di Performance, un solo invio per apertura, nessun errore visibile.
