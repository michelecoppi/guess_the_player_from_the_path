---
name: pulisci-worktree
description: Rimuove in sicurezza i worktree di guess_the_player_from_the_path la cui PR è già mergiata, senza modifiche locali né commit non pushati, cancella i relativi branch locali e toglie da .claude/launch.json le voci che puntano a worktree spariti. Usala quando l'utente chiede di pulire worktree, branch vecchi o la configurazione delle anteprime.
---

# Pulisci i worktree

Dal checkout principale. Si rimuove **solo** ciò che è sicuramente recuperabile da GitHub.

## 1. Stato aggiornato

```bash
git fetch -q --prune origin
gh pr list --state all --limit 400 --json headRefName,state > "$TEMP/prs.json"
```

## 2. Rimozione

Un worktree si rimuove solo se valgono **tutte**:
- è sotto questo repository (`.worktrees/` o `.claude/worktrees/`). Quelli in `C:\Users\Coppi\.codex\worktrees\`
  sono di Codex, un altro agente: non toccarli mai;
- l'unica PR del suo branch è `MERGED`;
- `git status --porcelain` è vuoto;
- l'upstream è `origin/<stesso branch>` e non ci sono commit locali in più (`git rev-list --count @{u}..HEAD` = 0).

Per quelli che passano: `git worktree remove <percorso>` (mai `--force`), poi `git branch -D <branch>` (il
branch resta su `origin`). Alla fine `git worktree prune`.

Script usato finora (adatta i percorsi se servono):

```bash
git worktree list --porcelain | awk '/^worktree/{w=$2} /^branch/{print w"\t"$2}' > "$TEMP/wt.tsv"
python - <<'EOF'
import json, os, subprocess
root = os.getcwd().replace("\\", "/")
prs = {}
for p in json.load(open(os.environ["TEMP"] + "/prs.json")):
    prs.setdefault(p["headRefName"], []).append(p["state"])
for line in open(os.environ["TEMP"] + "/wt.tsv"):
    w, b = line.rstrip("\n").split("\t"); b = b.replace("refs/heads/", "")
    if w == root or not w.startswith(root + "/"):
        continue
    git = lambda *a: subprocess.run(["git", "-C", w, *a], capture_output=True, text=True)
    dirty = git("status", "--porcelain").stdout.strip()
    up = git("rev-parse", "--abbrev-ref", "@{u}").stdout.strip()
    ahead = git("rev-list", "--count", up + "..HEAD").stdout.strip() if up == f"origin/{b}" else "x"
    if prs.get(b) == ["MERGED"] and not dirty and ahead == "0":
        r = subprocess.run(["git", "worktree", "remove", w], capture_output=True, text=True)
        if r.returncode == 0:
            subprocess.run(["git", "branch", "-D", b], capture_output=True)
            print("RIMOSSO", w); continue
        print("ERRORE", w, r.stderr.strip()); continue
    print("TENUTO", w, b, f"pr={prs.get(b)} modifiche={len(dirty.splitlines())} upstream={up or '-'} avanti={ahead}")
EOF
git worktree prune -v
```

### Cartelle rimaste

`git worktree remove` lascia la cartella se dentro c'è `node_modules` come **junction** verso quello della
root (o di un altro worktree). Toglila così, da PowerShell:

```powershell
cmd /c rmdir "<cartella>\node_modules"   # elimina solo il collegamento
cmd /c rmdir "<cartella>"
```

**Mai** `rm -rf` o `Remove-Item -Recurse` su una cartella che contiene un junction: seguono il collegamento e
cancellano il `node_modules` vero. Verifica prima con `(Get-Item "<cartella>\node_modules" -Force).LinkType`.
Cartelle con altri file (screenshot di review, appunti) non si toccano: segnalale.

## 3. launch.json

Togli da `.claude/launch.json` solo le voci il cui `runtimeArgs` punta a un file che non esiste più. Lascia
le altre voci e le altre modifiche locali del file.

## 4. Resoconto

Di' quanti worktree hai rimosso ed elenca quelli tenuti con il motivo (modifiche locali, commit non pushati,
nessuna PR, PR non mergiata). Per quelli tenuti non decidere tu: proponi all'utente cosa fare caso per caso.
