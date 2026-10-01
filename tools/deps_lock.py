"""Lock delle dipendenze Python: lo stesso grafo in CI e nell'immagine di produzione (#214).

Le dipendenze dirette stanno in ``requirements.in`` (runtime) e ``requirements-dev.in``
(sviluppo). ``pip-compile`` ne ricava ``requirements.txt`` e ``requirements-dev.txt`` con
**tutte** le versioni, transitive comprese: il Dockerfile installa il primo, la CI il secondo.

Si risolve prima il grafo di sviluppo, che contiene anche il runtime, e poi il runtime vincolato
a quello (``--constraint requirements-dev.txt``). L'ordine conta: risolto da solo, il runtime
prendeva versioni che gli strumenti di sviluppo escludono (``websockets`` 17 contro
``streamlit``, che chiede ``<17``), e la produzione girava con versioni mai provate in CI.

Il grafo si risolve sempre per la piattaforma di produzione, Linux con Python 3.11: una
risoluzione su Windows tralascerebbe le dipendenze solo-Linux (``uvloop`` di
``uvicorn[standard]``) e ne aggiungerebbe di solo-Windows (``colorama``). Se l'interprete
corrente non e' quello, ``pip-compile`` gira in un container ``python:3.11-slim``.

    python -m tools.deps_lock lock      # rigenera i lock dopo aver cambiato un .in
    python -m tools.deps_lock check     # i lock corrispondono ai .in? (CI)

``check`` ricompila una copia dei file: ``pip-compile`` tiene le versioni gia' presenti nel
lock, quindi un lock aggiornato si ricompila identico e un ``.in`` cambiato senza rigenerare
il lock produce una differenza. Si confrontano solo le righe ``nome==versione``: commenti e
intestazione non contano.
"""
from __future__ import annotations

import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]

# (sorgente, lock, argomenti in piu') nell'ordine di compilazione: il runtime e' un sottoinsieme
# esatto del grafo di sviluppo.
LOCKS = (
    ("requirements-dev.in", "requirements-dev.txt", ()),
    ("requirements.in", "requirements.txt", ("--constraint", "requirements-dev.txt")),
)
PIP_COMPILE_ARGS = ("--quiet", "--allow-unsafe", "--strip-extras", "--no-emit-index-url")
DOCKER_IMAGE = "python:3.11-slim"
TARGET_PYTHON = (3, 11)

_PIN_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==(\S+)")


def pip_tools_version(root: Path = ROOT_DIR) -> str:
    """La versione di pip-tools fissata in requirements-dev.in: la stessa in locale, Docker e CI."""
    text = (root / "requirements-dev.in").read_text(encoding="utf-8")
    match = re.search(r"^pip-tools==(\S+)", text, re.MULTILINE)
    if not match:
        raise SystemExit("pip-tools non e' fissato in requirements-dev.in")
    return match.group(1)


def read_pins(path: Path) -> dict[str, str]:
    """Le righe ``nome==versione`` di un lock, con il nome normalizzato come fa pip."""
    pins: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _PIN_RE.match(line.strip())
        if match:
            pins[re.sub(r"[-_.]+", "-", match.group(1)).lower()] = match.group(2)
    return pins


def diff_pins(expected: dict[str, str], actual: dict[str, str]) -> list[str]:
    """Le differenze tra due insiemi di pin, una riga per pacchetto, in ordine alfabetico."""
    lines = []
    for name in sorted(expected.keys() | actual.keys()):
        old, new = actual.get(name), expected.get(name)
        if old != new:
            lines.append(f"{name}: lock={old or '-'} atteso={new or '-'}")
    return lines


def is_target_platform() -> bool:
    return sys.platform.startswith("linux") and sys.version_info[:2] == TARGET_PYTHON


def _compile_args() -> list[list[str]]:
    """Gli argomenti di pip-compile per ogni lock, nell'ordine di LOCKS."""
    return [[*PIP_COMPILE_ARGS, *extra, "--output-file", lock, source] for source, lock, extra in LOCKS]


def compile_locks(workdir: Path) -> int:
    """Esegue pip-compile in ``workdir`` (che contiene i .in e gli eventuali lock da preservare)."""
    version = pip_tools_version(workdir)
    if is_target_platform():
        installed = subprocess.run(
            [sys.executable, "-m", "piptools", "--version"], capture_output=True, text=True
        )
        if version not in installed.stdout:
            print(f"Installo pip-tools=={version}")
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", f"pip-tools=={version}"], check=True)
        for args in _compile_args():
            code = subprocess.run([sys.executable, "-m", "piptools", "compile", *args], cwd=workdir).returncode
            if code:
                return code
        return 0

    if not shutil.which("docker"):
        print(
            f"Serve Linux con Python {TARGET_PYTHON[0]}.{TARGET_PYTHON[1]} oppure Docker: "
            f"qui c'e' {platform.system()} con Python {platform.python_version()}."
        )
        return 2
    script = " && ".join(
        [f"pip install -q --root-user-action=ignore pip-tools=={version}"]
        + ["pip-compile " + " ".join(args) for args in _compile_args()]
    )
    print(f">> pip-compile in {DOCKER_IMAGE} (pip-tools {version})")
    return subprocess.run(
        ["docker", "run", "--rm", "-v", f"{workdir.resolve()}:/src", "-w", "/src", DOCKER_IMAGE, "sh", "-c", script]
    ).returncode


def lock(root: Path = ROOT_DIR) -> int:
    code = compile_locks(root)
    if code == 0:
        print("Lock aggiornati: " + ", ".join(name for _, name, _ in LOCKS))
    return code


def check(root: Path = ROOT_DIR) -> int:
    missing = [name for source, lock, _ in LOCKS for name in (source, lock) if not (root / name).is_file()]
    if missing:
        print("File mancanti: " + ", ".join(missing))
        return 1
    with tempfile.TemporaryDirectory(dir=root) as tmp:
        workdir = Path(tmp)
        for source, lock_name, _ in LOCKS:
            for name in (source, lock_name):
                shutil.copy2(root / name, workdir / name)
        code = compile_locks(workdir)
        if code:
            print(
                "pip-compile non riesce a risolvere i file .in (vedi sopra): un pin diretto e' in "
                "conflitto con un'altra dipendenza. Correggi il .in e rigenera con "
                "`python -m tools.dev deps-lock`."
            )
            return code
        problems = []
        for _, name, _ in LOCKS:
            diff = diff_pins(read_pins(workdir / name), read_pins(root / name))
            problems += [f"  {name} -> {line}" for line in diff]
    if problems:
        print("I lock non corrispondono ai file .in. Rigenerali con `python -m tools.dev deps-lock`:")
        print("\n".join(problems))
        return 1
    print("Lock allineati ai file .in.")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args == ["lock"]:
        return lock()
    if args == ["check"]:
        return check()
    print("Uso: python -m tools.deps_lock {lock|check}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
