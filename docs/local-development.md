# Sviluppo locale e validazione configurazione

Questa guida documenta l'ambiente di sviluppo locale per **Guess the Player**, i comandi disponibili e le istruzioni per avviare ciascun componente dello stack (Firestore Emulator, API, Telegram bot, Mini App e Admin Dashboard) in modo riproducibile su Windows, WSL, Linux e macOS.

---

## 1. Prerequisiti

| Strumento | Versione richiesta | Perché serve |
|---|---|---|
| **Python** | **>= 3.11** | Richiesto da `asyncio.timeout` in `bot.py`, sintassi moderne e `pyproject.toml` |
| **Node.js** | **>= 20** (consigliata 22) | Esecuzione dei test client senza bundler (`node --test tests/client.test.cjs`) |
| **Java JRE/JDK** | **>= 17** (consigliata 21) | Runtime necessario per eseguire l'emulatore Firestore locale di Google Cloud |
| **Google Cloud SDK (`gcloud`)** | Qualsiasi recente | Gestione ed esecuzione dell'emulatore Firestore locale (`cloud-firestore-emulator`) |

---

## 2. Configurazione iniziale rapida

### 1. Clona il repository e crea il virtual environment

Su Linux / macOS / WSL:
```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

Su Windows (PowerShell):
```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
```

### 2. Configura le variabili d'ambiente (`.env`)

Copia il template di esempio:
```bash
cp .env.example .env       # Linux / macOS / WSL
copy .env.example .env     # Windows PowerShell / CMD
```

Per lo sviluppo locale base isolato (test, emulatore Firestore, anteprima Mini App `make webapp` e admin `make admin`):
- `BOT_TOKEN`: un token Telegram ottenuto da `@BotFather` (es. `123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ`).
- `FIRESTORE_EMULATOR_HOST`: impostato a `127.0.0.1:8571` per usare l'emulatore locale senza necessità di una chiave JSON di produzione.

Se invece intendi avviare il **server FastAPI completo `bot.py` (`make api`)**:
`bot.py` esegue all'avvio controlli rigorosi di lifespan (`task_queue.validate_configuration()`) e richiede:
- `WEBHOOK_SECRET`: stringa URL-safe da 32 a 256 caratteri.
- `TASK_SECRET`: stringa URL-safe da 32 a 256 caratteri.
- `TASKS_QUEUE` e `BROADCAST_QUEUE`: identificatori di coda (es. `projects/dev/locations/eu/queues/tasks`).
- `PUBLIC_BASE_URL`: URL con schema `https://` (es. `https://localhost:8000` o tunnel HTTPS).

In ambiente di produzione (es. Cloud Run):
- Le variabili vengono fornite direttamente dall'ambiente di runtime / Secret Manager **senza richiedere alcun file `.env`**.
- L'accesso a Firestore può avvenire automaticamente tramite **Application Default Credentials (ADC)** assegnate al Service Account del container, senza necessità di impostare `FIREBASE_CREDENTIALS_PATH` su un file JSON locale.

---

## 3. Validatore dell'ambiente (`tools.check_environment`)

Prima di avviare i servizi, puoi verificare preventivamente se tutti i requisiti, file e variabili sono corretti con:

```bash
python -m tools.check_environment
```

### Modalità e opzioni supportate:
- `python -m tools.check_environment` (oppure `--mode dev`): verifica l'ambiente per lo **sviluppo locale isolato** (test, emulatore, preview webapp). In questa modalità, le code Cloud Tasks o i segreti di webhook sono opzionali (segnalati con nota informativa `[INFO]`).
- `python -m tools.check_environment --mode api`: verifica i requisiti per avviare il **server FastAPI `bot.py` (`make api`)**, accertando la presenza di `WEBHOOK_SECRET`, `TASK_SECRET`, `TASKS_QUEUE`, `BROADCAST_QUEUE` e `PUBLIC_BASE_URL` (HTTPS) richiesti dal lifespan di avvio.
- `python -m tools.check_environment --mode prod`: verifica l'ambiente per il **deploy di produzione** (Cloud Run), accertando la validità dei segreti e dei percorsi GCP completi senza richiedere la presenza del file `.env` e supportando l'autenticazione via ADC.
- `python -m tools.check_environment --strict`: tratta gli avvisi (`WARN`) come errori bloccanti (codice di uscita `1`).
- `python -m tools.check_environment --json`: stampa l'esito formattato in JSON per integrazioni CI o script automatici.
- `python -m tools.check_environment --quiet`: nasconde i controlli passati mostrando solo problemi ed azioni correttive.

### Errori azionabili
Tutti gli errori e gli avvisi includono una sezione **Azioni Richieste** che fornisce l'esatto comando da lanciare o la riga da inserire nel `.env` per correggere il problema.

---

## 4. Comandi di sviluppo locale

Per garantire massima comodità su ogni sistema operativo sono disponibili tre punti di ingresso equivalenti:
1. **Runner multipiattaforma Python**: `python -m tools.dev <comando>` (funziona ovunque ci sia Python).
2. **Make**: `make <comando>` (standard per Linux, macOS, WSL e container).
3. **PowerShell script**: `.\dev.ps1 <comando>` (conveniente su Windows senza installare Make).

| Comando Make | Comando Python / PowerShell | Descrizione |
|---|---|---|
| `make check-env` | `python -m tools.dev check-env`<br>`.\dev.ps1 check-env` | Esegue il validatore dell'ambiente (modalità dev: sviluppo isolato) |
| `make check-api` | `python -m tools.dev check-api`<br>`.\dev.ps1 check-api` | Valida i requisiti completi per l'avvio del server FastAPI `bot.py` |
| `make test` | `python -m tools.dev test`<br>`.\dev.ps1 test` | Esegue i test unitari veloci con `pytest -q` |
| `make test-cov` | `python -m tools.dev test-cov`<br>`.\dev.ps1 test-cov` | Esegue i test con report di code coverage nel terminale |
| `make test-node` | `python -m tools.dev test-node`<br>`.\dev.ps1 test-node` | Esegue i test client Node.js per la Mini App (`tests/client.test.cjs`) |
| `make lint` | `python -m tools.dev lint`<br>`.\dev.ps1 lint` | Verifica lo stile del codice con `ruff check .` |
| `make typecheck` | `python -m tools.dev typecheck`<br>`.\dev.ps1 typecheck` | Controllo tipi statici con `mypy services/` |
| `make syntax` | `python -m tools.dev syntax`<br>`.\dev.ps1 syntax` | Verifica sintassi con `compileall` su tutti i moduli |
| `make dataset-check` | `python -m tools.dev dataset-check`<br>`.\dev.ps1 dataset-check` | Controlla integrità e salute del dataset calciatori (`scripts/dataset_report.py --strict`) |
| `make check` | `python -m tools.dev check`<br>`.\dev.ps1 check` | Esegue la **suite standard di validazione locale** (ambiente, sintassi, lint, mypy, dataset, client test, pytest) |
| `make emulator` | `python -m tools.dev emulator`<br>`.\dev.ps1 emulator` | Avvia l'emulatore Firestore locale su porta 8571 |
| `make api` | `python -m tools.dev api`<br>`.\dev.ps1 api` | Avvia il server FastAPI (`bot.py`) con `--reload` su porta 8000 |
| `make admin` | `python -m tools.dev admin`<br>`.\dev.ps1 admin` | Avvia la dashboard Streamlit su `admin_ui.py` |
| `make webapp` | `python -m tools.dev webapp`<br>`.\dev.ps1 webapp` | Avvia l'anteprima isolata della Mini App su `http://localhost:8888/app` |

> [!NOTE]
> `make check` (o `python -m tools.dev check`) è la **suite di validazione locale standard** concepita per un ciclo di feedback immediato prima del commit. A differenza di `check`, la pipeline GitHub Actions (`.github/workflows/ci.yml`) avvia in aggiunta un'istanza dell'emulatore Firestore su JVM per verificare le transazioni concorrenti reali ed applica la soglia di copertura minima del 70% (`--cov-fail-under=70`). In locale puoi eseguire i test con copertura usando `make test-cov`.

---

## 5. Avvio e funzionamento dei singoli componenti

### 5.1 Emulatore Firestore

L'emulatore simula Firestore in locale sulla JVM, permettendo di testare transazioni reali senza intaccare il database cloud.

1. Installa il componente (una volta sola):
   ```bash
   gcloud components install cloud-firestore-emulator
   ```
2. Avvia l'emulatore:
   ```bash
   make emulator
   # oppure: python -m tools.dev emulator
   ```
3. In altri terminali o nel `.env`, dichiara:
   ```bash
   export FIRESTORE_EMULATOR_HOST=127.0.0.1:8571   # Linux/WSL/macOS
   $env:FIRESTORE_EMULATOR_HOST="127.0.0.1:8571"   # PowerShell
   ```

Con `FIRESTORE_EMULATOR_HOST` configurato, la suite di test esegue anche `tests/test_firestore_transactions.py` (transazioni di bonus, pagamenti in Stelle e ricevute di update).

---

### 5.2 Anteprima della Mini App (senza Telegram)

Per sviluppare o verificare graficamente la Mini App, i temi del negozio, le cornici o il calendario senza dipendere da Telegram o Firestore:

```bash
make webapp
# oppure: python -m tools.dev webapp
```

Apri il browser su:
```
http://localhost:8888/app
```
Questo avvia un server FastAPI leggero (`scripts/preview_webapp.py`) che inietta un finto utente con tutti i cosmetici già sbloccati, conservando tutto in memoria.

---

### 5.3 Dashboard Amministrativa (Streamlit)

La dashboard amministrativa locale permette di ispezionare lo stato del gioco, gestire le sfide giornaliere, pianificare eventi e tarare la difficoltà:

```bash
make admin
# oppure: python -m tools.dev admin
```

Verrà aperta l'interfaccia Streamlit (solitamente su `http://localhost:8501`).
- Se è configurato `FIRESTORE_EMULATOR_HOST`, leggerà e scriverà sull'emulatore locale.
- Se è configurato `FIREBASE_CREDENTIALS_PATH=firebase-key.json`, scriverà sul progetto Firebase puntato dalla chiave.

---

### 5.4 API e Server Principale (`bot.py`)

Il server principale `bot.py` include l'applicazione FastAPI, il webhook Telegram e gli endpoint della Mini App.

#### Requisiti di avvio del lifespan
All'avvio (`lifespan`), `bot.py` verifica la sicurezza e l'integrazione con Cloud Tasks:
1. `WEBHOOK_SECRET`: stringa URL-safe da 32 a 256 caratteri;
2. `services.task_queue.validate_configuration()`: verifica `TASK_SECRET` (32-256 caratteri), `TASKS_QUEUE`, `BROADCAST_QUEUE` e `PUBLIC_BASE_URL` (deve iniziare con `https://`).

Prima di lanciare `make api`, puoi verificare se l'ambiente soddisfa questi requisiti con:
```bash
make check-api
# oppure: python -m tools.dev check-api
```

Per lo sviluppo locale, puoi impostare nel file `.env` valori sintetici conformi:
```env
WEBHOOK_SECRET=local-dev-webhook-secret-32-characters-minimum
TASK_SECRET=local-dev-task-secret-32-characters-minimum
TASKS_QUEUE=projects/dev/locations/europe-west1/queues/tasks
BROADCAST_QUEUE=projects/dev/locations/europe-west1/queues/broadcast
PUBLIC_BASE_URL=https://localhost:8000
```

Avvia quindi il server:
```bash
make api
# oppure: python -m tools.dev api
```

Il server risponde su `http://localhost:8000`:
- `GET /`: verifica stato (`{"message": "Bot attivo!"}`)
- `GET /ping`: health check
- `GET /app`: serve la pagina principale della Mini App (`webapp/index.html`)
- `POST /app/api/*`: endpoint API della Mini App
- `POST /webhook`: endpoint per ricevere update webhook da Telegram (richiede `WEBHOOK_SECRET`)

> [!TIP]
> Se desideri soltanto testare la grafica o la logica client della Mini App in locale senza dover configurare i segreti di Cloud Tasks di `bot.py`, usa il comando `make webapp` (`scripts/preview_webapp.py`), che opera in modalità completamente autonoma e isolata.

---

## 6. Risoluzione dei problemi comuni (Troubleshooting)

### 1. `UnicodeEncodeError: 'charmap' codec can't encode character`
- **Causa**: Console Windows con codepage non-UTF8 (es. cp1252) che non supporta certi caratteri emoji.
- **Risoluzione**: I tool `tools.check_environment` e `tools.dev` sono progettati con output ASCII-compatibile. In PowerShell puoi forzare la codifica UTF-8 per la sessione con: `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8`.

### 2. `ModuleNotFoundError: No module named 'google.cloud.tasks_v2'`
- **Causa**: Dipendenze mancanti nell'ambiente Python locale.
- **Risoluzione**: Esegui `pip install -r requirements-dev.txt` per installare tutte le dipendenze dichiarate in `requirements.txt` e `requirements-dev.txt`.

### 3. `[ERRORE AVVIO API] Requisiti del runtime bot.py non soddisfatti`
- **Causa**: `bot.py` richiede `WEBHOOK_SECRET`, `TASK_SECRET`, `TASKS_QUEUE`, `BROADCAST_QUEUE` e `PUBLIC_BASE_URL` (`https://`).
- **Risoluzione**: Esegui `make check-api` per diagnosticare i campi mancanti ed imposta valori sintetici nel `.env` come illustrato nella Sezione 5.4. Per l'anteprima statica della Mini App senza server bot usa `make webapp`.

### 4. `FIRESTORE_EMULATOR_HOST non impostata: emulatore Firestore non disponibile`
- **Causa**: I test delle transazioni Firestore vengono saltati se la variabile d'ambiente non è impostata.
- **Risoluzione**: Avvia l'emulatore con `make emulator` e imposta `$env:FIRESTORE_EMULATOR_HOST="127.0.0.1:8571"` nel terminale in cui lanci i test.
