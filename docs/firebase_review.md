# Revisione del database Firestore

Analisi del modello dati e dei pattern di accesso, **e degli interventi fatti**. Le stime di
costo derivano dalle query che il codice esegue, non da metriche di produzione: non ho
accesso all'istanza Firebase reale.

Gli interventi sono stati applicati a bot fermo; i dati esistenti si portano nel nuovo
modello con [`scripts/migrate_firestore.py`](../scripts/migrate_firestore.py) (vedi
[Come migrare](#come-migrare) in fondo).

## Modello dati

| Collection | Document ID | Contenuto |
|---|---|---|
| `users` | `telegram_id` | un documento per utente, con `last_played_day` che ancora i contatori al giorno |
| `daily_path` | `YYYY-MM-DD` | una sfida al giorno, generata in anticipo |
| `events` | codice evento | descrizione dell'evento e `daily_data` per giorno (niente classifica) |
| `events/{code}/participants` | `telegram_id` | un documento per partecipante: punti, tentativi, giorno |
| `seasons` | `{anno}-{mese}` | stagioni mensili, create automaticamente quando mancano |
| `admin_settings` | `dataset_overrides` | giocatori sospesi da `/admin_block` |
| `father_son_pairs` | auto-generato | coppie padre/figlio inviate da Telegram |

Tutte le date su Firestore sono ISO `YYYY-MM-DD`; il formato italiano `gg/mm/aa` resta solo
nei messaggi agli utenti. La conversione sta in un unico posto,
[`services/dates.py`](../services/dates.py).

---

## 1. Il reset notturno scriveva su tutti gli utenti ✅ risolto

**Prima**: `reset_daily_attempts()` leggeva **tutti** i documenti di `users` e ne riscriveva
uno per uno `daily_attempts` e `has_guessed_today`, ogni notte. N letture + N scritture al
giorno anche senza nessuno che giocasse: con 5.000 utenti circa 150.000 scritture al mese di
solo azzeramento, contro le 20.000 scritture/giorno del piano gratuito. C'era anche un
problema di correttezza: se il processo su Render dormiva a mezzanotte, i tentativi del
giorno prima restavano contati.

**Adesso**: ogni documento porta `last_played_day`. Se il giorno salvato non è oggi, i
contatori valgono zero senza che nessuno li abbia azzerati:

```python
def get_user_daily_status(user_id, day_iso=None):
    data = get_user_data(user_id)
    if normalize_day(data.get("last_played_day")) != day_iso:
        return 0, False
    return data.get("daily_attempts", 0), data.get("has_guessed_today", False)
```

Costo del reset: **zero scritture**. Il job di mezzanotte non azzera più niente, quindi può
saltare o girare in ritardo senza conseguenze sul gioco del giorno dopo.

## 2. Gli utenti si cercavano per campo invece che per ID ✅ risolto

**Prima**: ogni funzione faceva `users.where("telegram_id", "==", user_id).limit(1)`; un solo
`/guess` eseguiva 4 query sullo stesso utente. E `save_user()` leggeva-poi-scriveva senza
transazione, quindi due `/start` ravvicinati creavano **due documenti** per la stessa persona.

**Adesso**: `users/{telegram_id}`. Le letture sono `get()` dirette, la creazione è una
transazione, e un `/guess` costa 1 lettura + 1 scrittura. La migrazione fonde gli eventuali
duplicati già presenti sommando punti e unendo i trofei (`merge_duplicate_users`).

## 3. Il bonus "primo che indovina" non era atomico ✅ risolto

**Prima**: controllo e assegnazione erano separati (`if not first_correct_user: ... update`),
sia per la sfida del giorno sia per l'evento. Due utenti che rispondevano nello stesso
istante prendevano entrambi il bonus.

**Adesso** una transazione decide chi lo prende:

```python
def claim_daily_first_correct(day_iso):
    @firestore.transactional
    def _claim(transaction):
        snapshot = ref.get(transaction=transaction)
        if not snapshot.exists or snapshot.to_dict().get("first_correct_user"):
            return False
        transaction.update(ref, {"first_correct_user": True})
        return True
    return _claim(db.transaction())
```

Stessa cosa per i tentativi: `begin_guess_attempt()` legge, verifica il limite e incrementa
dentro un'unica transazione, quindi due `/guess` simultanei non possono più far saltare il
conteggio.

## 4. La cache in memoria teneva stato mutabile ✅ risolto

**Prima**: `cache.py` era un dizionario globale di processo che conteneva anche
`first_correct_user`. Su Render il processo va in sleep e riparte; con due worker le due
copie divergono e il bonus viene assegnato due volte.

**Adesso**: [`services/daily_challenge.py`](../services/daily_challenge.py) tiene in memoria
**solo** la parte immutabile del giorno (percorso, risposte, difficoltà). Lo stato che cambia
si legge da Firestore e si scrive in transazione. `cache.py` è stato rimosso.

## 5. La classifica leggeva tutti gli utenti ✅ risolto

**Prima**: `get_all_users()` faceva uno `stream()` completo ad ogni `/top`: con 2.000 utenti,
2.000 letture per mostrarne 10.

**Adesso**: `order_by(...).limit(10)` per la top 10 e un `count()` lato server per la
posizione di chi resta fuori — una manciata di letture invece di N.

## 6. `events`: classifica e dati giornalieri in un solo documento ✅ risolto

**Prima**: il documento evento conteneva `daily_data` **e** `ranking` (tutti i partecipanti,
ognuno con la mappa dei tentativi per data). Tre problemi: il limite di 1 MB per documento,
la contesa in scrittura (Firestore regge circa 1 scrittura al secondo sostenuta *per
documento*, e durante un evento tutti scrivevano lo stesso), e il reset notturno che
riscriveva l'intera mappa.

**Adesso**: `events/{code}/participants/{telegram_id}`. Ogni utente scrive solo il proprio
documento, la classifica è `order_by("points", desc).limit(3)` e il reset giornaliero non
serve più (stesso meccanismo `last_played_day` del punto 1).

## 7. Il formato data `gg/mm/aa` non era ordinabile ✅ risolto

**Prima**: `'%d/%m/%y'` era usato negli id documento, nelle chiavi di `daily_data` e in
`events.dates`. Non ordinabile lessicograficamente: niente query di intervallo, e
`get_recent_player_ids()` era costretto a ordinare per `generated_at` invece che per data di
gioco. In più `'%y'` a due cifre è ambiguo oltre il 2069.

**Adesso**: ISO ovunque sul database. `get_recent_player_ids()` è diventato una query di
intervallo vera (`where("day", ">=", ...)`), gli id documento sono ordinabili e
`normalize_day()` continua a leggere i documenti nel vecchio formato, così un documento non
migrato non rompe niente.

## 8. Letture per ID mascherate da query ✅ risolto

`daily_path` si leggeva con `where("current_day", "==", ...)` pur avendo la data come id
documento; `events` con `where("code", "==", code)` pur avendo il codice come id. Adesso sono
`document(id).get()`.

## 9. Regole, indici, backup, campi sentinella ✅ risolto

- **Regole**: aggiunto [`firestore.rules`](../firestore.rules) con deny-all. Il bot usa
  l'Admin SDK, che ignora le regole; senza questo file, chiunque conosca il project id
  potrebbe leggere `users` dal client SDK.
- **Indici**: aggiunto [`firestore.indexes.json`](../firestore.indexes.json) con i due indici
  compositi necessari (il resto è coperto dagli indici automatici a campo singolo).
- **`chat_id: -1` come sentinella**: sostituita da `notifications_enabled` (booleano).
  Le query di disuguaglianza in Firestore **escludono i documenti in cui il campo non
  esiste**, quindi un utente creato senza `chat_id` sarebbe sparito silenziosamente dal
  broadcast.
- **Timestamp**: `save_user()` usa `firestore.SERVER_TIMESTAMP` invece di `datetime.now()`
  senza fuso, così la data non dipende dall'orologio del processo che scrive.
- **Backup**: lo script di migrazione esporta tutto in JSON prima di toccare qualsiasi cosa.
  Resta da impostare un export **ricorrente** (vedi sotto).

## 10. Il reset mensile dipendeva da documenti scritti a mano ✅ risolto

**Prima**: `handle_monthly_reset()` cercava in `seasons` il documento del mese e, se non lo
trovava, usciva senza fare nulla: niente trofei e `monthly_points` mai azzerato, con un solo
log a segnalarlo.

**Adesso**: `get_or_create_season()` crea la stagione mancante numerandola dopo l'ultima, e
i punti mensili vengono azzerati comunque, anche quando nessuno ha giocato. L'azzeramento usa
batch da 400 operazioni invece di una scrittura per volta.

## 11. Trofei di evento assegnati un giorno troppo presto ✅ risolto

Trovato durante il lavoro: `get_event_trophy_day()` confrontava `trophy_day` con **oggi**, e
`trophy_day` è l'ultimo giorno dell'evento. Il job di mezzanotte assegnava quindi i trofei
all'inizio dell'ultima giornata, su una classifica ancora da giocare. Adesso il confronto è
con **ieri**: i trofei vanno a evento concluso.

---

## Come migrare

Con il bot fermo:

```bash
python scripts/migrate_firestore.py --dry-run   # mostra cosa farebbe
python scripts/migrate_firestore.py             # esegue, con export JSON preliminare
firebase deploy --only firestore:rules,firestore:indexes
```

Lo script è idempotente (si può rieseguire) e in ordine: backup JSON di `users`,
`daily_path`, `events`, `seasons`; poi utenti sul nuovo id con fusione dei duplicati; poi
date ISO su `daily_path`; poi eventi (date ISO + `ranking` spostato in `participants`).

Le trasformazioni sono funzioni pure, coperte da `tests/test_migration.py`: girano una volta
sola su dati veri, quindi devono essere giuste al primo colpo.

## Cosa resta da fare

- **Export ricorrente**: l'export automatico di Firestore richiede il piano Blaze. In
  alternativa, un workflow GitHub Actions settimanale che esegue la parte di backup dello
  script di migrazione e archivia il JSON.
- **Pulizia storica**: `daily_path` cresce di circa 365 documenti l'anno. Non è un problema
  di costo, ma prima o poi conviene una regola TTL (o una cancellazione annuale) sui giorni
  più vecchi di un anno.
- **`show_stats_handler`** legge l'utente ad ogni apertura delle statistiche e ad ogni
  navigazione dei trofei: si può servire dalla `context.user_data` già presente, ma è una
  lettura per interazione, non per utente registrato — bassa priorità.
