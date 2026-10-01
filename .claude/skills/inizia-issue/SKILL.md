---
name: inizia-issue
description: Avvia il lavoro su una issue di guess_the_player_from_the_path - legge issue e campi del Project #2, controlla WIP e blocchi, crea worktree e branch da origin/main aggiornato e sposta la issue in In Progress. Usala quando l'utente dice "inizia/lavora sulla issue N", "prendi la #N" o simili.
argument-hint: <numero issue>
---

# Inizia una issue

Argomento: il numero della issue (`$ARGUMENTS`). Se manca, chiedilo.
Regole di riferimento: `AGENTS.md`, `docs/agent-protocol.md` (sequenza di lavoro), `docs/github-workflow.md`
(nomi dei branch). Questa skill aggiunge solo i comandi; in caso di dubbio vincono quei documenti.

## 1. Stato aggiornato

```bash
git fetch origin --prune
gh issue view <n> --json number,title,state,body,labels,comments,url
```

Campi del Project #2 e dipendenze della issue:

```bash
gh api graphql -f query='query{repository(owner:"michelecoppi",name:"guess_the_player_from_the_path"){issue(number:<n>){state blockedBy(first:20){nodes{number state}} parent{number} subIssues(first:20){nodes{number state}} projectItems(first:5){nodes{id project{number} fieldValues(first:20){nodes{... on ProjectV2ItemFieldSingleSelectValue{name field{... on ProjectV2SingleSelectField{name}}}}}}}}}}'
```

## 2. Si può iniziare?

Fermati e riferisci all'utente (senza creare nulla) se:
- la issue è chiusa, oppure lo Status non è `Ready` e l'utente non ha chiesto esplicitamente di iniziarla lo stesso;
- ha un `blockedBy` ancora aperto (va in `Blocked`, non si aggira);
- ha l'etichetta `needs-decision` senza una decisione registrata nei commenti;
- è Size 8: proponi lo split invece di implementare;
- ci sono già due evolutive `In Progress` e la issue non registra un motivo per superare il limite. Conteggio:
  ```bash
  gh project item-list 2 --owner michelecoppi --format json --limit 300 --jq '[.items[] | select(.status=="In Progress")] | map("\(.content.number) \(.content.title)")'
  ```

Controlla anche che nessuna PR aperta tocchi già la stessa issue: `gh pr list --search "<n>" --state open`.

## 3. Worktree e branch

Nome del branch: `<tipo>/<n>-<slug-breve>` con tipo `feat|fix|refactor|chore|data|perf|infra`, scelto dal
contenuto della issue. Il worktree va in `.worktrees/issue-<n>` (ignorato da git):

```bash
git worktree add .worktrees/issue-<n> -b <tipo>/<n>-<slug> origin/main
```

Se il branch esiste già (lavoro precedente), non ricrearlo: verifica con `git log` e con l'eventuale PR se è
ancora valido e chiedi all'utente come procedere.

Per i comandi frontend nel worktree serve `node_modules`: crea un junction verso quello della root invece di
reinstallare:

```bash
cmd //c "mklink /J .worktrees\\issue-<n>\\node_modules node_modules"
```

Da qui in poi lavora **solo** dentro il worktree (usa `EnterWorktree` se disponibile).

## 4. Project → In Progress

```bash
gh project item-edit --project-id PVT_kwHOBIej284BjJ2T --id <item-id> \
  --field-id PVTSSF_lAHOBIej284BjJ2Tzhh_Q_A --single-select-option-id 47fc9ee4
```

`<item-id>` è il `projectItems.nodes[].id` del passo 1 con `project.number == 2`. Se la issue non è nel
Project, dillo all'utente invece di aggiungerla di tua iniziativa.

## 5. Prima di scrivere codice

Leggi il documento primario dell'area (indice in `docs/README.md`) e il codice coinvolto, poi riassumi
all'utente in poche righe: cosa chiede la issue, i file che pensi di toccare, i criteri di completamento.
