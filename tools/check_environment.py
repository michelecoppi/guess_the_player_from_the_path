"""Validatore dell'ambiente di sviluppo e della configurazione di runtime.

Verifica che i requisiti supportati dal codebase siano soddisfatti prima di
avviare i servizi in locale o in produzione.

Uso:
    python -m tools.check_environment
    python -m tools.check_environment --mode dev
    python -m tools.check_environment --mode prod
    python -m tools.check_environment --strict
    python -m tools.check_environment --json
"""
import argparse
import json
import os
import re
import shutil
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class CheckStatus(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    INFO = "INFO"


@dataclass
class CheckItem:
    category: str
    name: str
    status: CheckStatus
    message: str
    remediation: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data


class EnvironmentValidator:
    def __init__(self, project_root: Optional[Path] = None, mode: str = "dev", strict: bool = False):
        self.project_root = (project_root or Path(__file__).resolve().parents[1]).resolve()
        self.mode = mode.lower()
        self.strict = strict
        self.results: list[CheckItem] = []
        self._load_dotenv_if_present()

    def _load_dotenv_if_present(self) -> None:
        """Carica il file .env se presente, senza dipendere strettamente da python-dotenv."""
        env_file = self.project_root / ".env"
        if not env_file.exists():
            return
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file)
        except ImportError:
            # Fallback manuale minimale se python-dotenv non e' ancora installato
            try:
                with open(env_file, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        key, val = line.split("=", 1)
                        key = key.strip()
                        val = val.strip().strip("'\"")
                        if key and key not in os.environ:
                            os.environ[key] = val
            except Exception:
                pass

    def add_result(self, category: str, name: str, status: CheckStatus, message: str,
                   remediation: Optional[str] = None) -> None:
        self.results.append(CheckItem(
            category=category,
            name=name,
            status=status,
            message=message,
            remediation=remediation,
        ))

    def check_python_version(self) -> None:
        """Verifica la versione minima di Python (3.11+ richiesta per asyncio.timeout e annotazioni)."""
        current = sys.version_info
        major, minor, micro = current[0], current[1], current[2]
        version_str = f"{major}.{minor}.{micro}"
        if (major, minor) >= (3, 11):
            self.add_result(
                category="Runtime",
                name="Python Version",
                status=CheckStatus.PASS,
                message=f"Python {version_str} soddisfa il requisito minimo (>= 3.11)",
            )
        else:
            self.add_result(
                category="Runtime",
                name="Python Version",
                status=CheckStatus.FAIL,
                message=f"Python {version_str} rilevato: il progetto richiede Python 3.11 o successivo "
                        "(richiesto per asyncio.timeout in bot.py e target-version in pyproject.toml).",
                remediation="Installa Python 3.11 o successivo e ricrea il virtual environment:\n"
                            "    py -3.11 -m venv .venv\n"
                            "    .\\.venv\\Scripts\\activate  (Windows) oppure source .venv/bin/activate (Linux/WSL)",
            )

    def check_datasets_and_files(self) -> None:
        """Verifica la presenza e integrita sintattica dei dataset JSON e dei file core."""
        datasets = [
            ("data/players.json", "Dataset calciatori"),
            ("data/config.json", "Configurazione di gioco (pesi e regole)"),
            ("data/event_templates.json", "Template degli eventi"),
            ("data/shop.json", "Catalogo del negozio e cosmetici"),
        ]

        for rel_path, desc in datasets:
            file_path = self.project_root / rel_path
            if not file_path.exists():
                self.add_result(
                    category="Datasets",
                    name=rel_path,
                    status=CheckStatus.FAIL,
                    message=f"File {desc} non trovato: '{rel_path}'",
                    remediation=f"Verifica che il repository contenga '{rel_path}' o ripristinalo da Git.",
                )
                continue

            try:
                with open(file_path, encoding="utf-8") as f:
                    data = json.load(f)

                # Controllo specifico per data/players.json
                if rel_path == "data/players.json":
                    players_list = data.get("players") if isinstance(data, dict) else (data if isinstance(data, list) else None)
                    if not isinstance(players_list, list) or len(players_list) == 0:
                        self.add_result(
                            category="Datasets",
                            name=rel_path,
                            status=CheckStatus.FAIL,
                            message=f"{desc} vuoto o non contiene una lista 'players'",
                            remediation="Il file data/players.json deve contenere un dizionario con la chiave 'players' valida.",
                        )
                    else:
                        first = players_list[0] if isinstance(players_list[0], dict) else {}
                        required_fields = {"id", "full_name", "career"}
                        missing_fields = required_fields - set(first.keys())
                        if missing_fields:
                            self.add_result(
                                category="Datasets",
                                name=rel_path,
                                status=CheckStatus.FAIL,
                                message=f"{desc} non ha i campi attesi (mancano in testa: {missing_fields})",
                                remediation="Verifica l'integrita del file data/players.json con scripts/dataset_report.py.",
                            )
                        else:
                            self.add_result(
                                category="Datasets",
                                name=rel_path,
                                status=CheckStatus.PASS,
                                message=f"{desc} valido ({len(players_list)} calciatori caricati)",
                            )
                else:
                    self.add_result(
                        category="Datasets",
                        name=rel_path,
                        status=CheckStatus.PASS,
                        message=f"{desc} presente e JSON valido",
                    )
            except json.JSONDecodeError as err:
                self.add_result(
                    category="Datasets",
                    name=rel_path,
                    status=CheckStatus.FAIL,
                    message=f"{desc} contiene JSON non valido: riga {err.lineno}, colonna {err.colno}",
                    remediation=f"Correggi l'errore di sintassi JSON in '{rel_path}'.",
                )

        # Controllo asset statici WebApp
        webapp_files = [
            "webapp/index.html",
            "webapp/client.js",
            "webapp/strings.js",
            "webapp/arena.js",
            "webapp/referrals.js",
            "webapp/legal.css",
            "webapp/terms.html",
            "webapp/privacy.html",
        ]
        missing_webapp = [f for f in webapp_files if not (self.project_root / f).exists()]
        if missing_webapp:
            self.add_result(
                category="Mini App",
                name="Static Files",
                status=CheckStatus.FAIL,
                message=f"File statici della Mini App mancanti: {', '.join(missing_webapp)}",
                remediation="Ripristina i file della cartella webapp/ da git.",
            )
        else:
            self.add_result(
                category="Mini App",
                name="Static Files",
                status=CheckStatus.PASS,
                message="Tutti i file statici della Mini App sono presenti in webapp/",
            )

    def check_dotenv_file(self) -> None:
        """Verifica la presenza del file .env locale."""
        env_file = self.project_root / ".env"
        if env_file.exists():
            self.add_result(
                category="Configuration",
                name=".env File",
                status=CheckStatus.PASS,
                message="File .env trovato nella root del progetto",
            )
        else:
            status = CheckStatus.FAIL if self.mode == "prod" else CheckStatus.WARN
            self.add_result(
                category="Configuration",
                name=".env File",
                status=status,
                message="File .env non trovato nella root del progetto",
                remediation="Copia il file di esempio ed imposta le variabili d'ambiente necessarie:\n"
                            "    copy .env.example .env  (Windows) oppure cp .env.example .env (Linux/WSL)",
            )

    def check_telegram_configuration(self) -> None:
        """Verifica la configurazione del bot Telegram (BOT_TOKEN, BOT_USERNAME, ADMIN_TELEGRAM_IDS)."""
        bot_token = os.getenv("BOT_TOKEN", "").strip()
        if not bot_token:
            self.add_result(
                category="Telegram",
                name="BOT_TOKEN",
                status=CheckStatus.FAIL,
                message="BOT_TOKEN non e' impostato. Il bot e l'interfaccia admin non possono avviarsi.",
                remediation="Richiedi un token a @BotFather su Telegram e aggiungilo al tuo .env:\n"
                            "    BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ",
            )
        else:
            # Controllo formato generico token Telegram: <id_numerico>:<stringa_alfanumerica>
            token_pattern = r"^\d{6,15}:[A-Za-z0-9_-]{30,}$"
            # Supportiamo anche token di test sintetici in locale se esplicitamente impostati
            if re.match(token_pattern, bot_token) or bot_token.startswith("test-") or bot_token == "preview-bot-token":
                self.add_result(
                    category="Telegram",
                    name="BOT_TOKEN",
                    status=CheckStatus.PASS,
                    message="BOT_TOKEN configurato con formato valido",
                )
            else:
                self.add_result(
                    category="Telegram",
                    name="BOT_TOKEN",
                    status=CheckStatus.WARN,
                    message="BOT_TOKEN non rispetta il consueto formato Telegram (<id_numerico>:<token>)",
                    remediation="Verifica che BOT_TOKEN sia stato copiato interamente da @BotFather senza spazi.",
                )

        bot_username = os.getenv("BOT_USERNAME", "").strip()
        if not bot_username:
            self.add_result(
                category="Telegram",
                name="BOT_USERNAME",
                status=CheckStatus.WARN,
                message="BOT_USERNAME non impostato: i bottoni di condivisione risultato e i link d'invito non compariranno.",
                remediation="Imposta lo username del bot senza @ in .env (es. BOT_USERNAME=guess_the_player_bot).",
            )
        else:
            if bot_username.startswith("@"):
                self.add_result(
                    category="Telegram",
                    name="BOT_USERNAME",
                    status=CheckStatus.WARN,
                    message="BOT_USERNAME inizia con '@': deve essere impostato senza la chiocciola.",
                    remediation=f"Rimuovi '@' nel .env: BOT_USERNAME={bot_username.lstrip('@')}",
                )
            else:
                self.add_result(
                    category="Telegram",
                    name="BOT_USERNAME",
                    status=CheckStatus.PASS,
                    message=f"BOT_USERNAME configurato: @{bot_username}",
                )

        admin_ids_raw = os.getenv("ADMIN_TELEGRAM_IDS", "").strip()
        if admin_ids_raw:
            parts = [x.strip() for x in admin_ids_raw.split(",") if x.strip()]
            invalid_ids = [x for x in parts if not x.isdigit()]
            if invalid_ids:
                self.add_result(
                    category="Telegram",
                    name="ADMIN_TELEGRAM_IDS",
                    status=CheckStatus.WARN,
                    message=f"ADMIN_TELEGRAM_IDS contiene valori non numerici: {invalid_ids}",
                    remediation="ADMIN_TELEGRAM_IDS deve essere un elenco di ID numerici Telegram separati da virgola.",
                )
            else:
                self.add_result(
                    category="Telegram",
                    name="ADMIN_TELEGRAM_IDS",
                    status=CheckStatus.PASS,
                    message=f"ADMIN_TELEGRAM_IDS configurato ({len(parts)} amministratori abilitati)",
                )
        else:
            self.add_result(
                category="Telegram",
                name="ADMIN_TELEGRAM_IDS",
                status=CheckStatus.INFO,
                message="ADMIN_TELEGRAM_IDS non impostato: nessun utente abilitato ai comandi /admin_*",
                remediation="Se desideri usare i comandi admin su Telegram, aggiungi il tuo ID Telegram a ADMIN_TELEGRAM_IDS nel .env.",
            )

    def check_firebase_configuration(self) -> None:
        """Verifica la configurazione di Firebase / Firestore (Emulatore locale vs Credenziali di produzione)."""
        emulator_host = os.getenv("FIRESTORE_EMULATOR_HOST", "").strip()
        credentials_path_str = os.getenv("FIREBASE_CREDENTIALS_PATH", "").strip()

        # In dev mode: e' sufficiente l'emulatore OPPURE le credenziali
        if emulator_host:
            # Controllo formato host:porta
            host_pattern = r"^[a-zA-Z0-9.-]+:\d+$"
            if not re.match(host_pattern, emulator_host):
                self.add_result(
                    category="Firebase",
                    name="FIRESTORE_EMULATOR_HOST",
                    status=CheckStatus.FAIL,
                    message=f"Formato non valido per FIRESTORE_EMULATOR_HOST: '{emulator_host}' (atteso host:porta)",
                    remediation="Imposta un host valido, es. FIRESTORE_EMULATOR_HOST=127.0.0.1:8571",
                )
            else:
                # Prova di connettività HTTP verso l'emulatore
                reachable = False
                try:
                    url = f"http://{emulator_host}/"
                    req = urllib.request.Request(url, method="GET")
                    with urllib.request.urlopen(req, timeout=1.0) as resp:
                        reachable = resp.status in (200, 404)
                except Exception:
                    reachable = False

                if reachable:
                    self.add_result(
                        category="Firebase",
                        name="Firestore Emulator",
                        status=CheckStatus.PASS,
                        message=f"Emulatore Firestore attivo e raggiungibile su {emulator_host}",
                    )
                else:
                    msg_status = CheckStatus.WARN if self.mode == "dev" else CheckStatus.FAIL
                    self.add_result(
                        category="Firebase",
                        name="Firestore Emulator",
                        status=msg_status,
                        message=f"FIRESTORE_EMULATOR_HOST impostato su {emulator_host}, ma l'emulatore non risponde.",
                        remediation="Avvia l'emulatore Firestore in un terminale separato con:\n"
                                    "    gcloud emulators firestore start --host-port=" + emulator_host + "\n"
                                    "oppure con il comando di sviluppo: make emulator / python -m tools.dev emulator",
                    )

        if credentials_path_str:
            cred_path = Path(credentials_path_str)
            if not cred_path.is_absolute():
                cred_path = self.project_root / cred_path

            if not cred_path.exists():
                if emulator_host and self.mode == "dev":
                    self.add_result(
                        category="Firebase",
                        name="FIREBASE_CREDENTIALS_PATH",
                        status=CheckStatus.INFO,
                        message=f"FIREBASE_CREDENTIALS_PATH impostato su '{cred_path.name}', ma il file non esiste. "
                                "FIRESTORE_EMULATOR_HOST e' attivo per lo sviluppo locale.",
                    )
                else:
                    self.add_result(
                        category="Firebase",
                        name="FIREBASE_CREDENTIALS_PATH",
                        status=CheckStatus.FAIL,
                        message=f"File credenziali Firebase non trovato: '{cred_path}'",
                        remediation="Verifica che FIREBASE_CREDENTIALS_PATH nel .env punti a un file JSON esistente "
                                    "(es. firebase-key.json).",
                    )
            else:
                try:
                    with open(cred_path, encoding="utf-8") as f:
                        key_data = json.load(f)
                    if isinstance(key_data, dict) and ("project_id" in key_data or "client_email" in key_data):
                        self.add_result(
                            category="Firebase",
                            name="FIREBASE_CREDENTIALS_PATH",
                            status=CheckStatus.PASS,
                            message=f"File credenziali Firebase valido: {cred_path.name} (Project: {key_data.get('project_id', 'n/d')})",
                        )
                    else:
                        self.add_result(
                            category="Firebase",
                            name="FIREBASE_CREDENTIALS_PATH",
                            status=CheckStatus.WARN,
                            message=f"Il file '{cred_path.name}' non sembra una chiave di servizio valida.",
                            remediation="Scarica una chiave di servizio JSON valida dalla console Firebase/Google Cloud.",
                        )
                except Exception as err:
                    self.add_result(
                        category="Firebase",
                        name="FIREBASE_CREDENTIALS_PATH",
                        status=CheckStatus.FAIL,
                        message=f"Errore nella lettura del file credenziali Firebase: {err}",
                        remediation=f"Verifica che '{cred_path}' sia un file JSON valido.",
                    )

        if not emulator_host and not credentials_path_str:
            if self.mode == "dev":
                self.add_result(
                    category="Firebase",
                    name="Database Setup",
                    status=CheckStatus.FAIL,
                    message="Nessuna configurazione Firestore rilevata (ne' FIRESTORE_EMULATOR_HOST ne' FIREBASE_CREDENTIALS_PATH).",
                    remediation="Per lo sviluppo locale, scegli una delle due opzioni:\n"
                                "1. (Consigliato) Avvia l'emulatore locale ed imposta nel .env o nel terminale:\n"
                                "       FIRESTORE_EMULATOR_HOST=127.0.0.1:8571\n"
                                "2. Oppure scarica la chiave del service account da Firebase e impostala nel .env:\n"
                                "       FIREBASE_CREDENTIALS_PATH=firebase-key.json",
                )
            else:
                self.add_result(
                    category="Firebase",
                    name="FIREBASE_CREDENTIALS_PATH",
                    status=CheckStatus.FAIL,
                    message="In produzione FIREBASE_CREDENTIALS_PATH e' obbligatorio (oppure credenziali ADC su Cloud Run).",
                    remediation="Configura FIREBASE_CREDENTIALS_PATH con il percorso del file di credenziali.",
                )

    def check_cloud_tasks_and_hardening(self) -> None:
        """Verifica la configurazione di Cloud Tasks e dei segreti di sicurezza (lifespan e worker)."""
        webhook_secret = os.getenv("WEBHOOK_SECRET", "").strip()
        task_secret = os.getenv("TASK_SECRET", "").strip()
        tasks_queue = os.getenv("TASKS_QUEUE", "").strip()
        broadcast_queue = os.getenv("BROADCAST_QUEUE", "").strip()
        generation_secret = os.getenv("GENERATION_SECRET", "").strip()

        secret_regex = r"^[A-Za-z0-9_-]{32,256}$"
        queue_regex = r"^projects/[^/]+/locations/[^/]+/queues/[^/]+$"

        # Modalità dev: le code Cloud Tasks sono opzionali a meno che non si voglia avviare bot.py con lifespan completo
        is_prod = self.mode in ("prod", "all")

        # 1. WEBHOOK_SECRET
        if webhook_secret:
            if re.match(secret_regex, webhook_secret):
                self.add_result(
                    category="Security & Hardening",
                    name="WEBHOOK_SECRET",
                    status=CheckStatus.PASS,
                    message="WEBHOOK_SECRET valido (lunghezza adeguata, caratteri URL-safe)",
                )
            else:
                self.add_result(
                    category="Security & Hardening",
                    name="WEBHOOK_SECRET",
                    status=CheckStatus.FAIL,
                    message="WEBHOOK_SECRET non valido: deve contenere da 32 a 256 caratteri URL-safe ([A-Za-z0-9_-]).",
                    remediation="Genera un segreto sicuro con:\n"
                                "    python -c \"import secrets; print(secrets.token_urlsafe(48))\"",
                )
        else:
            status = CheckStatus.FAIL if is_prod else CheckStatus.INFO
            self.add_result(
                category="Security & Hardening",
                name="WEBHOOK_SECRET",
                status=status,
                message="WEBHOOK_SECRET non impostato (richiesto da bot.py per la registrazione e verifica del webhook).",
                remediation="Genera il segreto con: python -c \"import secrets; print(secrets.token_urlsafe(48))\" e impostalo in .env.",
            )

        # 2. TASK_SECRET
        if task_secret:
            if re.match(secret_regex, task_secret):
                self.add_result(
                    category="Security & Hardening",
                    name="TASK_SECRET",
                    status=CheckStatus.PASS,
                    message="TASK_SECRET valido (lunghezza adeguata, caratteri URL-safe)",
                )
            else:
                self.add_result(
                    category="Security & Hardening",
                    name="TASK_SECRET",
                    status=CheckStatus.FAIL,
                    message="TASK_SECRET non valido: deve contenere da 32 a 256 caratteri URL-safe ([A-Za-z0-9_-]).",
                    remediation="Genera un segreto sicuro con:\n"
                                "    python -c \"import secrets; print(secrets.token_urlsafe(48))\"",
                )
        else:
            status = CheckStatus.FAIL if is_prod else CheckStatus.INFO
            self.add_result(
                category="Security & Hardening",
                name="TASK_SECRET",
                status=status,
                message="TASK_SECRET non impostato (richiesto per proteggere gli endpoint worker Cloud Tasks).",
                remediation="Genera il segreto con: python -c \"import secrets; print(secrets.token_urlsafe(48))\" e impostalo in .env.",
            )

        # 3. TASKS_QUEUE e BROADCAST_QUEUE
        for var_name, q_val in [("TASKS_QUEUE", tasks_queue), ("BROADCAST_QUEUE", broadcast_queue)]:
            if q_val:
                if re.match(queue_regex, q_val):
                    self.add_result(
                        category="Cloud Tasks",
                        name=var_name,
                        status=CheckStatus.PASS,
                        message=f"{var_name} configurata con percorso risorsa GCP valido",
                    )
                else:
                    self.add_result(
                        category="Cloud Tasks",
                        name=var_name,
                        status=CheckStatus.FAIL,
                        message=f"{var_name} non valida: '{q_val}'. Formato atteso: projects/<p>/locations/<l>/queues/<q>",
                        remediation="Configura il percorso completo della coda come indicato in docs/runtime-hardening.md.",
                    )
            else:
                status = CheckStatus.FAIL if is_prod else CheckStatus.INFO
                self.add_result(
                    category="Cloud Tasks",
                    name=var_name,
                    status=status,
                    message=f"{var_name} non configurata (necessaria in produzione per le code Cloud Tasks).",
                    remediation="Crea la coda su Cloud Tasks e imposta il percorso completo nel .env (vedi docs/runtime-hardening.md).",
                )

        # 4. GENERATION_SECRET
        if generation_secret:
            self.add_result(
                category="Security & Hardening",
                name="GENERATION_SECRET",
                status=CheckStatus.PASS,
                message="GENERATION_SECRET configurato per il job di generazione notturna",
            )
        else:
            status = CheckStatus.WARN if is_prod else CheckStatus.INFO
            self.add_result(
                category="Security & Hardening",
                name="GENERATION_SECRET",
                status=status,
                message="GENERATION_SECRET non impostato: la chiamata a /internal/daily-job non sara' autorizzata.",
                remediation="Imposta GENERATION_SECRET con una stringa casuale condivisa con Cloud Scheduler.",
            )

    def check_miniapp_and_urls(self) -> None:
        """Verifica la configurazione degli URL pubblici e della Mini App Telegram."""
        public_url = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
        is_prod = self.mode in ("prod", "all")

        if public_url:
            if is_prod and not public_url.startswith("https://"):
                self.add_result(
                    category="Mini App",
                    name="PUBLIC_BASE_URL",
                    status=CheckStatus.FAIL,
                    message=f"PUBLIC_BASE_URL deve iniziare con 'https://' per la consegna dei task e la Mini App: '{public_url}'",
                    remediation="Imposta un URL pubblico HTTPS (es. https://xxx.run.app).",
                )
            elif not public_url.startswith(("http://", "https://")):
                self.add_result(
                    category="Mini App",
                    name="PUBLIC_BASE_URL",
                    status=CheckStatus.WARN,
                    message=f"PUBLIC_BASE_URL deve includere lo schema http:// o https://: '{public_url}'",
                    remediation="Correggi PUBLIC_BASE_URL in .env aggiungendo https:// o http://.",
                )
            else:
                self.add_result(
                    category="Mini App",
                    name="PUBLIC_BASE_URL",
                    status=CheckStatus.PASS,
                    message=f"PUBLIC_BASE_URL configurato: {public_url} (Mini App su {public_url}/app)",
                )
        else:
            status = CheckStatus.FAIL if is_prod else CheckStatus.WARN
            self.add_result(
                category="Mini App",
                name="PUBLIC_BASE_URL",
                status=status,
                message="PUBLIC_BASE_URL non impostato: il bottone 'Play' della Mini App e i link ai duelli non compariranno.",
                remediation="In locale puoi usare scripts/preview_webapp.py (porta 8888) senza configurare PUBLIC_BASE_URL.\n"
                            "Per provare bot.py con la Mini App o webhook, usa un tunnel HTTPS (ngrok/localtunnel) ed imposta PUBLIC_BASE_URL.",
            )

    def check_developer_tooling(self) -> None:
        """Verifica la presenza di strumenti e librerie di sviluppo utili (pytest, ruff, mypy, node, gcloud)."""
        # Dipendenze Python
        packages = [
            ("pytest", "pytest (suite di test)"),
            ("ruff", "ruff (linter e formatter)"),
            ("mypy", "mypy (type checker)"),
            ("streamlit", "streamlit (dashboard admin locale)"),
            ("fastapi", "fastapi (server API)"),
            ("uvicorn", "uvicorn (server ASGI)"),
            ("telegram", "python-telegram-bot (interfaccia bot)"),
        ]
        missing_pkgs = []
        for mod_name, label in packages:
            try:
                __import__(mod_name)
            except ImportError:
                missing_pkgs.append(label)

        if missing_pkgs:
            self.add_result(
                category="Tooling",
                name="Python Packages",
                status=CheckStatus.WARN,
                message=f"Alcuni pacchetti utili non sono installati: {', '.join(missing_pkgs)}",
                remediation="Installa le dipendenze di sviluppo con:\n    pip install -r requirements-dev.txt",
            )
        else:
            self.add_result(
                category="Tooling",
                name="Python Packages",
                status=CheckStatus.PASS,
                message="Tutti i pacchetti Python core e dev sono installati",
            )

        # Binari esterni: node, gcloud, java
        binaries = [
            ("node", "Node.js (necessario per node --test tests/client.test.cjs)"),
            ("gcloud", "Google Cloud SDK (necessario per l'emulatore Firestore)"),
            ("java", "Java JRE/JDK (necessario per l'emulatore Firestore)"),
        ]
        for bin_name, label in binaries:
            found = shutil.which(bin_name)
            if found:
                self.add_result(
                    category="Tooling",
                    name=f"CLI {bin_name}",
                    status=CheckStatus.PASS,
                    message=f"{label} disponibile nel PATH ({found})",
                )
            else:
                self.add_result(
                    category="Tooling",
                    name=f"CLI {bin_name}",
                    status=CheckStatus.INFO,
                    message=f"{label} non trovato nel PATH",
                    remediation=f"Se intendi eseguire {bin_name}, assicurati che sia installato e aggiunto al PATH.",
                )

    def run_all(self) -> list[CheckItem]:
        """Esegue tutti i controlli previsti per la modalita' configurata."""
        self.results.clear()
        self.check_python_version()
        self.check_datasets_and_files()
        self.check_dotenv_file()
        self.check_telegram_configuration()
        self.check_firebase_configuration()
        self.check_cloud_tasks_and_hardening()
        self.check_miniapp_and_urls()
        self.check_developer_tooling()
        return self.results

    @property
    def has_failures(self) -> bool:
        if self.strict:
            return any(r.status in (CheckStatus.FAIL, CheckStatus.WARN) for r in self.results)
        return any(r.status == CheckStatus.FAIL for r in self.results)

    def print_report(self, quiet: bool = False) -> None:
        """Stampa a terminale un report formattato e chiaro dei controlli eseguiti."""
        # Selettore simboli/colori
        icons = {
            CheckStatus.PASS: "[OK]  ",
            CheckStatus.WARN: "[WARN]",
            CheckStatus.FAIL: "[FAIL]",
            CheckStatus.INFO: "[INFO]",
        }

        # Raggruppa per categoria
        categories: dict[str, list[CheckItem]] = {}
        for item in self.results:
            categories.setdefault(item.category, []).append(item)

        print("\n============================================================")
        print(" Guess the Player - Environment & Configuration Validator")
        print(f" Modalita': {self.mode.upper()} | Root: {self.project_root}")
        print("============================================================\n")

        failures: list[CheckItem] = []
        warnings: list[CheckItem] = []

        for cat, items in categories.items():
            if quiet and all(i.status == CheckStatus.PASS for i in items):
                continue
            print(f"--- {cat} ---")
            for item in items:
                if quiet and item.status == CheckStatus.PASS:
                    continue
                tag = icons[item.status]
                print(f"  {tag} {item.name}: {item.message}")
                if item.status == CheckStatus.FAIL:
                    failures.append(item)
                elif item.status == CheckStatus.WARN:
                    warnings.append(item)
            print()

        pass_count = sum(1 for r in self.results if r.status == CheckStatus.PASS)
        warn_count = sum(1 for r in self.results if r.status == CheckStatus.WARN)
        fail_count = sum(1 for r in self.results if r.status == CheckStatus.FAIL)
        info_count = sum(1 for r in self.results if r.status == CheckStatus.INFO)

        print("------------------------------------------------------------")
        print(f"Riepilogo: {pass_count} OK, {warn_count} avvisi, {fail_count} errori, {info_count} note.")
        print("------------------------------------------------------------")

        # Sezione remediations per problemi bloccanti o avvisi
        action_items = failures + (warnings if self.strict else [])
        if action_items:
            print("\n>>> AZIONI RICHIESTE PER RISOLVERE I PROBLEMI RILEVATI <<<\n")
            for i, item in enumerate(action_items, 1):
                print(f"{i}. [{item.category}] {item.name}")
                print(f"   Problema: {item.message}")
                if item.remediation:
                    print("   Soluzione:\n     " + "\n     ".join(item.remediation.split("\n")))
                print()
        elif not quiet:
            print("\n Configurazione coerente per la modalita' selezionata!\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verifica l'ambiente di sviluppo e la configurazione per Guess the Player."
    )
    parser.add_argument(
        "--mode",
        choices=["dev", "prod", "all"],
        default="dev",
        help="Ambiente target per la validazione (default: dev). 'prod' verifica anche chiavi e code Cloud Tasks.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Modalita' rigorosa: considera i WARN come errori (exit code 1).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Stampa l'esito dei controlli in formato JSON per script e automazioni.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Mostra solo errori e avvisi, nascondendo i controlli superati.",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help="Percorso della root del progetto (opzionale).",
    )
    args = parser.parse_args()

    validator = EnvironmentValidator(
        project_root=args.project_root,
        mode=args.mode,
        strict=args.strict,
    )
    validator.run_all()

    if args.json:
        payload = {
            "mode": args.mode,
            "strict": args.strict,
            "has_failures": validator.has_failures,
            "checks": [r.to_dict() for r in validator.results],
        }
        print(json.dumps(payload, indent=2))
    else:
        validator.print_report(quiet=args.quiet)

    return 1 if validator.has_failures else 0


if __name__ == "__main__":
    sys.exit(main())
