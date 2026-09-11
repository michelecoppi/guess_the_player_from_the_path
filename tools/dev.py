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


def cmd_check(extra_args: list[str]) -> int:
    """Esegue l'intera suite di verifiche locali: sintassi, lint, mypy, dataset, test node e pytest."""
    steps = [
        ("Controllo ambiente", cmd_check_env, []),
        ("Controllo sintassi (compileall)", cmd_syntax, []),
        ("Lint (ruff)", cmd_lint, []),
        ("Type check (mypy)", cmd_typecheck, []),
        ("Integrita' dataset", cmd_dataset_check, []),
        ("Test client (node)", cmd_test_node, []),
        ("Unit test (pytest)", cmd_test, extra_args),
    ]
    for label, fn, args in steps:
        print(f"\n=== [CHECK] {label} ===")
        code = fn(args)
        if code != 0:
            print(f"\n[FAIL] Step '{label}' fallito con codice {code}. Interrompo.")
            return code
    print("\n[SUCCESS] Tutte le verifiche locali sono state superate con successo!")
    return 0


def cmd_api(extra_args: list[str]) -> int:
    """Avvia il server FastAPI/bot in modalita' reload su localhost:8000."""
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
    "check-env": (cmd_check_env, "Verifica l'ambiente locale e configurazione (.env, dataset, python)"),
    "test": (cmd_test, "Esegue i test unitari con pytest"),
    "test-cov": (cmd_test_cov, "Esegue i test con report di copertura del codice"),
    "test-node": (cmd_test_node, "Esegue i test client per la Mini App (richiede Node.js)"),
    "lint": (cmd_lint, "Controlla il codice con ruff"),
    "typecheck": (cmd_typecheck, "Verifica i tipi con mypy su services/"),
    "syntax": (cmd_syntax, "Verifica la sintassi Python di tutti i moduli"),
    "dataset-check": (cmd_dataset_check, "Controlla salute ed integrita' del dataset calciatori"),
    "check": (cmd_check, "Esegue tutte le verifiche di qualita' (syntax, lint, mypy, dataset, test)"),
    "api": (cmd_api, "Avvia il server API / bot con uvicorn (--reload)"),
    "admin": (cmd_admin, "Avvia la dashboard admin con Streamlit (admin_ui.py)"),
    "webapp": (cmd_webapp, "Avvia l'anteprima isolata della Mini App (preview_webapp.py)"),
    "emulator": (cmd_emulator, "Avvia l'emulatore locale Firestore con gcloud"),
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
    print("  python -m tools.dev test")
    print("  python -m tools.dev check")
    print("  python -m tools.dev admin")
    print("  python -m tools.dev webapp\n")


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
