"""Runner di comandi locali multipiattaforma per Guess the Player.

Fornisce un punto di ingresso unico per avviare servizi di sviluppo, test,
linting, typechecking e controlli di integrita' del dataset.

Funziona in modo identico su Windows, WSL, Linux e macOS senza richiedere
dipendenze esterne o l'installazione di GNU make.

Uso:
    python -m tools.dev <comando> [argomenti opzionali...]
    python -m tools.dev --help
"""
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

ROOT_DIR = Path(__file__).resolve().parents[1]


def _run_cmd(cmd: list[str], *, env: Optional[dict[str, str]] = None, cwd: Optional[Path] = None) -> int:
    """Esegue un comando di sistema e ne restituisce il codice di uscita."""
    working_dir = cwd or ROOT_DIR
    cmd_str = " ".join(cmd)
    print(f">> Eseguo: {cmd_str} (in {working_dir})")
    run_env = os.environ.copy()
    if env:
        run_env.update(env)
    try:
        proc = subprocess.run(cmd, cwd=str(working_dir), env=run_env)
        return proc.returncode
    except FileNotFoundError as err:
        print(f"Errore: eseguibile non trovato per '{cmd[0]}': {err}")
        return 1
    except KeyboardInterrupt:
        print("\nProcesso interrotto dall'utente.")
        return 130


# ---------------------------------------------------------------------------
# Comandi supportati
# ---------------------------------------------------------------------------


def cmd_check_env(extra_args: list[str]) -> int:
    """Verifica l'ambiente e la configurazione con tools.check_environment."""
    cmd = [sys.executable, "-m", "tools.check_environment"] + extra_args
    return _run_cmd(cmd)


def cmd_test(extra_args: list[str]) -> int:
    """Esegue la suite di unit test con pytest."""
    cmd = [sys.executable, "-m", "pytest", "-q"] + extra_args
    return _run_cmd(cmd)


def cmd_test_cov(extra_args: list[str]) -> int:
    """Esegue i test con report di copertura (coverage)."""
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "--cov=services",
        "--cov=handlers",
        "--cov-report=term-missing",
    ] + extra_args
    return _run_cmd(cmd)


def cmd_test_node(extra_args: list[str]) -> int:
    """Esegue i test client per la Mini App con Node.js."""
    cmd = ["node", "--test", "tests/client.test.cjs"] + extra_args
    return _run_cmd(cmd)


def cmd_lint(extra_args: list[str]) -> int:
    """Esegue il linter ruff su tutto il repository."""
    cmd = [sys.executable, "-m", "ruff", "check", "."] + extra_args
    return _run_cmd(cmd)


def cmd_typecheck(extra_args: list[str]) -> int:
    """Esegue il type checker mypy su services/."""
    cmd = [sys.executable, "-m", "mypy", "services/"] + extra_args
    return _run_cmd(cmd)


def cmd_syntax(extra_args: list[str]) -> int:
    """Verifica la sintassi Python compilando i moduli del progetto."""
    cmd = [
        sys.executable,
        "-m",
        "compileall",
        "-q",
        "bot.py",
        "config.py",
        "services",
        "handlers",
        "scripts",
        "admin_pages",
        "admin_ui.py",
        "tools",
    ] + extra_args
    return _run_cmd(cmd)


def cmd_dataset_check(extra_args: list[str]) -> int:
    """Esegue il report e la verifica di integrita' del dataset calciatori."""
    cmd = [sys.executable, "scripts/dataset_report.py", "--strict"] + extra_args
    return _run_cmd(cmd)


def cmd_dataset_regression_check(extra_args: list[str]) -> int:
    """Verifica le regressioni del dataset calciatori rispetto alla baseline."""
    cmd = [sys.executable, "-m", "scripts.dataset_regression", "--check"] + extra_args
    return _run_cmd(cmd)


def cmd_dataset_baseline_update(extra_args: list[str]) -> int:
    """Aggiorna la baseline del dataset calciatori (data/dataset_baseline.json)."""
    cmd = [sys.executable, "-m", "scripts.dataset_regression", "--update-baseline"] + extra_args
    return _run_cmd(cmd)


def cmd_security_check(extra_args: list[str]) -> int:
    """Esegue l'audit di sicurezza: pip-audit, detect-secrets e npm-audit."""
    cmd = [sys.executable, "-m", "tools.security"] + extra_args
    return _run_cmd(cmd)


def _npm_cmd() -> str:
    import shutil
    return shutil.which("npm") or "npm"


def cmd_frontend_dev(extra_args: list[str]) -> int:
    """Avvia il server di sviluppo Vite per la Mini App V2 (localhost:5173)."""
    cmd = [_npm_cmd(), "run", "dev"] + extra_args
    return _run_cmd(cmd)


def cmd_frontend_build(extra_args: list[str]) -> int:
    """Compila il bundle di produzione frontend con Vite e TypeScript (webapp/dist/)."""
    cmd = [_npm_cmd(), "run", "build"] + extra_args
    return _run_cmd(cmd)


def cmd_frontend_typecheck(extra_args: list[str]) -> int:
    """Esegue il controllo statico dei tipi TypeScript per il frontend (tsc --noEmit)."""
    cmd = [_npm_cmd(), "run", "typecheck"] + extra_args
    return _run_cmd(cmd)


def cmd_frontend_test(extra_args: list[str]) -> int:
    """Esegue i test unitari TypeScript della nuova foundation frontend."""
    cmd = [_npm_cmd(), "run", "test:frontend"] + extra_args
    return _run_cmd(cmd)


def cmd_check_api(extra_args: list[str]) -> int:
    """Verifica i requisiti per l'avvio del server FastAPI bot.py con tools.check_environment --mode api."""
    cmd = [sys.executable, "-m", "tools.check_environment", "--mode", "api"] + extra_args
    return _run_cmd(cmd)


def cmd_check(extra_args: list[str]) -> int:
    """Esegue la suite standard di validazione locale: ambiente, sintassi, lint, mypy, frontend, dataset e test."""
    steps = [
        ("Controllo ambiente", cmd_check_env, []),
        ("Controllo sintassi (compileall)", cmd_syntax, []),
        ("Lint (ruff)", cmd_lint, []),
        ("Type check (mypy)", cmd_typecheck, []),
        ("Type check frontend (tsc)", cmd_frontend_typecheck, []),
        ("Build frontend (vite)", cmd_frontend_build, []),
        ("Integrita' dataset", cmd_dataset_check, []),
        ("Regressione dataset", cmd_dataset_regression_check, []),
        ("Test client legacy (node)", cmd_test_node, []),
        ("Test frontend unitari", cmd_frontend_test, []),
        ("Unit test (pytest)", cmd_test, extra_args),
    ]
    for label, fn, args in steps:
        print(f"\n=== [CHECK] {label} ===")
        code = fn(args)
        if code != 0:
            print(f"\n[FAIL] Step '{label}' fallito con codice {code}. Interrompo.")
            return code
    print("\n[SUCCESS] Tutte le verifiche locali standard sono state superate con successo!")
    return 0


def cmd_api(extra_args: list[str]) -> int:
    """Avvia il server FastAPI/bot in modalita' reload su localhost:8000.

    bot.py esegue il lifespan FastAPI completo e richiede configurate le variabili:
    WEBHOOK_SECRET, TASK_SECRET, TASKS_QUEUE, BROADCAST_QUEUE e PUBLIC_BASE_URL (HTTPS).
    Se mancano, fornisce un avviso chiaro ed azionabile prima di lanciare uvicorn.
    """
    import re
    # Carica il file .env se non gia' presente in os.environ
    env_file = ROOT_DIR / ".env"
    if env_file.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file)
        except Exception:
            pass

    webhook_secret = os.environ.get("WEBHOOK_SECRET", "").strip()
    task_secret = os.environ.get("TASK_SECRET", "").strip()
    tasks_queue = os.environ.get("TASKS_QUEUE", "").strip()
    broadcast_queue = os.environ.get("BROADCAST_QUEUE", "").strip()
    public_base_url = (os.environ.get("PUBLIC_BASE_URL") or "").strip().rstrip("/")

    secret_pattern = r"^[A-Za-z0-9_-]{32,256}$"
    missing = []

    if not re.fullmatch(secret_pattern, webhook_secret):
        missing.append("WEBHOOK_SECRET (richiesto da bot.py lifespan: 32-256 caratteri URL-safe)")
    if not re.fullmatch(secret_pattern, task_secret):
        missing.append("TASK_SECRET (richiesto da task_queue: 32-256 caratteri URL-safe)")
    if not tasks_queue:
        missing.append("TASKS_QUEUE (richiesto da task_queue.validate_configuration())")
    if not broadcast_queue:
        missing.append("BROADCAST_QUEUE (richiesto da task_queue.validate_configuration())")
    if not public_base_url.startswith("https://"):
        missing.append("PUBLIC_BASE_URL (richiesto con schema https:// da task_queue.validate_configuration())")

    if missing:
        print("\n============================================================")
        print(" [ERRORE AVVIO API] Requisiti del runtime bot.py non soddisfatti")
        print("============================================================\n")
        print("Il server FastAPI 'bot.py' esegue controlli rigorosi al lifespan di avvio.")
        print("I seguenti requisiti non sono soddisfatti nell'ambiente corrente:\n")
        for item in missing:
            print(f"  * {item}")
        print("\nAzioni consigliate:")
        print("  1. Per diagnosticare l'ambiente del server:")
        print("     python -m tools.check_environment --mode api")
        print("  2. Per configurare valori di test conformi nel .env consulta:")
        print("     docs/local-development.md (Sezione 5.4)")
        print("  3. Se desideri unicamente testare la Mini App senza il server bot.py:")
        print("     make webapp   (oppure: python -m tools.dev webapp)\n")
        return 1

    port = os.environ.get("PORT", "8000")
    cmd = [sys.executable, "-m", "uvicorn", "bot:app", "--reload", "--port", port] + extra_args
    return _run_cmd(cmd)


def cmd_admin(extra_args: list[str]) -> int:
    """Avvia la dashboard amministrativa Streamlit locale."""
    cmd = [sys.executable, "-m", "streamlit", "run", "admin_ui.py"] + extra_args
    return _run_cmd(cmd)


def cmd_webapp(extra_args: list[str]) -> int:
    """Avvia l'anteprima locale della Mini App su http://localhost:8888/app."""
    cmd = [sys.executable, "scripts/preview_webapp.py"] + extra_args
    return _run_cmd(cmd)


def cmd_emulator(extra_args: list[str]) -> int:
    """Avvia l'emulatore Google Cloud Firestore sulla porta standard 8571."""
    host_port = os.environ.get("FIRESTORE_EMULATOR_HOST", "127.0.0.1:8571")
    cmd = ["gcloud", "emulators", "firestore", "start", f"--host-port={host_port}"] + extra_args
    return _run_cmd(cmd)


# ---------------------------------------------------------------------------
# Tabella comandi e CLI Dispatcher
# ---------------------------------------------------------------------------

COMMANDS: dict[str, tuple[Callable[[list[str]], int], str]] = {
    "check-env": (cmd_check_env, "Verifica l'ambiente locale (modalita' dev: isolato per test/webapp/emulator)"),
    "check-api": (cmd_check_api, "Verifica i requisiti per l'avvio del server FastAPI bot.py (lifespan e code)"),
    "test": (cmd_test, "Esegue i test unitari con pytest"),
    "test-cov": (cmd_test_cov, "Esegue i test con report di copertura del codice"),
    "test-node": (cmd_test_node, "Esegue i test client per la Mini App (richiede Node.js)"),
    "lint": (cmd_lint, "Controlla il codice con ruff"),
    "typecheck": (cmd_typecheck, "Verifica i tipi con mypy su services/"),
    "syntax": (cmd_syntax, "Verifica la sintassi Python di tutti i moduli"),
    "dataset-check": (cmd_dataset_check, "Controlla salute ed integrita' del dataset calciatori"),
    "check": (cmd_check, "Suite standard di validazione locale (ambiente, syntax, lint, mypy, frontend, dataset, test)"),
    "api": (cmd_api, "Avvia il server API / bot con uvicorn (--reload)"),
    "admin": (cmd_admin, "Avvia la dashboard admin con Streamlit (admin_ui.py)"),
    "webapp": (cmd_webapp, "Avvia l'anteprima isolata della Mini App (preview_webapp.py)"),
    "emulator": (cmd_emulator, "Avvia l'emulatore locale Firestore con gcloud"),
    "frontend-dev": (cmd_frontend_dev, "Avvia il server di sviluppo Vite per la Mini App (localhost:5173)"),
    "frontend-build": (cmd_frontend_build, "Compila il bundle di produzione frontend con Vite e TypeScript"),
    "frontend-typecheck": (cmd_frontend_typecheck, "Verifica i tipi TypeScript per il frontend (tsc --noEmit)"),
    "frontend-test": (cmd_frontend_test, "Esegue i test unitari TypeScript della nuova foundation"),
    "dataset-regression-check": (cmd_dataset_regression_check, "Verifica regressioni del dataset rispetto alla baseline"),
    "dataset-baseline-update": (cmd_dataset_baseline_update, "Aggiorna data/dataset_baseline.json con le metriche attuali"),
    "security-check": (cmd_security_check, "Esegue audit di sicurezza (pip-audit, detect-secrets, npm-audit)"),
}


def print_help() -> None:
    print("\n============================================================")
    print(" Guess the Player - Comandi di sviluppo locale")
    print("============================================================\n")
    print("Uso: python -m tools.dev <comando> [argomenti...]\n")
    print("Comandi disponibili:")
    max_len = max(len(name) for name in COMMANDS)
    for name, (_, desc) in COMMANDS.items():
        print(f"  {name.ljust(max_len + 2)} : {desc}")
    print("\nEsempi:")
    print("  python -m tools.dev check-env")
    print("  python -m tools.dev check-api")
    print("  python -m tools.dev test")
    print("  python -m tools.dev check")
    print("  python -m tools.dev security-check")
    print("  python -m tools.dev dataset-regression-check")
    print("  python -m tools.dev admin")
    print("  python -m tools.dev webapp")
    print("  python -m tools.dev frontend-dev\n")


def main(argv: Optional[list[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help", "help"):
        print_help()
        return 0

    cmd_name = args[0].lower()
    extra_args = args[1:]

    # Supporto per alias comuni
    aliases = {
        "check_env": "check-env",
        "env": "check-env",
        "check_api": "check-api",
        "api-check": "check-api",
        "api_check": "check-api",
        "tests": "test",
        "coverage": "test-cov",
        "type-check": "typecheck",
        "check-dataset": "dataset-check",
        "check_dataset": "dataset-check",
        "check-all": "check",
        "all": "check",
        "dev-api": "api",
        "dev-admin": "admin",
        "dev-webapp": "webapp",
        "dev-emulator": "emulator",
        "dev-frontend": "frontend-dev",
        "vite": "frontend-dev",
        "build-frontend": "frontend-build",
        "typecheck-frontend": "frontend-typecheck",
        "ts-check": "frontend-typecheck",
        "test-frontend": "frontend-test",
        "security": "security-check",
        "sec": "security-check",
        "security_check": "security-check",
        "dataset-regression": "dataset-regression-check",
        "dataset_regression": "dataset-regression-check",
        "regression-check": "dataset-regression-check",
        "update-baseline": "dataset-baseline-update",
        "baseline-update": "dataset-baseline-update",
        "update_baseline": "dataset-baseline-update",
    }
    target_cmd = aliases.get(cmd_name, cmd_name)

    if target_cmd not in COMMANDS:
        print(f"Errore: comando sconosciuto '{cmd_name}'.")
        print(f"Comandi validi: {', '.join(sorted(COMMANDS.keys()))}")
        print("Usa 'python -m tools.dev --help' per l'elenco completo.")
        return 1

    fn, _ = COMMANDS[target_cmd]
    return fn(extra_args)


if __name__ == "__main__":
    sys.exit(main())
