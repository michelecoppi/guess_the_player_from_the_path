# Prestazioni della mini app

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
riceve 304 senza corpo quando il contenuto è invariato. `webapp/client.js` contiene
escape HTML, iniziali e merge del profilo, verificati con `node --test` anche in CI.

Gli endpoint che usano Firestore sincrono sono funzioni `def`: FastAPI li esegue
nel pool di thread, lasciando libero il ciclo asincrono per le altre richieste.
La creazione della fattura resta asincrona per Telegram, ma sposta la lettura
dell'utente nel pool. L'inizializzazione condivisa di Firestore usa un lock per
evitare due inizializzazioni alla prima coppia di richieste concorrenti.

`/app/api/me` riusa il documento utente appena letto per l'autenticazione.
Con `lightweight: true` restituisce profilo e sfida senza interrogare classifica
e leghe. Il client unisce la risposta al profilo precedente dopo errori e indizi;
alla prima apertura, dopo una risposta corretta e dopo modifiche alle leghe
richiede il profilo completo. Non viene introdotta una cache dei tentativi.

Il refresh leggero richiede due letture di documenti (utente e sfida), anziché
tre letture di documenti più una query di classifica e due query per ogni lega.
Gli altri utenti possono comunque modificare le classifiche nel frattempo:
il refresh leggero conserva quelle dell'ultimo caricamento completo.

Ogni risposta API include `Server-Timing: app;dur=...` in millisecondi e genera
un log `[WEBAPP]` con endpoint, stato HTTP e durata. Non registra il corpo della
richiesta, la firma Telegram o la risposta tentata. Per confrontare prima e dopo
un deploy, osservare mediana e percentile 95 per endpoint a carico comparabile.
Il tempo comprende l'attesa dei worker e del database; non comprende la rete
del telefono o l'avvio del container precedente all'arrivo nell'applicazione.

I test HTTP simulano una lettura Firestore bloccata e verificano che `/ping`
continui a rispondere, oltre a controllare che `/me` legga l'utente una sola volta.
Sono verifiche locali: il miglioramento in millisecondi e l'eventuale peso del
cold start di Cloud Run richiedono misure nell'ambiente distribuito.
