# Prestazioni della mini app

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
