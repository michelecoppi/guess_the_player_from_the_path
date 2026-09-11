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

Per lo sviluppo locale base (senza chiamate verso Telegram e senza invio a code esterne), sono sufficienti:
- `BOT_TOKEN`: un token Telegram ottenuto da `@BotFather` (es. `123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ`).
- `FIRESTORE_EMULATOR_HOST`: impostato a `127.0.0.1:8571` per usare l'emulatore locale senza necessità di una chiave JSON di produzione.

Se invece disponi di un progetto Firebase di test/staging con service account:
- `FIREBASE_CREDENTIALS_PATH=firebase-key.json`

---

## 3. Validatore dell'ambiente (`tools.check_environment`)

Prima di avviare i servizi, puoi verificare preventivamente se tutti i requisiti, file e variabili sono corretti con:

```bash
python -m tools.check_environment
```

### Opzioni supportate:
- `python -m tools.check_environment`: verifica l'ambiente per lo **sviluppo locale** (default `dev`). In questa modalità, l'assenza di code Cloud Tasks o URL pubblici HTTPS viene segnalata come nota informativa, non come blocco.
- `python -m tools.check_environment --mode prod`: verifica l'ambiente per il **deploy o produzione**, accertando che tutti i segreti (`WEBHOOK_SECRET`, `TASK_SECRET`), code (`TASKS_QUEUE`, `BROADCAST_QUEUE`) e `PUBLIC_BASE_URL` siano configurati con formato rigoroso.
- `python -m tools.check_environment --strict`: tratta gli avvisi (`WARN`) come errori bloccanti (restituisce codice di uscita `1`).
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
| `make check-env` | `python -m tools.dev check-env`<br>`.\dev.ps1 check-env` | Esegue il validatore dell'ambiente |
| `make test` | `python -m tools.dev test`<br>`.\dev.ps1 test` | Esegue i test unitari veloci con `pytest -q` |
| `make test-cov` | `python -m tools.dev test-cov`<br>`.\dev.ps1 test-cov` | Esegue i test con report di code coverage nel terminale |
| `make test-node` | `python -m tools.dev test-node`<br>`.\dev.ps1 test-node` | Esegue i test client Node.js per la Mini App (`tests/client.test.cjs`) |
| `make lint` | `python -m tools.dev lint`<br>`.\dev.ps1 lint` | Verifica lo stile del codice con `ruff check .` |
| `make typecheck` | `python -m tools.dev typecheck`<br>`.\dev.ps1 typecheck` | Controllo tipi statici con `mypy services/` |
| `make syntax` | `python -m tools.dev syntax`<br>`.\dev.ps1 syntax` | Verifica sintassi con `compileall` su tutti i moduli |
| `make dataset-check` | `python -m tools.dev dataset-check`<br>`.\dev.ps1 dataset-check` | Controlla integrità e salute del dataset calciatori (`scripts/dataset_report.py --strict`) |
| `make check` | `python -m tools.dev check`<br>`.\dev.ps1 check` | Esegue **tutte** le verifiche di qualità in sequenza (CI locale completa) |
| `make emulator` | `python -m tools.dev emulator`<br>`.\dev.ps1 emulator` | Avvia l'emulatore Firestore locale su porta 8571 |
| `make api` | `python -m tools.dev api`<br>`.\dev.ps1 api` | Avvia il server FastAPI (`bot.py`) con `--reload` su porta 8000 |
| `make admin` | `python -m tools.dev admin`<br>`.\dev.ps1 admin` | Avvia la dashboard Streamlit su `admin_ui.py` |
| `make webapp` | `python -m tools.dev webapp`<br>`.\dev.ps1 webapp` | Avvia l'anteprima isolata della Mini App su `http://localhost:8888/app` |

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

Per avviare il server FastAPI completo:

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

> [!NOTE]
> In produzione `bot.py` gira su Cloud Run con un'architettura rinforzata descritta in [`docs/runtime-hardening.md`](runtime-hardening.md), basata su segreti a 48 caratteri URL-safe e code Cloud Tasks per l'accodamento duraturo. Per lo sviluppo e i test locali dei client webapp o delle funzioni di gioco, i comandi `make webapp` e `make test` operano in modo isolato e non richiedono risorse cloud.

---

## 6. Risoluzione dei problemi comuni (Troubleshooting)

### 1. `UnicodeEncodeError: 'charmap' codec can't encode character`
- **Causa**: Console Windows con codepage non-UTF8 (es. cp1252) che non supporta certi caratteri emoji.
- **Risoluzione**: I tool `tools.check_environment` e `tools.dev` sono progettati con output ASCII-compatibile. In PowerShell puoi forzare la codifica UTF-8 per la sessione con: `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8`.

### 2. `ModuleNotFoundError: No module named 'google.cloud.tasks_v2'`
- **Causa**: Dipendenze mancanti nell'ambiente Python locale.
- **Risoluzione**: Esegui `pip install -r requirements-dev.txt` per installare tutte le dipendenze dichiarate in `requirements.txt` e `requirements-dev.txt`.

### 3. `FIRESTORE_EMULATOR_HOST non impostata: emulatore Firestore non disponibile`
- **Causa**: I test delle transazioni Firestore vengono saltati se la variabile d'ambiente non è impostata.
- **Risoluzione**: Avvia l'emulatore con `make emulator` e imposta `$env:FIRESTORE_EMULATOR_HOST="127.0.0.1:8571"` nel terminale in cui lanci i test.
