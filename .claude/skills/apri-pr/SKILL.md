---
name: apri-pr
description: Chiude il lavoro su una issue di guess_the_player_from_the_path - riallinea il branch a origin/main, esegue i controlli, pusha, apre la PR con il template (Closes o Refs), sposta la issue in Review e collega la PR all'app. Usala quando l'utente dice "apri la PR", "manda in review", "pusha e apri la pull request".
argument-hint: "[numero issue]"
---

# Apri la PR

Lavora dal worktree della issue. Il numero si ricava dal branch (`<tipo>/<n>-slug`) se non è passato in
`$ARGUMENTS`. Riferimenti: `docs/agent-protocol.md` (passi 9–17 e checklist finale), `docs/github-workflow.md`.

## 1. Riallinea a main

```bash
git fetch origin --prune
git log --oneline HEAD..origin/main
```

Se `main` è andato avanti, unisci `origin/main` nel branch. Nei conflitti tieni **entrambi** i comportamenti,
mai scartare il lavoro altrui; poi rifai i controlli delle due aree.

## 2. Controlli

```bash
git diff --check origin/main...HEAD
python -m tools.dev check
```

- Senza `.env` nel worktree il controllo d'ambiente chiede `BOT_TOKEN` e una configurazione Firestore.
  Se l'emulatore non è avviato (`python -m tools.dev emulator`), lancia `check` con
  `BOT_TOKEN=123:placeholder FIRESTORE_EMULATOR_HOST=127.0.0.1:8571`: tutti i passi girano, ma i test
  dell'emulatore falliscono con *connection refused*. In quel caso, e solo per quegli errori, ripeti pytest
  senza la variabile (`BOT_TOKEN=123:placeholder python -m pytest -q`), così si saltano; in CI girano comunque.
  Nella PR scrivi che i test dell'emulatore non sono stati eseguiti in locale.
- Dipendenze o codice di sicurezza toccati → anche `python -m tools.dev security-check`.
- Se un controllo fallisce, sistemalo o riferiscilo con l'output: non aprire la PR come se fosse verde.

Rivedi il diff completo (`git diff origin/main...HEAD --stat` e poi il contenuto): solo file della issue,
nessun file estraneo (`.claude/launch.json`, file di anteprima, `review-evidence/` non richiesti).

## 3. Closes o Refs

Rileggi i criteri di completamento della issue (`gh issue view <n>`). `Closes #<n>` solo se sono **tutti**
soddisfatti; altrimenti `Refs #<n>` ed elenca nel corpo cosa resta.

## 4. Push e PR

```bash
git push -u origin HEAD
gh pr create --title "<tipo>(<area>): <descrizione in italiano> (Closes #<n>)" --body-file <file>
```

Corpo nello stile delle PR recenti, seguendo `.github/PULL_REQUEST_TEMPLATE.md`: **Perché**, **Cosa fa**,
**Verifica** (comandi realmente eseguiti e risultato, verifiche manuali in anteprima), poi `Closes #<n>` o
`Refs #<n>`, e in fondo la riga di attribuzione indicata dal sistema. Scrivi il corpo in un file nello
scratchpad e passalo con `--body-file`.

## 5. Project → Review

```bash
gh project item-edit --project-id PVT_kwHOBIej284BjJ2T --id <item-id> \
  --field-id PVTSSF_lAHOBIej284BjJ2Tzhh_Q_A --single-select-option-id ef88144a
```

(`<item-id>` si ottiene come nella skill `inizia-issue`.)

## 6. Dopo

- Collega la PR all'app con gli strumenti `ccd_pr` (`get_status`, poi `bind_pr` se serve) e lascia che sia
  l'app a seguire la CI: non fare polling.
- **Non fare merge**: serve l'approvazione esplicita dell'utente.
- Riporta all'utente: link alla PR, Closes/Refs, controlli eseguiti con esito, eventuali punti aperti.
